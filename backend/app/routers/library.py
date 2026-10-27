"""Policy library: real T&Cs and privacy policies of popular platforms, or of any website by its domain,
fetched server-side and put on trial."""
from fastapi import APIRouter, Depends
from pydantic import Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.acquire import discover as disc
from app.acquire import service as acq
from app.acquire.catalogue import BY_ID, SERVICES, service_for_domain
from app.acquire.tracking import LABEL, site_domain, track_service, track_url
from app.auth.deps import UserContext, current_user
from app.config import get_settings
from app.db import get_db
from app.errors import APIError, not_found
from app.models import AnalysisRun, PolicySource
from app.routers.policies import _analysis_out, policy_summary
from app.schemas.api import Strict

router = APIRouter(prefix="/library", tags=["library"])


def _result(db: Session, policy: PolicySource, got: acq.Acquired) -> dict:
    return {"policy": policy_summary(db, policy), "analysis": _analysis_out(db.get(AnalysisRun, policy.current_analysis_id)),
            "acquisition": {"method": got.method, "method_label": acq.METHOD_LABELS.get(got.method, got.method),
                            "source_url": got.source_url, "characters": len(got.text), "attempts": got.attempts}}


@router.get("")
def catalogue(ctx: UserContext = Depends(current_user), db: Session = Depends(get_db)):
    tracked = {p.url: p for p in db.execute(select(PolicySource).where(PolicySource.user_id == ctx.user.id)).scalars() if p.url}
    out = []
    for s in SERVICES:
        docs = []
        for d in s["docs"]:
            p = tracked.get(d["url"])
            docs.append({"kind": d["kind"], "label": LABEL[d["kind"]], "url": d["url"], "has_fallback": bool(d["ota"]),
                         "tracked": None if p is None else policy_summary(db, p)})
        out.append({"id": s["id"], "name": s["name"], "domain": s["domain"], "region": s["region"], "docs": docs})
    catalogue_urls = {d["url"] for s in SERVICES for d in s["docs"]}
    others = [policy_summary(db, p) for p in tracked.values() if p.url not in catalogue_urls]
    return {"services": out, "other_sites": others, "contact": get_settings().fetch_contact}


@router.post("/{service_id}/{kind}/track", status_code=201)
def track(service_id: str, kind: str, ctx: UserContext = Depends(current_user), db: Session = Depends(get_db)):
    svc = BY_ID.get(service_id)
    if svc is None or not any(d["kind"] == kind for d in svc["docs"]):
        raise not_found("catalogue document")
    policy, got = track_service(db, ctx.user, service_id, kind)
    db.commit()
    if policy is None:
        raise APIError(502, "ACQUISITION_FAILED", f"We couldn't get this document: {got.error}")
    return _result(db, policy, got)


class DomainIn(Strict):
    domain: str = Field(min_length=3, max_length=300)


@router.post("/discover")
def discover(body: DomainIn, ctx: UserContext = Depends(current_user)):
    """Finds a website's privacy policy and terms from its domain (reads the home page footer)."""
    domain = disc.normalize_domain(body.domain)
    if domain is None:
        raise APIError(422, "INVALID_DOMAIN", "enter a website like example.com")
    svc = service_for_domain(domain)
    found = disc.discover(domain)
    return {**found, "catalogue_id": svc["id"] if svc else None}


class SiteTrackIn(Strict):
    domain: str = Field(min_length=3, max_length=300)
    url: str = Field(min_length=8, max_length=2048)
    kind: str = Field(pattern="^(privacy|terms)$")


@router.post("/site/track", status_code=201)
def track_site(body: SiteTrackIn, ctx: UserContext = Depends(current_user), db: Session = Depends(get_db)):
    domain = disc.normalize_domain(body.domain)
    if domain is None or not body.url.lower().startswith(("http://", "https://")):
        raise APIError(422, "INVALID_SITE", "enter a website like example.com and an http(s) address")
    policy, got = track_url(db, ctx.user, name=f"{site_domain(domain)} {LABEL[body.kind]}", domain=domain, url=body.url)
    db.commit()
    if policy is None:
        raise APIError(502, "ACQUISITION_FAILED", f"We couldn't get this document: {got.error}")
    return _result(db, policy, got)
