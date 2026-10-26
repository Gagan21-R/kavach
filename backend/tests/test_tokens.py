"""Consent token enforcement at the gateway (acceptance tests 3, 4, 17)."""
from datetime import timedelta

import pytest

from app import clock
from app.gateway import adapters
from app.guardian import tokens
from app.models import ConsentToken, TokenUse
from tests.conftest import action, execute_body


def run(agent, token, **kw):
    return agent.post("/gateway/execute", json=execute_body(**kw), headers={"X-Consent-Token": token})


def code(r):
    return r.json()["error"]["code"]


def test_valid_token_executes_once_then_replay_is_rejected(granted):
    _, agent, _, _, token, info = granted()
    assert info["max_uses"] == 1 and "secret" not in str(info)

    first = run(agent, token)
    assert first.status_code == 200, first.text
    assert first.json()["executed"] is True and first.json()["simulated"] is True
    assert len(adapters.CALL_LOG) == 1

    replay = run(agent, token)
    assert replay.status_code == 403 and code(replay) == "REPLAYED"
    assert replay.json()["error"]["executed"] is False
    assert len(adapters.CALL_LOG) == 1  # never reached the adapter


def test_expired_token_rejected(granted, frozen):
    _, agent, _, _, token, info = granted(ttl_seconds=60)
    frozen.advance(seconds=61)
    assert code(run(agent, token)) == "EXPIRED"
    assert adapters.CALL_LOG == []


def test_revoked_token_rejected(granted):
    user, agent, _, _, token, info = granted()
    r = user.client.post("/guardian/revoke", json={"token_id": info["id"], "reason": "changed my mind"})
    assert r.json()["revoked"] == 1 and "cannot be recalled" in r.json()["note"]
    rejected = run(agent, token)
    assert code(rejected) == "REVOKED" and "changed my mind" in rejected.json()["error"]["message"]
    assert adapters.CALL_LOG == []


@pytest.mark.parametrize(
    "override, expected",
    [
        ({"destination": "ads.example.net"}, "WRONG_DESTINATION"),
        ({"destination": "evil.maps.example.com"}, "WRONG_DESTINATION"),
        ({"purpose": "advertising"}, "WRONG_PURPOSE"),
        ({"categories": ["location", "contacts"]}, "SCOPE_EXCEEDED"),
        ({"act": "accept_terms"}, "WRONG_ACTION"),
        ({"record_count": 2}, "BUDGET_EXCEEDED"),
    ],
)
def test_wrong_scope_rejected(granted, override, expected):
    _, agent, _, _, token, _ = granted()
    r = run(agent, token, **override)
    assert r.status_code == 403 and code(r) == expected
    assert adapters.CALL_LOG == []
    # The legitimate use is still available afterwards: a rejected attempt does not burn the token.
    assert run(agent, token).status_code == 200


def test_multi_use_token_usage_and_record_budget(granted):
    _, agent, _, _, token, _ = granted(max_uses=3, max_records=10)
    assert run(agent, token, record_count=4).status_code == 200
    assert run(agent, token, record_count=4).status_code == 200
    assert code(run(agent, token, record_count=4)) == "BUDGET_EXCEEDED"
    assert run(agent, token, record_count=2).status_code == 200
    assert code(run(agent, token, record_count=1)) == "USAGE_EXHAUSTED"
    assert len(adapters.CALL_LOG) == 3


def test_stale_policy_token_rejected(granted):
    user, agent, _, policy_id, token, _ = granted()
    r = user.client.post(f"/policies/{policy_id}/snapshots", json={"text": "MapsCo now shares location with AI partners."})
    assert r.json()["requires_reassessment"] is True
    assert code(run(agent, token)) == "STALE_POLICY"

    # Even after the user reassesses, the old token stays bound to the old version.
    user.step_up()
    user.client.post(f"/policies/{policy_id}/reassess")
    assert code(run(agent, token)) == "STALE_POLICY"
    assert adapters.CALL_LOG == []


def test_identical_snapshot_does_not_invalidate(granted):
    user, agent, _, policy_id, token, _ = granted()
    from tests.conftest import POLICY_TEXT

    r = user.client.post(f"/policies/{policy_id}/snapshots", json={"text": POLICY_TEXT})
    assert r.json()["requires_reassessment"] is False
    assert run(agent, token).status_code == 200


