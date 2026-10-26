from fastapi import APIRouter, Depends
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app import audit_log, clock
from app.auth.crypto import make_compound_secret
from app.auth.deps import UserContext, current_user, require_step_up
from app.db import get_db
from app.errors import not_found
from app.models import AgentClient, ConsentToken
from app.models._common import new_id
from app.schemas.api import AgentCreatedOut, AgentIn, AgentOut

router = APIRouter(prefix="/agents", tags=["agents"])


def _out(a: AgentClient) -> dict:
    return {"id": a.id, "name": a.name, "active": a.active, "created_at": a.created_at}


@router.post("", status_code=201, response_model=AgentCreatedOut)
def create_agent(body: AgentIn, ctx: UserContext = Depends(current_user), db: Session = Depends(get_db)):
    """Registering an agent grants it the ability to request tokens, so it needs recent re-authentication."""
    require_step_up(ctx)
    agent_id = new_id()
    api_key, key_hash = make_compound_secret("cca", agent_id)
    agent = AgentClient(id=agent_id, user_id=ctx.user.id, name=body.name, key_hash=key_hash)
    db.add(agent)
    audit_log.record(db, "agent.created", user_id=ctx.user.id, actor_type="user", actor_id=ctx.user.id,
                     target_type="agent", target_id=agent_id, details={"name": body.name})
    db.commit()
    return {**_out(agent), "api_key": api_key}


@router.get("", response_model=list[AgentOut])
def list_agents(ctx: UserContext = Depends(current_user), db: Session = Depends(get_db)):
    rows = db.execute(select(AgentClient).where(AgentClient.user_id == ctx.user.id).order_by(AgentClient.created_at)).scalars()
    return [_out(a) for a in rows]


@router.post("/{agent_id}/revoke", response_model=AgentOut)
def revoke_agent(agent_id: str, ctx: UserContext = Depends(current_user), db: Session = Depends(get_db)):
    """Disables the agent and revokes all of its tokens. Tightening, so no step-up needed."""
    agent = db.get(AgentClient, agent_id)
    if agent is None or agent.user_id != ctx.user.id:
        raise not_found("agent")
    now = clock.utcnow()
    agent.active = False
    agent.revoked_at = now
    result = db.execute(
        update(ConsentToken)
        .where(ConsentToken.agent_id == agent.id, ConsentToken.revoked_at.is_(None))
        .values(revoked_at=now, revocation_reason="agent revoked")
        .execution_options(synchronize_session=False)
    )
    audit_log.record(db, "agent.revoked", user_id=ctx.user.id, actor_type="user", actor_id=ctx.user.id,
                     target_type="agent", target_id=agent.id, details={"tokens_revoked": result.rowcount})
    db.commit()
    return _out(agent)
