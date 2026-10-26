import re
from urllib.parse import urlsplit

_LABEL = re.compile(r"^(?!-)[a-z0-9-]{1,63}(?<!-)$")


def normalize_host(value: str) -> str | None:
    """Accepts a hostname or URL and returns a lowercase hostname, or None if it is not a valid DNS name."""
    if not value:
        return None
    raw = value.strip().lower()
    if "://" in raw:
        raw = urlsplit(raw).hostname or ""
    raw = raw.rstrip(".")
    if not raw or len(raw) > 253 or any(c in raw for c in "/:@?# "):
        return None
    labels = raw.split(".")
    if len(labels) < 2 or not all(_LABEL.match(l) for l in labels):
        return None
    return raw


def host_matches(pattern: str, host: str) -> bool:
    """'*' matches anything; '*.example.com' matches example.com and every subdomain; otherwise exact."""
    pattern = pattern.lower().rstrip(".")
    if pattern == "*":
        return True
    if pattern.startswith("*."):
        base = pattern[2:]
        return host == base or host.endswith("." + base)
    return host == pattern


def host_within(host: str, domain: str) -> bool:
    return host == domain or host.endswith("." + domain)
