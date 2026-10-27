"""Rule groups (deny by default inside a group), their use by the Guardian, site reviews and the gateway, the
improved Emergency Stop, and the compact Courtroom."""
from fastapi.testclient import TestClient

from tests.conftest import action

LOCATION_OK = {"location": {"service": "OK"}}  # "service" covers navigation, service delivery, account, security


def make_group(user, name="Maps", choices=LOCATION_OK, expect=201):
    r = user.client.post("/rule-groups", json={"name": name, "choices": choices})
    assert r.status_code == expect, r.text
    return r.json()


def assign(user, domain, group_id):
    r = user.client.post("/rule-groups/assign", json={"domain": domain, "group_id": group_id})
    assert r.status_code == 200, r.text
    return r.json()


def test_groups_store_only_ok_and_ask_and_loosening_needs_step_up(make_actor, frozen):
    u = make_actor()
    frozen.advance(minutes=6)  # the sign-in no longer counts as recent re-authentication
    r = u.client.post("/rule-groups", json={"name": "Maps", "choices": LOCATION_OK})
    assert r.status_code == 403 and r.json()["error"]["code"] == "STEP_UP_REQUIRED"
    u.step_up()
    g = make_group(u, choices={"location": {"service": "OK", "ads": "NEVER"}, "basic": {"analytics": "ASK"}})
    assert g["choices"] == {"location": {"service": "OK"}, "basic": {"analytics": "ASK"}}  # NEVER is simply absent
    assert g["allowed"] == 1 and g["ask"] == 1
    assert u.client.post("/rule-groups", json={"name": "Maps", "choices": {}}).status_code == 409
    frozen.advance(minutes=6)
    r = u.client.post("/rule-groups/assign", json={"domain": "maps.example.com", "group_id": g["id"]})
    assert r.status_code == 403 and r.json()["error"]["code"] == "STEP_UP_REQUIRED"


def test_guardian_uses_the_sites_group_and_denies_anything_not_allowed(make_actor):
    u = make_actor()
    policy_id = u.policy()  # maps.example.com, location for navigation
    _, agent = u.agent()
    # General rules have nothing for location, so it needs approval.
    general = agent.post("/guardian/authorize", json=action(policy_id))
    assert general.status_code == 202 and general.json()["decision"] == "REVIEW"
    g = make_group(u)
    assert assign(u, "https://www.maps.example.com/", g["id"]) == {"domain": "example.com", "group_id": g["id"], "label": "Maps group"}
    allowed = agent.post("/guardian/authorize", json=action(policy_id))
    assert allowed.status_code == 201 and allowed.json()["decision"] == "ALLOW"
    denied = agent.post("/guardian/authorize", json=action(policy_id, purpose="advertising"))
    assert denied.status_code == 403 and denied.json()["decision"] == "BLOCK"
    assert "isn't something you allowed for the Maps group" in " ".join(denied.json()["evaluation"]["reasons"])
    # Back to the general rules: approval needed again.
    assign(u, "maps.example.com", None)
    assert agent.post("/guardian/authorize", json=action(policy_id)).status_code == 202


def test_a_token_stops_working_when_its_site_moves_to_a_stricter_group(make_actor):
    u = make_actor()
    u.rule("ALLOW", ["location"], purposes=["navigation"], recipients=["maps.example.com"])
    policy_id = u.policy()
    _, agent = u.agent()
    token = agent.post("/guardian/authorize", json=action(policy_id)).json()["token"]
    strict = make_group(u, name="Strict", choices={"basic": {"service": "OK"}})
    assign(u, "maps.example.com", strict["id"])
    agent.headers["X-Consent-Token"] = token
    r = agent.post("/gateway/execute", json={"action": "transfer_data", "destination": "maps.example.com", "purpose": "navigation",
                                             "data_categories": ["location"], "record_count": 1})
    assert r.status_code == 403 and r.json()["error"]["code"] == "RULES_NOW_DENY"


def test_group_is_shown_on_reviews_and_site_list_and_deleting_moves_sites_back(make_actor, monkeypatch):
    from app.acquire import discover as disc
    from app.acquire import service as acq

    text = "We collect your precise location at all times and share it with advertising partners. " * 8
    monkeypatch.setattr(acq, "acquire", lambda url, ota=None, allow_wayback=True: acq.Acquired(True, text, "DIRECT", url))
    monkeypatch.setattr(disc, "discover", lambda d: {"privacy": f"https://{d}/privacy", "terms": None})
    u = make_actor()
    g = make_group(u, name="Shopping", choices={"basic": {"service": "OK"}})
    r = u.client.post("/sites/track", json={"domain": "shop.example.org", "group_id": g["id"]})
    assert r.status_code == 201 and r.json()["rules"] == {"group_id": g["id"], "label": "Shopping group"}
    assert r.json()["status"] == "CONFLICT"  # location isn't allowed in Shopping, so it is denied
    listed = u.client.get("/sites").json()["sites"][0]
    assert listed["group"] == {"id": g["id"], "name": "Shopping"}
    groups = u.client.get("/rule-groups").json()
    assert groups["groups"][0]["sites"] == [{"domain": "example.org", "name": "example.org"}]
    d = u.client.delete(f"/rule-groups/{g['id']}")
    assert d.status_code == 200 and d.json()["sites_moved_to_general"] == ["example.org"]
    assert u.client.post("/sites/review", json={"domain": "example.org"}).json()["rules"]["label"] == "General rules"


