"""Guardian API.

Agent-facing (X-Agent-Key): evaluate, authorize.
User-facing (session): tokens, revoke, approvals.
"""
from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse
from fastapi.encoders import jsonable_encoder
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app import audit_log, clock
from app.auth.deps import UserContext, current_agent, current_user, require_step_up
from app.db import get_db
from app.errors import APIError, not_found
from app.guardian import service
from app.models import AgentClient, ApprovalRequest, ConsentToken, User
from app.schemas.api import ApprovalOut, AuthorizeIn, EvaluationOut, GuardianIn, RevokeIn, TokenOut

router = APIRouter(prefix="/guardian", tags=["guardian"])


@router.post("/evaluate", response_model=EvaluationOut)
def evaluate(body: GuardianIn, agent: AgentClient = Depends(current_agent), db: Session = Depends(get_db)):
    """Dry run for an agent: would this action be allowed right now? Issues nothing."""
    user = db.get(User, agent.user_id)
    ev = service.evaluate(
        db, user, action=body.action, destination=body.destination, purpose=body.purpose,
        data_categories=list(body.data_categories), policy_source_id=body.policy_source_id,
    )
    audit_log.record(
        db, "guardian.evaluated", user_id=user.id, actor_type="agent", actor_id=agent.id, decision=ev.decision,
        details={"evaluation_id": ev.id, "action": body.action, "destination": body.destination,
                 "purpose": body.purpose, "data_categories": list(body.data_categories), "reasons": ev.reasons},
    )
    db.commit()
    return ev.as_dict()


@router.post("/authorize", response_model=None)
def authorize(body: AuthorizeIn, agent: AgentClient = Depends(current_agent), db: Session = Depends(get_db)):
    """201 + token when allowed; 202 + approval_request_id when the user must approve; 403 BLOCK; 409 REVIEW."""
    status, payload = service.authorize(db, agent, body)
    return JSONResponse(status_code=status, content=jsonable_encoder(payload))


@router.get("/tokens", response_model=list[TokenOut])
def list_tokens(
    active_only: bool = Query(False),
    ctx: UserContext = Depends(current_user),
    db: Session = Depends(get_db),
):
    q = select(ConsentToken).where(ConsentToken.user_id == ctx.user.id)
    if active_only:
        q = q.where(ConsentToken.revoked_at.is_(None), ConsentToken.expires_at > clock.utcnow())
    return [service.token_out(t) for t in db.execute(q.order_by(ConsentToken.issued_at.desc())).scalars()]


@router.post("/revoke")
def revoke(body: RevokeIn, ctx: UserContext = Depends(current_user), db: Session = Depends(get_db)):
    """Stops FUTURE use of tokens. It cannot recall data already delivered to a recipient."""
    conditions = [ConsentToken.user_id == ctx.user.id, ConsentToken.revoked_at.is_(None)]
    if body.token_id is not None:
        token = db.get(ConsentToken, body.token_id)
        if token is None or token.user_id != ctx.user.id:
            raise not_found("token")
        conditions.append(ConsentToken.id == body.token_id)
    elif body.agent_id is not None:
        agent = db.get(AgentClient, body.agent_id)
        if agent is None or agent.user_id != ctx.user.id:
            raise not_found("agent")
        conditions.append(ConsentToken.agent_id == body.agent_id)
    ids = list(db.execute(select(ConsentToken.id).where(*conditions)).scalars())
    if ids:
        db.execute(
            update(ConsentToken)
            .where(ConsentToken.id.in_(ids))
            .values(revoked_at=clock.utcnow(), revocation_reason=body.reason)
            .execution_options(synchronize_session=False)
        )
    for token_id in ids:
        audit_log.record(db, "token.revoked", user_id=ctx.user.id, actor_type="user", actor_id=ctx.user.id,
                         target_type="token", target_id=token_id, details={"reason": body.reason})
    db.commit()
    return {
        "revoked": len(ids),
        "token_ids": ids,
        "note": "Revocation blocks future use only. Data already sent cannot be recalled by revoking a token.",
    }


@router.get("/approvals", response_model=list[ApprovalOut])
def list_approvals(
    status: str | None = Query(None, pattern="^(PENDING|APPROVED|DENIED|USED)$"),
    ctx: UserContext = Depends(current_user),
    db: Session = Depends(get_db),
):
    q = select(ApprovalRequest).where(ApprovalRequest.user_id == ctx.user.id)
    if status:
        q = q.where(ApprovalRequest.status == status)
    return list(db.execute(q.order_by(ApprovalRequest.created_at.desc())).scalars())


def _pending(db: Session, ctx: UserContext, approval_id: str) -> ApprovalRequest:
    approval = db.get(ApprovalRequest, approval_id)
    if approval is None or approval.user_id != ctx.user.id:
        raise not_found("approval")
    if approval.status != "PENDING":
        raise APIError(409, "NOT_PENDING", f"approval is already {approval.status.lower()}")
    if approval.expires_at <= clock.utcnow():
        raise APIError(409, "APPROVAL_EXPIRED", "approval request has expired; the agent must ask again")
    return approval


@router.post("/approvals/{approval_id}/approve", response_model=ApprovalOut)
def approve(approval_id: str, ctx: UserContext = Depends(current_user), db: Session = Depends(get_db)):
    approval = _pending(db, ctx, approval_id)
    require_step_up(ctx)
    approval.status = "APPROVED"
    approval.decided_at = clock.utcnow()
    audit_log.record(db, "guardian.approval.approved", user_id=ctx.user.id, actor_type="user", actor_id=ctx.user.id,
                     target_type="approval", target_id=approval.id,
                     details={"action": approval.action, "destination": approval.destination,
                              "purpose": approval.purpose, "data_categories": approval.data_categories,
                              "policy_hash": approval.policy_hash})
    db.commit()
    return approval


@router.post("/approvals/{approval_id}/deny", response_model=ApprovalOut)
def deny(approval_id: str, ctx: UserContext = Depends(current_user), db: Session = Depends(get_db)):
    approval = _pending(db, ctx, approval_id)
    approval.status = "DENIED"
    approval.decided_at = clock.utcnow()
    audit_log.record(db, "guardian.approval.denied", user_id=ctx.user.id, actor_type="user", actor_id=ctx.user.id,
                     target_type="approval", target_id=approval.id)
    db.commit()
    return approval
