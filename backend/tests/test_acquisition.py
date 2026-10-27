"""Policy acquisition, discovery, first-run preferences, the browser extension API and email signals.
No test touches the network: fetching is replaced with fakes."""
import pytest

from app.acquire import discover as disc
from app.acquire import render
from app.acquire import service as acq
from app.inbox import parse as email_parse
from app.models import FetchCache, PolicySource, SiteVisit
from app.preferences import default_choices, rules_from_choices

RISKY = ("We sell your browsing history to data brokers and advertisers for targeted ads. "
         "We use your messages and photos to train our AI models. We collect your precise location at all times. "
         "We keep your data indefinitely. ") * 3
EN = "We collect your email to run the service and we share it with our partners for the purposes of the service. "
CALM = "We collect your email to create your account. We do not sell your data. You can delete your account at any time. " * 3


@pytest.fixture
def fake_fetch(monkeypatch):
    """Every acquisition returns this text and records the URLs asked for."""
    state = {"text": RISKY, "calls": [], "ok": True}

    def fake(url, ota=None, allow_wayback=True):
        state["calls"].append(url)
        if not state["ok"]:
            return acq.Acquired(False, error="HTTP 403", attempts=[{"method": "DIRECT", "ok": False, "detail": "HTTP 403"}])
        return acq.Acquired(True, state["text"], "DIRECT", url, attempts=[{"method": "DIRECT", "ok": True, "detail": "fetched"}])

    monkeypatch.setattr(acq, "acquire", fake)
    return state


# --- Extraction and sources -----------------------------------------------------------------------------------

def test_html_to_text_keeps_policy_drops_navigation():
    html = ("<html><body><nav>Home About Careers</nav><main><h1>Privacy Policy</h1><p>We collect your email.</p>"
            "<ul><li>We share data with partners.</li></ul></main><footer>© 2026</footer><script>evil()</script></body></html>")
    text = acq.html_to_text(html)
    assert "We collect your email." in text and "We share data with partners." in text
    assert "Careers" not in text and "evil" not in text and "2026" not in text


def test_robots_disallow_skips_the_site_and_uses_public_copies(monkeypatch):
    monkeypatch.setattr(acq, "robots_allows", lambda url: False)
    monkeypatch.setattr(acq, "_direct", lambda url: pytest.fail("must not fetch a page robots.txt disallows"))
    monkeypatch.setattr(acq, "_ota", lambda s, d: (acq.Acquired(True, EN, "OPEN_TERMS_ARCHIVE", "ota"), ""))
    got = acq.acquire("https://site.example/privacy", ("Site", "Privacy Policy"))
    assert got.ok and got.method == "OPEN_TERMS_ARCHIVE"
    assert got.attempts[0]["method"] == "DIRECT" and "robots.txt" in got.attempts[0]["detail"]


def test_fallback_order_and_wayback_never_used_for_rechecks(monkeypatch):
    order = []
    monkeypatch.setattr(acq, "robots_allows", lambda url: True)
    monkeypatch.setattr(acq, "_direct", lambda url: (order.append("direct"), (None, "HTTP 403"))[1])
    monkeypatch.setattr(acq, "_ota", lambda s, d: (order.append("ota"), (None, "HTTP 404"))[1])
    monkeypatch.setattr(acq, "_wayback", lambda url: (order.append("wayback"), (acq.Acquired(True, EN, "WAYBACK", "wb"), ""))[1])
    assert acq.acquire("https://site.example/p", ("S", "P")).method == "WAYBACK"
    assert order == ["direct", "ota", "wayback"]
    order.clear()
    res = acq.fetch_clean("https://site.example/p")  # Watchman re-check: an old capture must not pass for current
    assert not res.ok and "wayback" not in order


def test_javascript_pages_are_rendered_when_direct_is_empty(monkeypatch):
    monkeypatch.setattr(acq, "robots_allows", lambda url: True)
    monkeypatch.setattr(acq, "_direct", lambda url: (None, "the page needs JavaScript or has little text (0 characters)"))
    monkeypatch.setattr(acq.render, "available", lambda: True)
    monkeypatch.setattr(acq, "_rendered", lambda url: (acq.Acquired(True, EN, "RENDERED", url), ""))
    assert acq.acquire("https://app.example/privacy").method == "RENDERED"


@pytest.mark.parametrize("url", ["http://127.0.0.1/x", "http://localhost/", "http://10.0.0.5/", "file:///etc/passwd",
                                 "http://169.254.169.254/latest", "https://example.com:8443/"])
def test_headless_browser_refuses_non_public_addresses(url):
    assert not render.request_allowed(url)


