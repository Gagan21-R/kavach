"""Offline, rule-based implementations of the court agents.

Each function returns a plain dict that must pass app.schemas.agents.validate_agent_output before anyone uses it.
They share no mutable state and have no tools: they read text and return structured claims, nothing more.
"""
import hashlib
import re

from app.court import lexicon as lx
from app.court.text import Clause, Extracted
from app.vocab import PolicyCategory as PC

OFFLINE_MODEL = "offline-rules"
AGENT_VERSION = "1.0"

CLAIMS = {
    PC.LOCATION: "The policy allows collection or use of your location.",
    PC.CONTACTS: "The policy allows access to your contacts.",
    PC.BIOMETRICS: "The policy allows processing of your biometric data.",
    PC.THIRD_PARTY_SHARING: "The policy allows your data to be shared with or sold to others.",
    PC.RETENTION: "The policy keeps your data for an unclear or unlimited period.",
    PC.DELETION: "The policy limits your ability to have your data deleted.",
    PC.ADVERTISING: "Your data may be used for advertising or marketing.",
    PC.AI_TRAINING: "Your data may be used to train AI systems.",
}
LABELS = {
    PC.LOCATION: "location", PC.CONTACTS: "contacts", PC.BIOMETRICS: "biometric data",
    PC.THIRD_PARTY_SHARING: "third-party sharing", PC.RETENTION: "data retention", PC.DELETION: "deletion",
    PC.ADVERTISING: "advertising", PC.AI_TRAINING: "AI training",
}
QUESTIONS = {
    PC.LOCATION: "Does the app need precise location, or would approximate location work? Can you use it with location off?",
    PC.CONTACTS: "Why does this app need your contacts, and does it upload them to its servers?",
    PC.BIOMETRICS: "Where is your biometric data stored, and is it ever shared or used beyond unlocking the feature?",
    PC.THIRD_PARTY_SHARING: "Which companies receive your data, and can you opt out of sharing or sale?",
    PC.RETENTION: "Exactly how long is your data kept after you stop using the service?",
    PC.DELETION: "How do you delete your data, and is anything kept afterwards?",
    PC.ADVERTISING: "Can you opt out of ad targeting while still using the service?",
    PC.AI_TRAINING: "Is your content used to train AI models, and how do you opt out?",
}
SAFER = {
    PC.LOCATION: "Grant location only while using the app, or choose approximate location.",
    PC.CONTACTS: "Deny contacts permission; add people manually if a feature needs them.",
    PC.BIOMETRICS: "Use a passcode instead of biometric unlock for this service.",
    PC.THIRD_PARTY_SHARING: "Use the service's 'Do not sell or share' setting, or pick an alternative that does not sell data.",
    PC.RETENTION: "Delete your account and data when you stop using the service.",
    PC.DELETION: "Ask the company in writing how to delete your data before you sign up.",
    PC.ADVERTISING: "Turn off ad personalisation in the app and your device settings.",
    PC.AI_TRAINING: "Look for an AI-training opt-out, or avoid uploading private content.",
}
LEVEL_WEIGHTS = {"high": 20, "medium": 8, "low": 2, "none": 0, "unknown": 4}
RISK_METHOD = "cc-risk-v2: sum of per-category weights (high 20, medium 8, low 2, unknown 4, none 0), capped at 100"
_DOWN = {"high": "medium", "medium": "low", "low": "none", "none": "none"}
_SEV_LEVEL = {"CRITICAL": "high", "HIGH": "high", "MEDIUM": "medium", "LOW": "low"}
_RANK = {"none": 0, "unknown": 1, "low": 2, "medium": 3, "high": 4}
# Plain-language verb phrases for headlines ("FlashLight wants to use your contacts").
WANTS = {
    PC.LOCATION: "use your location", PC.CONTACTS: "use your contacts", PC.BIOMETRICS: "use your biometric data",
    PC.THIRD_PARTY_SHARING: "share your data with other companies", PC.RETENTION: "keep your data without a clear limit",
    PC.DELETION: "limit deleting your data", PC.ADVERTISING: "use your data for advertising",
    PC.AI_TRAINING: "use your data to train AI",
}


