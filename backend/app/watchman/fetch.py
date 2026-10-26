"""SSRF-resistant policy retrieval.

Only http(s) on default ports; every hop's host must resolve exclusively to public addresses; redirects are
followed manually (max 3) and re-validated; size and time are capped. Any failure is reported, never hidden:
the caller records the check as UNKNOWN, not UNCHANGED.

Known limitation: the address is checked at resolution time, and the HTTP client resolves again when it
connects, so a DNS-rebinding attacker could race the check. Pinning the connection to the vetted IP
closes this; it is listed in docs/ARCHITECTURE.md.
"""
import ipaddress
import socket
from dataclasses import dataclass
from urllib.parse import urljoin, urlsplit

import httpx

MAX_BYTES = 2_000_000
TIMEOUT = httpx.Timeout(10.0, connect=5.0)
MAX_REDIRECTS = 3


@dataclass
class FetchResult:
    ok: bool
    text: str = ""
    final_url: str = ""
    error: str = ""


class FetchBlocked(Exception):
    pass


def _check_url(url: str) -> None:
    parts = urlsplit(url)
    if parts.scheme not in ("http", "https"):
        raise FetchBlocked("only http and https URLs are allowed")
    if parts.username or parts.password:
        raise FetchBlocked("URLs with credentials are not allowed")
    if parts.port not in (None, 80, 443):
        raise FetchBlocked("only default ports are allowed")
    host = parts.hostname
    if not host:
        raise FetchBlocked("URL has no host")
    try:
        infos = socket.getaddrinfo(host, None, proto=socket.IPPROTO_TCP)
    except socket.gaierror as e:
        raise FetchBlocked(f"could not resolve {host}: {e}") from None
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if not ip.is_global or ip.is_multicast:
            raise FetchBlocked(f"{host} resolves to a non-public address ({ip}); refusing to fetch")


def fetch_policy(url: str, client: httpx.Client | None = None) -> FetchResult:
    own = client is None
    client = client or httpx.Client(timeout=TIMEOUT, follow_redirects=False, headers={"User-Agent": "ConsentCourt-Watchman/1.0"})
    try:
        current = url
        for _ in range(MAX_REDIRECTS + 1):
            _check_url(current)
            with client.stream("GET", current) as resp:
                if resp.is_redirect:
                    location = resp.headers.get("location")
                    if not location:
                        return FetchResult(False, error="redirect without a location")
                    current = urljoin(current, location)
                    continue
                if resp.status_code != 200:
                    return FetchResult(False, error=f"HTTP {resp.status_code}", final_url=current)
                ctype = resp.headers.get("content-type", "")
                if not any(t in ctype for t in ("text/html", "text/plain", "application/xhtml")):
                    return FetchResult(False, error=f"unsupported content type {ctype or 'unknown'}", final_url=current)
                body = b""
                for chunk in resp.iter_bytes():
                    body += chunk
                    if len(body) > MAX_BYTES:
                        return FetchResult(False, error="document larger than 2 MB", final_url=current)
                return FetchResult(True, text=body.decode(resp.encoding or "utf-8", errors="replace"), final_url=current)
        return FetchResult(False, error="too many redirects")
    except FetchBlocked as e:
        return FetchResult(False, error=str(e))
    except httpx.HTTPError as e:
        return FetchResult(False, error=f"retrieval failed: {type(e).__name__}")
    finally:
        if own:
            client.close()
