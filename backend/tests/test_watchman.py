"""Watchman change detection (acceptance tests 5, 6, 7)."""
from app.demo import fixtures as fx
from app.watchman import service as watchman
from app.watchman.diff import compare
from app.watchman.fetch import FetchResult, fetch_policy
from tests.conftest import action, execute_body

BASE = fx.MAPSCO["text"]


def test_formatting_only_changes_do_not_alert():
    for variant in (fx.MAPSCO_REFORMATTED, BASE.upper(), BASE.replace("\n", "\n\n   "), BASE.replace("'", "’")):
        assert compare(BASE, variant)["classification"] == "FORMATTING_ONLY"


def test_classifications_on_labelled_cases():
    cases = {
        fx.MAPSCO_BETRAYAL: "POTENTIALLY_MATERIAL",
        BASE.replace("We do not sell your location data.", "We sell your location data."): "POTENTIALLY_MATERIAL",
        BASE.replace("30 days", "5 years"): "POTENTIALLY_MATERIAL",
        BASE.replace("We do not sell your location data.\n", ""): "POTENTIALLY_MATERIAL",
        BASE.replace("send receipts and security alerts", "send you receipts and account security alerts"): "WORDING_NO_MATERIAL_CHANGE",
        BASE.replace("We collect your location only to provide navigation", "We may collect your location from time to time to provide navigation"): "AMBIGUOUS",
    }
    for new, expected in cases.items():
        assert compare(BASE, new)["classification"] == expected, new


def _setup(make_actor):
    user = make_actor()
    user.rule("ALLOW", ["location"], purposes=["navigation"], recipients=["maps.example.com"])
    pid = user.policy(text=BASE)
    agent_id, agent = user.agent()
    tok = agent.post("/guardian/authorize", json=action(pid)).json()
    return user, agent, pid, tok


def test_formatting_change_keeps_tokens_valid(make_actor):
    user, agent, pid, tok = _setup(make_actor)
    r = user.client.post(f"/policies/{pid}/snapshots", json={"text": fx.MAPSCO_REFORMATTED}).json()
    assert r["watch_event"]["classification"] == "FORMATTING_ONLY" and r["requires_reassessment"] is False
    assert agent.post("/gateway/execute", json=execute_body(), headers={"X-Consent-Token": tok["token"]}).status_code == 200


def test_material_change_shows_old_new_text_affected_rules_and_suspends_tokens(make_actor):
    user, agent, pid, tok = _setup(make_actor)
    rule_id = user.client.get("/consent/rules").json()[0]["id"]
    unrelated = user.rule("REQUIRE_APPROVAL", ["contacts"])["id"]
    elsewhere = user.rule("DENY", ["*"], recipients=["*.adnet.example"])["id"]
    r = user.client.post(f"/policies/{pid}/snapshots", json={"text": fx.MAPSCO_BETRAYAL}).json()
    ev = r["watch_event"]
    assert ev["classification"] == "POTENTIALLY_MATERIAL" and r["requires_reassessment"]
    added = [c for c in ev["changes"] if c["classification"] == "POTENTIALLY_MATERIAL"][0]
    assert "AI partners" in added["new_text"] and added["old_text"] == ""
    assert {"ai_training", "location"} <= set(added["categories"])
    assert any(d["op"] == "insert" for d in added["diff"])
    assert rule_id in ev["affected_rule_ids"]
    assert unrelated not in ev["affected_rule_ids"] and elsewhere not in ev["affected_rule_ids"]
    assert tok["token_info"]["id"] in ev["affected_token_ids"]
    assert ev["confidence"]["basis"] == "heuristic"
    assert any(rec["id"] == "withdraw_consent" for rec in ev["recommendations"])
    blocked = agent.post("/gateway/execute", json=execute_body(), headers={"X-Consent-Token": tok["token"]})
    assert blocked.json()["error"]["code"] == "STALE_POLICY"
    # A fresh analysis of the new version is attached.
    assert user.client.get(f"/policies/{pid}/analysis").json()["snapshot_version"] == 2


def test_failed_retrieval_is_unknown_not_unchanged(make_actor):
    user = make_actor()
    r = user.client.post("/policies", json={"name": "Local", "url": "http://127.0.0.1/privacy", "text": BASE})
    pid = r.json()["id"]
    ev = user.client.post(f"/policies/{pid}/check").json()
    assert ev["status"] == "UNKNOWN" and "non-public" in ev["error"]
    assert user.client.get(f"/policies/{pid}").json()["watch_status"] == "UNKNOWN"


def test_policy_without_url_check_is_unknown(make_actor):
    user = make_actor()
    pid = user.policy()
    assert user.client.post(f"/policies/{pid}/check").json()["status"] == "UNKNOWN"


def test_check_with_successful_fetch(make_actor, Session):
    user = make_actor()
    pid = user.client.post("/policies", json={"name": "MapsCo", "url": "https://maps.example.com/privacy", "text": BASE}).json()["id"]
    with Session() as db:
        from app.models import PolicySource

        policy = db.get(PolicySource, pid)
        same = watchman.check_source(db, policy, fetcher=lambda url: FetchResult(True, text=BASE, final_url=url))
        assert same.status == "NO_CHANGE"
        changed = watchman.check_source(db, policy, fetcher=lambda url: FetchResult(True, text=fx.MAPSCO_BETRAYAL, final_url=url))
        assert changed.status == "CHANGED" and changed.classification == "POTENTIALLY_MATERIAL"
        db.commit()


def test_ssrf_targets_are_refused():
    for url in ("http://127.0.0.1/", "http://169.254.169.254/latest/meta-data", "http://10.0.0.5/", "file:///etc/passwd",
                "http://localhost:8000/", "http://user:pw@example.com/", "gopher://example.com/"):
        r = fetch_policy(url)
        assert not r.ok and r.error, url
