"""Demo support: fixtures, the 'Trap' simulation, one-click seeding and the dashboard summary.

The Trap simulation never clicks anything real. It shows what a naive agent would do with a page (obey every
instruction it reads, including hidden ones) next to what a Kavach-guarded agent does.
"""
from datetime import timedelta

from fastapi import APIRouter, Depends
from pydantic import Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import audit_log, clock
from app.auth.crypto import make_compound_secret
from app.auth.deps import UserContext, current_user, require_step_up
from app.court import lexicon as lx
from app.court.pipeline import run_trial
from app.court.text import extract
from app.dataflow import service as dataflow
from app.db import get_db
from app.errors import APIError
from app.models import (AgentClient, AnalysisRun, ApprovalRequest, AuditEvent, ConsentRule, ConsentToken, FlowEvent,
                        PolicySource, RedTeamRun)
from app.models._common import new_id
from app.demo import fixtures as fx
from app.schemas.api import Strict
from app.watchman import service as watchman

router = APIRouter(tags=["demo"])


@router.get("/demo/fixtures")
def fixtures():
    return {
        "policies": [fx.FLASHLIGHT, fx.MAPSCO],
        "betrayal_text": fx.MAPSCO_BETRAYAL,
        "reformatted_text": fx.MAPSCO_REFORMATTED,
        "trap_page": fx.TRAP_PAGE,
        "benign_page": fx.BENIGN_PAGE,
        "synthetic_note": "All companies and pages are fictional.",
    }


class TrapIn(Strict):
    html: str = Field(min_length=1, max_length=200_000)
    guarded: bool


@router.post("/demo/trap")
def trap(body: TrapIn, ctx: UserContext = Depends(current_user), db: Session = Depends(get_db)):
    ex = extract(body.html)
    every_text = [ex.canonical] + [h.text for h in ex.hidden]
    hits = [h for t in every_text for h in lx.injection_hits(t)]
    segments = []
    for s in ex.segments:
        segments.append({"text": s.text, "hidden": s.hidden, "reason": s.reason, "suspicious": bool(lx.injection_hits(s.text))})
    if not body.guarded:
        steps = ["Opened the signup page.", "Read all of the page's text, including text people cannot see."]
        if hits:
            steps += [f"Found an instruction: “{hits[0]}”.", "Followed it: clicked “Accept All” and ticked every data-sharing box."]
            outcome = "ACCEPTED_ALL"
        else:
            steps += ["Found no instructions; clicked the main button."]
            outcome = "CLICKED_PRIMARY"
        result = {"mode": "naive", "outcome": outcome, "steps": steps, "segments": segments, "simulated": True}
    else:
        trial = run_trial(body.html, snapshot_id="trap", policy_hash=watchman.content_hash(body.html), app_name="signup")
        sentinel = trial.get("sentinel", {"signals": []})
        suspicious = trial["summary"]["sentinel_suspicious"]
        steps = ["Sentinel screened the page before reading it.",
                 f"Found {len(sentinel['signals'])} signal(s); {sum(s['assessment'] == 'suspicious' for s in sentinel['signals'])} are instructions aimed at AI agents."]
        if suspicious:
            steps += ["Guardian: BLOCK. The page tries to instruct AI agents, so it cannot be trusted.",
                      "Did not click anything. Asked you to decide."]
            outcome = "BLOCKED"
        else:
            steps += ["No instructions aimed at agents. Checking your rules before agreeing.", "Asked you to approve accepting these terms."]
            outcome = "NEEDS_APPROVAL"
        result = {"mode": "guarded", "outcome": outcome, "steps": steps, "segments": segments, "simulated": True,
                  "signals": sentinel["signals"], "headline": trial["summary"]["headline"],
                  "charges": trial.get("prosecutor", {}).get("charges", [])}
    audit_log.record(db, "demo.trap", user_id=ctx.user.id, actor_type="user", actor_id=ctx.user.id,
                     decision="BLOCK" if result["outcome"] == "BLOCKED" else None,
                     details={"mode": result["mode"], "outcome": result["outcome"], "simulated": True})
    db.commit()
    return result