def _meta(agent: str, run_id: str, policy_hash: str) -> dict:
    return {"agent": agent, "agent_version": AGENT_VERSION, "model": OFFLINE_MODEL, "run_id": run_id, "policy_hash": policy_hash, "errors": []}


def _span(snapshot_id: str, c: Clause) -> dict:
    return {"snapshot_id": snapshot_id, "clause_id": c.id, "start": c.start, "end": c.end, "quote": c.text[:2000]}


def _short(text: str, n: int = 140) -> str:
    return text if len(text) <= n else text[: n - 1] + "…"


# --- Sentinel -----------------------------------------------------------------


def sentinel(ex: Extracted, clauses: list[Clause], snapshot_id: str, run_id: str, policy_hash: str) -> dict:
    signals = []
    for h in ex.hidden:
        hits = lx.injection_hits(h.text)
        kind = h.kind if h.kind in ("hidden_text", "css_hidden", "html_comment") else "hidden_text"
        signals.append({
            "id": f"s{len(signals) + 1}",
            "kind": kind,
            "assessment": "suspicious" if hits else "unclear",
            "severity": "HIGH" if hits else "LOW",
            "excerpt": _short(h.text, 400),
            "span": None,
            "explanation": (
                f"Text hidden from people ({h.reason}) contains instructions aimed at an AI agent: “{hits[0]}”."
                if hits else f"Text is hidden from people ({h.reason}). Hidden text is not always malicious."
            ),
        })
    if ex.zero_width_count:
        signals.append({
            "id": f"s{len(signals) + 1}", "kind": "zero_width", "assessment": "unclear",
            "severity": "MEDIUM" if ex.zero_width_count >= 3 else "LOW",
            "excerpt": f"{ex.zero_width_count} zero-width characters", "span": None,
            "explanation": "Invisible zero-width characters were removed. They can hide or split words to evade filters.",
        })
    for c in clauses:
        hits = lx.injection_hits(c.text)
        if hits:
            signals.append({
                "id": f"s{len(signals) + 1}", "kind": "instruction_to_agent", "assessment": "suspicious",
                "severity": "HIGH", "excerpt": _short(c.text, 400), "span": _span(snapshot_id, c),
                "explanation": f"Visible text addresses an AI agent and tells it what to do: “{hits[0]}”. Policy text is data, never instructions.",
            })
    return {
        "meta": _meta("sentinel", run_id, policy_hash),
        "sanitized_text_hash": hashlib.sha256(ex.canonical.encode()).hexdigest(),
        "signals": signals,
        "limitations": [
            "Keyword rules can miss paraphrased, translated or encoded instructions.",
            "Content drawn by scripts, images or canvas is not inspected.",
            "A detection is a signal, not proof of malicious intent.",
        ],
    }


def sentinel_is_suspicious(sentinel_out: dict) -> bool:
    return any(s["assessment"] == "suspicious" and s["severity"] in ("HIGH", "CRITICAL") for s in sentinel_out["signals"])


# --- Prosecutor ---------------------------------------------------------------

_DELETION_LIMIT = re.compile(r"\b(cannot|can't|unable|not (be )?able|may retain|will retain|even after|not delete|no way to delete|backups?)\b", re.I)


