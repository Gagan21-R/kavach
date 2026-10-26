"""Policy sources, versioned snapshots, court analyses and Watchman checks.

Every new version is compared with the previous one. Material or ambiguous changes pause authorizations bound
to the old version and require the user's reassessment; formatting-only and non-material wording changes do not.
"""
from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import audit_log
from app.auth.deps import UserContext, current_user, require_step_up
from app.court import service as court
from app.db import get_db
from app.errors import APIError, not_found
from app.guardian.service import owned_policy
from app.models import AnalysisRun, PolicySnapshot, PolicySource, WatchEvent
from app.schemas.api import PolicyIn, PolicyOut, SnapshotIn, SnapshotOut
from app.watchman import service as watchman

router = APIRouter(prefix="/policies", tags=["policies"])


def _snap_out(s: PolicySnapshot) -> dict:
    return {"id": s.id, "version": s.version, "content_hash": s.content_hash, "retrieved_at": s.retrieved_at,
            "length": len(s.text), "classification": s.classification}


def _analysis_out(run: AnalysisRun) -> dict:
    return {"id": run.id, "snapshot_id": run.snapshot_id, "snapshot_version": run.snapshot_version, "status": run.status,
            "recommendation": run.recommendation, "audit_verdict": run.audit_verdict, "risk_score": run.risk_score,
            "sentinel_suspicious": run.sentinel_suspicious, "headline": run.headline, "created_at": run.created_at,
            "result": run.result}


def _event_out(e: WatchEvent) -> dict:
    return {"id": e.id, "status": e.status, "classification": e.classification, "from_version": e.from_version,
            "to_version": e.to_version, "changes": e.output.get("changes", []), "confidence": e.output.get("confidence"),
            "affected_rule_ids": e.affected_rule_ids, "affected_token_ids": e.affected_token_ids,
            "recommendations": e.recommendations, "error": e.error, "created_at": e.created_at}


def policy_summary(db: Session, p: PolicySource) -> dict:
    run = db.get(AnalysisRun, p.current_analysis_id) if p.current_analysis_id else None
    return {
        **PolicyOut.model_validate(p).model_dump(),
        "analysis": None if run is None else {k: v for k, v in _analysis_out(run).items() if k != "result"},
    }


@router.post("", status_code=201)
def create_policy(body: PolicyIn, ctx: UserContext = Depends(current_user), db: Session = Depends(get_db)):
    policy = watchman.create_policy(db, ctx.user, name=body.name, domain=body.domain, text=body.text, url=body.url, locale=body.locale)
    db.commit()
    return policy_summary(db, policy)


@router.post("/analyze", status_code=201)
def analyze_new(body: PolicyIn, ctx: UserContext = Depends(current_user), db: Session = Depends(get_db)):
    """Register a policy and put it on trial in one call. Returns the full trial."""
    policy = watchman.create_policy(db, ctx.user, name=body.name, domain=body.domain, text=body.text, url=body.url, locale=body.locale)
    db.commit()
    return {"policy": policy_summary(db, policy), "analysis": _analysis_out(db.get(AnalysisRun, policy.current_analysis_id))}


@router.get("")
def list_policies(ctx: UserContext = Depends(current_user), db: Session = Depends(get_db)):
    rows = db.execute(select(PolicySource).where(PolicySource.user_id == ctx.user.id).order_by(PolicySource.created_at)).scalars()
    return [policy_summary(db, p) for p in rows]


@router.get("/{policy_id}")
def get_policy(policy_id: str, ctx: UserContext = Depends(current_user), db: Session = Depends(get_db)):
    return policy_summary(db, owned_policy(db, ctx.user.id, policy_id))


@router.post("/{policy_id}/snapshots")
def add_snapshot(policy_id: str, body: SnapshotIn, ctx: UserContext = Depends(current_user), db: Session = Depends(get_db)):
    policy = owned_policy(db, ctx.user.id, policy_id)
    ev = watchman.record_snapshot(db, policy, body.text, "user", ctx.user.id)
    db.commit()
    return {**policy_summary(db, policy), "watch_event": _event_out(ev) if ev else None}


@router.get("/{policy_id}/snapshots", response_model=list[SnapshotOut])
def list_snapshots(policy_id: str, ctx: UserContext = Depends(current_user), db: Session = Depends(get_db)):
    policy = owned_policy(db, ctx.user.id, policy_id)
    rows = db.execute(select(PolicySnapshot).where(PolicySnapshot.source_id == policy.id).order_by(PolicySnapshot.version)).scalars()
    return [_snap_out(s) for s in rows]


@router.get("/{policy_id}/snapshots/{snapshot_id}")
def get_snapshot(policy_id: str, snapshot_id: str, ctx: UserContext = Depends(current_user), db: Session = Depends(get_db)):
    policy = owned_policy(db, ctx.user.id, policy_id)
    snap = db.get(PolicySnapshot, snapshot_id)
    if snap is None or snap.source_id != policy.id:
        raise not_found("snapshot")
    return {**_snap_out(snap), "text": snap.text}


@router.get("/{policy_id}/analysis")
def current_analysis(policy_id: str, ctx: UserContext = Depends(current_user), db: Session = Depends(get_db)):
    policy = owned_policy(db, ctx.user.id, policy_id)
    if not policy.current_analysis_id:
        raise not_found("analysis")
    return _analysis_out(db.get(AnalysisRun, policy.current_analysis_id))


@router.post("/{policy_id}/analyze")
def rerun_analysis(policy_id: str, ctx: UserContext = Depends(current_user), db: Session = Depends(get_db)):
    policy = owned_policy(db, ctx.user.id, policy_id)
    run = court.analyze(db, policy, db.get(PolicySnapshot, policy.current_snapshot_id), actor_type="user", actor_id=ctx.user.id)
    db.commit()
    return _analysis_out(run)


@router.get("/{policy_id}/watch-events")
def watch_events(policy_id: str, ctx: UserContext = Depends(current_user), db: Session = Depends(get_db)):
    policy = owned_policy(db, ctx.user.id, policy_id)
    rows = db.execute(select(WatchEvent).where(WatchEvent.source_id == policy.id).order_by(WatchEvent.created_at.desc())).scalars()
    return [_event_out(e) for e in rows]


@router.post("/{policy_id}/check")
def check_now(policy_id: str, ctx: UserContext = Depends(current_user), db: Session = Depends(get_db)):
    """Fetch the policy URL now (SSRF-protected). A failed fetch is reported as UNKNOWN."""
    policy = owned_policy(db, ctx.user.id, policy_id)
    ev = watchman.check_source(db, policy, "user", ctx.user.id)
    db.commit()
    return _event_out(ev)


@router.post("/{policy_id}/reassess")
def mark_reassessed(policy_id: str, ctx: UserContext = Depends(current_user), db: Session = Depends(get_db)):
    """The user confirms they reviewed the new version. Re-enables new authorizations; old tokens stay stale."""
    policy = owned_policy(db, ctx.user.id, policy_id)
    require_step_up(ctx)
    if not policy.requires_reassessment:
        raise APIError(409, "NOTHING_TO_REASSESS", "this policy has no pending changes")
    policy.requires_reassessment = False
    audit_log.record(db, "policy.reassessed", user_id=ctx.user.id, actor_type="user", actor_id=ctx.user.id,
                     target_type="policy", target_id=policy.id, details={"hash": policy.current_hash, "version": policy.current_version})
    db.commit()
    return policy_summary(db, policy)
