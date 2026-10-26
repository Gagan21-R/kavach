from fastapi import APIRouter, Depends, Header
from sqlalchemy.orm import Session

from app.auth.deps import current_agent
from app.db import get_db
from app.gateway import executor
from app.models import AgentClient
from app.schemas.api import GatewayIn, GatewayOut

router = APIRouter(prefix="/gateway", tags=["gateway"])


@router.post("/execute", response_model=GatewayOut)
def execute(
    body: GatewayIn,
    x_consent_token: str = Header(default=""),
    agent: AgentClient = Depends(current_agent),
    db: Session = Depends(get_db),
):
    """The only route that can run a protected action. Requires the agent key AND a matching consent token."""
    return executor.execute(db, agent, x_consent_token, body)