def test_deny_added_after_issuance_blocks_at_the_boundary(granted):
    user, agent, _, _, token, _ = granted()
    user.rule("DENY", ["location"], recipients=["maps.example.com"])
    r = run(agent, token)
    assert code(r) == "RULES_NOW_DENY" and r.json()["error"]["decision"] == "BLOCK"
    assert adapters.CALL_LOG == []


def test_revoking_the_allow_rule_invalidates_outstanding_tokens(granted):
    user, agent, _, _, token, _ = granted()
    rule_id = user.client.get("/consent/rules").json()[0]["id"]
    user.client.delete(f"/consent/rules/{rule_id}")
    assert code(run(agent, token)) == "AUTHORIZATION_NO_LONGER_VALID"


def test_token_never_outlives_its_rule(make_actor, frozen):
    user = make_actor()
    rule_expiry = frozen.now + timedelta(seconds=30)
    user.rule("ALLOW", ["location"], purposes=["navigation"], expires_at=rule_expiry)
    policy_id = user.policy()
    _, agent = user.agent()
    info = agent.post("/guardian/authorize", json=action(policy_id, ttl_seconds=600)).json()["token_info"]
    assert info["expires_at"].startswith("2026-10-26T12:00:30")


def test_token_limits_are_enforced(granted, make_actor):
    user = make_actor()
    user.rule("ALLOW", ["location"], purposes=["navigation"])
    policy_id = user.policy()
    _, agent = user.agent()
    assert code(agent.post("/guardian/authorize", json=action(policy_id, ttl_seconds=86400))) == "TTL_TOO_LONG"
    assert code(agent.post("/guardian/authorize", json=action(policy_id, max_uses=10_000))) == "MAX_USES_TOO_HIGH"


@pytest.mark.parametrize("bad", ["", "garbage", "cct_unknown.secret", "cca_x.y"])
def test_malformed_or_unknown_tokens_rejected(granted, bad):
    _, agent, _, _, _, _ = granted()
    assert code(run(agent, bad)) == "INVALID_TOKEN"


def test_tampered_secret_rejected(granted):
    _, agent, _, _, token, _ = granted()
    assert code(run(agent, token[:-2] + "xx")) == "INVALID_TOKEN"


def test_revoked_agent_cannot_reach_gateway(granted):
    user, agent, agent_id, _, token, _ = granted()
    user.client.post(f"/agents/{agent_id}/revoke")
    r = run(agent, token)
    assert r.status_code == 401 and code(r) == "AGENT_UNAUTHENTICATED"
    assert user.client.get("/guardian/tokens").json()[0]["revocation_reason"] == "agent revoked"


def test_token_lifecycle_is_recorded(granted, Session):
    user, agent, _, _, token, info = granted(max_uses=2)
    run(agent, token)
    run(agent, token, destination="ads.example.net")
    user.client.post("/guardian/revoke", json={"token_id": info["id"]})
    run(agent, token)

    types = [e["event_type"] for e in user.client.get("/audit/events?limit=200").json()]
    for expected in ["token.issued", "gateway.executed", "gateway.blocked", "token.revoked"]:
        assert expected in types
    with Session() as db:
        outcomes = [u.outcome for u in db.query(TokenUse).filter_by(token_id=info["id"]).order_by(TokenUse.created_at)]
    assert outcomes == ["ACCEPTED", "WRONG_DESTINATION", "REVOKED"]


@pytest.mark.parametrize(
    "limits, first, second, expected",
    [
        # Plenty of record budget, so only the use-count guard can stop the second use.
        ({"max_uses": 1, "max_records": 100}, 1, 1, "REPLAYED"),
        # Plenty of uses, so only the record-budget guard can stop the second use.
        ({"max_uses": 5, "max_records": 10}, 6, 6, "BUDGET_EXCEEDED"),
    ],
)
def test_consume_is_atomic_against_stale_reads(granted, Session, limits, first, second, expected):
    """Two workers load the same token; the second conditional UPDATE must fail even though its view is stale."""
    _, _, _, _, _, info = granted(**limits)
    s1, s2 = Session(), Session()
    t1, t2 = s1.get(ConsentToken, info["id"]), s2.get(ConsentToken, info["id"])
    now = clock.utcnow()
    tokens.consume(s2, t2, first, now)
    s2.commit()
    assert t1.use_count == 0 and t1.records_used == 0  # s1 still thinks the token is untouched
    with pytest.raises(tokens.TokenRejected) as e:
        tokens.consume(s1, t1, second, now)
    assert e.value.code == expected
    s1.close()
    s2.close()
