"""Policy sources and versioned snapshots.

Milestone 1 compares exact content hashes: ANY change marks the policy as needing reassessment, which makes
tokens bound to the old version unusable. Watchman (Milestone 3) will refine this so formatting-only changes
do not require re-approval.
"""
import hashlib

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import audit_log
from app.auth.deps import UserContext, current_user, require_step_up
from app.db import get_db
from app.errors import not_found
from app.guardian.service import owned_policy
from app.models import PolicySnapshot, PolicySource
from app.schemas.api import PolicyIn, PolicyOut, SnapshotIn, SnapshotOut

router = APIRouter(prefix="/policies", tags=["policies"])


def _hash(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def _snap_out(s: PolicySnapshot) -> dict:
    return {"id": s.id, "version": s.version, "content_hash": s.content_hash, "retrieved_at": s.retrieved_at, "length": len(s.text)}


def _add_snapshot(db: Session, policy: PolicySource, text: str) -> PolicySnapshot:
    version = (db.execute(select(func.max(PolicySnapshot.version)).where(PolicySnapshot.source_id == policy.id)).scalar() or 0) + 1
    snap = PolicySnapshot(source_id=policy.id, user_id=policy.user_id, version=version, content_hash=_hash(text), text=text)
    db.add(snap)
    db.flush()
    policy.current_snapshot_id = snap.id
    policy.current_hash = snap.content_hash
    return snap


@router.post("", status_code=201, response_model=PolicyOut)
def create_policy(body: PolicyIn, ctx: UserContext = Depends(current_user), db: Session = Depends(get_db)):
    policy = PolicySource(user_id=ctx.user.id, name=body.name, url=body.url, domain=body.domain, locale=body.locale)
    db.add(policy)
    db.flush()
    snap = _add_snapshot(db, policy, body.text)
    audit_log.record(db, "policy.snapshot.created", user_id=ctx.user.id, actor_type="user", actor_id=ctx.user.id,
                     target_type="policy", target_id=policy.id, details={"version": snap.version, "hash": snap.content_hash})
    db.commit()
    return policy


@router.get("", response_model=list[PolicyOut])
def list_policies(ctx: UserContext = Depends(current_user), db: Session = Depends(get_db)):
    return list(db.execute(select(PolicySource).where(PolicySource.user_id == ctx.user.id).order_by(PolicySource.created_at)).scalars())


@router.get("/{policy_id}", response_model=PolicyOut)
def get_policy(policy_id: str, ctx: UserContext = Depends(current_user), db: Session = Depends(get_db)):
    return owned_policy(db, ctx.user.id, policy_id)


@router.post("/{policy_id}/snapshots", response_model=PolicyOut)
def add_snapshot(policy_id: str, body: SnapshotIn, ctx: UserContext = Depends(current_user), db: Session = Depends(get_db)):
    policy = owned_policy(db, ctx.user.id, policy_id)
    if _hash(body.text) == policy.current_hash:
        return policy  # identical content: no new version
    previous = policy.current_hash
    snap = _add_snapshot(db, policy, body.text)
    policy.requires_reassessment = True
    audit_log.record(db, "policy.snapshot.created", user_id=ctx.user.id, actor_type="user", actor_id=ctx.user.id,
                     target_type="policy", target_id=policy.id,
                     details={"version": snap.version, "hash": snap.content_hash, "previous_hash": previous})
    audit_log.record(db, "consent.review.required", user_id=ctx.user.id, actor_type="system",
                     target_type="policy", target_id=policy.id,
                     details={"reason": "policy content changed; authorizations bound to the previous version no longer apply"})
    db.commit()
    return policy


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


@router.post("/{policy_id}/reassess", response_model=PolicyOut)
def mark_reassessed(policy_id: str, ctx: UserContext = Depends(current_user), db: Session = Depends(get_db)):
    """The user confirms they reviewed the new version. Re-enables new authorizations (old tokens stay stale)."""
    policy = owned_policy(db, ctx.user.id, policy_id)
    require_step_up(ctx)
    policy.requires_reassessment = False
    audit_log.record(db, "policy.reassessed", user_id=ctx.user.id, actor_type="user", actor_id=ctx.user.id,
                     target_type="policy", target_id=policy.id, details={"hash": policy.current_hash})
    db.commit()
    return policy
