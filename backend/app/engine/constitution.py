"""Deterministic evaluation of a proposed action against a user's Personal Consent Constitution.

No model is involved. Precedence, per data category:
  1. any matching DENY              -> BLOCK
  2. any matching REQUIRE_APPROVAL  -> REVIEW (approvable)
  3. any matching ALLOW             -> ALLOW
  4. no matching rule               -> REVIEW (approvable); nothing is allowed by default
The overall decision is the most restrictive category outcome. A DENY always wins, even over a more
specific ALLOW, so a prohibition can never be bypassed by adding a narrower permission.
"""
from dataclasses import dataclass, field
from datetime import datetime
from typing import Iterable, Protocol

from app.engine.hosts import host_matches
from app.vocab import SENSITIVE_CATEGORIES, Decision, RuleEffect

WILDCARD = "*"


class RuleLike(Protocol):
    id: str
    effect: str
    data_categories: list
    purposes: list
    recipients: list
    actions: list
    expires_at: datetime | None
    active: bool


@dataclass(frozen=True)
class ActionRequest:
    action: str
    destination: str
    purpose: str
    data_categories: tuple[str, ...]


@dataclass
class CategoryOutcome:
    category: str
    decision: Decision
    sensitive: bool
    matched_rule_ids: list[str]
    deciding_rule_ids: list[str]
    reason: str


@dataclass
class EngineResult:
    decision: Decision
    approvable: bool
    outcomes: list[CategoryOutcome] = field(default_factory=list)
    reasons: list[str] = field(default_factory=list)

    @property
    def deciding_rule_ids(self) -> list[str]:
        ids: list[str] = []
        for o in self.outcomes:
            ids.extend(i for i in o.deciding_rule_ids if i not in ids)
        return ids


def _matches(rule: RuleLike, req: ActionRequest, category: str) -> bool:
    cats = rule.data_categories or []
    if WILDCARD not in cats and category not in cats:
        return False
    if rule.purposes and WILDCARD not in rule.purposes and req.purpose not in rule.purposes:
        return False
    if rule.actions and WILDCARD not in rule.actions and req.action not in rule.actions:
        return False
    if rule.recipients and not any(host_matches(p, req.destination) for p in rule.recipients):
        return False
    return True


def _usable(rule: RuleLike, now: datetime) -> bool:
    return rule.active and (rule.expires_at is None or rule.expires_at > now)


def evaluate(rules: Iterable[RuleLike], req: ActionRequest, now: datetime, deny_unlisted: str | None = None) -> EngineResult:
    """`deny_unlisted` names a rule group: within a group, anything the user didn't allow or mark "ask me" is denied
    (instead of needing approval, as it does under the general rules)."""
    missing = [
        name
        for name, value in (
            ("action", req.action),
            ("destination", req.destination),
            ("purpose", req.purpose),
            ("data_categories", req.data_categories),
        )
        if not value
    ]
    if missing:
        return EngineResult(
            decision=Decision.REVIEW,
            approvable=False,
            reasons=[f"request is missing essential information: {', '.join(missing)}"],
        )

    usable = [r for r in rules if _usable(r, now)]
    outcomes: list[CategoryOutcome] = []
    for category in dict.fromkeys(req.data_categories):
        matched = [r for r in usable if _matches(r, req, category)]
        by_effect = {e: [r.id for r in matched if r.effect == e] for e in RuleEffect}
        sensitive = category in {c.value for c in SENSITIVE_CATEGORIES}
        if by_effect[RuleEffect.DENY]:
            decision, deciding = Decision.BLOCK, by_effect[RuleEffect.DENY]
            reason = f"'{category}' is prohibited for purpose '{req.purpose}' to {req.destination} by your rule"
        elif by_effect[RuleEffect.REQUIRE_APPROVAL]:
            decision, deciding = Decision.REVIEW, by_effect[RuleEffect.REQUIRE_APPROVAL]
            reason = f"your rule requires explicit approval to share '{category}' for '{req.purpose}'"
        elif by_effect[RuleEffect.ALLOW]:
            decision, deciding = Decision.ALLOW, by_effect[RuleEffect.ALLOW]
            reason = f"'{category}' for '{req.purpose}' to {req.destination} is allowed by your rule"
        elif deny_unlisted is not None:
            decision, deciding = Decision.BLOCK, []
            reason = (f"'{category}' for '{req.purpose}' isn't something you allowed for the {deny_unlisted} group, "
                      "so it is denied")
        else:
            decision, deciding = Decision.REVIEW, []
            reason = (
                f"no rule covers '{category}' for '{req.purpose}' to {req.destination}"
                + ("; it is a sensitive category" if sensitive else "")
                + ", so your approval is needed"
            )
        outcomes.append(
            CategoryOutcome(
                category=category,
                decision=decision,
                sensitive=sensitive,
                matched_rule_ids=[r.id for r in matched],
                deciding_rule_ids=deciding,
                reason=reason,
            )
        )

    if any(o.decision == Decision.BLOCK for o in outcomes):
        overall = Decision.BLOCK
    elif any(o.decision == Decision.REVIEW for o in outcomes):
        overall = Decision.REVIEW
    else:
        overall = Decision.ALLOW
    reasons = [o.reason for o in outcomes if o.decision == overall]
    return EngineResult(decision=overall, approvable=overall == Decision.REVIEW, outcomes=outcomes, reasons=reasons)


def earliest_expiry(rules: Iterable[RuleLike], rule_ids: Iterable[str]) -> datetime | None:
    ids = set(rule_ids)
    expiries = [r.expires_at for r in rules if r.id in ids and r.expires_at is not None]
    return min(expiries) if expiries else None
