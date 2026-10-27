"""Reads a "we're updating our terms" email: who sent it, whether it announces a policy change, and which policy
links it contains. The email body is used only here and is never stored."""
import email
import re
from dataclasses import dataclass, field
from email import policy as email_policy
from email.utils import getaddresses, parseaddr

from bs4 import BeautifulSoup

UPDATE_PATTERNS = [
    re.compile(r"\b(updat\w*|chang\w*|revis\w*|amend\w*)\b.{0,40}\b(privacy (policy|notice|statement)|terms( of (service|use))?|user agreement|conditions of use|data policy)", re.I),
    re.compile(r"\b(privacy (policy|notice|statement)|terms( of (service|use))?|user agreement|data policy)\b.{0,40}\b(updat\w*|chang\w*|revis\w*)", re.I),
    re.compile(r"\bnew (privacy (policy|notice)|terms( of (service|use))?|user agreement)\b", re.I),
]
EFFECTIVE = re.compile(r"\beffective\s+(?:on|from|as of)?\s*([A-Z][a-z]+ \d{1,2},? \d{4}|\d{1,2} [A-Z][a-z]+,? \d{4}|\d{4}-\d{2}-\d{2})")
URL = re.compile(r"https?://[^\s<>\"')\]]+")
POLICY_LINK = re.compile(r"privacy|terms|legal|policy|policies|agreement", re.I)


@dataclass
class ParsedEmail:
    from_address: str
    from_domain: str
    subject: str
    recipients: list[str]
    authenticated: bool
    is_policy_update: bool
    matched_phrases: list[str] = field(default_factory=list)
    links: list[str] = field(default_factory=list)
    effective_date: str | None = None
    changes: str = ""  # the paragraphs that describe the new terms, without greeting, links and footer
    date: str = ""


def _body(msg) -> tuple[str, list[str]]:
    plain, html = [], []
    for part in msg.walk() if msg.is_multipart() else [msg]:
        ctype = part.get_content_type()
        if part.get_content_maintype() == "multipart" or part.get_filename():
            continue
        try:
            content = part.get_content()
        except (LookupError, ValueError):
            continue
        if ctype == "text/plain":
            plain.append(str(content))
        elif ctype == "text/html":
            html.append(str(content))
    hrefs = []
    for h in html:
        soup = BeautifulSoup(h, "html.parser")
        hrefs += [a["href"] for a in soup.find_all("a", href=True)]
        if not plain:
            plain.append(soup.get_text(" ", strip=True))
    return "\n".join(plain), hrefs


_SKIP_LINE = re.compile(
    r"unsubscribe|view (it |this )?in (your )?browser|©|all rights reserved|^(hi|hello|dear|thanks|thank you|regards|best|cheers)\b|"
    r"this (is a sample|email was sent)|^\(",
    re.I,
)


def _changes(text: str) -> str:
    """Paragraphs that describe the new terms, without greeting, link-only lines and footer. Used to build the new
    version when the site itself can't show it yet."""
    keep = []
    for para in re.split(r"\n\s*\n", text.replace("\r\n", "\n")):
        p = " ".join(para.split())
        if len(p) < 40 or _SKIP_LINE.search(p) or len(URL.sub("", p).strip()) < 40:
            continue
        keep.append(URL.sub("", p).strip())
    return "\n".join(keep)[:6000]


def parse(raw: bytes | str) -> ParsedEmail:
    msg = email.message_from_bytes(raw.encode() if isinstance(raw, str) else raw, policy=email_policy.default)
    from_address = parseaddr(str(msg.get("From", "")))[1].lower()
    from_domain = from_address.rpartition("@")[2]
    subject = str(msg.get("Subject", ""))[:500]
    recipients = [a.lower() for _, a in getaddresses([str(v) for h in ("To", "Cc", "Delivered-To", "X-Original-To") for v in msg.get_all(h, [])]) if a]
    auth = " ".join(str(v) for v in msg.get_all("Authentication-Results", [])).lower()
    authenticated = bool(from_domain) and ("dmarc=pass" in auth or ("dkim=pass" in auth and from_domain.split(".")[-2] in auth))
    text, hrefs = _body(msg)
    hay = f"{subject}\n{text}"
    phrases = [m.group(0)[:120] for p in UPDATE_PATTERNS for m in [p.search(hay)] if m]
    links = list(dict.fromkeys(u.rstrip(".,;") for u in [*hrefs, *URL.findall(text)] if u.startswith("http") and POLICY_LINK.search(u)))[:10]
    eff = EFFECTIVE.search(hay)
    return ParsedEmail(from_address, from_domain, subject, recipients, authenticated, bool(phrases), phrases, links,
                       eff.group(1) if eff else None, _changes(text), str(msg.get("Date", ""))[:60])
