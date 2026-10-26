"""Guardian decisions: DENY precedence, approvals, policy checks (acceptance tests 3, 17)."""
from app.gateway import adapters
from tests.conftest import action, execute_body


def setup(make_actor, *rules):
    user = make_actor()
    for effect, cats, kw in rules:
        user.rule(effect, cats, **kw)
    policy_id = user.policy()
    agent_id, agent = user.agent()
    return user, agent, agent_id, policy_id


def test_explicit_prohibition_blocks_and_issues_nothing(make_actor):
    user, agent, _, policy_id = setup(
        make_actor,
        ("ALLOW", ["location"], {}),
        ("DENY", ["location"], {"purposes": ["advertising"]}),
    )
    r = agent.post("/guardian/authorize", json=action(policy_id, purpose="advertising"))
    assert r.status_code == 403
    body = r.json()
    assert body["decision"] == "BLOCK" and "token" not in body
    assert body["evaluation"]["deciding_rule_ids"]
    assert user.client.get("/guardian/tokens").json() == []
    assert adapters.CALL_LOG == []


def test_evaluate_is_a_dry_run_with_explanation(make_actor):
    user, agent, _, policy_id = setup(make_actor, ("ALLOW", ["location"], {"purposes": ["navigation"]}))
    r = agent.post("/guardian/evaluate", json=action(policy_id))
    body = r.json()
    assert body["decision"] == "ALLOW"
    assert body["outcomes"][0]["reason"].startswith("'location' for 'navigation'")
    assert body["policy_hash"] and body["constitution_version"] >= 1
    assert user.client.get("/guardian/tokens").json() == []


def test_model_recommendations_have_no_channel_into_guardian(make_actor):
    """There is no field through which an LLM verdict could override a user rule."""
    _, agent, _, policy_id = setup(make_actor, ("DENY", ["location"], {}))
    for field in ("judge_recommendation", "risk_score", "override", "decision"):
        r = agent.post("/guardian/authorize", json=action(policy_id, **{field: "ALLOW"}))
        assert r.status_code == 422, field


def test_require_approval_flow(make_actor):
    user, agent, agent_id, policy_id = setup(make_actor, ("REQUIRE_APPROVAL", ["contacts"], {}))
    body = action(policy_id, purpose="service_delivery", categories=["contacts"])

    pending = agent.post("/guardian/authorize", json=body)
    assert pending.status_code == 202
    approval_id = pending.json()["approval_request_id"]
    # Asking again does not pile up duplicate requests.
    assert agent.post("/guardian/authorize", json=body).json()["approval_request_id"] == approval_id

    # The agent cannot redeem an approval the user has not granted.
    early = agent.post("/guardian/authorize", json={**body, "approval_id": approval_id})
    assert early.status_code == 409

    assert user.client.post(f"/guardian/approvals/{approval_id}/approve").status_code == 200
    granted = agent.post("/guardian/authorize", json={**body, "approval_id": approval_id})
    assert granted.status_code == 201, granted.text
    token = granted.json()["token"]
    assert granted.json()["token_info"]["approval_id"] == approval_id

    r = agent.post("/gateway/execute", json=execute_body(purpose="service_delivery", categories=["contacts"]),
                   headers={"X-Consent-Token": token})
    assert r.status_code == 200, r.text

    # One approval, one token.
    again = agent.post("/guardian/authorize", json={**body, "approval_id": approval_id})
    assert again.status_code == 409 and "used" in again.json()["evaluation"]["reasons"][0]


def test_approval_scope_cannot_be_widened(make_actor):
    user, agent, _, policy_id = setup(make_actor)
    body = action(policy_id, purpose="service_delivery", categories=["contacts"])
    approval_id = agent.post("/guardian/authorize", json=body).json()["approval_request_id"]
    user.client.post(f"/guardian/approvals/{approval_id}/approve")
    wider = agent.post("/guardian/authorize", json={**body, "data_categories": ["contacts", "photos"], "approval_id": approval_id})
    assert wider.status_code == 409
    other_purpose = agent.post("/guardian/authorize", json={**body, "purpose": "marketing", "approval_id": approval_id})
    assert other_purpose.status_code == 409


def test_approval_needs_step_up_and_denial_is_final(make_actor, frozen):
    user, agent, _, policy_id = setup(make_actor)
    body = action(policy_id, categories=["biometrics"], purpose="security")
    approval_id = agent.post("/guardian/authorize", json=body).json()["approval_request_id"]
    frozen.advance(minutes=6)
    r = user.client.post(f"/guardian/approvals/{approval_id}/approve")
    assert r.json()["error"]["code"] == "STEP_UP_REQUIRED"
    assert user.client.post(f"/guardian/approvals/{approval_id}/deny").json()["status"] == "DENIED"
    assert user.client.post(f"/guardian/approvals/{approval_id}/approve").status_code == 409


def test_approval_expires(make_actor, frozen):
    user, agent, _, policy_id = setup(make_actor)
    approval_id = agent.post("/guardian/authorize", json=action(policy_id)).json()["approval_request_id"]
    frozen.advance(minutes=16)
    user.step_up()
    assert user.client.post(f"/guardian/approvals/{approval_id}/approve").json()["error"]["code"] == "APPROVAL_EXPIRED"


def test_policy_change_after_approval_invalidates_it(make_actor):
    user, agent, _, policy_id = setup(make_actor)
    body = action(policy_id)
    approval_id = agent.post("/guardian/authorize", json=body).json()["approval_request_id"]
    user.client.post(f"/guardian/approvals/{approval_id}/approve")
    user.client.post(f"/policies/{policy_id}/snapshots", json={"text": "New terms: we share location with AI partners."})
    r = agent.post("/guardian/authorize", json={**body, "approval_id": approval_id})
    assert r.status_code == 409


def test_destination_outside_referenced_policy_is_not_approvable(make_actor):
    _, agent, _, policy_id = setup(make_actor, ("ALLOW", ["location"], {}))
    r = agent.post("/guardian/authorize", json=action(policy_id, destination="tracker.adnet.example"))
    assert r.status_code == 409
    assert "not covered by the referenced policy" in r.json()["evaluation"]["reasons"][0]


def test_policy_awaiting_reassessment_blocks_new_tokens_until_user_reviews(make_actor):
    user, agent, _, policy_id = setup(make_actor, ("ALLOW", ["location"], {"purposes": ["navigation"]}))
    user.client.post(f"/policies/{policy_id}/snapshots", json={"text": "We now sell location data."})
    assert agent.post("/guardian/authorize", json=action(policy_id)).status_code == 409
    user.step_up()
    assert user.client.post(f"/policies/{policy_id}/reassess").json()["requires_reassessment"] is False
    assert agent.post("/guardian/authorize", json=action(policy_id)).status_code == 201


def test_deny_still_wins_over_policy_problems(make_actor):
    user, agent, _, policy_id = setup(make_actor, ("DENY", ["location"], {}))
    user.client.post(f"/policies/{policy_id}/snapshots", json={"text": "changed"})
    r = agent.post("/guardian/authorize", json=action(policy_id))
    assert r.status_code == 403 and r.json()["decision"] == "BLOCK"