@router.post("/demo/seed", status_code=201)
def seed(ctx: UserContext = Depends(current_user), db: Session = Depends(get_db)):
    """Populates the account with sample rules, the two demo policies, a demo agent and a data lineage chain."""
    require_step_up(ctx)
    exists = db.execute(select(PolicySource.id).where(PolicySource.user_id == ctx.user.id, PolicySource.name == "MapsCo")).first()
    if exists:
        raise APIError(409, "ALREADY_SEEDED", "demo data already exists on this account")
    user = ctx.user
    rules = [
        ("ALLOW", ["location"], ["navigation"], ["maps.example.com"], [], "Maps may use my location for directions"),
        ("DENY", ["location"], ["advertising", "marketing"], [], [], "Never use my location for ads"),
        ("REQUIRE_APPROVAL", ["contacts"], [], [], [], "Ask me before anyone gets my contacts"),
        ("DENY", ["*"], [], ["*.adnet.example"], [], "Nothing goes to ad networks"),
        ("ALLOW", ["email"], ["account_management", "service_delivery"], [], ["accept_terms", "create_account", "submit_form"], "Agents may sign me up with my email"),
        ("REQUIRE_APPROVAL", ["biometrics"], [], [], [], "Biometrics always need my approval"),
    ]
    for effect, cats, purposes, recipients, actions, desc in rules:
        user.constitution_version += 1
        db.add(ConsentRule(user_id=user.id, effect=effect, data_categories=cats, purposes=purposes, recipients=recipients,
                           actions=actions, description=desc, constitution_version=user.constitution_version))
    maps = watchman.create_policy(db, user, name="MapsCo", domain="maps.example.com", text=fx.MAPSCO["text"])
    torch = watchman.create_policy(db, user, name="FlashLight", domain="flashlight.example", text=fx.FLASHLIGHT["text"])
    agent_id = new_id()
    key, key_hash = make_compound_secret("cca", agent_id)
    db.add(AgentClient(id=agent_id, user_id=user.id, name="demo-browser-agent", key_hash=key_hash))
    gps = dataflow.create_asset(db, user.id, label="Device GPS fix", categories=["location"], source="device:gps")
    hood = dataflow.create_asset(db, user.id, label="Home neighbourhood", categories=["preferences"], derived_from=[gps.id],
                                 transformation="reverse-geocode to neighbourhood")
    dataflow.create_asset(db, user.id, label="Commute profile", categories=["preferences"], derived_from=[hood.id],
                          transformation="aggregate weekday trips")
    audit_log.record(db, "demo.seeded", user_id=user.id, actor_type="user", actor_id=user.id,
                     details={"rules": len(rules), "policies": [maps.id, torch.id], "agent_id": agent_id})
    db.commit()
    return {"agent_id": agent_id, "agent_key": key, "policies": {"mapsco": maps.id, "flashlight": torch.id},
            "assets": {"gps": gps.id, "neighbourhood": hood.id}}


@router.get("/dashboard/summary")
def dashboard(ctx: UserContext = Depends(current_user), db: Session = Depends(get_db)):
    uid = ctx.user.id
    now = clock.utcnow()
    day_ago = now - timedelta(days=1)

    def count(q):
        return db.execute(q).scalar() or 0

    policies = db.execute(select(PolicySource).where(PolicySource.user_id == uid).order_by(PolicySource.created_at)).scalars().all()
    policy_rows = []
    for p in policies:
        run = db.get(AnalysisRun, p.current_analysis_id) if p.current_analysis_id else None
        policy_rows.append({"id": p.id, "name": p.name, "domain": p.domain, "version": p.current_version,
                            "requires_reassessment": p.requires_reassessment, "watch_status": p.watch_status,
                            "risk_score": run.risk_score if run else None, "recommendation": run.recommendation if run else None,
                            "audit_verdict": run.audit_verdict if run else None, "headline": run.headline if run else ""})
    week = now - timedelta(days=6)
    flows = db.execute(select(FlowEvent).where(FlowEvent.user_id == uid, FlowEvent.created_at >= week.replace(hour=0, minute=0, second=0, microsecond=0))).scalars().all()
    days = {}
    for i in range(7):
        d = (week + timedelta(days=i)).date().isoformat()
        days[d] = {"date": d, "completed": 0, "blocked": 0}
    for f in flows:
        d = f.created_at.date().isoformat()
        if d in days:
            days[d]["completed" if f.outcome == "COMPLETED" else "blocked"] += 1
    recent = db.execute(select(AuditEvent).where(AuditEvent.user_id == uid).order_by(AuditEvent.seq.desc()).limit(12)).scalars().all()
    last_run = db.execute(select(RedTeamRun).where(RedTeamRun.user_id == uid).order_by(RedTeamRun.created_at.desc()).limit(1)).scalar()
    return {
        "frozen": ctx.user.frozen,
        "counts": {
            "policies": len(policies),
            "needs_reassessment": sum(p.requires_reassessment for p in policies),
            "active_rules": count(select(func.count()).select_from(ConsentRule).where(ConsentRule.user_id == uid, ConsentRule.active.is_(True))),
            "active_tokens": count(select(func.count()).select_from(ConsentToken).where(ConsentToken.user_id == uid, ConsentToken.revoked_at.is_(None), ConsentToken.expires_at > now)),
            "pending_approvals": count(select(func.count()).select_from(ApprovalRequest).where(ApprovalRequest.user_id == uid, ApprovalRequest.status == "PENDING", ApprovalRequest.expires_at > now)),
            "blocked_24h": count(select(func.count()).select_from(FlowEvent).where(FlowEvent.user_id == uid, FlowEvent.decision == "BLOCK", FlowEvent.created_at >= day_ago)),
            "completed_24h": count(select(func.count()).select_from(FlowEvent).where(FlowEvent.user_id == uid, FlowEvent.outcome == "COMPLETED", FlowEvent.created_at >= day_ago)),
            "agents": count(select(func.count()).select_from(AgentClient).where(AgentClient.user_id == uid, AgentClient.active.is_(True))),
        },
        "policies": policy_rows,
        "flows_by_day": list(days.values()),
        "recent": [{"seq": e.seq, "event_type": e.event_type, "decision": e.decision, "actor_type": e.actor_type,
                    "created_at": e.created_at, "details": e.details} for e in recent],
        "red_team": None if last_run is None else {"id": last_run.id, "seed": last_run.seed, "created_at": last_run.created_at, **last_run.summary},
    }
