from datetime import timedelta

from fastapi import APIRouter, Depends, Response
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app import audit_log, clock
from app.auth.crypto import hash_password, random_secret, sha256, verify_password
from app.auth.deps import UserContext, current_user
from app.config import get_settings
from app.db import get_db
from app.errors import APIError
from app.models import AuthSession, User
from app.ratelimit import auth_limit
from app.schemas.api import Credentials, LoginOut, StepUpIn, UserOut

router = APIRouter(prefix="/auth", tags=["auth"])


def _user_out(u: User) -> UserOut:
    return UserOut(id=u.id, email=u.email, constitution_version=u.constitution_version)


@router.post("/register", status_code=201, response_model=UserOut, dependencies=[Depends(auth_limit)])
def register(body: Credentials, db: Session = Depends(get_db)):
    if len(body.password) < get_settings().password_min_length:
        raise APIError(422, "WEAK_PASSWORD", f"password must be at least {get_settings().password_min_length} characters")
    if db.execute(select(User.id).where(User.email == body.email)).first():
        raise APIError(409, "EMAIL_TAKEN", "an account with this email already exists")
    user = User(email=body.email, password_hash=hash_password(body.password))
    db.add(user)
    db.flush()
    audit_log.record(db, "user.registered", user_id=user.id, actor_type="user", actor_id=user.id)
    db.commit()
    return _user_out(user)


@router.post("/login", response_model=LoginOut, dependencies=[Depends(auth_limit)])
def login(body: Credentials, response: Response, db: Session = Depends(get_db)):
    settings = get_settings()
    user = db.execute(select(User).where(User.email == body.email)).scalar_one_or_none()
    if not verify_password(user.password_hash if user else None, body.password):
        if user is not None:
            audit_log.record(db, "auth.login_failed", user_id=user.id, actor_type="user", actor_id=user.id)
            db.commit()
        raise APIError(401, "INVALID_CREDENTIALS", "email or password is incorrect")
    now = clock.utcnow()
    token = random_secret()
    sess = AuthSession(
        user_id=user.id,
        token_hash=sha256(token),
        csrf_token=random_secret(24),
        expires_at=now + timedelta(minutes=settings.session_ttl_minutes),
        step_up_at=now,  # a fresh password login counts as recent re-authentication
    )
    db.add(sess)
    db.flush()
    audit_log.record(db, "auth.login", user_id=user.id, actor_type="user", actor_id=user.id, target_type="session", target_id=sess.id)
    db.commit()
    response.set_cookie(
        settings.session_cookie_name,
        token,
        max_age=settings.session_ttl_minutes * 60,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="strict",
        path="/",
    )
    return LoginOut(user=_user_out(user), csrf_token=sess.csrf_token, expires_at=sess.expires_at)


@router.post("/logout", status_code=204)
def logout(response: Response, ctx: UserContext = Depends(current_user), db: Session = Depends(get_db)):
    ctx.session.revoked_at = clock.utcnow()
    audit_log.record(db, "auth.logout", user_id=ctx.user.id, actor_type="user", actor_id=ctx.user.id, target_type="session", target_id=ctx.session.id)
    db.commit()
    response.delete_cookie(get_settings().session_cookie_name, path="/")


@router.post("/step-up", dependencies=[Depends(auth_limit)])
def step_up(body: StepUpIn, ctx: UserContext = Depends(current_user), db: Session = Depends(get_db)):
    if not verify_password(ctx.user.password_hash, body.password):
        audit_log.record(db, "auth.step_up_failed", user_id=ctx.user.id, actor_type="user", actor_id=ctx.user.id)
        db.commit()
        raise APIError(401, "INVALID_CREDENTIALS", "password is incorrect")
    now = clock.utcnow()
    ctx.session.step_up_at = now
    audit_log.record(db, "auth.step_up", user_id=ctx.user.id, actor_type="user", actor_id=ctx.user.id, target_type="session", target_id=ctx.session.id)
    db.commit()
    return {"step_up_valid_until": now + timedelta(minutes=get_settings().step_up_ttl_minutes)}


@router.get("/me", response_model=UserOut)
def me(ctx: UserContext = Depends(current_user)):
    return _user_out(ctx.user)


@router.post("/sessions/revoke-all")
def revoke_all_sessions(response: Response, ctx: UserContext = Depends(current_user), db: Session = Depends(get_db)):
    """Signs out every device, including this one. Tightening, so no step-up needed."""
    now = clock.utcnow()
    result = db.execute(
        update(AuthSession)
        .where(AuthSession.user_id == ctx.user.id, AuthSession.revoked_at.is_(None))
        .values(revoked_at=now)
        .execution_options(synchronize_session=False)
    )
    audit_log.record(db, "auth.sessions_revoked", user_id=ctx.user.id, actor_type="user", actor_id=ctx.user.id, details={"count": result.rowcount})
    db.commit()
    response.delete_cookie(get_settings().session_cookie_name, path="/")
    return {"revoked": result.rowcount}
