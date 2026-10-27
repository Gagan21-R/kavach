"""A short, user-facing report of one trial: the score, how confident the analysis is, and the risky factors
with the sentence each one comes from. Used by the extension popup, page panel and site checks."""
import hashlib

from app.court.agents import LABELS
from app.court.pipeline import run_trial
from app.preferences import site_verdict
from app.vocab import PolicyCategory as PC

_LEVEL_RANK = {"high": 3, "medium": 2, "low": 1, "unknown": 0, "none": -1}
_SEV_RANK = {"HIGH": 3, "MEDIUM": 2, "LOW": 1}


def trial(text: str, name: str = "") -> dict:
    return run_trial(text, snapshot_id="preview", policy_hash=hashlib.sha256(text.encode()).hexdigest(), app_name=name)


def summarize(result: dict, rules=None, domain: str = "", now=None) -> dict:
    s = result["summary"]
    if result["status"] != "COMPLETED":
        return {"status": result["status"], "recommendation": s["recommendation"], "risk_score": None, "confidence": None,
                "audit_verdict": s["audit_verdict"], "headline": s["headline"], "factors": [], "missing": []}
    judge = result["judge"]
    parts = [c for c in judge["confidence"] if c["value"] is not None]
    confidence = round(100 * sum(c["value"] for c in parts) / len(parts)) if parts else None
    best: dict[str, dict] = {}
    for ch in result["prosecutor"]["charges"]:
        cur = best.get(ch["category"])
        if cur is None or _SEV_RANK[ch["severity"]] > _SEV_RANK[cur["severity"]]:
            best[ch["category"]] = ch
    factors = []
    for c in sorted(judge["category_map"], key=lambda c: -_LEVEL_RANK[c["risk_level"]]):
        if c["risk_level"] in ("none", "low"):
            continue
        ch = best.get(c["category"])
        factors.append({
            "category": c["category"], "label": LABELS[PC(c["category"])], "level": c["risk_level"],
            "explanation": c["explanation"],
            "quote": (ch["citations"][0]["quote"][:280] if ch and ch["citations"] else None),
        })
    out = {
        "status": "COMPLETED", "recommendation": s["recommendation"], "risk_score": s["risk_score"], "confidence": confidence,
        "confidence_basis": "heuristic: share of verified citations, clean clause extraction and agent agreement",
        "audit_verdict": s["audit_verdict"], "headline": s["headline"], "hidden_instructions": s["sentinel_suspicious"],
        "factors": factors, "missing": judge["missing_information"],
    }
    if rules is not None:
        out["preferences"] = site_verdict(rules, result, domain, now)
    return out
