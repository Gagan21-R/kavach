"""The enforcement boundary. Every protected action runs through execute(), which re-validates authorization
immediately before the adapter is called. Any failure (including the database) stops the action: fail closed.
Every attempt, blocked or completed, is recorded as a flow event for the Data Flow Observatory.
"""
import logging

from sqlalchemy.orm import Session

from app import audit_log, clock
from app.dataflow import service as dataflow
from app.errors import APIError
from app.gateway import adapters
from app.guardian import service as guardian
from app.guardian import tokens
from app.models import AgentClient, FlowEvent, PolicySource, TokenUse, User
from app.vocab import Decision

log = logging.getLogger("consent_court.gateway")


def _flow(db: Session, *, user_id, agent_id, body, effective, decision, outcome, code=None, reason="", token_id=None, records=0):
    db.add(FlowEvent(
        user_id=user_id, agent_id=agent_id, asset_id=body.asset_id, action=body.action, destination=body.destination,
        purpose=body.purpose, declared_categories=sorted(set(body.data_categories)), effective_categories=sorted(effective),
        decision=decision, outcome=outcome, code=code, reason=reason, token_id=token_id, records=records,
    ))


def _reject(db: Session, user_id: str, agent_id: str, token_id: str | None, exc: tokens.TokenRejected, scope: dict,
            body, effective: set[str]) -> APIError:
    db.add(TokenUse(token_id=token_id, user_id=user_id, agent_id=agent_id, outcome=exc.code, detail=exc.message))
    _flow(db, user_id=user_id, agent_id=agent_id, body=body, effective=effective, decision=Decision.BLOCK,
          outcome="BLOCKED_BEFORE_EXECUTION", code=exc.code, reason=exc.message, token_id=token_id)
    audit_log.record(
        db, "gateway.blocked", user_id=user_id, actor_type="agent", actor_id=agent_id,
        target_type="token", target_id=token_id, decision=Decision.BLOCK,
        details={**scope, "code": exc.code, "reason": exc.message},
    )
    db.commit()
    return APIError(403, exc.code, exc.message, decision=Decision.BLOCK, executed=False)


def execute(db: Session, agent: AgentClient, token_plaintext: str, body) -> dict:
    agent_id, user_id = agent.id, agent.user_id  # read before any rollback expires the instance
    scope = {
        "action": body.action,
        "destination": body.destination,
        "purpose": body.purpose,
        "data_categories": list(body.data_categories),
        "record_count": body.record_count,
        "asset_id": body.asset_id,
    }
    effective = set(body.data_categories)
    token = None
    try:
        now = clock.utcnow()
        user = db.get(User, user_id)
        if user.frozen:
            raise tokens.TokenRejected("EMERGENCY_STOP", "Emergency Stop is active: all protected actions are frozen")
        if body.asset_id:
            effective |= dataflow.effective_categories(db, user_id, body.asset_id)
            undeclared = sorted(effective - set(body.data_categories))
            if undeclared:
                raise tokens.TokenRejected(
                    "UNDECLARED_DATA",
                    f"this data is derived from sources carrying {', '.join(undeclared)}; those categories must be declared and authorized",
                )
        token = tokens.lookup(db, token_plaintext)
        policy = db.get(PolicySource, token.policy_source_id)
        tokens.check_static(
            token, agent=agent, action=body.action, destination=body.destination, purpose=body.purpose,
            data_categories=list(body.data_categories), record_count=body.record_count, policy=policy, now=now,
        )
        # Re-check the user's *current* constitution: a DENY added after issuance must stop the action.
        ev = guardian.evaluate(
            db, user, action=body.action, destination=body.destination,
            purpose=body.purpose, data_categories=list(body.data_categories), policy_source_id=token.policy_source_id,
        )
        if ev.decision == Decision.BLOCK:
            raise tokens.TokenRejected("RULES_NOW_DENY", "; ".join(ev.reasons), token)
        if ev.decision == Decision.REVIEW and not (ev.approvable and token.approval_id):
            raise tokens.TokenRejected("AUTHORIZATION_NO_LONGER_VALID", "; ".join(ev.reasons), token)
        tokens.consume(db, token, body.record_count, now)
    except tokens.TokenRejected as exc:
        token_id = exc.token.id if exc.token is not None else None
        db.rollback()
        raise _reject(db, user_id, agent_id, token_id, exc, scope, body, effective) from None
    except APIError as exc:
        db.rollback()
        if exc.status == 404:  # unknown asset: treat as a blocked attempt, not a lookup error
            raise _reject(db, user_id, agent_id, None, tokens.TokenRejected("UNKNOWN_ASSET", "asset not found"), scope, body, effective) from None
        raise
    except Exception:
        db.rollback()
        log.exception("gateway authorization failed; failing closed")
        raise APIError(503, "AUTHORIZATION_UNAVAILABLE", "authorization could not be verified; action blocked",
                       decision=Decision.BLOCK, executed=False) from None

    token_id = token.id
    adapter_name, adapter = adapters.ADAPTERS[body.action]
    act = adapters.AuthorizedAction(
        token_id=token_id, user_id=user_id, agent_id=agent_id, action=body.action,
        destination=body.destination, purpose=body.purpose, data_categories=tuple(body.data_categories),
        record_count=body.record_count,
    )
    # The budget is committed before the adapter runs, so a crash mid-action can never refund a use.
    db.add(TokenUse(token_id=token_id, user_id=user_id, agent_id=agent_id, outcome="ACCEPTED", records=body.record_count))
    db.commit()
    try:
        result = adapter(act, body.payload, adapters._GATEWAY_PASS)
        outcome = "gateway.executed"
    except Exception as e:  # adapter failure is recorded, budget stays spent
        log.exception("adapter %s failed", adapter_name)
        result, outcome = {"error": type(e).__name__}, "gateway.adapter_failed"
    _flow(db, user_id=user_id, agent_id=agent_id, body=body, effective=effective, decision=Decision.ALLOW,
          outcome="COMPLETED" if outcome == "gateway.executed" else "ADAPTER_FAILED", token_id=token_id,
          records=body.record_count, reason="simulated delivery" if result.get("simulated") else "")
    audit_log.record(
        db, outcome, user_id=user_id, actor_type="agent", actor_id=agent_id, target_type="token",
        target_id=token_id, decision=Decision.ALLOW,
        details={**scope, "adapter": adapter_name, "simulated": bool(result.get("simulated")),
                 "content_sha256": result.get("payload_sha256")},
    )
    db.commit()
    if outcome == "gateway.adapter_failed":
        raise APIError(502, "ADAPTER_FAILED", "authorized, but the action failed downstream", executed=False, token_id=token_id)
    return {
        "executed": True,
        "decision": Decision.ALLOW,
        "token_id": token_id,
        "adapter": adapter_name,
        "simulated": bool(result.get("simulated")),
        "result": result,
    }
