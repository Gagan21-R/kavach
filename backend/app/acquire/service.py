"""Server-side acquisition of real policy text.

Order of attempts for one URL:
  1. DIRECT    polite fetch, only if robots.txt allows it
  2. RENDERED  headless browser, only if the direct page had no readable text (needs JavaScript)
  3. OPEN_TERMS_ARCHIVE  the public Open Terms Archive copy, when the catalogue knows the document
  4. WAYBACK   the Internet Archive's latest public capture
Nothing bypasses a block: a refused page moves on to the next public source, or is reported as failed.
One shared copy per URL is cached, so many users tracking the same policy cause one request to the site.
"""
import json
import re
import threading
import time
import urllib.robotparser
from dataclasses import dataclass, field
from datetime import timedelta
from urllib.parse import quote, urlsplit

import httpx
from bs4 import BeautifulSoup
from sqlalchemy.orm import Session

from app import clock
from app.acquire import render
from app.config import get_settings
from app.models import FetchCache
from app.watchman.fetch import TIMEOUT, FetchResult, fetch_policy

MAX_TEXT = 60_000  # keeps one trial within the court's per-step time budget
MIN_TEXT = 1500
HOST_INTERVAL = 2.0  # seconds between two requests to the same site
OTA_RAW = "https://raw.githubusercontent.com/OpenTermsArchive/contrib-versions/main/{service}/{doc}.md"
WAYBACK_API = "https://archive.org/wayback/available?url={url}"
_BOILER = ["script", "style", "noscript", "svg", "nav", "header", "footer", "aside", "form", "button", "iframe", "template"]
_robots: dict[str, urllib.robotparser.RobotFileParser | None] = {}
_last_hit: dict[str, float] = {}
_lock = threading.Lock()

METHOD_LABELS = {
    "DIRECT": "Fetched from the site",
    "RENDERED": "Fetched with a browser (page needs JavaScript)",
    "OPEN_TERMS_ARCHIVE": "Public copy from Open Terms Archive",
    "WAYBACK": "Public copy from the Internet Archive",
}


_SHORT = {"DIRECT": "the site", "RENDERED": "with a browser", "OPEN_TERMS_ARCHIVE": "Open Terms Archive", "WAYBACK": "Internet Archive"}


def user_agent() -> str:
    return f"Mozilla/5.0 (compatible; Kavach-Watchman/1.0; policy monitoring; contact: {get_settings().fetch_contact})"


@dataclass
class Acquired:
    ok: bool
    text: str = ""
    method: str = ""
    source_url: str = ""
    error: str = ""
    attempts: list = field(default_factory=list)
    etag: str = ""
    last_modified: str = ""


def _client() -> httpx.Client:
    return httpx.Client(timeout=TIMEOUT, follow_redirects=False, headers={"User-Agent": user_agent(), "Accept-Language": "en"})


def _polite_wait(url: str) -> None:
    host = urlsplit(url).hostname or ""
    with _lock:
        wait = _last_hit.get(host, 0) + HOST_INTERVAL - time.monotonic()
        _last_hit[host] = time.monotonic() + max(0.0, wait)
    if wait > 0:
        time.sleep(wait)


def _get(url: str, headers: dict | None = None) -> FetchResult:
    _polite_wait(url)
    with _client() as c:
        return fetch_policy(url, client=c, headers=headers)


def robots_allows(url: str) -> bool:
    parts = urlsplit(url)
    origin = f"{parts.scheme}://{parts.netloc}"
    if origin not in _robots:
        res = _get(origin + "/robots.txt")
        if res.ok:
            rp = urllib.robotparser.RobotFileParser()
            rp.parse(res.text.splitlines())
            _robots[origin] = rp
        else:
            _robots[origin] = None  # no readable robots.txt: no restriction stated
    rp = _robots[origin]
    return rp is None or rp.can_fetch("Kavach-Watchman", url)