def test_shared_cache_serves_many_users_with_one_request(Session, fake_fetch, frozen):
    with Session() as db:
        a = acq.acquire_cached(db, "https://site.example/privacy")
        b = acq.acquire_cached(db, "https://site.example/privacy")
        assert a.ok and b.ok and b.text == a.text
        assert fake_fetch["calls"] == ["https://site.example/privacy"]
        frozen.advance(hours=7)  # past the 6-hour freshness window
        acq.acquire_cached(db, "https://site.example/privacy")
        assert len(fake_fetch["calls"]) == 2
        assert db.get(FetchCache, "https://site.example/privacy").ok


def test_discovery_finds_footer_links_and_rejects_bad_domains():
    html = ('<footer><a href="/about">About</a><a href="/legal/privacy-notice">Privacy Notice</a>'
            '<a href="https://help.example.com/terms">Terms of Service</a><a href="/cookies">Cookie settings</a></footer>')
    found = disc.links_from_html(html, "https://www.example.com/")
    assert found["privacy"][0]["url"] == "https://www.example.com/legal/privacy-notice"
    assert found["terms"][0]["url"] == "https://help.example.com/terms"
    assert disc.normalize_domain("https://www.Spotify.com/in/") == "www.spotify.com"
    for bad in ("localhost", "127.0.0.1", "not a domain", "javascript:alert(1)"):
        assert disc.normalize_domain(bad) is None


# --- Library -----------------------------------------------------------------------------------------------------

def test_library_tracks_a_real_platform_and_reports_how(make_actor, fake_fetch):
    u = make_actor()
    r = u.client.post("/library/spotify/privacy/track")
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["acquisition"]["method"] == "DIRECT" and body["analysis"]["status"] == "COMPLETED"
    lib = u.client.get("/library").json()
    spotify = next(s for s in lib["services"] if s["id"] == "spotify")
    assert spotify["docs"][0]["tracked"]["id"] == body["policy"]["id"]
    assert u.client.post("/library/spotify/privacy/track").json()["acquisition"]["method"] == "ALREADY_TRACKED"


def test_library_failure_is_reported_not_hidden(make_actor, fake_fetch):
    fake_fetch["ok"] = False
    u = make_actor()
    r = u.client.post("/library/amazon/privacy/track")
    assert r.status_code == 502 and r.json()["error"]["code"] == "ACQUISITION_FAILED"
    assert u.client.get("/policies").json() == []


# --- First-run preferences ---------------------------------------------------------------------------------------

def test_default_preferences_become_rules():
    rules = rules_from_choices(default_choices())
    deny_sharing = next(r for r in rules if r["effect"] == "DENY" and "third_party_sharing" in r["purposes"])
    assert "location" in deny_sharing["data_categories"] and "email" in deny_sharing["data_categories"]
    assert all(r["description"].startswith("Preferences:") for r in rules)


def test_onboarding_saves_rules_needs_step_up_for_ok_and_tracks_services(make_actor, fake_fetch, Session, frozen):
    u = make_actor()
    frozen.advance(minutes=6)  # signing in counts as recent re-authentication; let it lapse
    state = u.client.get("/onboarding").json()
    assert state["onboarded"] is False and len(state["services"]) >= 19
    r = u.client.post("/onboarding", json={"choices": state["defaults"], "services": ["spotify"]})
    assert r.status_code == 403 and r.json()["error"]["code"] == "STEP_UP_REQUIRED"  # "OK" answers loosen protection
    u.step_up()
    r = u.client.post("/onboarding", json={"choices": state["defaults"], "services": ["spotify"]})
    assert r.status_code == 200 and r.json()["rules_created"] > 0
    assert u.client.get("/auth/session").json()["user"]["onboarded"] is True
    with Session() as db:  # tracked in the background
        assert [p.name for p in db.query(PolicySource).filter_by(user_id=u.user_id)] == ["Spotify Privacy Policy"]
    assert u.client.get("/onboarding").json()["current"]["location"]["sharing"] == "NEVER"


def test_onboarding_only_never_needs_no_step_up_and_skip_works(make_actor):
    u = make_actor()
    r = u.client.post("/onboarding", json={"choices": {"location": {"ads": "NEVER"}}})
    assert r.status_code == 200 and r.json()["rules_created"] == 1
    v = make_actor()
    assert v.client.post("/onboarding", json={"skip": True}).json()["onboarded"] is True


def test_copies_not_in_english_are_not_used(monkeypatch):
    french = "Chez Meta, nous souhaitons que vous compreniez quelles informations nous recueillons et comment nous les utilisons. " * 5
    monkeypatch.setattr(acq, "robots_allows", lambda url: False)
    monkeypatch.setattr(acq, "_ota", lambda s, d: (acq.Acquired(True, french, "OPEN_TERMS_ARCHIVE", "ota"), ""))
    monkeypatch.setattr(acq, "_wayback", lambda url: (None, "Internet Archive has no copy of this page"))
    got = acq.acquire("https://site.example/privacy", ("Site", "Privacy Policy"))
    assert not got.ok and "not in English" in got.error