def test_general_preferences_ignore_group_rules(make_actor):
    u = make_actor()
    u.client.post("/onboarding", json={"choices": {"location": {"ads": "NEVER"}}})
    make_group(u, name="Work", choices={"location": {"ads": "OK"}})
    current = u.client.get("/onboarding").json()["current"]
    assert current["location"] == {"ads": "NEVER"}


# --- Emergency stop ----------------------------------------------------------------------------------------------

def test_emergency_stop_preview_then_contains_everything_and_lists_what_it_blocked(make_actor, app):
    u = make_actor()
    policy_id = u.policy()
    _, agent = u.agent()
    assert agent.post("/guardian/authorize", json=action(policy_id)).status_code == 202  # a pending approval
    ext = u.client.post("/extension/pair", json={"name": "Chrome · x"}).json()["key"]
    impact = u.client.get("/emergency-stop/status").json()["impact"]
    assert impact["agents"] == 1 and impact["pending_approvals"] == 1 and impact["extensions"] == 1
    r = u.client.post("/emergency-stop/activate", json={"reason": "an agent is acting strangely", "disconnect_extensions": True})
    assert r.status_code == 201
    steps = {a["step"]: a["count"] for a in r.json()["actions"]}
    assert steps["deny_pending_approvals"] == 1 and steps["disconnect_extensions"] == 1
    assert u.client.get("/guardian/approvals").json()[0]["status"] == "DENIED"
    c = TestClient(app)
    c.headers["X-Extension-Key"] = ext
    assert c.get("/ext/me").status_code == 401
    assert agent.post("/guardian/authorize", json=action(policy_id)).json()["decision"] == "BLOCK"
    status = u.client.get("/emergency-stop/status").json()
    assert status["frozen"] and status["impact"] is None
    assert status["blocked_since_stop"] and status["blocked_since_stop"][0]["actor"] == "agent"


# --- Compact Courtroom -------------------------------------------------------------------------------------------

def test_courtroom_trial_reviews_pasted_text_without_tracking_it(make_actor):
    u = make_actor()
    r = u.client.post("/sites/trial", json={"name": "FlashLight", "text": (
        "FlashLight Privacy Policy\nWe access your contacts and upload your entire address book to improve our services.\n"
        "We may share your information with advertising partners and data brokers.\nWe retain your data indefinitely.")})
    assert r.status_code == 200
    body = r.json()
    assert body["recommendation"] == "BLOCK" and body["recommendation_words"] == "Not recommended"
    assert [s["agent"] for s in body["how_decided"]][0] == "Sentinel" and body["transcript"]
    assert u.client.get("/policies").json() == []


def test_group_created_with_its_websites_and_bulk_moves(make_actor):
    u = make_actor()
    g = u.client.post("/rule-groups", json={"name": "Shopping", "choices": {"basic": {"service": "OK"}},
                                            "sites": ["https://www.flipkart.com/", "amazon.in"]}).json()
    assert [s["domain"] for s in g["sites"]] == ["amazon.in", "flipkart.com"]
    other = make_group(u, name="Social", choices={})
    r = u.client.post("/rule-groups/assign-many", json={"domains": ["flipkart.com", "instagram.com"], "group_id": other["id"]})
    assert r.status_code == 200 and r.json()["moved"] == ["flipkart.com", "instagram.com"]
    groups = {x["name"]: [s["domain"] for s in x["sites"]] for x in u.client.get("/rule-groups").json()["groups"]}
    assert groups == {"Shopping": ["amazon.in"], "Social": ["flipkart.com", "instagram.com"]}
    upd = u.client.put(f"/rule-groups/{g['id']}", json={"sites": []}).json()  # empty the group: back to general
    assert upd["sites"] == []


# --- Notifications -----------------------------------------------------------------------------------------------

