"""Browser extension: connecting it to the account, the sites the user visits, policy pages they read, and consent
moments (signup and "I agree" pages).

Connecting needs no key typed by the user: when the user is signed in to the dashboard in the same browser, the
extension asks the dashboard page to create its connection (POST /extension/pair with the session and CSRF token).

Privacy: on an ordinary visit the extension sends only the site's domain. On a privacy policy or terms page it sends
that page's address and text, which is what the user is reading. On a signup page it sends the consent text near
the form so the Sentinel can check it for instructions aimed at AI agents; that text is checked and not stored.
"""
import logging
from datetime import timedelta

from fastapi import APIRouter, BackgroundTasks, Depends, Request
from pydantic import Field
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app import audit_log, clock
from app.acquire import discover as disc
from app.acquire.tracking import site_domain
from app.auth.crypto import constant_time_equal, make_compound_secret, sha256, split_compound_secret
from app.auth.deps import UserContext, current_user
from app.court import lexicon as lx
from app.db import get_db
from app.errors import APIError, not_found
from app.models import ExtensionClient, PolicySource, SiteVisit, User
from app.models._common import new_id
from app.review import review, track_site, tracked_summary
from app.routers.sites import remember
from app.schemas.api import Strict

router = APIRouter(tags=["extension"])
log = logging.getLogger("consent_court.extension")
_inflight: set[str] = set()  # sites being looked up right now, so repeat visits don't start a second lookup
FRESH = timedelta(hours=6)


# --- Managed from the dashboard (session auth) -------------------------------------------------------------

def _client_out(c: ExtensionClient) -> dict:
    return {"id": c.id, "name": c.name, "active": c.active, "created_at": c.created_at, "last_seen_at": c.last_seen_at}


class PairIn(Strict):
    name: str = Field(default="Browser extension", min_length=1, max_length=120)


@router.post("/extension/pair", status_code=201)
def pair(body: PairIn, ctx: UserContext = Depends(current_user), db: Session = Depends(get_db)):
    """Connects the extension in this browser to the signed-in account. The extension calls this from the dashboard
    page itself, so the session cookie and CSRF token prove who is asking; nothing is typed by the user. A browser
    that connects again replaces its previous connection."""
    for old in db.execute(select(ExtensionClient).where(ExtensionClient.user_id == ctx.user.id, ExtensionClient.name == body.name,
                                                        ExtensionClient.active.is_(True))).scalars():
        old.active, old.revoked_at = False, clock.utcnow()
    cid = new_id()
    key, key_hash = make_compound_secret("cce", cid)
    client = ExtensionClient(id=cid, user_id=ctx.user.id, name=body.name, key_hash=key_hash)
    db.add(client)
    audit_log.record(db, "extension.paired", user_id=ctx.user.id, actor_type="user", actor_id=ctx.user.id,
                     target_type="extension", target_id=cid, details={"name": body.name})
    db.commit()
    return {**_client_out(client), "key": key, "email": ctx.user.email}


@router.get("/extension/clients")
def clients(ctx: UserContext = Depends(current_user), db: Session = Depends(get_db)):
    rows = db.execute(select(ExtensionClient).where(ExtensionClient.user_id == ctx.user.id).order_by(ExtensionClient.created_at)).scalars()
    return [_client_out(c) for c in rows]


@router.post("/extension/clients/{client_id}/revoke")
def revoke(client_id: str, ctx: UserContext = Depends(current_user), db: Session = Depends(get_db)):
    c = db.get(ExtensionClient, client_id)
    if c is None or c.user_id != ctx.user.id:
        raise not_found("extension")
    c.active, c.revoked_at = False, clock.utcnow()
    audit_log.record(db, "extension.revoked", user_id=ctx.user.id, actor_type="user", actor_id=ctx.user.id,
                     target_type="extension", target_id=c.id)
    db.commit()
    return _client_out(c)


@router.post("/extension/sites/clear")
def clear_sites(ctx: UserContext = Depends(current_user), db: Session = Depends(get_db)):
    rows = list(db.execute(select(SiteVisit).where(SiteVisit.user_id == ctx.user.id)).scalars())
    for v in rows:
        db.delete(v)
    audit_log.record(db, "extension.history.cleared", user_id=ctx.user.id, actor_type="user", actor_id=ctx.user.id,
                     target_type="user", target_id=ctx.user.id, details={"sites": len(rows)})
    db.commit()
    return {"cleared": len(rows)}


# --- Called by the extension (X-Extension-Key) -------------------------------------------------------------

def current_extension(request: Request, db: Session = Depends(get_db)) -> ExtensionClient:
    parts = split_compound_secret("cce", request.headers.get("x-extension-key", ""))
    if parts is None:
        raise APIError(401, "EXTENSION_UNAUTHENTICATED", "X-Extension-Key header missing or malformed")
    c = db.get(ExtensionClient, parts[0])
    if c is None or not c.active or not constant_time_equal(c.key_hash, sha256(parts[1])):
        raise APIError(401, "EXTENSION_UNAUTHENTICATED", "this browser isn't connected; open Kavach while signed in")
    c.last_seen_at = clock.utcnow()
    return c


def _site(raw: str) -> str:
    host = disc.normalize_domain(raw)
    if host is None:
        raise APIError(422, "INVALID_DOMAIN", "not a website address")
    return site_domain(host)


def _tracked(db: Session, user_id: str, site: str) -> list[PolicySource]:
    rows = db.execute(select(PolicySource).where(PolicySource.user_id == user_id)).scalars()
    return [p for p in rows if site_domain(p.domain) == site]


