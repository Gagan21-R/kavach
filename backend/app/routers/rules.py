"""Personal Consent Constitution.

Step-up policy: changes that LOOSEN protection need recent re-authentication (creating ALLOW rules, editing any
rule, removing DENY / REQUIRE_APPROVAL rules). Changes that only TIGHTEN (adding DENY or REQUIRE_APPROVAL,
removing an ALLOW) never do, so a user can always lock things down quickly.
"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import audit_log, clock
from app.auth.deps import UserContext, current_user, require_step_up
from app.db import get_db
from app.engine import constitution
from app.errors import APIError, not_found
from app.models import ConsentRule, User
from app.schemas.api import ActionIn, RuleIn, RuleOut
from app.vocab import RuleEffect

router = APIRouter(prefix="/consent", tags=["consent"])


def _owned_rule(db: Session, user_id: str, rule_id: str) -> ConsentRule:
    rule = db.get(ConsentRule, rule_id)
    if rule is None or rule.user_id != user_id:
        raise not_found("rule")
    return rule


def _bump(user: User) -> int:
    user.constitution_version += 1
    return user.constitution_version


def _new_rule(user: User, body: RuleIn, supersedes_id: str | None = None) -> ConsentRule:
    return ConsentRule(
        user_id=user.id,
        effect=body.effect,
        data_categories=sorted(set(body.data_categories)),
        purposes=sorted(set(body.purposes)),
        recipients=sorted(set(body.recipients)),
        actions=sorted(set(body.actions)),
        description=body.description,
        expires_at=body.expires_at,
        supersedes_id=supersedes_id,
        constitution_version=_bump(user),
    )


def _rule_details(rule: ConsentRule) -> dict:
    return {
        "effect": rule.effect,
        "data_categories": rule.data_categories,
        "purposes": rule.purposes,
        "recipients": rule.recipients,
        "actions": rule.actions,
        "expires_at": rule.expires_at.isoformat() if rule.expires_at else None,
        "constitution_version": rule.constitution_version,
    }


@router.get("/rules", response_model=list[RuleOut])
def list_rules(
    include_inactive: bool = Query(False),
    ctx: UserContext = Depends(current_user),
    db: Session = Depends(get_db),
):
    q = select(ConsentRule).where(ConsentRule.user_id == ctx.user.id)
    if not include_inactive:
        q = q.where(ConsentRule.active.is_(True))
    return list(db.execute(q.order_by(ConsentRule.created_at)).scalars())


@router.post("/rules", status_code=201, response_model=RuleOut)
def create_rule(body: RuleIn, ctx: UserContext = Depends(current_user), db: Session = Depends(get_db)):
    if body.effect == RuleEffect.ALLOW:
        require_step_up(ctx)
    if body.expires_at is not None and body.expires_at <= clock.utcnow():
        raise APIError(422, "ALREADY_EXPIRED", "expires_at is in the past")
    rule = _new_rule(ctx.user, body)
    db.add(rule)
    db.flush()
    audit_log.record(db, "consent.rule.created", user_id=ctx.user.id, actor_type="user", actor_id=ctx.user.id,
                     target_type="rule", target_id=rule.id, details=_rule_details(rule))
    db.commit()
    return rule


@router.put("/rules/{rule_id}", response_model=RuleOut)
def replace_rule(rule_id: str, body: RuleIn, ctx: UserContext = Depends(current_user), db: Session = Depends(get_db)):
    """Edits are new versions: the old rule is deactivated and kept for history."""
    old = _owned_rule(db, ctx.user.id, rule_id)
    if not old.active:
        raise APIError(409, "RULE_INACTIVE", "only active rules can be edited")
    require_step_up(ctx)
    now = clock.utcnow()
    old.active = False
    old.revoked_at = now
    rule = _new_rule(ctx.user, body, supersedes_id=old.id)
    db.add(rule)
    db.flush()
    audit_log.record(db, "consent.rule.replaced", user_id=ctx.user.id, actor_type="user", actor_id=ctx.user.id,
                     target_type="rule", target_id=rule.id, details={"supersedes": old.id, **_rule_details(rule)})
    db.commit()
    return rule


@router.delete("/rules/{rule_id}", response_model=RuleOut)
def revoke_rule(rule_id: str, ctx: UserContext = Depends(current_user), db: Session = Depends(get_db)):
    rule = _owned_rule(db, ctx.user.id, rule_id)
    if not rule.active:
        raise APIError(409, "RULE_INACTIVE", "rule is already inactive")
    if rule.effect != RuleEffect.ALLOW:
        require_step_up(ctx)  # removing a prohibition loosens protection
    rule.active = False
    rule.revoked_at = clock.utcnow()
    _bump(ctx.user)
    audit_log.record(db, "consent.rule.revoked", user_id=ctx.user.id, actor_type="user", actor_id=ctx.user.id,
                     target_type="rule", target_id=rule.id, details=_rule_details(rule))
    db.commit()
    return rule


@router.get("/rules/{rule_id}/history", response_model=list[RuleOut])
def rule_history(rule_id: str, ctx: UserContext = Depends(current_user), db: Session = Depends(get_db)):
    """The rule and every earlier version it superseded, newest first."""
    chain = []
    rule = _owned_rule(db, ctx.user.id, rule_id)
    while rule is not None and len(chain) < 100:
        chain.append(rule)
        rule = _owned_rule(db, ctx.user.id, rule.supersedes_id) if rule.supersedes_id else None
    return chain


@router.post("/check")
def check_action(body: ActionIn, ctx: UserContext = Depends(current_user), db: Session = Depends(get_db)):
    """Dry run: what would the user's rules alone say about this action? Issues nothing."""
    rules = db.execute(
        select(ConsentRule).where(ConsentRule.user_id == ctx.user.id, ConsentRule.active.is_(True))
    ).scalars()
    result = constitution.evaluate(
        list(rules),
        constitution.ActionRequest(body.action, body.destination, body.purpose, tuple(body.data_categories)),
        clock.utcnow(),
    )
    return {
        "decision": result.decision,
        "approvable": result.approvable,
        "reasons": result.reasons,
        "outcomes": [o.__dict__ for o in result.outcomes],
        "deciding_rule_ids": result.deciding_rule_ids,
        "constitution_version": ctx.user.constitution_version,
    }
