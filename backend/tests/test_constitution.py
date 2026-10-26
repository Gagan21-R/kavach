"""Deterministic Constitution engine (no HTTP, no database)."""
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from app.engine.constitution import ActionRequest, earliest_expiry, evaluate
from app.engine.hosts import host_matches, normalize_host
from app.vocab import Decision

NOW = datetime(2026, 10, 26, 12, 0, tzinfo=timezone.utc)


@dataclass
class R:
    id: str
    effect: str
    data_categories: list
    purposes: list = field(default_factory=list)
    recipients: list = field(default_factory=list)
    actions: list = field(default_factory=list)
    expires_at: datetime | None = None
    active: bool = True


def req(purpose="navigation", dest="maps.example.com", cats=("location",), action="transfer_data"):
    return ActionRequest(action, dest, purpose, tuple(cats))


def test_same_data_allowed_for_one_purpose_denied_for_another():
    rules = [
        R("allow-nav", "ALLOW", ["location"], purposes=["navigation"]),
        R("deny-ads", "DENY", ["location"], purposes=["advertising"]),
    ]
    nav = evaluate(rules, req("navigation"), NOW)
    ads = evaluate(rules, req("advertising", dest="ads.example.net"), NOW)
    assert nav.decision == Decision.ALLOW and nav.deciding_rule_ids == ["allow-nav"]
    assert ads.decision == Decision.BLOCK and ads.deciding_rule_ids == ["deny-ads"]
    assert "prohibited" in ads.reasons[0]


def test_deny_beats_a_more_specific_allow():
    rules = [
        R("deny-all-location", "DENY", ["location"]),
        R("allow-maps", "ALLOW", ["location"], purposes=["navigation"], recipients=["maps.example.com"]),
    ]
    result = evaluate(rules, req(), NOW)
    assert result.decision == Decision.BLOCK
    assert result.deciding_rule_ids == ["deny-all-location"]


def test_no_rule_means_review_not_allow():
    result = evaluate([], req(), NOW)
    assert result.decision == Decision.REVIEW and result.approvable
    assert "sensitive" in result.reasons[0]


def test_require_approval_gives_approvable_review():
    result = evaluate([R("ask", "REQUIRE_APPROVAL", ["biometrics"])], req(cats=("biometrics",)), NOW)
    assert result.decision == Decision.REVIEW and result.approvable
    assert result.deciding_rule_ids == ["ask"]


def test_require_approval_beats_allow():
    rules = [R("allow", "ALLOW", ["contacts"]), R("ask", "REQUIRE_APPROVAL", ["contacts"])]
    assert evaluate(rules, req(cats=("contacts",)), NOW).decision == Decision.REVIEW


def test_missing_information_is_review_and_not_approvable():
    result = evaluate([R("allow", "ALLOW", ["*"])], ActionRequest("transfer_data", "maps.example.com", "", ()), NOW)
    assert result.decision == Decision.REVIEW and not result.approvable
    assert "purpose" in result.reasons[0] and "data_categories" in result.reasons[0]


def test_expired_and_inactive_rules_are_ignored():
    rules = [
        R("expired-allow", "ALLOW", ["location"], expires_at=NOW - timedelta(seconds=1)),
        R("inactive-deny", "DENY", ["location"], active=False),
    ]
    assert evaluate(rules, req(), NOW).decision == Decision.REVIEW


def test_one_blocked_category_blocks_the_whole_action():
    rules = [R("allow-loc", "ALLOW", ["location"]), R("deny-contacts", "DENY", ["contacts"])]
    result = evaluate(rules, req(cats=("location", "contacts")), NOW)
    assert result.decision == Decision.BLOCK
    by_cat = {o.category: o.decision for o in result.outcomes}
    assert by_cat == {"location": Decision.ALLOW, "contacts": Decision.BLOCK}


def test_recipient_and_action_scoping():
    rules = [R("allow", "ALLOW", ["email"], recipients=["*.booking.example"], actions=["submit_form"])]
    assert evaluate(rules, req(cats=("email",), dest="api.booking.example", action="submit_form"), NOW).decision == Decision.ALLOW
    assert evaluate(rules, req(cats=("email",), dest="booking.example", action="submit_form"), NOW).decision == Decision.ALLOW
    assert evaluate(rules, req(cats=("email",), dest="evil.example", action="submit_form"), NOW).decision == Decision.REVIEW
    assert evaluate(rules, req(cats=("email",), dest="api.booking.example", action="transfer_data"), NOW).decision == Decision.REVIEW


def test_wildcard_deny_to_a_recipient_blocks_every_category():
    rules = [R("allow", "ALLOW", ["email"]), R("no-adnet", "DENY", ["*"], recipients=["*.adnet.example"])]
    assert evaluate(rules, req(cats=("email",), dest="t.adnet.example"), NOW).decision == Decision.BLOCK


def test_earliest_expiry_of_deciding_rules():
    soon, later = NOW + timedelta(minutes=1), NOW + timedelta(hours=1)
    rules = [R("a", "ALLOW", ["email"], expires_at=later), R("b", "ALLOW", ["email"], expires_at=soon)]
    assert earliest_expiry(rules, ["a", "b"]) == soon
    assert earliest_expiry(rules, []) is None


def test_host_helpers():
    assert normalize_host("https://Maps.Example.com/privacy") == "maps.example.com"
    assert normalize_host("localhost") is None
    assert normalize_host("evil.com@maps.example.com") is None
    assert host_matches("*.example.com", "a.b.example.com")
    assert not host_matches("*.example.com", "example.com.evil.net")
    assert not host_matches("maps.example.com", "evilmaps.example.com")
