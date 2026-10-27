"""Find a website's privacy policy and terms from just its domain.

Reads the home page (the footer almost always links them), scores every link by its text and address, and
falls back to the usual paths (/privacy, /terms, ...). Only fetches what robots.txt allows.
"""
import re
from urllib.parse import urljoin, urlsplit

from bs4 import BeautifulSoup

from app.acquire import service as acq

_PATTERNS = {
    "privacy": [(r"privacy (policy|notice|statement)", 6), (r"\bprivacy\b", 4), (r"data (policy|protection)", 3)],
    "terms": [(r"terms (of (service|use)|and conditions|& conditions)", 6), (r"user agreement|conditions of use", 5),
              (r"\bterms\b", 4), (r"\blegal\b", 1)],
}
_PATHS = {
    "privacy": ["/privacy", "/privacy-policy", "/legal/privacy", "/privacy-policy/", "/policies/privacy"],
    "terms": ["/terms", "/terms-of-service", "/terms-and-conditions", "/legal/terms", "/tos", "/terms-of-use"],
}
_DOMAIN = re.compile(r"^(?=.{1,253}$)([a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}$")


def normalize_domain(value: str) -> str | None:
    v = value.strip().lower()
    if "://" in v:
        v = urlsplit(v).hostname or ""
    v = v.split("/")[0].split(":")[0].rstrip(".")
    return v if _DOMAIN.match(v) else None


def _score(kind: str, text: str, href: str) -> int:
    hay = f"{text.lower()} {href.lower().replace('-', ' ').replace('_', ' ')}"
    return sum(w for pat, w in _PATTERNS[kind] if re.search(pat, hay))


def links_from_html(html: str, base: str) -> dict[str, list[dict]]:
    soup = BeautifulSoup(html, "html.parser")
    found: dict[str, dict[str, dict]] = {"privacy": {}, "terms": {}}
    for a in soup.find_all("a", href=True):
        href = urljoin(base, a["href"].strip())
        if not href.startswith(("http://", "https://")):
            continue
        href = href.split("#")[0]
        text = re.sub(r"\s+", " ", a.get_text(" ", strip=True))[:120]
        for kind in found:
            s = _score(kind, text, href)
            other = _score("terms" if kind == "privacy" else "privacy", text, href)
            if s >= 4 and s >= other:
                prev = found[kind].get(href)
                if prev is None or prev["score"] < s:
                    found[kind][href] = {"url": href, "text": text, "score": s}
    return {k: sorted(v.values(), key=lambda c: -c["score"])[:5] for k, v in found.items()}


def discover(domain: str) -> dict:
    """Returns {"domain", "home": url|None, "privacy": url|None, "terms": url|None, "candidates", "notes"}."""
    notes = []
    candidates = {"privacy": [], "terms": []}
    home = None
    for root in (f"https://{domain}/", f"https://www.{domain}/"):
        if not acq.robots_allows(root):
            notes.append(f"{root} asks bots not to read its home page")
            continue
        res = acq._get(root)
        if res.ok:
            home = res.final_url or root
            candidates = links_from_html(res.text, home)
            break
        notes.append(f"could not open {root}: {res.error}")
    result = {"domain": domain, "home": home, "candidates": candidates, "notes": notes}
    base = home or f"https://{domain}/"
    for kind in ("privacy", "terms"):
        if candidates[kind]:
            result[kind] = candidates[kind][0]["url"]
            continue
        result[kind] = None
        for path in _PATHS[kind]:  # no link found: try the usual addresses
            url = urljoin(base, path)
            if acq.robots_allows(url) and acq._get(url).ok:
                result[kind] = url
                notes.append(f"no {kind} link on the home page; found {path}")
                break
    return result
