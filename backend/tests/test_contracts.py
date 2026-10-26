"""Agent output contracts: invalid agent outputs are rejected (acceptance test 2)."""
import copy
import json

import pytest

from app.schemas.agents import AgentName, AgentOutputError, validate_agent_output

H = "a" * 64
SPAN = {"snapshot_id": "s1", "clause_id": "c3", "start": 10, "end": 52, "quote": "we may share your contacts with partners"}


def meta(agent):
    return {"agent": agent, "agent_version": "1", "model": "offline-rules", "run_id": "run-1", "policy_hash": H}


def prosecutor(**finding_overrides):
    finding = {"id": "f1", "category": "contacts", "claim": "Contacts are shared with partners", "severity": "HIGH",
               "status": "DIRECT", "citations": [SPAN], "reasoning": "The clause permits sharing contacts."}
    finding.update(finding_overrides)
    return {"meta": meta("prosecutor"), "charges": [finding]}


def judge(**overrides):
    out = {
        "meta": meta("judge"),
        "recommendation": "REVIEW",
        "category_map": [{"category": "contacts", "risk_level": "high", "finding_ids": ["f1"], "explanation": "shared"}],
        "limitations": ["Signals, not legal advice."],
    }
    out.update(overrides)
    return out


def rejected(agent, raw) -> list[str]:
    with pytest.raises(AgentOutputError) as e:
        validate_agent_output(agent, raw)
    return e.value.errors


def test_valid_prosecutor_output_passes():
    out = validate_agent_output(AgentName.PROSECUTOR, prosecutor())
    assert out.charges[0].citations[0].clause_id == "c3"


def test_finding_without_citation_must_be_marked_unsupported():
    errs = rejected(AgentName.PROSECUTOR, prosecutor(citations=[]))
    assert any("cite source text or be marked UNSUPPORTED" in e for e in errs)
    validate_agent_output(AgentName.PROSECUTOR, prosecutor(citations=[], status="UNSUPPORTED"))


def test_unknown_fields_are_rejected():
    raw = prosecutor()
    raw["authorize"] = True
    assert rejected(AgentName.PROSECUTOR, raw)


def test_malformed_json_is_rejected():
    assert "not valid JSON" in rejected(AgentName.PROSECUTOR, "{charges: [")[0]
    assert rejected(AgentName.PROSECUTOR, json.dumps(["not", "an", "object"]))


def test_role_escalation_is_rejected():
    raw = judge()
    raw["meta"]["agent"] = "sentinel"
    # A Sentinel-labelled payload cannot be accepted as the Judge's output, and vice versa.
    assert rejected(AgentName.JUDGE, raw)
    errs = rejected(AgentName.SENTINEL, {"meta": meta("judge"), "sanitized_text_hash": H, "signals": [], "limitations": ["x"]})
    assert "expected 'sentinel'" in errs[0]


def test_inverted_span_is_rejected():
    bad = dict(SPAN, start=60, end=10)
    assert rejected(AgentName.PROSECUTOR, prosecutor(citations=[bad]))


def test_defense_justification_needs_evidence():
    raw = {"meta": meta("defense"), "responses": [
        {"finding_id": "f1", "position": "justified", "argument": "needed for the service", "status": "INTERPRETATION", "citations": []}
    ]}
    assert any("must cite" in e for e in rejected(AgentName.DEFENSE, raw))


def test_judge_cannot_allow_with_unresolved_disagreement_or_missing_info():
    dis = [{"finding_id": "f1", "prosecutor_view": "excessive", "defense_view": "needed", "resolved": False}]
    assert rejected(AgentName.JUDGE, judge(recommendation="ALLOW", disagreements=dis))
    assert rejected(AgentName.JUDGE, judge(recommendation="ALLOW", missing_information=["retention period"]))
    validate_agent_output(AgentName.JUDGE, judge(recommendation="REVIEW", disagreements=dis))


def test_judge_category_map_has_no_duplicates():
    cm = judge()["category_map"] * 2
    assert rejected(AgentName.JUDGE, judge(category_map=cm))


def test_confidence_value_requires_a_basis():
    bad = [{"component": "evidence_support", "value": 0.9, "basis": "not_available", "explanation": "x"}]
    assert rejected(AgentName.JUDGE, judge(confidence=bad))
    ok = [{"component": "evidence_support", "value": None, "basis": "not_available", "explanation": "not calibrated yet"}]
    validate_agent_output(AgentName.JUDGE, judge(confidence=ok))


def test_auditor_verdict_consistency():
    base = {"meta": meta("auditor"), "explanation": "checked"}
    assert rejected(AgentName.AUDITOR, {**base, "verdict": "FAIL", "issues": []})
    assert rejected(AgentName.AUDITOR, {**base, "verdict": "ABSTAIN"})
    high = [{"kind": "unsupported_claim", "severity": "HIGH", "explanation": "no span supports f1"}]
    assert rejected(AgentName.AUDITOR, {**base, "verdict": "PASS", "issues": high})
    out = validate_agent_output(AgentName.AUDITOR, {**base, "verdict": "ABSTAIN", "abstain_reason": "policy text truncated"})
    assert out.verdict == "ABSTAIN"
    validate_agent_output(AgentName.AUDITOR, {**base, "verdict": "FAIL", "issues": high})


def test_watchman_unknown_is_never_unchanged():
    base = {"meta": meta("watchman"), "previous_hash": H}
    assert rejected(AgentName.WATCHMAN, {**base, "status": "UNKNOWN", "new_hash": H, "error": "timeout"})
    assert rejected(AgentName.WATCHMAN, {**base, "status": "UNKNOWN"})
    assert rejected(AgentName.WATCHMAN, {**base, "status": "NO_CHANGE", "new_hash": "b" * 64})
    assert rejected(AgentName.WATCHMAN, {**base, "status": "CHANGED", "new_hash": "b" * 64, "changes": []})
    validate_agent_output(AgentName.WATCHMAN, {**base, "status": "UNKNOWN", "error": "HTTP 503"})


def test_validation_does_not_mutate_input():
    raw = prosecutor()
    snapshot = copy.deepcopy(raw)
    validate_agent_output(AgentName.PROSECUTOR, raw)
    assert raw == snapshot
