"""Turning a fetched policy into a tracked, analysed policy for one user. Shared by the Library, first-run
preferences, the browser extension and email signals."""
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import audit_log
from app.acquire import service as acq
from app.acquire.catalogue import BY_ID, ota_for
from app.models import PolicySource, User
from app.watchman import service as watchman

LABEL = {"privacy": "Privacy Policy", "terms": "Terms of Service"}
_SUFFIX2 = {"co.in", "org.in", "net.in", "gov.in", "ac.in", "co.uk", "org.uk", "ac.uk", "com.au", "co.jp", "com.br", "co.nz", "com.sg"}


def site_domain(host: str) -> str:
    """Registrable part of a host: accounts.google.com -> google.com, www.amazon.co.in -> amazon.co.in."""
    parts = host.lower().rstrip(".").split(".")
    n = 3 if ".".join(parts[-2:]) in _SUFFIX2 else 2
    return ".".join(parts[-n:])


def tracked_for_domain(db: Session, user_id: str, domain: str) -> PolicySource | None:
    """The user's policy for this site, preferring the privacy policy, matching subdomains and catalogue aliases."""
    from app.acquire.catalogue import service_for_domain

    svc = service_for_domain(domain)
    names = {domain} | ({svc["domain"], *svc.get("aliases", [])} if svc else set())
    rows = list(db.execute(select(PolicySource).where(PolicySource.user_id == user_id)).scalars())
    hits = [p for p in rows if any(p.domain == n or p.domain.endswith("." + n) or site_domain(p.domain) == n for n in names)]
    hits.sort(key=lambda p: (0 if "privacy" in p.name.lower() else 1, p.created_at))
    return hits[0] if hits else None


def track_url(db: Session, user: User, *, name: str, domain: str, url: str, ota=None, actor: str = "user", fetcher=None):
    """Returns (policy or None, Acquired). Reuses the user's existing policy for the same URL."""
    existing = db.execute(select(PolicySource).where(PolicySource.user_id == user.id, PolicySource.url == url)).scalar_one_or_none()
    if existing is not None:
        return existing, acq.Acquired(True, method="ALREADY_TRACKED", source_url=url)
    got = acq.acquire_cached(db, url, ota if ota is not None else ota_for(url), fetcher=fetcher)
    if not got.ok:
        audit_log.record(db, "policy.acquire.failed", user_id=user.id, actor_type=actor, actor_id=user.id if actor == "user" else None,
                         target_type="url", target_id=url[:120], details={"attempts": got.attempts})
        return None, got
    policy = watchman.create_policy(db, user, name=name, domain=domain, text=got.text, url=url, locale="en")
    audit_log.record(db, "policy.acquired", user_id=user.id, actor_type=actor, actor_id=user.id if actor == "user" else None,
                     target_type="policy", target_id=policy.id,
                     details={"method": got.method, "source_url": got.source_url, "characters": len(got.text), "attempts": got.attempts})
    return policy, got


def track_service(db: Session, user: User, service_id: str, kind: str = "privacy", actor: str = "user", fetcher=None):
    svc = BY_ID[service_id]
    doc = next((d for d in svc["docs"] if d["kind"] == kind), svc["docs"][0])
    return track_url(db, user, name=f"{svc['name']} {LABEL[doc['kind']]}", domain=svc["domain"], url=doc["url"],
                     ota=doc["ota"], actor=actor, fetcher=fetcher)
