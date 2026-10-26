"""Request authentication for humans (sessions) and AI agents (API keys)."""
from dataclasses import dataclass
from datetime import timedelta

from fastapi import Depends, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import clock
from app.auth.crypto import constant_time_equal, sha256, split_compound_secret
from app.config import get_settings
from app.db import get_db
from app.errors import APIError
from app.models import AgentClient, AuthSession, User

_SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}


@dataclass
class UserContext:
    user: User
    session: AuthSession


def current_user(request: Request, db: Session = Depends(get_db)) -> UserContext:
    """Humans authenticate with an HttpOnly session cookie only (no bearer tokens), so CSRF checks always apply."""
    token = request.cookies.get(get_settings().session_cookie_name)
    if not token:
        raise APIError(401, "UNAUTHENTICATED", "login required")
    sess = db.execute(select(AuthSession).where(AuthSession.token_hash == sha256(token))).scalar_one_or_none()
    now = clock.utcnow()
    if sess is None or sess.revoked_at is not None or sess.expires_at <= now:
        raise APIError(401, "UNAUTHENTICATED", "session invalid or expired")
    # Cookies are sent automatically by browsers, so writes must prove same-origin intent.
    if request.method not in _SAFE_METHODS:
        sent = request.headers.get("x-csrf-token", "")
        if not sent or not constant_time_equal(sent, sess.csrf_token):
            raise APIError(403, "CSRF_FAILED", "missing or invalid X-CSRF-Token header")
    user = db.get(User, sess.user_id)
    if user is None:
        raise APIError(401, "UNAUTHENTICATED", "user not found")
    return UserContext(user=user, session=sess)


def has_recent_step_up(sess: AuthSession) -> bool:
    if sess.step_up_at is None:
        return False
    return clock.utcnow() - sess.step_up_at <= timedelta(minutes=get_settings().step_up_ttl_minutes)


def require_step_up(ctx: UserContext) -> None:
    if not has_recent_step_up(ctx.session):
        raise APIError(403, "STEP_UP_REQUIRED", "re-enter your password via POST /auth/step-up to continue")


def current_agent(request: Request, db: Session = Depends(get_db)) -> AgentClient:
    parts = split_compound_secret("cca", request.headers.get("x-agent-key", ""))
    if parts is None:
        raise APIError(401, "AGENT_UNAUTHENTICATED", "X-Agent-Key header missing or malformed")
    agent_id, secret = parts
    agent = db.get(AgentClient, agent_id)
    if agent is None or not constant_time_equal(agent.key_hash, sha256(secret)) or not agent.active:
        raise APIError(401, "AGENT_UNAUTHENTICATED", "agent key invalid or revoked")
    return agent