def html_to_text(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(_BOILER):
        tag.decompose()
    root = soup.find("main") or soup.find(attrs={"role": "main"}) or soup.find("article") or soup.body or soup
    for br in root.find_all("br"):
        br.replace_with("\n")
    lines = []
    for el in root.find_all(["h1", "h2", "h3", "h4", "p", "li", "td"]):
        if el.find(["p", "li"]):  # a container; its children are emitted on their own
            continue
        t = re.sub(r"\s+", " ", el.get_text(" ", strip=True))
        if len(t) >= 3:
            lines.append(("\n" + t) if el.name.startswith("h") else t)
    text = "\n".join(lines).strip()
    if len(text) < 500:  # unusual markup: fall back to all visible text
        text = re.sub(r"\n\s*\n+", "\n\n", root.get_text("\n", strip=True))
    return text[:MAX_TEXT]


_ENGLISH = re.compile(r"\b(the|and|of|to|you|your|we|our|information|data|with|for|that)\b", re.I)


def looks_english(text: str) -> bool:
    """The court's rules read English only; a French archive copy would look like a policy with no practices."""
    sample = text[:20000]
    words = max(1, len(re.findall(r"\w+", sample)))
    return len(_ENGLISH.findall(sample)) / words >= 0.12


def _thin(text: str) -> bool:
    return len(text) < MIN_TEXT or bool(re.search(r"enable javascript", text[:2000], re.I))


def _direct(url: str) -> tuple[Acquired | None, str]:
    res = _get(url)
    if not res.ok:
        return None, res.error
    text = html_to_text(res.text)
    if _thin(text):
        return None, f"the page needs JavaScript or has little text ({len(text)} characters)"
    return Acquired(True, text, "DIRECT", res.final_url, etag=res.etag, last_modified=res.last_modified), ""


def _rendered(url: str) -> tuple[Acquired | None, str]:
    _polite_wait(url)
    html, err = render.render_html(url, user_agent())
    if html is None:
        return None, err
    text = html_to_text(html)
    if _thin(text):
        return None, f"still little text after rendering ({len(text)} characters)"
    return Acquired(True, text, "RENDERED", url), ""


def _ota(service: str, doc: str) -> tuple[Acquired | None, str]:
    url = OTA_RAW.format(service=quote(service), doc=quote(doc))
    try:
        with httpx.Client(timeout=TIMEOUT, headers={"User-Agent": user_agent()}) as c:
            r = c.get(url)
    except httpx.HTTPError as e:
        return None, f"Open Terms Archive unavailable: {type(e).__name__}"
    if r.status_code != 200:
        return None, f"Open Terms Archive: HTTP {r.status_code}"
    text = re.sub(r"[#*_>`]+", "", r.text)
    text = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", text).strip()[:MAX_TEXT]
    return Acquired(True, text, "OPEN_TERMS_ARCHIVE", url), ""


def _wayback(url: str) -> tuple[Acquired | None, str]:
    try:  # fixed, well-known host; the JSON API is not a policy page, so it skips the HTML-only fetcher
        with httpx.Client(timeout=TIMEOUT, headers={"User-Agent": user_agent()}) as c:
            r = c.get(WAYBACK_API.format(url=quote(url, safe="")))
    except httpx.HTTPError as e:
        return None, f"Internet Archive lookup failed: {type(e).__name__}"
    if r.status_code != 200:
        return None, f"Internet Archive lookup failed: HTTP {r.status_code}"
    try:
        closest = json.loads(r.text)["archived_snapshots"]["closest"]
    except (ValueError, KeyError, TypeError):
        return None, "Internet Archive has no copy of this page"
    if not closest.get("available") or not closest.get("timestamp"):
        return None, "Internet Archive has no copy of this page"
    raw = f"https://web.archive.org/web/{closest['timestamp']}id_/{url}"
    page = _get(raw)
    if not page.ok:
        return None, f"Internet Archive copy unavailable: {page.error}"
    text = html_to_text(page.text)
    if _thin(text):
        return None, "the Internet Archive copy has little text"
    return Acquired(True, text, "WAYBACK", raw), ""


def acquire(url: str, ota: tuple[str, str] | None = None, allow_wayback: bool = True) -> Acquired:
    attempts = []

    def attempt(method, fn):
        got, err = fn()
        attempts.append({"method": method, "ok": got is not None, "detail": err or "fetched"})
        return got

    got = None
    if robots_allows(url):
        got = attempt("DIRECT", lambda: _direct(url))
        if got is None and "JavaScript" in attempts[-1]["detail"] and render.available():
            got = attempt("RENDERED", lambda: _rendered(url))
    else:
        attempts.append({"method": "DIRECT", "ok": False, "detail": "the site's robots.txt asks bots not to fetch this page, so we did not"})
    if got is None and ota:
        got = attempt("OPEN_TERMS_ARCHIVE", lambda: _ota(*ota))
    if got is None and allow_wayback:
        got = attempt("WAYBACK", lambda: _wayback(url))
    if got is not None and not looks_english(got.text):
        attempts[-1].update(ok=False, detail="this copy is not in English, which Kavach's rules can't read yet")
        got = None
        if allow_wayback and attempts[-1]["method"] != "WAYBACK":
            got = attempt("WAYBACK", lambda: _wayback(url))
            if got is not None and not looks_english(got.text):
                attempts[-1].update(ok=False, detail="this copy is not in English, which Kavach's rules can't read yet")
                got = None
    if got is None:
        tried = "; ".join(f"{_SHORT[a['method']]}: {a['detail']}" for a in attempts)
        return Acquired(False, error=tried, attempts=attempts)
    got.attempts = attempts
    return got


def acquire_cached(db: Session, url: str, ota: tuple[str, str] | None = None, max_age_minutes: int | None = None,
                   fetcher=None) -> Acquired:
    """Shared copy if it is fresh enough, otherwise fetch and store. Failures are cached briefly too."""
    max_age = timedelta(minutes=get_settings().fetch_cache_minutes if max_age_minutes is None else max_age_minutes)
    row = db.get(FetchCache, url)
    now = clock.utcnow()
    if row is not None and now - row.fetched_at <= (max_age if row.ok else min(max_age, timedelta(minutes=10))):
        return Acquired(row.ok, row.text, row.method, row.source_url, row.error, [*row.attempts, {"method": "CACHE", "ok": row.ok, "detail": "shared copy"}])
    got = (fetcher or acquire)(url, ota)
    if row is None:
        row = FetchCache(url=url)
        db.add(row)
    _store(row, got, now)
    db.flush()
    return got


def _store(row: FetchCache, got: Acquired, now) -> None:
    row.ok, row.text, row.method, row.source_url, row.error, row.attempts, row.fetched_at = (
        got.ok, got.text, got.method, got.source_url, got.error, got.attempts, now)
    row.etag, row.last_modified = got.etag[:300], got.last_modified[:100]


NOT_MODIFIED = "The site said the page hasn't changed (ETag / Last-Modified)"
COMPARED = "Downloaded the page and compared it with the last version"


def recheck(db: Session, url: str) -> tuple[FetchResult, str]:
    """Watchman's automatic re-check. Asks the site "changed since?" first, using the ETag / Last-Modified it gave
    last time; a 304 answer costs no download. Otherwise fetches again through the same sources and extraction as
    the first version, so the texts compare like with like. Returns (result, how it was checked)."""
    from app.acquire.catalogue import ota_for

    row = db.get(FetchCache, url)
    now = clock.utcnow()
    if row is not None and row.ok and row.method == "DIRECT" and (row.etag or row.last_modified) and robots_allows(url):
        headers = {k: v for k, v in (("If-None-Match", row.etag), ("If-Modified-Since", row.last_modified)) if v}
        res = _get(url, headers)
        if res.ok and res.not_modified:
            row.fetched_at = now
            db.flush()
            return FetchResult(True, text=row.text, final_url=url), NOT_MODIFIED
    got = acquire(url, ota_for(url), allow_wayback=False)  # an old archive capture must never pass for the current version
    if got.ok:
        if row is None:
            row = FetchCache(url=url)
            db.add(row)
        _store(row, got, now)
        db.flush()
    return FetchResult(got.ok, text=got.text, final_url=got.source_url, error=got.error), COMPARED


def fetch_clean(url: str) -> FetchResult:
    """Watchman fetcher for acquired policies: same sources and extraction as the first version, so re-checks compare
    like with like. The Internet Archive is skipped here: an old capture must never pass for the current version."""
    from app.acquire.catalogue import ota_for

    got = acquire(url, ota_for(url), allow_wayback=False)
    return FetchResult(got.ok, text=got.text, final_url=got.source_url, error=got.error)