def test_notifications_for_changes_and_approvals_then_read_and_clear(make_actor):
    from app.demo import fixtures as fx

    u = make_actor()
    policy_id = u.policy(text=fx.MAPSCO["text"])
    _, agent = u.agent()
    agent.post("/guardian/authorize", json=action(policy_id))  # needs approval
    agent.post("/guardian/authorize", json=action(policy_id))  # same request again: no duplicate notice
    u.client.post(f"/policies/{policy_id}/snapshots", json={"text": fx.MAPSCO_BETRAYAL})  # material change
    n = u.client.get("/notifications").json()
    kinds = [i["kind"] for i in n["items"]]
    assert n["unread_count"] == 2 and sorted(kinds) == ["approval_needed", "policy_changed"]
    changed = next(i for i in n["items"] if i["kind"] == "policy_changed")
    assert changed["tone"] == "bad" and changed["section"] == "watchman"
    assert u.client.post(f"/notifications/{changed['id']}/read").json()["read"] is True
    assert u.client.get("/notifications").json()["unread_count"] == 1
    assert u.client.post("/notifications/read-all").json() == {"cleared": 1}
    assert u.client.get("/notifications").json() == {"unread_count": 0, "items": []}
    other = make_actor()
    assert other.client.post(f"/notifications/{changed['id']}/read").status_code == 404  # never another user's


# --- Test history and postmortem reports -------------------------------------------------------------------------

def test_red_team_runs_have_a_postmortem_with_policies_steps_and_verdicts(make_actor, tmp_path, monkeypatch):
    monkeypatch.setenv("CC_TEST_HISTORY_DIR", str(tmp_path))
    u = make_actor()
    run = u.client.post("/red-team/runs", json={"seed": 1, "scenario_ids": ["TOK-05", "INJ-06", "GRD-03"]}).json()
    listed = u.client.get("/test-history").json()["runs"]
    assert [(r["id"], r["kind"], r["total"], r["missed"]) for r in listed] == [(run["id"], "redteam", 3, 1)]

    rep = u.client.get(f"/test-history/redteam/{run['id']}").json()
    assert rep["traced"] and rep["counts"] == {"MISSED": 1, "FALSE_ALARM": 0, "INCONCLUSIVE": 0, "SAFE": 2}
    first = rep["results"][0]  # what went wrong comes first
    assert first["id"] == "INJ-06" and first["outcome"] == "MISSED" and first["root_cause"] and first["follow_up"]
    replay = next(r for r in rep["results"] if r["id"] == "TOK-05")
    assert replay["outcome"] == "SAFE" and replay["kavach_did"].startswith("Checked the agent's one-time permission")
    assert [s["outcome"] for s in replay["steps"]][-1] == "REPLAYED" and replay["steps"][-1]["actor"] == "AI agent"
    assert all("password" not in s["request"] and "api_key" not in str(s) for s in replay["steps"])
    trap = next(p for p in rep["policies"] if p["name"] == "QuickDeals")
    assert trap["verdict"]["recommendation"] and "GRD-03" in trap["scenarios"]
    # Someone else's run is not visible.
    assert make_actor().client.get(f"/test-history/redteam/{run['id']}").status_code == 404


def test_automated_test_runs_are_listed_and_reported_by_area(make_actor, tmp_path, monkeypatch):
    import json

    monkeypatch.setenv("CC_TEST_HISTORY_DIR", str(tmp_path))
    d = tmp_path / "pytest"
    d.mkdir()
    rec = {"id": "20261027-101500-ab12", "kind": "pytest", "started_at": "2026-10-27T10:15:00+00:00", "duration_s": 12.5,
           "commit": "59b9f8e", "dirty": True, "totals": {"total": 2, "passed": 1, "failed": 1, "error": 0, "skipped": 0},
           "tests": [{"id": "tests/test_tokens.py::test_replay", "area": "One-time agent permissions", "name": "Replay",
                      "doc": "", "outcome": "passed", "duration_s": 0.1, "message": ""},
                     {"id": "tests/test_court.py::test_scores", "area": "Court (six agents)", "name": "Scores",
                      "doc": "", "outcome": "failed", "duration_s": 0.2, "message": "AssertionError: 54 != 60"}]}
    (d / f"{rec['id']}.json").write_text(json.dumps(rec))
    u = make_actor()
    runs = u.client.get("/test-history").json()["runs"]
    assert [(r["kind"], r["passed"], r["failed"], r["commit"]) for r in runs] == [("pytest", 1, 1, "59b9f8e")]
    rep = u.client.get(f"/test-history/pytest/{rec['id']}").json()
    assert rep["areas"][0]["area"] == "Court (six agents)" and rep["failures"][0]["message"].startswith("AssertionError")
    assert u.client.get("/test-history/pytest/..%2F..%2Fsecrets").status_code == 404
    assert u.client.get("/test-history/pytest/20990101-000000-zzzz").status_code == 404
