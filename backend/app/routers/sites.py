"""Websites: check any site (one combined review of its privacy policy and terms), track it, and list the sites the
user has checked or tracked, from the dashboard or the browser extension."""
from fastapi import APIRouter, Depends
from pydantic import Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import audit_log, clock
from app.acquire import discover as disc
from app.acquire.catalogue import SERVICES, service_for_domain
from app.acquire.tracking import site_domain
from app.auth.deps import UserContext, current_user
from app.db import get_db
from app.errors import APIError
from app.models import ExtensionClient, PolicySource, SiteVisit, User
from app.review import review, track_site, tracked_summary
from app.schemas.api import Strict

router = APIRouter(prefix="/sites", tags=["sites"])


class DomainIn(Strict):
    domain: str = Field(min_length=3, max_length=2048)


class TrackIn(Strict):
    domain: str = Field(min_length=3, max_length=2048)
    group_id: str | None = Field(default=None, max_length=32)  # optional: also put the site in this rule group


def site_of(raw: str) -> str:
    host = disc.normalize_domain(raw)
    if host is None:
        raise APIError(422, "INVALID_DOMAIN", "enter a website like spotify.com")
    return site_domain(host)


def remember(db: Session, user: User, site: str, result: dict, via: str) -> SiteVisit:
    """Keep the latest review on the user's list of websites. A risky review found by the extension (not one the user
    asked for here) becomes a notification."""
    if via == "extension" and result.get("status") in ("CONFLICT", "CAUTION") and result.get("recommendation"):
        from app.notifications import notify

        conflict = result["status"] == "CONFLICT"
        notify(db, user.id, "site_review", f"{result.get('name') or site}: {'goes against your rules' if conflict else 'worth a look'}",
               (result.get("reasons") or [""])[0], tone="bad" if conflict else "warn", section="websites", ref_id=f"{site}:{result.get('risk_score')}")
    v = db.execute(select(SiteVisit).where(SiteVisit.user_id == user.id, SiteVisit.domain == site).order_by(SiteVisit.first_seen_at)).scalars().first()
    now = clock.utcnow()
    if v is None:
        v = SiteVisit(user_id=user.id, domain=site, first_seen_at=now, visit_count=0)
        db.add(v)
    v.last_seen_at, v.visit_count = now, (v.visit_count or 0) + 1
    v.status = "TRACKED" if result.get("tracked") else ("CHECKED" if result.get("recommendation") else "NOT_FOUND")
    v.verdict, v.note = result, via
    db.flush()
    return v


@router.post("/review")
def review_site(body: DomainIn, ctx: UserContext = Depends(current_user), db: Session = Depends(get_db)):
    site = site_of(body.domain)
    result = review(db, ctx.user, site)
    remember(db, ctx.user, site, result, "dashboard")
    db.commit()
    return result


@router.post("/track", status_code=201)
def track(body: TrackIn, ctx: UserContext = Depends(current_user), db: Session = Depends(get_db)):
    site = site_of(body.domain)
    if body.group_id:
        from app.auth.deps import require_step_up
        from app.routers.groups import assign

        require_step_up(ctx)
        assign(db, ctx.user, site, body.group_id)
    tracked = track_site(db, ctx.user, site)
    if not tracked:
        db.commit()
        raise APIError(502, "NOTHING_TO_TRACK", "We couldn't get any policy for this site, so there is nothing to watch yet")
    audit_log.record(db, "site.tracked", user_id=ctx.user.id, actor_type="user", actor_id=ctx.user.id,
                     target_type="site", target_id=site, details={"policies": [p.id for p in tracked]})
    result = review(db, ctx.user, site)
    remember(db, ctx.user, site, result, "dashboard")
    db.commit()
    return result


def _brief(v: dict) -> dict:
    return {k: v.get(k) for k in ("status", "reasons", "recommendation", "recommendation_words", "risk_score", "confidence",
                                   "headline", "factors", "audit")}


@router.get("")
def list_sites(ctx: UserContext = Depends(current_user), db: Session = Depends(get_db)):
    uid = ctx.user.id
    policies = list(db.execute(select(PolicySource).where(PolicySource.user_id == uid).order_by(PolicySource.created_at)).scalars())
    by_site: dict[str, list[PolicySource]] = {}
    for p in policies:
        by_site.setdefault(site_domain(p.domain), []).append(p)
    visits = {v.domain: v for v in db.execute(select(SiteVisit).where(SiteVisit.user_id == uid)).scalars()}
    out = []
    for site, ps in by_site.items():
        svc = service_for_domain(site)
        out.append({"domain": site, "name": svc["name"] if svc else site, "tracked": True, **_brief(tracked_summary(db, ctx.user, site, ps)),
                    "documents": [{"id": p.id, "name": p.name, "url": p.url, "version": p.current_version,
                                   "changed": p.requires_reassessment, "watch_status": p.watch_status,
                                   "last_checked_at": p.last_checked_at} for p in ps],
                    "changes_pending": any(p.requires_reassessment for p in ps),
                    "last_seen_at": visits[site].last_seen_at if site in visits else ps[-1].created_at,
                    "via": visits[site].note if site in visits else "dashboard", "looking": False})
    for site, v in visits.items():
        if site not in by_site:
            out.append({"domain": site, "name": (v.verdict or {}).get("name", site), "tracked": False, **_brief(v.verdict or {}),
                        "documents": [], "changes_pending": False, "last_seen_at": v.last_seen_at, "via": v.note or "extension",
                        "looking": v.status == "LOOKING"})
    from app.engine.scope import group_for

    for s in out:
        g = group_for(db, uid, s["domain"])
        s["group"] = {"id": g.id, "name": g.name} if g else None
    out.sort(key=lambda s: s["last_seen_at"], reverse=True)
    clients = list(db.execute(select(ExtensionClient).where(ExtensionClient.user_id == uid, ExtensionClient.active.is_(True))).scalars())
    seen = max((c.last_seen_at for c in clients if c.last_seen_at), default=None)
    return {"sites": out,
            "popular": [{"id": s["id"], "name": s["name"], "domain": s["domain"], "region": s["region"]} for s in SERVICES],
            "extension": {"connected": bool(clients), "last_seen_at": seen}}


class TrialIn(Strict):
    name: str = Field(default="This policy", min_length=1, max_length=120)
    text: str = Field(min_length=20, max_length=200_000)


@router.post("/trial")
def trial_text(body: TrialIn, ctx: UserContext = Depends(current_user), db: Session = Depends(get_db)):
    """Courtroom: put any pasted policy text through the six agents. Nothing is tracked or stored."""
    from app.acquire.service import MAX_TEXT
    from app.court.report import summarize, trial
    from app.preferences import site_verdict
    from app.review import REC_WORDS, how_decided

    result = trial(body.text[:MAX_TEXT], body.name)
    report = summarize(result)
    prefs = site_verdict([r for r in _general_rules(db, ctx.user.id)], result, "example.invalid", clock.utcnow())
    return {**report, "name": body.name, "status": prefs["status"], "reasons": prefs["reasons"],
            "recommendation_words": REC_WORDS.get(report["recommendation"]), "how_decided": how_decided(result),
            "transcript": result.get("transcript", []), "audit": report.get("audit_verdict")}


def _general_rules(db: Session, user_id: str):
    from app.models import ConsentRule

    return db.execute(select(ConsentRule).where(ConsentRule.user_id == user_id, ConsentRule.active.is_(True),
                                                ConsentRule.group_id.is_(None))).scalars()