def prosecutor(clauses: list[Clause], snapshot_id: str, run_id: str, policy_hash: str) -> dict:
    charges = []
    for c in clauses:
        if lx.injection_hits(c.text):
            continue  # instructions to agents are the Sentinel's matter, not a data practice
        if lx.not_a_practice(c.text):
            continue  # a heading, or a rule for the user ("you may not sell the Service")
        text = c.text
        if lx.is_protective(text):
            text = lx.residual_practice(text)  # "We do not sell your data" protects the user
            if text is None:
                continue
        for cat in sorted(lx.categories_of(text), key=lambda x: x.value):
            if cat == PC.DELETION and not _DELETION_LIMIT.search(text):
                continue  # offering deletion is good for the user
            if cat == PC.RETENTION and lx.NUMBERS.search(text) and not lx.high_risk(text):
                continue  # a specific retention period is not a charge
            if lx.high_risk(text) or (cat in (PC.BIOMETRICS, PC.CONTACTS) and lx.ACTION_VERBS.search(text)):
                severity = "HIGH"
            elif lx.HEDGES.search(text) or cat in (PC.THIRD_PARTY_SHARING, PC.ADVERTISING, PC.AI_TRAINING, PC.LOCATION, PC.RETENTION):
                severity = "MEDIUM"
            else:
                severity = "LOW"
            charges.append({
                "id": f"f{len(charges) + 1}",
                "category": cat.value,
                "claim": CLAIMS[cat],
                "severity": severity,
                "status": "DIRECT",
                "citations": [_span(snapshot_id, c)],
                "reasoning": f"Clause {c.id} says “{_short(c.text)}”. This concerns {LABELS[cat]}"
                + (" and uses high-risk wording." if severity == "HIGH" else "."),
            })
    return {"meta": _meta("prosecutor", run_id, policy_hash), "charges": charges}


# --- Defense ------------------------------------------------------------------


def defense(charges: list[dict], clauses: list[Clause], snapshot_id: str, run_id: str, policy_hash: str) -> dict:
    by_id = {c.id: c for c in clauses}
    order = [c.id for c in clauses]
    responses = []
    for ch in charges:
        cid = ch["citations"][0]["clause_id"]
        i = order.index(cid)
        cat = PC(ch["category"])
        # A neighbouring clause only counts if it talks about the same practice; "security alerts" in the next
        # sentence must not excuse AI training in this one.
        neighbourhood = [by_id[cid]] + [
            by_id[order[j]] for j in (i + 1, i - 1)
            if 0 <= j < len(order) and cat in lx.categories_of(by_id[order[j]].text)
        ]
        specific = next((c for c in neighbourhood if lx.SPECIFIC_PURPOSE.search(c.text)), None)
        vague = next((c for c in neighbourhood if lx.VAGUE_PURPOSE.search(c.text)), None)
        numbers = next((c for c in neighbourhood if lx.NUMBERS.search(c.text)), None)
        control = next((c for c in neighbourhood if lx.USER_CONTROL.search(c.text)), None)
        deidentified = next((c for c in neighbourhood if lx.DEIDENTIFIED.search(c.text)), None)
        if specific is not None and not (vague is specific and not lx.SPECIFIC_PURPOSE.search(specific.text)):
            m = lx.SPECIFIC_PURPOSE.search(specific.text)
            position = "partially_justified" if ch["severity"] == "HIGH" else "justified"
            responses.append({
                "finding_id": ch["id"], "position": position, "status": "DIRECT", "citations": [_span(snapshot_id, specific)],
                "argument": f"The policy states a specific purpose: “{m.group(0)}”."
                + (" The wording is still high-risk, so this only partly answers the charge." if position == "partially_justified" else ""),
            })
        elif control is not None:
            m = lx.USER_CONTROL.search(control.text)
            position = "partially_justified" if ch["severity"] == "HIGH" else "justified"
            responses.append({
                "finding_id": ch["id"], "position": position, "status": "DIRECT", "citations": [_span(snapshot_id, control)],
                "argument": f"The policy gives you a choice: “{m.group(0)}”."
                + (" The practice is still high-risk, so this only partly answers the charge." if position == "partially_justified" else ""),
            })
        elif deidentified is not None:
            m = lx.DEIDENTIFIED.search(deidentified.text)
            position = "partially_justified" if ch["severity"] == "HIGH" else "justified"
            responses.append({
                "finding_id": ch["id"], "position": position, "status": "DIRECT", "citations": [_span(snapshot_id, deidentified)],
                "argument": f"The policy says the data is “{m.group(0)}”, which lowers the risk to you."
                + (" It is still a high-risk use, so this only partly answers the charge." if position == "partially_justified" else ""),
            })
        elif ch["category"] in ("retention", "deletion") and numbers is not None:
            responses.append({
                "finding_id": ch["id"], "position": "partially_justified", "status": "INTERPRETATION",
                "citations": [_span(snapshot_id, numbers)],
                "argument": f"The policy gives a time frame (“{lx.NUMBERS.search(numbers.text).group(0)}”), which limits the practice somewhat.",
            })
        elif vague is not None:
            m = lx.VAGUE_PURPOSE.search(vague.text)
            responses.append({
                "finding_id": ch["id"], "position": "not_justified", "status": "INTERPRETATION",
                "citations": [_span(snapshot_id, vague)],
                "argument": f"The only stated purpose is vague (“{m.group(0)}”). It does not explain why {LABELS[PC(ch['category'])]} is needed.",
            })
        else:
            responses.append({
                "finding_id": ch["id"], "position": "not_justified", "status": "UNSUPPORTED", "citations": [],
                "argument": f"I could not find any stated purpose for {LABELS[PC(ch['category'])]} in the policy.",
            })
    return {"meta": _meta("defense", run_id, policy_hash), "responses": responses}


