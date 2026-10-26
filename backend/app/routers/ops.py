"""Data Flow Observatory, Emergency Stop, Red Team Lab, explainer chat and request drafts."""
from typing import Literal

from fastapi import APIRouter, Depends, Query
from pydantic import Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import audit_log, chat, drafts
from app.auth.deps import UserContext, current_user, require_step_up
from app.dataflow import service as dataflow
from app.db import get_db
from app.engine import constitution
from app.errors import not_found
from app.guardian.service import owned_policy
from app.incidents import service as incidents
from app.models import ConsentRule, DataAsset, FlowEvent, Incident, PolicySnapshot, RedTeamRun, WatchEvent
from app.redteam import lab
from app.schemas.api import Strict
from app.vocab import DataCategory, ProtectedAction, Purpose
from app import clock

router = APIRouter(tags=["operations"])


# --- data flow ----------------------------------------------------------------


class AssetIn(Strict):
    label: str = Field(min_length=1, max_length=200)
    categories: list[DataCategory] = Field(default_factory=list, max_length=20)
    source: str = Field(default="", max_length=200)
    derived_from: list[str] = Field(default_factory=list, max_length=20)
    transformation: str = Field(default="", max_length=200)


class FlowCheckIn(Strict):
    asset_id: str = Field(max_length=32)
    action: ProtectedAction
    destination: str = Field(max_length=253)
    purpose: Purpose
    declared_categories: list[DataCategory] = Field(default_factory=list, max_length=20)


@router.post("/data-flow/assets", status_code=201)
def create_asset(body: AssetIn, ctx: UserContext = Depends(current_user), db: Session = Depends(get_db)):
    a = dataflow.create_asset(db, ctx.user.id, label=body.label, categories=list(body.categories), source=body.source,
                              derived_from=body.derived_from, transformation=body.transformation)
    audit_log.record(db, "dataflow.asset.created", user_id=ctx.user.id, actor_type="user", actor_id=ctx.user.id,
                     target_type="asset", target_id=a.id, details={"label": a.label, "derived_from": a.derived_from})
    db.commit()
    return dataflow.asset_out(db, a)


@router.get("/data-flow/assets")
def list_assets(ctx: UserContext = Depends(current_user), db: Session = Depends(get_db)):
    rows = db.execute(select(DataAsset).where(DataAsset.user_id == ctx.user.id).order_by(DataAsset.created_at)).scalars()
    return [dataflow.asset_out(db, a) for a in rows]


@router.get("/data-flow/lineage/{asset_id}")
def lineage(asset_id: str, ctx: UserContext = Depends(current_user), db: Session = Depends(get_db)):
    return dataflow.lineage(db, ctx.user.id, asset_id)


@router.post("/data-flow/evaluate")
def evaluate_flow(body: FlowCheckIn, ctx: UserContext = Depends(current_user), db: Session = Depends(get_db)):
    """Dry run: would this asset be allowed to go there, given everything it was derived from?"""
    from app.engine.hosts import normalize_host

    dest = normalize_host(body.destination) or body.destination
    effective = dataflow.effective_categories(db, ctx.user.id, body.asset_id)
    undeclared = sorted(effective - set(body.declared_categories))
    rules = db.execute(select(ConsentRule).where(ConsentRule.user_id == ctx.user.id, ConsentRule.active.is_(True))).scalars().all()
    res = constitution.evaluate(rules, constitution.ActionRequest(body.action, dest, body.purpose, tuple(sorted(effective))), clock.utcnow())
    return {"effective_categories": sorted(effective), "undeclared_categories": undeclared,
            "decision": "BLOCK" if undeclared else res.decision, "reasons": (
                [f"derived from data carrying {', '.join(undeclared)} that is not declared"] if undeclared else res.reasons),
            "outcomes": [o.__dict__ for o in res.outcomes]}


@router.get("/data-flow/events")
def flow_events(outcome: str | None = Query(None, max_length=40), limit: int = Query(100, ge=1, le=500),
                ctx: UserContext = Depends(current_user), db: Session = Depends(get_db)):
    q = select(FlowEvent).where(FlowEvent.user_id == ctx.user.id)
    if outcome:
        q = q.where(FlowEvent.outcome == outcome)
    return [dataflow.flow_out(f) for f in db.execute(q.order_by(FlowEvent.created_at.desc()).limit(limit)).scalars()]


@router.get("/data-flow/violations")
def violations(ctx: UserContext = Depends(current_user), db: Session = Depends(get_db)):
    q = select(FlowEvent).where(FlowEvent.user_id == ctx.user.id, FlowEvent.decision == "BLOCK").order_by(FlowEvent.created_at.desc()).limit(200)
    return [dataflow.flow_out(f) for f in db.execute(q).scalars()]


@router.get("/data-flow/coverage")
def coverage():
    return dataflow.COVERAGE


# --- emergency stop -----------------------------------------------------------


class StopIn(Strict):
    reason: str = Field(min_length=3, max_length=500)
    revoke_tokens: bool = True
    revoke_agents: bool = False
    revoke_other_sessions: bool = True
    pause_monitoring: bool = True


class RecoverIn(Strict):
    incident_id: str = Field(max_length=32)
    confirmation: str = Field(max_length=20)
    findings: str = Field(min_length=1, max_length=2000)


class NoteIn(Strict):
    note: str = Field(min_length=1, max_length=2000)


