"""Headless rendering for policy pages that only show their text after JavaScript runs.

Used only after a plain fetch came back empty, and only where robots.txt allows the page. Every request the
browser makes (the page and its scripts) goes through the same public-address check as the plain fetcher, so a
page cannot steer the browser into the internal network. Images, fonts and media are not loaded.
"""
import ipaddress
import socket
from functools import lru_cache
from urllib.parse import urlsplit

from app.config import get_settings

_SKIP_TYPES = {"image", "media", "font"}  # stylesheets stay: some apps wait for them before showing text


def available() -> bool:
    if not get_settings().fetch_render_enabled:
        return False
    try:
        import playwright.sync_api  # noqa: F401
    except ImportError:
        return False
    return True


@lru_cache(maxsize=512)
def _public_host(host: str) -> bool:
    try:
        infos = socket.getaddrinfo(host, None, proto=socket.IPPROTO_TCP)
    except socket.gaierror:
        return False
    return all(ipaddress.ip_address(i[4][0]).is_global for i in infos)


def request_allowed(url: str) -> bool:
    parts = urlsplit(url)
    if parts.scheme not in ("http", "https") or parts.username or parts.password or parts.port not in (None, 80, 443):
        return False
    return bool(parts.hostname) and _public_host(parts.hostname)


def render_html(url: str, user_agent: str, timeout_ms: int = 20_000) -> tuple[str | None, str]:
    """Returns (html, error). Never raises."""
    if not available():
        return None, "headless browser not installed"
    if not request_allowed(url):
        return None, "address is not public; refusing to render"
    from playwright.sync_api import Error as PWError
    from playwright.sync_api import sync_playwright

    def guard(route):
        req = route.request
        if req.resource_type in _SKIP_TYPES or not request_allowed(req.url):
            return route.abort()
        return route.continue_()

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            try:
                page = browser.new_page(user_agent=user_agent, java_script_enabled=True)
                page.route("**/*", guard)
                resp = page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
                if resp is None or resp.status >= 400:
                    return None, f"HTTP {resp.status if resp else 'no response'} when rendering"
                try:
                    page.wait_for_load_state("networkidle", timeout=8_000)
                except PWError:
                    pass  # some pages never go idle; use what has rendered
                return page.content(), ""
            finally:
                browser.close()
    except PWError as e:
        return None, f"rendering failed: {str(e).splitlines()[0][:160]}"