# --- Evidence Clerk -----------------------------------------------------------


def span_valid(canonical: str, clause_ids: set[str], span: dict) -> bool:
    return span["clause_id"] in clause_ids and 0 <= span["start"] < span["end"] <= len(canonical) and canonical[span["start"]:span["end"]] == span["quote"]


def clerk(canonical: str, clauses: list[Clause], charges: list[dict], responses: list[dict], run_id: str, policy_hash: str) -> dict:
    ids = {c.id for c in clauses}
    checks = []
    for ch in charges:
        valid = bool(ch["citations"]) and all(span_valid(canonical, ids, s) for s in ch["citations"])
        cat_ok = valid and any(lx.CATEGORY_PATTERNS[PC(ch["category"])].search(s["quote"]) for s in ch["citations"])
        support = "direct" if cat_ok else ("interpretation" if valid else "unsupported")
        checks.append({"finding_id": ch["id"], "citation_valid": valid, "support": support,
                       "note": "prosecution: quoted text matches the source exactly" if valid else "prosecution: citation does not match the source"})
    for r in responses:
        if not r["citations"]:
            checks.append({"finding_id": r["finding_id"], "citation_valid": False, "support": "unsupported", "note": "defense: no source text cited"})
            continue
        valid = all(span_valid(canonical, ids, s) for s in r["citations"])
        checks.append({"finding_id": r["finding_id"], "citation_valid": valid,
                       "support": ("direct" if r["status"] == "DIRECT" else "interpretation") if valid else "unsupported",
                       "note": "defense: cited text verified" if valid else "defense: citation does not match the source"})
    return {"meta": _meta("evidence_clerk", run_id, policy_hash), "checks": checks}


# --- Judge --------------------------------------------------------------------


def score_from_map(category_map: list[dict]) -> tuple[int, dict]:
    inputs = {c["category"]: float(LEVEL_WEIGHTS[c["risk_level"]]) for c in category_map}
    return min(100, int(sum(inputs.values()))), inputs