@router.post("/emergency-stop/activate", status_code=201)
def activate(body: StopIn, ctx: UserContext = Depends(current_user), db: Session = Depends(get_db)):
    """Tightening only, so no step-up: anyone signed in as the user can stop everything immediately."""
    inc = incidents.activate(db, ctx.user, ctx.session.id, reason=body.reason, revoke_tokens=body.revoke_tokens,
                             revoke_agents=body.revoke_agents, revoke_other_sessions=body.revoke_other_sessions,
                             pause_monitoring=body.pause_monitoring)
    db.commit()
    return incidents.incident_out(inc)


@router.post("/emergency-stop/recover")
def recover(body: RecoverIn, ctx: UserContext = Depends(current_user), db: Session = Depends(get_db)):
    incidents.owned_incident(db, ctx.user.id, body.incident_id)
    require_step_up(ctx)
    inc = incidents.recover(db, ctx.user, body.incident_id, confirmation=body.confirmation, findings=body.findings)
    db.commit()
    return incidents.incident_out(inc)


@router.get("/emergency-stop/status")
def stop_status(ctx: UserContext = Depends(current_user), db: Session = Depends(get_db)):
    inc = db.get(Incident, ctx.user.active_incident_id) if ctx.user.active_incident_id else None
    return {"frozen": ctx.user.frozen, "active_incident": incidents.incident_out(inc) if inc else None}


@router.get("/incidents")
def list_incidents(ctx: UserContext = Depends(current_user), db: Session = Depends(get_db)):
    rows = db.execute(select(Incident).where(Incident.user_id == ctx.user.id).order_by(Incident.created_at.desc())).scalars()
    return [incidents.incident_out(i) for i in rows]


@router.post("/incidents/{incident_id}/notes")
def incident_note(incident_id: str, body: NoteIn, ctx: UserContext = Depends(current_user), db: Session = Depends(get_db)):
    inc = incidents.add_note(db, ctx.user, incident_id, body.note)
    db.commit()
    return incidents.incident_out(inc)


# --- red team lab -------------------------------------------------------------


class RunIn(Strict):
    seed: int = Field(default=7, ge=0, le=1_000_000)
    scenario_ids: list[str] = Field(default_factory=list, max_length=100)


@router.post("/red-team/runs", status_code=201)
def start_run(body: RunIn, ctx: UserContext = Depends(current_user), db: Session = Depends(get_db)):
    out = lab.run(seed=body.seed, only=body.scenario_ids or None)
    run = RedTeamRun(user_id=ctx.user.id, seed=body.seed, summary=out["summary"], results=out["results"])
    db.add(run)
    db.flush()
    audit_log.record(db, "redteam.run", user_id=ctx.user.id, actor_type="user", actor_id=ctx.user.id, target_type="red_team_run",
                     target_id=run.id, details={k: out["summary"][k] for k in ("total", "passed", "failed", "abstained")})
    db.commit()
    return {"id": run.id, "seed": run.seed, "created_at": run.created_at, "summary": run.summary, "results": run.results}


@router.get("/red-team/runs")
def list_runs(ctx: UserContext = Depends(current_user), db: Session = Depends(get_db)):
    rows = db.execute(select(RedTeamRun).where(RedTeamRun.user_id == ctx.user.id).order_by(RedTeamRun.created_at.desc()).limit(20)).scalars()
    return [{"id": r.id, "seed": r.seed, "created_at": r.created_at, "summary": r.summary} for r in rows]


@router.get("/red-team/runs/{run_id}")
def get_run(run_id: str, ctx: UserContext = Depends(current_user), db: Session = Depends(get_db)):
    r = db.get(RedTeamRun, run_id)
    if r is None or r.user_id != ctx.user.id:
        raise not_found("run")
    return {"id": r.id, "seed": r.seed, "created_at": r.created_at, "summary": r.summary, "results": r.results}


@router.get("/red-team/scenarios")
def scenarios():
    return [{"id": s[0], "category": s[1], "description": s[2], "expected": s[3]} for s in lab.SCENARIOS]


# --- chat and drafts ----------------------------------------------------------


class ChatIn(Strict):
    message: str = Field(min_length=1, max_length=1000)


@router.post("/chat/explain")
def explain(body: ChatIn, ctx: UserContext = Depends(current_user), db: Session = Depends(get_db)):
    return chat.explain(db, ctx.user, body.message)


class DraftIn(Strict):
    policy_source_id: str = Field(max_length=32)
    request_type: Literal["access", "deletion", "withdraw_consent", "objection"]
    watch_event_id: str | None = Field(default=None, max_length=32)
    sender_name: str = Field(default="", max_length=120)
    account_email: str = Field(default="", max_length=320)


@router.post("/provider-requests/draft")
def draft_request(body: DraftIn, ctx: UserContext = Depends(current_user), db: Session = Depends(get_db)):
    """Returns text only. There is deliberately no endpoint that sends it."""
    policy = owned_policy(db, ctx.user.id, body.policy_source_id)
    ev = None
    if body.watch_event_id:
        ev = db.get(WatchEvent, body.watch_event_id)
        if ev is None or ev.user_id != ctx.user.id or ev.source_id != policy.id:
            raise not_found("watch event")
    out = drafts.draft(policy, db.get(PolicySnapshot, policy.current_snapshot_id), body.request_type, event=ev,
                       sender_name=body.sender_name, account_email=body.account_email or ctx.user.email)
    audit_log.record(db, "provider_request.drafted", user_id=ctx.user.id, actor_type="user", actor_id=ctx.user.id,
                     target_type="policy", target_id=policy.id, details={"request_type": body.request_type, "sent": False})
    db.commit()
    return out