def _look_up(factory: sessionmaker, user_id: str, site: str) -> None:
    """Background: review the site's policies and keep the result on the user's list of websites."""
    with factory() as db:
        try:
            remember(db, db.get(User, user_id), site, review(db, db.get(User, user_id), site), "extension")
            db.commit()
        except Exception:
            db.rollback()
            log.exception("site lookup failed for %s", site)
        finally:
            _inflight.discard(f"{user_id}:{site}")


def _visit_state(db: Session, background: BackgroundTasks, user: User, site: str, refresh: bool = False) -> dict:
    tracked = _tracked(db, user.id, site)
    v = db.execute(select(SiteVisit).where(SiteVisit.user_id == user.id, SiteVisit.domain == site)).scalar_one_or_none()
    if tracked:  # verdict from Kavach's tracked copies: instant, no fetching
        verdict = {**tracked_summary(db, user, site, tracked), "name": tracked[0].name.rsplit(" ", 2)[0], "tracked": True}
        v = remember(db, user, site, verdict, "extension")
        db.commit()
        return {"domain": site, "status": "TRACKED", "verdict": verdict}
    fresh = v is not None and v.verdict and v.status != "LOOKING" and clock.utcnow() - v.last_seen_at < FRESH
    if fresh and not refresh:
        v.visit_count += 1
        db.commit()
        return {"domain": site, "status": v.status, "verdict": v.verdict}
    key = f"{user.id}:{site}"
    if key not in _inflight:
        _inflight.add(key)
        v = remember(db, user, site, {"status": "LOOKING", "reasons": ["Reading this site's privacy policy and terms…"]}, "extension")
        v.status = "LOOKING"
        background.add_task(_look_up, sessionmaker(bind=db.get_bind(), autoflush=False, expire_on_commit=False), user.id, site)
    db.commit()
    return {"domain": site, "status": "LOOKING", "verdict": {"status": "LOOKING", "reasons": ["Reading this site's privacy policy and terms…"]}}


@router.get("/ext/me")
def ext_me(ext: ExtensionClient = Depends(current_extension), db: Session = Depends(get_db)):
    user = db.get(User, ext.user_id)
    db.commit()
    return {"email": user.email, "extension": ext.name, "onboarded": user.onboarded_at is not None}


class VisitIn(Strict):
    domain: str = Field(min_length=3, max_length=300)


@router.post("/ext/visit")
def ext_visit(body: VisitIn, background: BackgroundTasks, ext: ExtensionClient = Depends(current_extension), db: Session = Depends(get_db)):
    return _visit_state(db, background, db.get(User, ext.user_id), _site(body.domain))


class PageIn(Strict):
    url: str = Field(min_length=8, max_length=2048, pattern=r"^https?://")
    title: str = Field(default="", max_length=300)
    text: str = Field(default="", max_length=200_000)


@router.post("/ext/analyze")
def ext_analyze(body: PageIn, ext: ExtensionClient = Depends(current_extension), db: Session = Depends(get_db)):
    """The user is reading a privacy policy or terms page: review the whole site (this page plus the site's other
    policy) through all six agents and return one verdict."""
    user = db.get(User, ext.user_id)
    site = _site(body.url)
    page = {"url": body.url, "title": body.title, "text": body.text} if len(body.text) >= 400 else None
    result = review(db, user, site, page)
    remember(db, user, site, result, "extension")
    audit_log.record(db, "extension.page_analyzed", user_id=user.id, actor_type="extension", actor_id=ext.id,
                     target_type="site", target_id=site, details={"risk_score": result.get("risk_score"), "recommendation": result.get("recommendation")})
    db.commit()
    return result


@router.post("/ext/track", status_code=201)
def ext_track(body: PageIn, ext: ExtensionClient = Depends(current_extension), db: Session = Depends(get_db)):
    """Track the site's policies: Watchman re-checks them automatically from now on."""
    user = db.get(User, ext.user_id)
    site = _site(body.url)
    page = {"url": body.url, "title": body.title, "text": body.text} if len(body.text) >= 400 else None
    if not track_site(db, user, site, page):
        db.commit()
        raise APIError(502, "NOTHING_TO_TRACK", "We couldn't get any policy for this site")
    result = review(db, user, site)
    remember(db, user, site, result, "extension")
    db.commit()
    return result


class ConsentIn(Strict):
    domain: str = Field(min_length=3, max_length=300)
    kind: str = Field(default="signup", pattern="^(signup|agree|cookies)$")
    text: str = Field(default="", max_length=20_000)
    links: list[str] = Field(default_factory=list, max_length=20)


@router.post("/ext/consent")
def ext_consent(body: ConsentIn, background: BackgroundTasks, ext: ExtensionClient = Depends(current_extension), db: Session = Depends(get_db)):
    """A signup / "I agree" / cookie page: check the consent text for AI-agent instructions and return the site's verdict."""
    user = db.get(User, ext.user_id)
    site = _site(body.domain)
    hits = lx.injection_hits(body.text) if body.text else []
    audit_log.record(db, "extension.consent_moment", user_id=user.id, actor_type="extension", actor_id=ext.id,
                     target_type="site", target_id=site, decision="BLOCK" if hits else None,
                     details={"kind": body.kind, "instructions_found": len(hits), "text_characters": len(body.text)})
    out = _visit_state(db, background, user, site)
    v = db.execute(select(SiteVisit).where(SiteVisit.user_id == user.id, SiteVisit.domain == site)).scalar_one_or_none()
    if v is not None:
        v.consent_moments += 1
        db.commit()
    return {**out, "kind": body.kind, "hidden_instructions": hits[:5]}


@router.post("/extension/check")
def check_from_dashboard(body: VisitIn, background: BackgroundTasks, ctx: UserContext = Depends(current_user), db: Session = Depends(get_db)):
    """Same check the extension makes on a visit, started from the dashboard."""
    return _visit_state(db, background, ctx.user, _site(body.domain), refresh=True)