def judge(canonical: str, clauses: list[Clause], charges: list[dict], responses: list[dict], checks: list[dict],
          sentinel_out: dict, app_name: str, run_id: str, policy_hash: str) -> dict:
    resp = {r["finding_id"]: r for r in responses}
    pros_valid = {c["finding_id"]: c["citation_valid"] for c in checks if c["note"].startswith("prosecution")}
    def_valid = {c["finding_id"]: c["citation_valid"] for c in checks if c["note"].startswith("defense")}
    mentioned = set().union(*(lx.categories_of(c.text) for c in clauses)) if clauses else set()

    levels: dict[str, str] = {}
    per_cat: dict[str, list[str]] = {}
    unexcused: dict[str, list[str]] = {}
    disagreements = []
    for ch in charges:
        r = resp.get(ch["id"])
        level = _SEV_LEVEL[ch["severity"]]
        position = r["position"] if r else "insufficient_evidence"
        if position == "justified" and def_valid.get(ch["id"]):
            level = _DOWN[level]
        elif position == "partially_justified" and def_valid.get(ch["id"]) and level == "high":
            level = "medium"  # a stated purpose or a real choice for the user softens, but doesn't clear, the finding
        if not pros_valid.get(ch["id"], False):
            level = "unknown"
        cat = ch["category"]
        per_cat.setdefault(cat, []).append(ch["id"])
        if _RANK[level] > _RANK[levels.get(cat, "none")]:
            levels[cat] = level
        if position in ("not_justified", "insufficient_evidence"):
            unexcused.setdefault(cat, []).append(ch["id"])
        else:
            resolved = position == "justified" and def_valid.get(ch["id"], False) and ch["severity"] != "HIGH"
            disagreements.append({
                "finding_id": ch["id"],
                "prosecutor_view": ch["claim"],
                "defense_view": r["argument"],
                "resolved": resolved,
                "resolution": "The stated purpose is specific and the citation checks out." if resolved
                else "The purpose is stated but the practice is high-risk; your judgement is needed.",
            })

    agreements = [
        f"{LABELS[PC(cat)]}: the Defense could not justify {len(ids)} finding(s) ({', '.join(ids[:5])}{', …' if len(ids) > 5 else ''})."
        for cat, ids in unexcused.items()
    ]
    disagreements = sorted(disagreements, key=lambda d: d["resolved"])[:100]  # unresolved first
    category_map, missing = [], []
    for cat in PC:
        if cat.value in levels:
            lvl = levels[cat.value]
            expl = f"{len(per_cat[cat.value])} finding(s); highest remaining risk is {lvl}."
        elif cat in mentioned:
            lvl, expl = "none", "Mentioned, but in a protective or specific way."
        elif cat in (PC.RETENTION, PC.DELETION):
            lvl, expl = "unknown", "The policy does not say. Silence here is a risk in itself."
            missing.append("how long data is kept" if cat == PC.RETENTION else "how to delete your data")
        else:
            lvl, expl = "none", "Not mentioned in the policy."
        category_map.append({"category": cat.value, "risk_level": lvl, "finding_ids": per_cat.get(cat.value, [])[:100], "explanation": expl})

    score, inputs = score_from_map(category_map)
    unresolved = [d for d in disagreements if not d["resolved"]]
    highs = [c for c in category_map if c["risk_level"] == "high"]
    injected = sentinel_is_suspicious(sentinel_out)

    def unexcused(cat):
        return [ch for ch in charges if ch["category"] == cat and _SEV_LEVEL[ch["severity"]] == "high"
                and resp.get(ch["id"], {}).get("position") in ("not_justified", "insufficient_evidence", None)]

    # Not recommended: hidden instructions, several high-risk practices, or selling your data. One high-risk
    # practice on its own (common in large services' policies) needs the user's judgement instead.
    sells = any(lx.SALE_OF_DATA.search(ch["citations"][0]["quote"]) for ch in unexcused(PC.THIRD_PARTY_SHARING.value) if ch["citations"])
    if injected or len(highs) >= 2 or sells:
        rec = "BLOCK"
    elif highs or unresolved or missing or score >= 25:
        rec = "REVIEW"
    else:
        rec = "ALLOW"

    name = app_name or "This service"
    if injected:
        headline = f"The {name} page contains hidden instructions aimed at AI agents. Do not let an agent accept it."
    elif highs:
        # Lead with what the Defense could not justify; ties go to the most sensitive categories.
        priority = [PC.CONTACTS, PC.BIOMETRICS, PC.AI_TRAINING, PC.THIRD_PARTY_SHARING, PC.LOCATION, PC.ADVERTISING, PC.RETENTION, PC.DELETION]
        high_cats = [PC(h["category"]) for h in highs]
        ordered = sorted(high_cats, key=lambda c: (not unexcused(c.value), priority.index(c)))
        worst = ordered[0]
        if unexcused(worst.value) and rec == "BLOCK":
            headline = f"{name} wants to {WANTS[worst]}. The Defense could not justify it. Excessive."
        elif unexcused(worst.value):
            headline = f"{name} wants to {WANTS[worst]}, and the Defense could not justify it. Your judgement is needed."
        else:
            headline = f"{name}: {LABELS[worst]} is high-risk and the Defense offered only a partial justification."
    elif rec == "REVIEW":
        headline = f"{name} is mostly specific, but some points need your judgement."
    else:
        headline = f"{name} states specific purposes for what it collects."

    concerns = [PC(c["category"]) for c in category_map if c["risk_level"] in ("high", "medium", "unknown")]
    valid_ratio = (sum(1 for c in checks if c["citation_valid"]) / len(checks)) if checks else 1.0
    tidy = sum(1 for c in clauses if 3 <= len(c.text) <= 400) / len(clauses) if clauses else 0.0
    reliability = max(0.0, 1.0 - 0.5 * (len(unresolved) / max(1, len(charges))) - (0.2 if missing else 0.0))
    return {
        "meta": _meta("judge", run_id, policy_hash),
        "recommendation": rec,
        "headline": headline,
        "category_map": category_map,
        "agreements": agreements,
        "disagreements": disagreements,
        "missing_information": missing,
        "risk_score": {"value": score, "method": RISK_METHOD, "inputs": inputs},
        "questions_to_ask": [QUESTIONS[c] for c in concerns][:8],
        "safer_choices": [SAFER[c] for c in concerns][:8],
        "confidence": [
            {"component": "clause_extraction", "value": round(tidy, 2), "basis": "heuristic",
             "explanation": "Share of clauses with a plausible length. Not a calibrated probability."},
            {"component": "data_classification", "value": None, "basis": "not_available",
             "explanation": "Keyword classification has not been calibrated on labelled data yet."},
            {"component": "evidence_support", "value": round(valid_ratio, 2), "basis": "heuristic",
             "explanation": "Share of citations the Evidence Clerk verified character-for-character."},
            {"component": "decision_reliability", "value": round(reliability, 2), "basis": "heuristic",
             "explanation": "Lower when the Prosecutor and Defense disagree or the policy leaves questions open."},
        ],
        "limitations": [
            "Explainable signals, not legal advice.",
            "Offline keyword agents can miss paraphrases and context.",
            "Confidence values are heuristics, not calibrated probabilities.",
        ],
    }


