"""Data flow, Emergency Stop, chatbot, drafts, Trap demo, Red Team Lab (acceptance tests 10-17)."""
from app.demo import fixtures as fx
from app.redteam import lab
from tests.conftest import PASSWORD, action, execute_body


def test_derived_data_inherits_restrictions(granted):
    user, agent, _, _, token, info = granted(max_uses=3)
    gps = user.client.post("/data-flow/assets", json={"label": "GPS", "categories": ["location"], "source": "device:gps"}).json()
    hood = user.client.post("/data-flow/assets", json={"label": "Neighbourhood", "categories": ["preferences"],
                                                       "derived_from": [gps["id"]], "transformation": "reverse geocode"}).json()
    assert hood["effective_categories"] == ["location", "preferences"]
    laundered = agent.post("/gateway/execute", json=execute_body(categories=["preferences"]) | {"asset_id": hood["id"]},
                           headers={"X-Consent-Token": token})
    assert laundered.json()["error"]["code"] == "UNDECLARED_DATA"
    honest = agent.post("/gateway/execute", json=execute_body() | {"asset_id": gps["id"]}, headers={"X-Consent-Token": token})
    assert honest.status_code == 200
    lin = user.client.get(f"/data-flow/lineage/{gps['id']}").json()
    assert {n["id"] for n in lin["nodes"]} == {gps["id"], hood["id"]}
    assert lin["edges"] == [{"from": gps["id"], "to": hood["id"], "transformation": "reverse geocode"}]
    outcomes = sorted(f["outcome"] for f in lin["flows"])
    assert outcomes == ["BLOCKED_BEFORE_EXECUTION", "COMPLETED"]
    v = user.client.get("/data-flow/violations").json()
    assert v[0]["code"] == "UNDECLARED_DATA"


def test_flow_dry_run_and_coverage(make_actor):
    user = make_actor()
    user.rule("DENY", ["location"], purposes=["advertising"])
    gps = user.client.post("/data-flow/assets", json={"label": "GPS", "categories": ["location"]}).json()
    hood = user.client.post("/data-flow/assets", json={"label": "Hood", "categories": [], "derived_from": [gps["id"]], "transformation": "geocode"}).json()
    r = user.client.post("/data-flow/evaluate", json={"asset_id": hood["id"], "action": "transfer_data", "destination": "ads.example.net",
                                                      "purpose": "advertising", "declared_categories": ["location"]}).json()
    assert r["decision"] == "BLOCK" and r["effective_categories"] == ["location"]
    cov = user.client.get("/data-flow/coverage").json()
    assert cov["not_instrumented"] and "simulated" in cov["note"]


def test_derivation_requires_owned_sources(make_actor):
    a, b = make_actor(), make_actor()
    gps = a.client.post("/data-flow/assets", json={"label": "GPS", "categories": ["location"]}).json()
    r = b.client.post("/data-flow/assets", json={"label": "x", "categories": [], "derived_from": [gps["id"]], "transformation": "t"})
    assert r.status_code == 404
    assert b.client.get(f"/data-flow/lineage/{gps['id']}").status_code == 404


def test_emergency_stop_contains_and_recovery_needs_step_up(granted, frozen):
    user, agent, agent_id, pid, token, info = granted()
    inc = user.client.post("/emergency-stop/activate", json={"reason": "suspicious agent behaviour"}).json()
    assert inc["state"] == "CONTAINED"
    steps = {a["step"]: a["count"] for a in inc["actions"]}
    assert steps["revoke_tokens"] == 1 and "preserve_evidence" in steps
    assert "cannot be recalled" in inc["external_limits"]
    # Protected actions are frozen at both entry points.
    assert agent.post("/gateway/execute", json=execute_body(), headers={"X-Consent-Token": token}).json()["error"]["code"] in ("EMERGENCY_STOP", "REVOKED")
    blocked = agent.post("/guardian/authorize", json=action(pid))
    assert blocked.status_code == 403 and "Emergency Stop" in blocked.json()["evaluation"]["reasons"][0]
    # Evidence is preserved.
    assert user.client.get("/audit/events?event_type=token.issued").json()
    # Recovery requires re-authentication and confirmation.
    frozen.advance(minutes=6)
    body = {"incident_id": inc["id"], "confirmation": "RESTORE", "findings": "agent key leaked in logs; rotated"}
    assert user.client.post("/emergency-stop/recover", json=body).json()["error"]["code"] == "STEP_UP_REQUIRED"
    user.step_up()
    assert user.client.post("/emergency-stop/recover", json={**body, "confirmation": "yes"}).status_code == 422
    done = user.client.post("/emergency-stop/recover", json=body).json()
    assert done["state"] == "RESOLVED"
    assert user.client.get("/emergency-stop/status").json()["frozen"] is False
    # Revoked tokens stay revoked; a new authorization works.
    assert agent.post("/gateway/execute", json=execute_body(), headers={"X-Consent-Token": token}).json()["error"]["code"] == "REVOKED"
    assert agent.post("/guardian/authorize", json=action(pid)).status_code == 201


