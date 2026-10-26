"""Guardian: deterministic authorization for protected agent actions.

Decision order (no model can change it):
  1. A user DENY rule                                  -> BLOCK
  2. Policy problems (no snapshot, awaiting reassessment,
     destination outside the referenced policy)        -> REVIEW, not approvable
  3. REQUIRE_APPROVAL rule or no covering rule         -> REVIEW, approvable by the user
  4. Every category covered by ALLOW rules             -> ALLOW
"""
from dataclasses import dataclass
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import audit_log, clock
from app.config import get_settings
from app.engine import constitution
from app.engine.hosts import host_within
from app.errors import APIError, not_found
from app.guardian import tokens
from app.models import AgentClient, ApprovalRequest, ConsentRule, PolicySource, User
from app.models._common import new_id
from app.vocab import Decision


@dataclass
class Evaluation:
    id: str
    decision: Decision
    approvable: bool
    reasons: list[str]
    engine: constitution.EngineResult
    rules: list[ConsentRule]
    policy: PolicySource
    constitution_version: int

    def as_dict(self) -> dict:
        return {
            "evaluation_id": self.id,
            "decision": self.decision,
            "approvable": self.approvable,
            "reasons": self.reasons,
            "outcomes": [o.__dict__ for o in self.engine.outcomes],
            "deciding_rule_ids": self.engine.deciding_rule_ids,
            "constitution_version": self.constitution_version,
            "policy_hash": self.policy.current_hash,
        }


def owned_policy(db: Session, user_id: str, policy_id: str) -> PolicySource:
    policy = db.get(PolicySource, policy_id)
    if policy is None or policy.user_id != user_id:
        raise not_found("policy")
    return policy


def active_rules(db: Session, user_id: str) -> list[ConsentRule]:
    return list(
        db.execute(select(ConsentRule).where(ConsentRule.user_id == user_id, ConsentRule.active.is_(True))).scalars()
    )


def _policy_problems(policy: PolicySource, destination: str) -> list[str]:
    problems = []
    if policy.current_hash is None:
        problems.append("no policy snapshot is on record for this destination")
    if policy.requires_reassessment:
        problems.append("the destination's policy changed and is awaiting your reassessment")
    if not host_within(destination, policy.domain):
        problems.append(f"{destination} is not covered by the referenced policy for {policy.domain}")
    return problems


def evaluate(
    db: Session,
    user: User,
    *,
    action: str,
    destination: str,
    purpose: str,
    data_categories: list[str],
    policy_source_id: str,
) -> Evaluation:
    policy = owned_policy(db, user.id, policy_source_id)
    rules = active_rules(db, user.id)
    result = constitution.evaluate(
        rules,
        constitution.ActionRequest(action, destination, purpose, tuple(data_categories)),
        clock.utcnow(),
    )
    problems = _policy_problems(policy, destination)
    if result.decision == Decision.BLOCK:
        decision, approvable, reasons = Decision.BLOCK, False, result.reasons
    elif problems:
        decision, approvable, reasons = Decision.REVIEW, False, problems + result.reasons
    else:
        decision, approvable, reasons = result.decision, result.approvable, result.reasons
    return Evaluation(
        id=new_id(),
        decision=decision,
        approvable=approvable,
        reasons=reasons,
        engine=result,
        rules=rules,
        policy=policy,
        constitution_version=user.constitution_version,
    )


def _approval_covers(approval: ApprovalRequest, agent: AgentClient, body, policy: PolicySource, now) -> str | None:
    """Returns why the approval does not cover this request, or None if it does."""
    if approval.status != "APPROVED":
        return f"approval is {approval.status.lower()}"
    if now >= approval.expires_at:
        return "approval has expired"
    if approval.agent_id != agent.id:
        return "approval was granted to a different agent"
    if (approval.action, approval.destination, approval.purpose, approval.policy_source_id) != (
        body.action,
        body.destination,
        body.purpose,
        body.policy_source_id,
    ):
        return "approval does not match this action, destination, purpose or policy"
    if not set(body.data_categories) <= set(approval.data_categories):
        return "request includes data categories the user did not approve"
    if approval.policy_hash != policy.current_hash:
        return "the policy changed after approval was given"
    return None


