from fastapi.testclient import TestClient

from tests.conftest import PASSWORD


def test_register_rejects_weak_password_and_duplicates(app):
    c = TestClient(app)
    assert c.post("/auth/register", json={"email": "a@example.com", "password": "short"}).json()["error"]["code"] == "WEAK_PASSWORD"
    assert c.post("/auth/register", json={"email": "a@example.com", "password": PASSWORD}).status_code == 201
    assert c.post("/auth/register", json={"email": "A@Example.com", "password": PASSWORD}).status_code == 409


def test_login_wrong_password_and_rate_limit(app):
    c = TestClient(app)
    c.post("/auth/register", json={"email": "a@example.com", "password": PASSWORD})
    codes = [c.post("/auth/login", json={"email": "a@example.com", "password": "wrong password!!"}).status_code for _ in range(11)]
    assert codes[:10] == [401] * 10
    assert codes[10] == 429


def test_session_cookie_is_httponly_and_strict(app):
    c = TestClient(app)
    c.post("/auth/register", json={"email": "a@example.com", "password": PASSWORD})
    r = c.post("/auth/login", json={"email": "a@example.com", "password": PASSWORD})
    cookie = r.headers["set-cookie"].lower()
    assert "httponly" in cookie and "samesite=strict" in cookie
    assert "session_token" not in r.json()  # the session secret is never exposed to page scripts


def test_writes_without_csrf_header_are_rejected(make_actor):
    user = make_actor()
    del user.client.headers["X-CSRF-Token"]
    r = user.client.post("/consent/rules", json={"effect": "DENY", "data_categories": ["location"]})
    assert r.status_code == 403 and r.json()["error"]["code"] == "CSRF_FAILED"
    assert user.client.get("/consent/rules").status_code == 200  # reads are fine


def test_unauthenticated_requests_are_rejected(app):
    c = TestClient(app)
    for method, path in [("get", "/consent/rules"), ("get", "/audit/events"), ("post", "/guardian/revoke"), ("get", "/guardian/tokens")]:
        assert getattr(c, method)(path).status_code == 401


def test_session_expiry_and_logout(make_actor, frozen):
    user = make_actor()
    assert user.client.get("/auth/me").status_code == 200
    frozen.advance(minutes=61)
    assert user.client.get("/auth/me").status_code == 401

    other = make_actor()
    assert other.client.post("/auth/logout").status_code == 204
    assert other.client.get("/auth/me").status_code == 401


def test_step_up_required_only_for_loosening_changes(make_actor, frozen):
    user = make_actor()
    frozen.advance(minutes=6)  # login's implicit step-up has lapsed

    # Tightening: no step-up needed.
    deny = user.rule("DENY", ["biometrics"])
    allow_rule_needed = user.client.post("/consent/rules", json={"effect": "ALLOW", "data_categories": ["location"]})
    assert allow_rule_needed.status_code == 403 and allow_rule_needed.json()["error"]["code"] == "STEP_UP_REQUIRED"

    # Removing a prohibition loosens protection, so it needs step-up too.
    assert user.client.delete(f"/consent/rules/{deny['id']}").json()["error"]["code"] == "STEP_UP_REQUIRED"
    assert user.client.post("/agents", json={"name": "x"}).json()["error"]["code"] == "STEP_UP_REQUIRED"

    bad = user.client.post("/auth/step-up", json={"password": "not my password"})
    assert bad.status_code == 401
    user.step_up()
    allow = user.rule("ALLOW", ["location"], purposes=["navigation"])
    assert user.client.delete(f"/consent/rules/{deny['id']}").status_code == 200

    frozen.advance(minutes=6)
    # Revoking an ALLOW only tightens: allowed without step-up.
    assert user.client.delete(f"/consent/rules/{allow['id']}").status_code == 200


def test_rule_edit_creates_new_version_and_keeps_history(make_actor):
    user = make_actor()
    v1 = user.rule("ALLOW", ["location"], purposes=["navigation"])
    r = user.client.put(f"/consent/rules/{v1['id']}", json={"effect": "ALLOW", "data_categories": ["location"], "purposes": ["navigation", "service_delivery"]})
    assert r.status_code == 200
    v2 = r.json()
    assert v2["supersedes_id"] == v1["id"] and v2["constitution_version"] > v1["constitution_version"]
    history = user.client.get(f"/consent/rules/{v2['id']}/history").json()
    assert [h["id"] for h in history] == [v2["id"], v1["id"]]
    assert history[1]["active"] is False
    active = user.client.get("/consent/rules").json()
    assert [r["id"] for r in active] == [v2["id"]]


def test_rule_validation_rejects_unknown_vocabulary(make_actor):
    user = make_actor()
    for body in [
        {"effect": "DENY", "data_categories": ["Location"]},
        {"effect": "DENY", "data_categories": ["location"], "purposes": ["world-domination"]},
        {"effect": "DENY", "data_categories": ["location"], "recipients": ["not a host"]},
        {"effect": "MAYBE", "data_categories": ["location"]},
        {"effect": "DENY", "data_categories": []},
    ]:
        assert user.client.post("/consent/rules", json=body).status_code == 422, body


def test_consent_check_explains_the_deciding_rule(make_actor):
    user = make_actor()
    deny = user.rule("DENY", ["location"], purposes=["advertising"])
    r = user.client.post("/consent/check", json={"action": "transfer_data", "destination": "ads.example.net",
                                                 "purpose": "advertising", "data_categories": ["location"]})
    body = r.json()
    assert body["decision"] == "BLOCK" and body["deciding_rule_ids"] == [deny["id"]]
