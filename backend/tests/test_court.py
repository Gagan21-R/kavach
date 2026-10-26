"""Court pipeline: evidence-linked findings, auditor PASS/FAIL/ABSTAIN, Sentinel detection (acceptance tests 1, 2, 8, 9)."""
import hashlib

from app.court.pipeline import run_trial
from app.court.text import extract, split_clauses
from app.demo import fixtures as fx


def trial(text, name="Test", tamper=None):
    return run_trial(text, snapshot_id="s1", policy_hash=hashlib.sha256(text.encode()).hexdigest(), app_name=name, tamper=tamper)


def test_every_finding_cites_exact_source_text_or_is_unsupported():
    for text in (fx.FLASHLIGHT["text"], fx.MAPSCO["text"], fx.MAPSCO_BETRAYAL, fx.TRAP_PAGE):
        r = trial(text)
        canon = r["canonical_text"]
        for ch in r["prosecutor"]["charges"]:
            assert ch["citations"] or ch["status"] == "UNSUPPORTED"
            for c in ch["citations"]:
                assert canon[c["start"]:c["end"]] == c["quote"]
        assert all(c["citation_valid"] for c in r["clerk"]["checks"] if c["note"].startswith("prosecution"))


def test_flashlight_trial_matches_the_demo_script():
    r = trial(fx.FLASHLIGHT["text"], "FlashLight")
    assert r["summary"]["headline"] == "FlashLight wants to use your contacts. The Defense could not justify it. Excessive."
    assert r["summary"]["recommendation"] == "BLOCK" and r["summary"]["audit_verdict"] == "PASS"
    kinds = [m["agent"] for m in r["transcript"]]
    assert kinds[0] == "sentinel" and kinds[-2:] == ["judge", "auditor"]
    assert {"prosecutor", "defense", "evidence_clerk"} <= set(kinds)


def test_specific_purpose_is_justified_and_protective_clauses_are_not_charged():
    r = trial(fx.MAPSCO["text"], "MapsCo")
    assert [(c["category"]) for c in r["prosecutor"]["charges"]] == ["location"]
    assert r["defense"]["responses"][0]["position"] == "justified"
    assert r["summary"]["recommendation"] == "ALLOW"


def test_justification_is_not_borrowed_from_an_unrelated_clause():
    r = trial(fx.MAPSCO_BETRAYAL, "MapsCo")
    ai = next(c for c in r["prosecutor"]["charges"] if c["category"] == "ai_training")
    pos = {x["finding_id"]: x["position"] for x in r["defense"]["responses"]}
    assert pos[ai["id"]] == "not_justified"


def test_risk_score_follows_documented_method():
    r = trial(fx.FLASHLIGHT["text"])
    weights = {"high": 25, "medium": 12, "low": 4, "none": 0, "unknown": 3}
    expected = min(100, sum(weights[c["risk_level"]] for c in r["judge"]["category_map"]))
    assert r["judge"]["risk_score"]["value"] == expected
    assert all(c["basis"] in ("heuristic", "not_available") for c in r["judge"]["confidence"])


def test_auditor_detects_unsupported_claim():
    def tamper(name, out):
        if name.value == "prosecutor":
            out["charges"][0]["category"] = "biometrics"
        return out
    r = trial(fx.MAPSCO["text"], tamper=tamper)
    assert r["auditor"]["verdict"] == "FAIL"
    assert "unsupported_claim" in [i["kind"] for i in r["auditor"]["issues"]]


def test_auditor_detects_omitted_risk():
    def tamper(name, out):
        if name.value == "prosecutor":
            out["charges"] = [c for c in out["charges"] if c["category"] != "third_party_sharing"]
        return out
    r = trial(fx.FLASHLIGHT["text"], tamper=tamper)
    assert r["auditor"]["verdict"] == "FAIL"
    assert "omitted_risk" in [i["kind"] for i in r["auditor"]["issues"]]