def authorize(db: Session, agent: AgentClient, body) -> tuple[int, dict]:
    """Agent asks for a token. Re-evaluates from scratch; never trusts an earlier evaluate call."""
    settings = get_settings()
    user = db.get(User, agent.user_id)
    now = clock.utcnow()
    ttl = body.ttl_seconds or settings.token_default_ttl_seconds
    if ttl > settings.token_max_ttl_seconds:
        raise APIError(422, "TTL_TOO_LONG", f"ttl_seconds may not exceed {settings.token_max_ttl_seconds}")
    if body.max_uses > settings.token_max_uses_limit:
        raise APIError(422, "MAX_USES_TOO_HIGH", f"max_uses may not exceed {settings.token_max_uses_limit}")

    ev = evaluate(
        db,
        user,
        action=body.action,
        destination=body.destination,
        purpose=body.purpose,
        data_categories=list(body.data_categories),
        policy_source_id=body.policy_source_id,
    )
    scope = {
        "action": body.action,
        "destination": body.destination,
        "purpose": body.purpose,
        "data_categories": list(body.data_categories),
        "policy_source_id": body.policy_source_id,
    }
    audit_common = dict(user_id=user.id, actor_type="agent", actor_id=agent.id)

    approval_id = None
    if ev.decision == Decision.BLOCK or (ev.decision == Decision.REVIEW and not ev.approvable):
        audit_log.record(db, "guardian.authorize.denied", decision=ev.decision, details={**scope, "reasons": ev.reasons}, **audit_common)
        db.commit()
        return (403 if ev.decision == Decision.BLOCK else 409), {"decision": ev.decision, "evaluation": ev.as_dict()}

    if ev.decision == Decision.REVIEW:
        if body.approval_id is None:
            approval = _pending_or_new_approval(db, user, agent, body, ev, now)
            audit_log.record(
                db, "guardian.approval.requested", decision=Decision.REVIEW, target_type="approval", target_id=approval.id,
                details={**scope, "reasons": ev.reasons}, **audit_common,
            )
            db.commit()
            return 202, {"decision": Decision.REVIEW, "evaluation": ev.as_dict(), "approval_request_id": approval.id}
        approval = db.get(ApprovalRequest, body.approval_id)
        if approval is None or approval.user_id != user.id:
            raise not_found("approval")
        problem = _approval_covers(approval, agent, body, ev.policy, now)
        if problem:
            audit_log.record(
                db, "guardian.authorize.denied", decision=Decision.REVIEW, target_type="approval", target_id=approval.id,
                details={**scope, "reasons": [problem]}, **audit_common,
            )
            db.commit()
            return 409, {"decision": Decision.REVIEW, "evaluation": {**ev.as_dict(), "reasons": [problem] + ev.reasons}}
        approval.status = "USED"  # one approval yields exactly one token
        approval_id = approval.id

    expires_at = now + timedelta(seconds=ttl)
    rule_expiry = constitution.earliest_expiry(ev.rules, ev.engine.deciding_rule_ids)
    if rule_expiry is not None and rule_expiry < expires_at:
        expires_at = rule_expiry  # a token never outlives the rule that justified it
    if approval_id is not None:
        expires_at = min(expires_at, approval.expires_at)

    plaintext, token = tokens.issue(
        db,
        user_id=user.id,
        agent_id=agent.id,
        action=body.action,
        destination=body.destination,
        purpose=body.purpose,
        data_categories=list(body.data_categories),
        policy=ev.policy,
        constitution_version=user.constitution_version,
        issued_at=now,
        expires_at=expires_at,
        max_uses=body.max_uses,
        max_records=body.max_records,
        approval_id=approval_id,
    )
    audit_log.record(
        db, "token.issued", decision=Decision.ALLOW, target_type="token", target_id=token.id,
        details={**scope, "expires_at": expires_at.isoformat(), "max_uses": body.max_uses,
                 "max_records": body.max_records, "approval_id": approval_id,
                 "deciding_rule_ids": ev.engine.deciding_rule_ids},
        **audit_common,
    )
    db.commit()
    return 201, {"decision": Decision.ALLOW, "evaluation": ev.as_dict(), "token": plaintext, "token_info": token_out(token)}


def _pending_or_new_approval(db, user, agent, body, ev: Evaluation, now) -> ApprovalRequest:
    existing = db.execute(
        select(ApprovalRequest).where(
            ApprovalRequest.user_id == user.id,
            ApprovalRequest.agent_id == agent.id,
            ApprovalRequest.status == "PENDING",
            ApprovalRequest.action == body.action,
            ApprovalRequest.destination == body.destination,
            ApprovalRequest.purpose == body.purpose,
            ApprovalRequest.policy_source_id == body.policy_source_id,
            ApprovalRequest.policy_hash == ev.policy.current_hash,
        )
    ).scalars()
    for a in existing:
        if sorted(a.data_categories) == sorted(set(body.data_categories)) and a.expires_at > now:
            return a
    approval = ApprovalRequest(
        user_id=user.id,
        agent_id=agent.id,
        action=body.action,
        destination=body.destination,
        purpose=body.purpose,
        data_categories=sorted(set(body.data_categories)),
        policy_source_id=body.policy_source_id,
        policy_hash=ev.policy.current_hash,
        reason="; ".join(ev.reasons),
        expires_at=now + timedelta(minutes=get_settings().approval_ttl_minutes),
    )
    db.add(approval)
    db.flush()
    return approval


def token_out(t) -> dict:
    return {
        "id": t.id,
        "agent_id": t.agent_id,
        "action": t.action,
        "destination": t.destination,
        "purpose": t.purpose,
        "data_categories": t.data_categories,
        "policy_source_id": t.policy_source_id,
        "policy_hash": t.policy_hash,
        "issued_at": t.issued_at,
        "expires_at": t.expires_at,
        "max_uses": t.max_uses,
        "use_count": t.use_count,
        "max_records": t.max_records,
        "records_used": t.records_used,
        "revoked_at": t.revoked_at,
        "revocation_reason": t.revocation_reason,
        "approval_id": t.approval_id,
    }
