"""Notifications: the few new things the user should take care of. Read ones leave the panel.

Raised for: a tracked policy that changed in a way that matters, a policy Kavach couldn't read, an update email
that reached the monitoring inbox, an AI agent waiting for a decision, and a site the extension reviewed that goes
against the user's rules. An unread notice about the same thing is not repeated.
"""
from fastapi import APIRouter, Depends
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app import clock
from app.auth.deps import UserContext, current_user
from app.db import get_db
from app.errors import not_found
from app.models import Notification


def notify(db: Session, user_id: str, kind: str, title: str, body: str = "", *, tone: str = "info", section: str = "",
           ref_id: str | None = None) -> Notification | None:
    if ref_id is not None:
        dup = db.execute(select(Notification).where(Notification.user_id == user_id, Notification.kind == kind,
                                                    Notification.ref_id == ref_id, Notification.read_at.is_(None))).first()
        if dup:
            return None
    n = Notification(user_id=user_id, kind=kind, title=title[:300], body=body[:2000], tone=tone, section=section, ref_id=ref_id)
    db.add(n)
    db.flush()
    return n


router = APIRouter(prefix="/notifications", tags=["notifications"])


def _out(n: Notification) -> dict:
    return {"id": n.id, "kind": n.kind, "title": n.title, "body": n.body, "tone": n.tone, "section": n.section,
            "created_at": n.created_at, "read": n.read_at is not None}


@router.get("")
def list_notifications(ctx: UserContext = Depends(current_user), db: Session = Depends(get_db)):
    unread = list(db.execute(select(Notification).where(Notification.user_id == ctx.user.id, Notification.read_at.is_(None))
                             .order_by(Notification.created_at.desc()).limit(30)).scalars())
    return {"unread_count": len(unread), "items": [_out(n) for n in unread]}


@router.post("/{notification_id}/read")
def mark_read(notification_id: str, ctx: UserContext = Depends(current_user), db: Session = Depends(get_db)):
    n = db.get(Notification, notification_id)
    if n is None or n.user_id != ctx.user.id:
        raise not_found("notification")
    n.read_at = n.read_at or clock.utcnow()
    db.commit()
    return _out(n)


@router.post("/read-all")
def mark_all_read(ctx: UserContext = Depends(current_user), db: Session = Depends(get_db)):
    n = db.execute(update(Notification).where(Notification.user_id == ctx.user.id, Notification.read_at.is_(None))
                   .values(read_at=clock.utcnow()).execution_options(synchronize_session=False)).rowcount
    db.commit()
    return {"cleared": n}
