"""User A cannot read or modify User B's records (acceptance test 14)."""
from tests.conftest import action, execute_body


def test_user_cannot_touch_another_users_records(make_actor, granted):
    a, a_agent, a_agent_id, a_policy, a_token, a_token_info = granted()
    a_rule = a.client.get("/consent/rules").json()[0]
    snapshots = a.client.get(f"/policies/{a_policy}/snapshots").json()

    # A also has a pending approval.
    a_agent.post("/guardian/authorize", json=action(a_policy, categories=["contacts"]))
    a_approval = a.client.get("/guardian/approvals").json()[0]

    b = make_actor()
    b.step_up()
    c = b.client
    not_found = lambda r: r.status_code == 404  # noqa: E731

    # Reads
    assert c.get("/consent/rules").json() == []
    assert c.get("/policies").json() == []
    assert c.get("/guardian/tokens").json() == []
    assert c.get("/guardian/approvals").json() == []
    assert c.get("/agents").json() == []
    assert not_found(c.get(f"/policies/{a_policy}"))
    assert not_found(c.get(f"/policies/{a_policy}/snapshots"))
    assert not_found(c.get(f"/policies/{a_policy}/snapshots/{snapshots[0]['id']}"))
    assert not_found(c.get(f"/consent/rules/{a_rule['id']}/history"))
    assert all(e["actor_id"] != a.user_id for e in c.get("/audit/events").json())

    # Writes
    assert not_found(c.put(f"/consent/rules/{a_rule['id']}", json={"effect": "DENY", "data_categories": ["location"]}))
    assert not_found(c.delete(f"/consent/rules/{a_rule['id']}"))
    assert not_found(c.post(f"/policies/{a_policy}/snapshots", json={"text": "hijacked"}))
    assert not_found(c.post(f"/policies/{a_policy}/reassess"))
    assert not_found(c.post("/guardian/revoke", json={"token_id": a_token_info["id"]}))
    assert not_found(c.post("/guardian/revoke", json={"agent_id": a_agent_id}))
    assert not_found(c.post(f"/guardian/approvals/{a_approval['id']}/approve"))
    assert not_found(c.post(f"/guardian/approvals/{a_approval['id']}/deny"))
    assert not_found(c.post(f"/agents/{a_agent_id}/revoke"))
    assert b.client.post("/guardian/revoke", json={"all": True}).json()["revoked"] == 0

    # A's records are untouched.
    assert a.client.get("/consent/rules").json()[0]["active"] is True
    assert a.client.get("/guardian/tokens").json()[0]["revoked_at"] is None
    assert a.client.get("/guardian/approvals").json()[0]["status"] == "PENDING"


def test_agent_cannot_use_another_users_policy_or_token(make_actor, granted):
    a, a_agent, _, a_policy, a_token, _ = granted()
    b = make_actor()
    b.rule("ALLOW", ["location"], purposes=["navigation"])
    _, b_agent = b.agent()

    assert b_agent.post("/guardian/evaluate", json=action(a_policy)).status_code == 404
    assert b_agent.post("/guardian/authorize", json=action(a_policy)).status_code == 404

    r = b_agent.post("/gateway/execute", json=execute_body(), headers={"X-Consent-Token": a_token})
    assert r.status_code == 403 and r.json()["error"]["code"] == "WRONG_AGENT"

    # A's token is still intact for A.
    assert a_agent.post("/gateway/execute", json=execute_body(), headers={"X-Consent-Token": a_token}).status_code == 200


def test_second_agent_of_same_user_cannot_use_first_agents_token(granted):
    user, _, _, _, token, _ = granted()
    _, other_agent = user.agent("second")
    r = other_agent.post("/gateway/execute", json=execute_body(), headers={"X-Consent-Token": token})
    assert r.json()["error"]["code"] == "WRONG_AGENT"
