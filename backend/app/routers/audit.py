from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.deps import UserContext, current_user
from app.db import get_db
from app.models import AuditEvent
from app.schemas.api import AuditEventOut

router = APIRouter(prefix="/audit", tags=["audit"])


@router.get("/events", response_model=list[AuditEventOut])
def list_events(
    event_type: str | None = Query(None, max_length=60),
    before_seq: int | None = Query(None, ge=1),
    limit: int = Query(50, ge=1, le=200),
    ctx: UserContext = Depends(current_user),
    db: Session = Depends(get_db),
):
    """The signed-in user's own events only, newest first."""
    q = select(AuditEvent).where(AuditEvent.user_id == ctx.user.id)
    if event_type:
        q = q.where(AuditEvent.event_type == event_type)
    if before_seq:
        q = q.where(AuditEvent.seq < before_seq)
    return list(db.execute(q.order_by(AuditEvent.seq.desc()).limit(limit)).scalars())
