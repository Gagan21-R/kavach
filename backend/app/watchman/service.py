"""Watchman: versioned snapshots, change classification, and what a change means for this user's consent.

A material (or ambiguous) change bumps the policy's material version, which makes every token issued under an
earlier version stale at the gateway, and marks the policy as needing the user's reassessment. Nothing here
changes the user's rules or declares consent legally void: it says the earlier assessment no longer covers
the new wording and asks the user to decide.
"""
import hashlib

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import audit_log, clock
from app.court import service as court
from app.engine.hosts import host_matches
from app.models import ConsentRule, ConsentToken, PolicySnapshot, PolicySource, User, WatchEvent
from app.schemas.agents import AgentName, validate_agent_output
from app.watchman import diff
from app.watchman.fetch import fetch_policy

POLICY_TO_DATA = {"location": {"location"}, "contacts": {"contacts"}, "biometrics": {"biometrics"}}
POLICY_TO_PURPOSE = {
    "third_party_sharing": {"third_party_sharing"},
    "advertising": {"advertising", "marketing"},
    "ai_training": {"ai_training", "research"},
}


def content_hash(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def create_policy(db: Session, user: User, *, name: str, domain: str, text: str, url: str | None = None, locale: str | None = None) -> PolicySource:
    policy = PolicySource(user_id=user.id, name=name, url=url, domain=domain, locale=locale)
    db.add(policy)
    db.flush()
    snap = _add_snapshot(db, policy, text, classification=None)
    audit_log.record(db, "policy.snapshot.created", user_id=user.id, actor_type="user", actor_id=user.id,
                     target_type="policy", target_id=policy.id, details={"version": snap.version, "hash": snap.content_hash})
    court.analyze(db, policy, snap, actor_type="user", actor_id=user.id)
    return policy


def _add_snapshot(db: Session, policy: PolicySource, text: str, classification: str | None) -> PolicySnapshot:
    version = (db.execute(select(func.max(PolicySnapshot.version)).where(PolicySnapshot.source_id == policy.id)).scalar() or 0) + 1
    snap = PolicySnapshot(source_id=policy.id, user_id=policy.user_id, version=version, content_hash=content_hash(text),
                          text=text, classification=classification)
    db.add(snap)
    db.flush()
    policy.current_snapshot_id = snap.id
    policy.current_hash = snap.content_hash
    policy.current_version = version
    return snap


def affected_rules(db: Session, policy: PolicySource, categories: set[str]) -> list[ConsentRule]:
    data = set().union(*(POLICY_TO_DATA.get(c, set()) for c in categories)) if categories else set()
    purposes = set().union(*(POLICY_TO_PURPOSE.get(c, set()) for c in categories)) if categories else set()
    rules = db.execute(select(ConsentRule).where(ConsentRule.user_id == policy.user_id, ConsentRule.active.is_(True))).scalars()
    out = []
    for r in rules:
        names_domain = any(host_matches(p, policy.domain) or p.endswith("." + policy.domain) for p in r.recipients)
        applies_here = not r.recipients or names_domain  # a rule scoped to other recipients is not affected
        cats = set(r.data_categories)
        data_hit = applies_here and ("*" in cats or bool(data & cats))
        purpose_hit = applies_here and bool(purposes & set(r.purposes))
        if data_hit or purpose_hit or names_domain:
            out.append(r)
    return out


def recommendations(classification: str, categories: set[str]) -> list[dict]:
    if classification not in diff.MATERIAL:
        return [{"id": "none", "title": "No action required",
                 "detail": "The change does not alter any data practice we track. Your earlier approvals still apply."}]
    recs = [
        {"id": "review", "title": "Review the changed clauses",
         "detail": "Your earlier assessment was made against the old wording and does not cover the new text."},
        {"id": "suspend", "title": "Authorizations for this policy are paused",
         "detail": "Agent tokens issued under the previous version can no longer be used. New ones need your reassessment."},
    ]
    if categories & {"ai_training", "third_party_sharing", "advertising"}:
        recs.append({"id": "withdraw_consent", "title": "Withdraw consent or object",
                     "detail": "If you do not accept the new use, you can ask the company to stop. A draft email is ready to edit."})
        recs.append({"id": "access", "title": "Request a copy of your data",
                     "detail": "Find out what has already been collected and shared."})
    if categories & {"retention", "deletion", "biometrics", "location", "contacts"}:
        recs.append({"id": "deletion", "title": "Request deletion",
                     "detail": "Where the law gives you this right, ask the company to delete data it holds about you."})
    recs.append({"id": "settings", "title": "Check your privacy settings",
                 "detail": "The service may offer an opt-out for the new practice."})
    return recs


def record_snapshot(db: Session, policy: PolicySource, text: str, actor_type: str, actor_id: str | None) -> WatchEvent | None:
    """Stores a new version if the content changed and classifies the change. Returns None if identical."""
    if content_hash(text) == policy.current_hash:
        return None
    previous = db.get(PolicySnapshot, policy.current_snapshot_id)
    comparison = diff.compare(previous.text, text)
    classification = comparison["classification"]
    snap = _add_snapshot(db, policy, text, classification)
    categories = set().union(*(set(c["categories"]) for c in comparison["changes"]))

    output = {
        "meta": {"agent": "watchman", "agent_version": "1.0", "model": "offline-rules", "run_id": snap.id,
                 "policy_hash": previous.content_hash, "errors": []},
        "status": "CHANGED", "previous_hash": previous.content_hash, "new_hash": snap.content_hash,
        "changes": [{k: v for k, v in c.items() if k != "diff"} for c in comparison["changes"]],
    }
    validate_agent_output(AgentName.WATCHMAN, output)  # same contract as every other agent

    rules = affected_rules(db, policy, categories) if classification in diff.MATERIAL else []
    tokens = []
    if classification in diff.MATERIAL:
        policy.last_material_version = snap.version
        policy.requires_reassessment = True
        now = clock.utcnow()
        tokens = list(db.execute(select(ConsentToken.id).where(
            ConsentToken.policy_source_id == policy.id, ConsentToken.revoked_at.is_(None), ConsentToken.expires_at > now,
            ConsentToken.use_count < ConsentToken.max_uses,  # only tokens that could still be used are "paused"
        )).scalars())
    ev = WatchEvent(
        user_id=policy.user_id, source_id=policy.id, status="CHANGED", classification=classification,
        from_version=previous.version, to_version=snap.version,
        output={**output, "changes": comparison["changes"], "confidence": comparison["confidence"]},
        affected_rule_ids=[r.id for r in rules], affected_token_ids=tokens,
        recommendations=recommendations(classification, categories),
    )
    db.add(ev)
    policy.watch_status, policy.watch_error, policy.last_checked_at = "OK", None, clock.utcnow()
    audit_log.record(db, "policy.snapshot.created", user_id=policy.user_id, actor_type=actor_type, actor_id=actor_id,
                     target_type="policy", target_id=policy.id,
                     details={"version": snap.version, "hash": snap.content_hash, "previous_hash": previous.content_hash,
                              "classification": classification})
    if classification in diff.MATERIAL:
        audit_log.record(db, "consent.review.required", user_id=policy.user_id, actor_type="system",
                         target_type="policy", target_id=policy.id, decision="REVIEW",
                         details={"classification": classification, "categories": sorted(categories),
                                  "affected_rule_ids": [r.id for r in rules], "suspended_token_count": len(tokens),
                                  "reason": "the policy changed in a way your earlier assessment does not cover"})
    db.flush()
    court.analyze(db, policy, snap, actor_type="system")
    return ev


def check_source(db: Session, policy: PolicySource, actor_type: str = "system", actor_id: str | None = None, fetcher=fetch_policy) -> WatchEvent:
    """Fetch the policy URL and compare. A failed fetch is UNKNOWN, never UNCHANGED."""
    now = clock.utcnow()
    policy.last_checked_at = now
    if not policy.url:
        result_ok, error = False, "this policy has no URL to check; paste a new version instead"
        res = None
    else:
        res = fetcher(policy.url)
        result_ok, error = res.ok, res.error
    if not result_ok:
        policy.watch_status, policy.watch_error = "UNKNOWN", error
        ev = WatchEvent(user_id=policy.user_id, source_id=policy.id, status="UNKNOWN", from_version=policy.current_version,
                        error=error, recommendations=[{"id": "retry", "title": "Status unknown",
                                                        "detail": "We could not retrieve the policy, so we cannot say it is unchanged. New authorizations need your approval until a check succeeds."}])
        db.add(ev)
        audit_log.record(db, "policy.watch.unknown", user_id=policy.user_id, actor_type=actor_type, actor_id=actor_id,
                         target_type="policy", target_id=policy.id, details={"error": error})
        db.flush()
        return ev
    changed = record_snapshot(db, policy, res.text, actor_type, actor_id)
    if changed is not None:
        return changed
    policy.watch_status, policy.watch_error = "OK", None
    ev = WatchEvent(user_id=policy.user_id, source_id=policy.id, status="NO_CHANGE", from_version=policy.current_version,
                    to_version=policy.current_version, recommendations=recommendations("NO_CHANGE", set()))
    db.add(ev)
    db.flush()
    return ev
