"""Acting on a "we're updating our terms" email that reached Kavach's monitoring inbox.

1. Re-check the policy on the site (cheaply, with ETag / Last-Modified). If the site already shows a new version,
   Watchman records it as usual.
2. If the site still shows the old version, or won't let a bot read it, Kavach builds the new version from the email:
   the current policy plus the changes the company announced. Watchman then compares, classifies and, if material,
   pauses old authorizations and asks the user to review, exactly as for a change found on the site.

An email is a claim by its sender. Kavach notes whether the sender was verified (DKIM / DMARC) and keeps the
announced text clearly labelled as coming from email. Emails that don't announce a policy change are dropped.
"""
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import audit_log
from app.acquire.catalogue import service_for_domain
from app.acquire.tracking import site_domain
from app.inbox.parse import ParsedEmail
from app.models import EmailSignal, PolicySnapshot, PolicySource, User
from app.watchman import service as watchman

MIN_CHANGES = 80  # characters of announced change needed to build a version from an email


def policies_for(db: Session, user_id: str, site: str, svc: dict | None) -> list[PolicySource]:
    names = {site} | ({svc["domain"], *svc.get("aliases", [])} if svc else set())
    rows = db.execute(select(PolicySource).where(PolicySource.user_id == user_id)).scalars()
    return [p for p in rows if site_domain(p.domain) in names or p.domain in names]


def _target(policies: list[PolicySource], parsed: ParsedEmail) -> list[PolicySource]:
    """The documents the email is about: terms if it says terms, privacy policy if it says privacy, else all."""
    text = f"{parsed.subject} {' '.join(parsed.matched_phrases)}".lower()
    terms = any(w in text for w in ("terms", "agreement", "conditions"))
    privacy = any(w in text for w in ("privacy", "data policy"))
    picked = [p for p in policies if (terms and "terms" in p.name.lower()) or (privacy and "privacy" in p.name.lower())]
    return picked or policies


def email_version(current: str, parsed: ParsedEmail) -> str:
    when = parsed.effective_date or parsed.date or "a date not stated"
    return (f"{current}\n\nAnnounced changes (from an email by {parsed.from_address}, “{parsed.subject}”, effective {when}):\n"
            f"{parsed.changes}")


def apply_to_policy(db: Session, policy: PolicySource, parsed: ParsedEmail) -> dict:
    if policy.url:
        ev = watchman.check_source(db, policy, "system")
        if ev.status == "CHANGED":
            return {"kind": "site_changed", "policy_id": policy.id, "status": "CHANGED", "classification": ev.classification,
                    "detail": f"{policy.name}: the site already shows a new version ({ev.classification.replace('_', ' ').lower()})"}
        site_note = "the site still shows the old version" if ev.status == "NO_CHANGE" else "the site couldn't be read"
    else:
        site_note = "this policy has no address to re-check"
    if len(parsed.changes) < MIN_CHANGES:
        return {"kind": "rechecked", "policy_id": policy.id, "status": "NO_CHANGE",
                "detail": f"{policy.name}: {site_note}, and the email doesn't describe the changes, so there's no new version yet"}
    current = db.get(PolicySnapshot, policy.current_snapshot_id)
    ev = None if parsed.changes in current.text else watchman.record_snapshot(db, policy, email_version(current.text, parsed), "system", None)
    if ev is None:
        return {"kind": "already_recorded", "policy_id": policy.id, "status": "NO_CHANGE",
                "detail": f"{policy.name}: this announcement is already recorded"}
    ev.output = {**ev.output, "source": "EMAIL", "checked_by": f"Built from the email because {site_note}"}
    return {"kind": "email_version", "policy_id": policy.id, "status": "CHANGED", "classification": ev.classification,
            "detail": f"{policy.name}: {site_note}, so Kavach built version {ev.to_version} from the email "
                      f"({ev.classification.replace('_', ' ').lower()})"}


def handle(db: Session, parsed: ParsedEmail, channel: str, user: User | None = None) -> list[EmailSignal]:
    """user=None: Kavach's own monitoring mailbox, applied for every user tracking the sender's site."""
    if not parsed.is_policy_update or not parsed.from_domain:
        return []
    site = site_domain(parsed.from_domain)
    svc = service_for_domain(site)
    if user is not None:
        users = [user]
    else:
        owners = db.execute(select(PolicySource.user_id).distinct()).scalars()
        users = [u for u in (db.get(User, uid) for uid in owners) if policies_for(db, u.id, site, svc)]
    signals = []
    for u in users or [None]:
        actions = []
        if u is not None and not u.frozen:
            policies = policies_for(db, u.id, site, svc)
            if not policies:
                actions.append({"kind": "not_tracked", "status": None,
                                "detail": f"You don't track {svc['name'] if svc else site} yet, so there was nothing to update"})
            for p in _target(policies, parsed):
                actions.append(apply_to_policy(db, p, parsed))
        sig = EmailSignal(user_id=u.id if u else None, channel=channel, from_address=parsed.from_address, from_domain=parsed.from_domain,
                          subject=parsed.subject, service_name=svc["name"] if svc else site, is_policy_update=True,
                          authenticated=parsed.authenticated,
                          matched_phrases=parsed.matched_phrases + ([f"effective {parsed.effective_date}"] if parsed.effective_date else []),
                          links=parsed.links, actions=actions)
        db.add(sig)
        db.flush()
        if u is not None:
            from app.notifications import notify

            # A real change already raises a "policy changed" notification; only announce emails that didn't change anything.
            if not any(a.get("status") == "CHANGED" for a in actions):
                notify(db, u.id, "email_update", f"{svc['name'] if svc else site} emailed about a policy update",
                       "; ".join(a["detail"] for a in actions)[:400] or parsed.subject,
                       tone="info", section="watchman", ref_id=f"email:{site}")
            audit_log.record(db, "email.policy_update", user_id=u.id, actor_type="system", target_type="email", target_id=sig.id,
                             details={"from_domain": parsed.from_domain, "channel": channel, "authenticated": parsed.authenticated,
                                      "actions": [a["kind"] for a in actions]})
        signals.append(sig)
    return signals