def test_emergency_stop_signs_out_other_sessions(make_actor, app):
    from fastapi.testclient import TestClient

    user = make_actor("stop@example.com")
    other = TestClient(app)
    other.post("/auth/login", json={"email": "stop@example.com", "password": PASSWORD})
    assert other.get("/auth/me").status_code == 200
    user.client.post("/emergency-stop/activate", json={"reason": "lost phone"})
    assert other.get("/auth/me").status_code == 401
    assert user.client.get("/auth/me").status_code == 200


def test_chatbot_is_read_only_and_tenant_scoped(granted, make_actor):
    user, agent, _, _, token, info = granted()
    r = user.client.post("/chat/explain", json={"message": "revoke all my tokens"}).json()
    assert r["intent"] == "refused_action" and r["read_only"]
    assert user.client.get("/guardian/tokens").json()[0]["revoked_at"] is None
    mine = user.client.post("/chat/explain", json={"message": "which tokens are active?"}).json()
    assert "maps.example.com" in mine["answer"]
    other = make_actor()
    theirs = other.post if False else other.client.post("/chat/explain", json={"message": "which tokens are active?"}).json()
    assert "maps.example.com" not in theirs["answer"]
    arch = user.client.post("/chat/explain", json={"message": "How does Kavach work?"}).json()
    assert arch["intent"] == "architecture"


def test_chatbot_explains_blocks(granted):
    user, agent, *_ = granted()
    user.rule("DENY", ["location"])
    tok = None
    agent.post("/gateway/execute", json=execute_body(), headers={"X-Consent-Token": "cct_bad.token"})
    r = user.client.post("/chat/explain", json={"message": "Why was my agent blocked?"}).json()
    assert r["intent"] == "why_blocked" and "INVALID_TOKEN" in r["answer"] or "not recognised" in r["answer"]


def test_email_drafts_are_never_sent(make_actor):
    user = make_actor()
    pid = user.policy(text=fx.MAPSCO["text"])
    ev = user.client.post(f"/policies/{pid}/snapshots", json={"text": fx.MAPSCO_BETRAYAL}).json()["watch_event"]
    d = user.client.post("/provider-requests/draft", json={"policy_source_id": pid, "request_type": "withdraw_consent",
                                                           "watch_event_id": ev["id"]}).json()
    assert d["sent"] is False and "AI partners" in d["body"] and "not legal advice" in d["disclaimer"]
    # There is no route that sends anything.
    assert user.client.post("/provider-requests/send", json={}).status_code in (404, 405)
    paths = [getattr(r, "path", "") for r in user.app.routes]
    assert not any("send" in p for p in paths)


def test_trap_demo_naive_vs_guarded(make_actor):
    user = make_actor()
    naive = user.client.post("/demo/trap", json={"html": fx.TRAP_PAGE, "guarded": False}).json()
    guarded = user.client.post("/demo/trap", json={"html": fx.TRAP_PAGE, "guarded": True}).json()
    assert naive["outcome"] == "ACCEPTED_ALL" and guarded["outcome"] == "BLOCKED"
    assert any(s["hidden"] and s["suspicious"] for s in guarded["segments"])
    assert naive["simulated"] and guarded["simulated"]


def test_seed_and_dashboard(make_actor):
    user = make_actor()
    seeded = user.client.post("/demo/seed")
    assert seeded.status_code == 201 and seeded.json()["agent_key"].startswith("cca_")
    assert user.client.post("/demo/seed").status_code == 409
    d = user.client.get("/dashboard/summary").json()
    assert d["counts"]["policies"] == 2 and d["counts"]["active_rules"] == 6
    names = {p["name"]: p for p in d["policies"]}
    assert names["FlashLight"]["recommendation"] == "BLOCK" and names["MapsCo"]["recommendation"] == "ALLOW"


def test_red_team_lab_is_reproducible_and_honest():
    a = lab.run(seed=11)
    b = lab.run(seed=11)
    strip = lambda r: [(x["id"], x["status"], x["actual"]) for x in r["results"]]  # noqa: E731
    assert strip(a) == strip(b)
    s = a["summary"]
    assert s["total"] == len(lab.SCENARIOS) and s["abstained"] == 0
    failed = {r["id"] for r in a["results"] if r["status"] == "FAIL"}
    assert failed == {"INJ-06", "WAT-05"}  # the two documented hard cases
    assert s["false_approvals"] == 0 and s["attack_success_rate"] == 0
    assert s["injection_detection"]["precision"] == 1.0 and s["injection_detection"]["recall"] < 1.0
    assert s["citation_support_rate"] == 1.0


def test_red_team_lab_still_signs_in_with_secure_cookies(monkeypatch):
    from app.config import get_settings

    monkeypatch.setattr(get_settings(), "cookie_secure", True)  # production setting on Render
    s = lab.run(seed=11)["summary"]
    assert s["abstained"] == 0 and s["passed"] == len(lab.SCENARIOS) - 2


def test_red_team_run_endpoint(make_actor):
    user = make_actor()
    r = user.client.post("/red-team/runs", json={"seed": 3, "scenario_ids": ["TOK-05", "GRD-01"]}).json()
    assert {x["id"] for x in r["results"]} == {"TOK-05", "GRD-01"} and r["summary"]["passed"] == 2
    assert user.client.get(f"/red-team/runs/{r['id']}").json()["seed"] == 3