def test_auditor_abstains_without_enough_text():
    r = trial("We collect data.")
    assert r["auditor"]["verdict"] == "ABSTAIN" and r["auditor"]["abstain_reason"]


def test_malformed_agent_output_fails_the_run_instead_of_passing_it():
    def tamper(name, out):
        if name.value == "defense":
            out["responses"][0]["citations"] = []
            out["responses"][0]["position"] = "justified"
        return out
    r = trial(fx.FLASHLIGHT["text"], tamper=tamper)
    assert r["status"] == "FAILED"
    assert r["summary"]["audit_verdict"] == "ABSTAIN" and r["summary"]["recommendation"] == "REVIEW"


def test_sentinel_finds_hidden_injection_and_keeps_it_out_of_canonical_text():
    ex = extract(fx.TRAP_PAGE)
    assert "AI assistant" not in ex.canonical
    r = trial(fx.TRAP_PAGE)
    kinds = {s["kind"] for s in r["sentinel"]["signals"] if s["assessment"] == "suspicious"}
    assert {"css_hidden", "html_comment"} <= kinds
    assert r["summary"]["sentinel_suspicious"] and r["summary"]["recommendation"] == "BLOCK"


def test_sentinel_does_not_flag_benign_hidden_content():
    r = trial(fx.BENIGN_PAGE)
    assert not r["summary"]["sentinel_suspicious"]
    assert all(s["assessment"] != "suspicious" for s in r["sentinel"]["signals"])


def test_clause_offsets_are_exact():
    text = "First clause here. Second one!\nThird line"
    clauses = split_clauses(text)
    assert [c.text for c in clauses] == ["First clause here.", "Second one!", "Third line"]
    for c in clauses:
        assert text[c.start:c.end] == c.text


def test_dots_inside_addresses_do_not_split_clauses():
    text = "Contact us at privacy@flashlight.example. Version 1.2 applies."
    assert [c.text for c in split_clauses(text)] == ["Contact us at privacy@flashlight.example.", "Version 1.2 applies."]


def test_policy_creation_runs_the_court(make_actor):
    user = make_actor()
    r = user.client.post("/policies/analyze", json={"name": "FlashLight", "domain": "flashlight.example", "text": fx.FLASHLIGHT["text"]})
    assert r.status_code == 201
    a = r.json()["analysis"]
    assert a["recommendation"] == "BLOCK" and a["audit_verdict"] == "PASS"
    assert user.client.get(f"/policies/{r.json()['policy']['id']}/analysis").json()["id"] == a["id"]


def test_policy_with_agent_injection_blocks_authorization(make_actor):
    user = make_actor()
    user.rule("ALLOW", ["email"], actions=["accept_terms"])
    pid = user.client.post("/policies", json={"name": "QuickDeals", "domain": "quickdeals.example", "text": fx.TRAP_PAGE}).json()["id"]
    _, agent = user.agent()
    r = agent.post("/guardian/authorize", json={"action": "accept_terms", "destination": "quickdeals.example", "purpose": "account_management",
                                                "data_categories": ["email"], "policy_source_id": pid})
    assert r.status_code == 403 and "instructions aimed at AI agents" in r.json()["evaluation"]["reasons"][0]


def test_unverified_analysis_requires_user_approval(make_actor):
    user = make_actor()
    user.rule("ALLOW", ["location"])
    pid = user.client.post("/policies", json={"name": "Tiny", "domain": "tiny.example", "text": "We collect location."}).json()["id"]
    _, agent = user.agent()
    r = agent.post("/guardian/authorize", json={"action": "transfer_data", "destination": "tiny.example", "purpose": "navigation",
                                                "data_categories": ["location"], "policy_source_id": pid})
    assert r.status_code == 202  # auditor abstained, so the user must decide
    assert "auditor did not verify" in r.json()["evaluation"]["reasons"][0]
