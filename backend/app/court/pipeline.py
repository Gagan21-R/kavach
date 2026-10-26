"""Runs one trial: Sentinel -> Prosecutor -> Defense -> Evidence Clerk -> Judge -> Independent Auditor.

Every agent output is schema-validated before the next agent sees it. A failure anywhere ends the trial with
status FAILED and an ABSTAIN audit, so an unverified analysis can never look verified. The run is bounded: a
fixed sequence of agents, no loops, no retries of model output, no tools.
"""
import time
import uuid

from app.court import agents
from app.court.text import extract, split_clauses
from app.schemas.agents import AgentName, AgentOutputError, validate_agent_output

STEP_BUDGET_SECONDS = 5.0


class StepTimeout(Exception):
    pass


def _validated(name: AgentName, out: dict, started: float) -> dict:
    if time.monotonic() - started > STEP_BUDGET_SECONDS:
        raise StepTimeout(f"{name} exceeded its {STEP_BUDGET_SECONDS}s budget")
    return validate_agent_output(name, out).model_dump(mode="json")


def _transcript(sentinel, charges, responses, checks, judge, auditor) -> list[dict]:
    msgs = []

    def add(agent, kind, text, **extra):
        msgs.append({"seq": len(msgs) + 1, "agent": agent, "kind": kind, "text": text, **extra})

    sig = sentinel["signals"]
    sus = [s for s in sig if s["assessment"] == "suspicious"]
    add("sentinel", "screening",
        f"Screened the input. {len(sig)} signal(s), {len(sus)} suspicious." + (" Hidden or injected instructions found; they are treated as data, never obeyed." if sus else " Nothing aimed at AI agents."),
        signals=sig)
    resp = {r["finding_id"]: r for r in responses}
    chk = {}
    for c in checks:
        chk.setdefault(c["finding_id"], []).append(c)
    for ch in charges:
        add("prosecutor", "charge", f"{ch['claim']} {ch['reasoning']}", finding_id=ch["id"], severity=ch["severity"],
            category=ch["category"], citations=ch["citations"])
        r = resp.get(ch["id"])
        if r:
            add("defense", r["position"], r["argument"], finding_id=ch["id"], citations=r["citations"])
        notes = chk.get(ch["id"], [])
        if notes:
            ok = all(n["citation_valid"] for n in notes if n["note"].startswith("prosecution"))
            add("evidence_clerk", "verified" if ok else "rejected",
                "; ".join(n["note"] for n in notes), finding_id=ch["id"])
    add("judge", "verdict", judge["headline"], recommendation=judge["recommendation"], risk_score=judge["risk_score"])
    add("auditor", auditor["verdict"].lower(), auditor["explanation"], verdict=auditor["verdict"])
    return msgs


def run_trial(raw_text: str, *, snapshot_id: str, policy_hash: str, app_name: str = "", tamper=None) -> dict:
    """Returns a JSON-serialisable result. `tamper` is a test hook (Red Team Lab) that may corrupt one agent's
    output between steps, to prove the downstream checks catch it."""
    run_id = uuid.uuid4().hex
    started = time.monotonic()
    timings = {}
    ex = extract(raw_text)
    clauses = split_clauses(ex.canonical)
    result = {
        "run_id": run_id,
        "canonical_text": ex.canonical,
        "clauses": [c.__dict__ for c in clauses],
        "segments": [s.__dict__ for s in ex.segments] if ex.was_html else [],
        "status": "COMPLETED",
        "errors": [],
    }

    def step(name: AgentName, fn):
        t = time.monotonic()
        out = fn()
        if tamper:
            out = tamper(name, out) or out
        val = _validated(name, out, t)
        timings[name.value] = round((time.monotonic() - t) * 1000, 2)
        return val

    try:
        s = step(AgentName.SENTINEL, lambda: agents.sentinel(ex, clauses, snapshot_id, run_id, policy_hash))
        p = step(AgentName.PROSECUTOR, lambda: agents.prosecutor(clauses, snapshot_id, run_id, policy_hash))
        d = step(AgentName.DEFENSE, lambda: agents.defense(p["charges"], clauses, snapshot_id, run_id, policy_hash))
        c = step(AgentName.EVIDENCE_CLERK, lambda: agents.clerk(ex.canonical, clauses, p["charges"], d["responses"], run_id, policy_hash))
        j = step(AgentName.JUDGE, lambda: agents.judge(ex.canonical, clauses, p["charges"], d["responses"], c["checks"], s, app_name, run_id, policy_hash))
        a = step(AgentName.AUDITOR, lambda: agents.auditor(ex.canonical, clauses, p["charges"], d["responses"], j, run_id, policy_hash))
    except (AgentOutputError, StepTimeout) as e:
        result.update(status="FAILED", errors=[str(e)])
        result["auditor"] = {"verdict": "ABSTAIN", "explanation": "An agent produced invalid output, so nothing was verified.",
                             "abstain_reason": str(e), "issues": []}
        result["summary"] = {"recommendation": "REVIEW", "audit_verdict": "ABSTAIN", "risk_score": None,
                             "sentinel_suspicious": False, "headline": "Analysis failed validation; treat this policy as unreviewed."}
        result["timings_ms"] = timings
        return result

    result.update(sentinel=s, prosecutor=p, defense=d, clerk=c, judge=j, auditor=a)
    result["transcript"] = _transcript(s, p["charges"], d["responses"], c["checks"], j, a)
    result["summary"] = {
        "recommendation": j["recommendation"],
        "audit_verdict": a["verdict"],
        "risk_score": j["risk_score"]["value"] if j.get("risk_score") else None,
        "sentinel_suspicious": agents.sentinel_is_suspicious(s),
        "headline": j["headline"],
    }
    result["timings_ms"] = timings
    result["duration_ms"] = round((time.monotonic() - started) * 1000, 2)
    return result