# --- Independent auditor ------------------------------------------------------


def auditor(canonical: str, clauses: list[Clause], charges: list[dict], responses: list[dict], judge_out: dict,
            run_id: str, policy_hash: str) -> dict:
    """Blind check: sees the source, the structured claims and the Judge's structured verdict, never the debate text.
    Uses its own scan for omissions rather than the Prosecutor's rules."""
    meta = _meta("auditor", run_id, policy_hash)
    if len(canonical) < 80 or len(clauses) < 2:
        return {"meta": meta, "verdict": "ABSTAIN", "issues": [], "explanation": "Not enough policy text to verify the analysis.",
                "abstain_reason": f"Only {len(canonical)} characters and {len(clauses)} clause(s) of text were available."}
    ids = {c.id for c in clauses}
    issues = []
    cited = set()
    for ch in charges:
        for s in ch["citations"]:
            cited.add(s["clause_id"])
            if not span_valid(canonical, ids, s):
                issues.append({"kind": "wrong_citation", "severity": "HIGH", "finding_id": ch["id"], "evidence": [],
                               "explanation": f"{ch['id']} cites text that does not appear at that position in the source."})
            elif not lx.CATEGORY_PATTERNS[PC(ch["category"])].search(s["quote"]):
                issues.append({"kind": "unsupported_claim", "severity": "HIGH", "finding_id": ch["id"], "evidence": [s],
                               "explanation": f"{ch['id']} claims a {ch['category']} practice, but the quoted text does not mention it."})
        if not ch["citations"] and ch["status"] != "UNSUPPORTED":
            issues.append({"kind": "unsupported_claim", "severity": "HIGH", "finding_id": ch["id"], "evidence": [],
                           "explanation": f"{ch['id']} has no citation."})
    charged = {}
    for ch in charges:
        for s in ch["citations"]:
            charged.setdefault(s["clause_id"], set()).add(ch["category"])
    always_charged = {PC.THIRD_PARTY_SHARING, PC.AI_TRAINING, PC.BIOMETRICS, PC.CONTACTS, PC.ADVERTISING}
    for c in clauses:
        if lx.injection_hits(c.text) or lx.not_a_practice(c.text):
            continue
        residual = lx.residual_practice(c.text) if lx.is_protective(c.text) else c.text
        if residual is None:
            continue
        ev = [{"snapshot_id": "audit", "clause_id": c.id, "start": c.start, "end": c.end, "quote": c.text[:2000]}]
        # High-risk wording only needs a finding when the clause is about a data practice the court can name;
        # "subscriptions renew indefinitely" or "you forever waive a claim" are not privacy practices.
        if lx.high_risk(residual) and c.id not in cited and lx.categories_of(residual):
            issues.append({"kind": "omitted_risk", "severity": "HIGH", "finding_id": None, "evidence": ev,
                           "explanation": f"Clause {c.id} uses high-risk wording but no finding addresses it."})
            continue
        missing = sorted(cat.value for cat in (lx.categories_of(residual) & always_charged) if cat.value not in charged.get(c.id, set()))
        if missing and lx.ACTION_VERBS.search(residual):
            issues.append({"kind": "omitted_risk", "severity": "HIGH", "finding_id": None, "evidence": ev,
                           "explanation": f"Clause {c.id} involves {', '.join(missing)} but no finding covers it."})
    for r in responses:
        if r["position"] in ("justified", "partially_justified") and not all(span_valid(canonical, ids, s) for s in r["citations"]):
            issues.append({"kind": "agent_contradiction", "severity": "MEDIUM", "finding_id": r["finding_id"], "evidence": [],
                           "explanation": "The Defense's justification cites text that is not in the source."})
    expected, _ = score_from_map(judge_out["category_map"])
    if judge_out.get("risk_score") and judge_out["risk_score"]["value"] != expected:
        issues.append({"kind": "score_mismatch", "severity": "MEDIUM", "finding_id": None, "evidence": [],
                       "explanation": f"Risk score {judge_out['risk_score']['value']} does not follow the documented method (expected {expected})."})
    if judge_out["recommendation"] == "ALLOW" and any(c["risk_level"] == "high" for c in judge_out["category_map"]):
        issues.append({"kind": "self_contradiction", "severity": "HIGH", "finding_id": None, "evidence": [],
                       "explanation": "The Judge recommends ALLOW while rating a category as high risk."})
    finding_ids = {ch["id"] for ch in charges}
    for c in judge_out["category_map"]:
        if c["risk_level"] == "high" and not (set(c["finding_ids"]) & finding_ids):
            issues.append({"kind": "overreach", "severity": "MEDIUM", "finding_id": None, "evidence": [],
                           "explanation": f"{c['category']} is rated high without any supporting finding."})
    failing = [i for i in issues if i["severity"] in ("HIGH", "CRITICAL")]
    verdict = "FAIL" if failing else "PASS"
    explanation = (f"{len(failing)} serious problem(s) found; the analysis should not be treated as verified." if failing
                   else f"Checked {len(charges)} finding(s): every citation matches the source and the score follows the documented method.")
    return {"meta": meta, "verdict": verdict, "issues": issues, "explanation": explanation, "abstain_reason": None}
