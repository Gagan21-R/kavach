"""Append-only, hash-chained audit log.

Each event stores the hash of the previous event, so editing or deleting a row breaks verify_chain().
Details are scrubbed: keys that look like secrets or raw payloads are never written.
"""
import hashlib
import json
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import clock, context
from app.models import AuditEvent
from app.models._common import new_id

GENESIS = "0" * 64
_SECRET_MARKERS = ("password", "secret", "token", "api_key", "apikey", "authorization", "cookie", "payload", "csrf")


def scrub(value: Any) -> Any:
    if isinstance(value, dict):
        out = {}
        for k, v in value.items():
            if any(m in str(k).lower() for m in _SECRET_MARKERS):
                out[k] = "[redacted]"
            else:
                out[k] = scrub(v)
        return out
    if isinstance(value, (list, tuple)):
        return [scrub(v) for v in value]
    return value


def _digest(prev_hash: str, fields: dict) -> str:
    body = json.dumps(fields, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256((prev_hash + body).encode()).hexdigest()


def _hash_fields(ev: AuditEvent) -> dict:
    return {
        "id": ev.id,
        "user_id": ev.user_id,
        "actor_type": ev.actor_type,
        "actor_id": ev.actor_id,
        "event_type": ev.event_type,
        "target_type": ev.target_type,
        "target_id": ev.target_id,
        "decision": ev.decision,
        "details": ev.details,
        "correlation_id": ev.correlation_id,
        "created_at": ev.created_at.isoformat(),
    }


def record(
    db: Session,
    event_type: str,
    *,
    user_id: str | None,
    actor_type: str,
    actor_id: str | None = None,
    target_type: str | None = None,
    target_id: str | None = None,
    decision: str | None = None,
    details: dict | None = None,
    correlation_id: str | None = None,
) -> AuditEvent:
    """Adds an event to the session. The caller commits, so the event lands atomically with the change it describes."""
    prev = db.execute(select(AuditEvent.hash).order_by(AuditEvent.seq.desc()).limit(1)).scalar()
    # Also chain to events added in this unit of work but not yet flushed.
    pending = [o for o in db.new if isinstance(o, AuditEvent)]
    if pending:
        prev = pending[-1].hash
    ev = AuditEvent(
        id=new_id(),
        user_id=user_id,
        actor_type=actor_type,
        actor_id=actor_id,
        event_type=event_type,
        target_type=target_type,
        target_id=target_id,
        decision=decision,
        details=scrub(details or {}),
        correlation_id=correlation_id or context.correlation_id.get(),
        created_at=clock.utcnow(),
        prev_hash=prev or GENESIS,
    )
    ev.hash = _digest(ev.prev_hash, _hash_fields(ev))
    db.add(ev)
    return ev


def verify_chain(db: Session) -> tuple[bool, str | None]:
    """Returns (ok, id_of_first_bad_event)."""
    prev = GENESIS
    for ev in db.execute(select(AuditEvent).order_by(AuditEvent.seq)).scalars():
        if ev.prev_hash != prev or _digest(prev, _hash_fields(ev)) != ev.hash:
            return False, ev.id
        prev = ev.hash
    return True, None
