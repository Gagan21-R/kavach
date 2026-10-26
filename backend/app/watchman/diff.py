"""Two-stage policy comparison.

Stage 1 (deterministic): extract visible text from both versions and normalise case, whitespace and quote styles.
If the results are identical, the change is FORMATTING_ONLY.
Stage 2 (clause level): align clauses, then classify each changed pair by its "risk signature" — the data
categories, risk terms, negation and time periods it mentions.
  - signature changed, or a clause with data practices was added/removed -> POTENTIALLY_MATERIAL
  - only hedging words added ("may", "from time to time")                -> AMBIGUOUS
  - signature unchanged                                                    -> WORDING_NO_MATERIAL_CHANGE
These are keyword heuristics. They are evaluated in the Red Team Lab and their confidence is labelled heuristic.
"""
import difflib

from app.court import lexicon as lx
from app.court.text import extract, normalize_for_compare, split_clauses

ORDER = ["FORMATTING_ONLY", "WORDING_NO_MATERIAL_CHANGE", "AMBIGUOUS", "POTENTIALLY_MATERIAL"]
MATERIAL = {"POTENTIALLY_MATERIAL", "AMBIGUOUS"}
CONFIDENCE = {
    "FORMATTING_ONLY": (0.95, "Visible text is identical after normalisation; only markup, spacing or case changed."),
    "WORDING_NO_MATERIAL_CHANGE": (0.6, "No data category, risk term, negation or time period changed. Keyword rules can miss subtle meaning shifts."),
    "AMBIGUOUS": (0.4, "New hedging language widens what the company may do, but the practice itself is unclear."),
    "POTENTIALLY_MATERIAL": (0.7, "The clause's data categories, risk terms, negation or time periods changed."),
}


def word_diff(old: str, new: str) -> list[dict]:
    a, b = old.split(), new.split()
    out = []
    for op, i1, i2, j1, j2 in difflib.SequenceMatcher(a=a, b=b, autojunk=False).get_opcodes():
        if op == "equal":
            out.append({"op": "equal", "text": " ".join(a[i1:i2])})
        if op in ("delete", "replace"):
            out.append({"op": "delete", "text": " ".join(a[i1:i2])})
        if op in ("insert", "replace"):
            out.append({"op": "insert", "text": " ".join(b[j1:j2])})
    return out


def _classify_pair(old: str | None, new: str | None) -> tuple[str, list[str], str]:
    old_t, new_t = old or "", new or ""
    cats = sorted(c.value for c in (lx.categories_of(old_t) | lx.categories_of(new_t)))
    if old is None or new is None:
        text = new_t or old_t
        verb = "added" if old is None else "removed"
        if cats or lx.RISK_TERMS.search(text) or lx.is_protective(text):
            what = ", ".join(c.replace("_", " ") for c in cats) or "a data practice"
            return "POTENTIALLY_MATERIAL", cats, f"A clause about {what} was {verb}."
        return "WORDING_NO_MATERIAL_CHANGE", cats, f"A clause with no data practice was {verb}."
    s_old, s_new = lx.risk_signature(old_t), lx.risk_signature(new_t)
    if s_old != s_new:
        parts = []
        if s_old[0] != s_new[0]:
            parts.append("data categories changed")
        if s_old[1] != s_new[1]:
            added = sorted(s_new[1] - s_old[1])
            removed = sorted(s_old[1] - s_new[1])
            if added:
                parts.append("new risk terms: " + ", ".join(added))
            if removed:
                parts.append("removed terms: " + ", ".join(removed))
        if s_old[2] != s_new[2]:
            parts.append("a negation was " + ("removed" if s_old[2] else "added"))
        if s_old[3] != s_new[3]:
            parts.append("time periods changed")
        return "POTENTIALLY_MATERIAL", cats, "; ".join(parts).capitalize() + "."
    h_old = {m.group(0).lower() for m in lx.HEDGES.finditer(old_t)}
    h_new = {m.group(0).lower() for m in lx.HEDGES.finditer(new_t)}
    if h_new - h_old and cats:
        return "AMBIGUOUS", cats, f"New hedging words ({', '.join(sorted(h_new - h_old))}) may widen what is permitted."
    return "WORDING_NO_MATERIAL_CHANGE", cats, "Wording changed, but no category, risk term, negation or time period did."


def compare(old_raw: str, new_raw: str) -> dict:
    old_ex, new_ex = extract(old_raw), extract(new_raw)
    if normalize_for_compare(old_ex.canonical) == normalize_for_compare(new_ex.canonical):
        conf, why = CONFIDENCE["FORMATTING_ONLY"]
        return {
            "classification": "FORMATTING_ONLY",
            "changes": [{"old_clause_id": None, "new_clause_id": None, "old_text": "", "new_text": "", "classification": "FORMATTING_ONLY",
                         "categories": [], "explanation": "Only formatting, markup, spacing or letter case changed.", "diff": []}],
            "confidence": {"value": conf, "basis": "heuristic", "explanation": why},
        }
    oc, nc = split_clauses(old_ex.canonical), split_clauses(new_ex.canonical)
    a = [normalize_for_compare(c.text) for c in oc]
    b = [normalize_for_compare(c.text) for c in nc]
    changes = []
    for op, i1, i2, j1, j2 in difflib.SequenceMatcher(a=a, b=b, autojunk=False).get_opcodes():
        if op == "equal":
            continue
        olds, news = oc[i1:i2], nc[j1:j2]
        for k in range(max(len(olds), len(news))):
            o = olds[k] if k < len(olds) else None
            n = news[k] if k < len(news) else None
            cls, cats, why = _classify_pair(o.text if o else None, n.text if n else None)
            changes.append({
                "old_clause_id": o.id if o else None, "new_clause_id": n.id if n else None,
                "old_text": o.text if o else "", "new_text": n.text if n else "",
                "classification": cls, "categories": cats, "explanation": why,
                "diff": word_diff(o.text if o else "", n.text if n else ""),
            })
    if not changes:  # clause boundaries moved but normalised clauses match
        changes.append({"old_clause_id": None, "new_clause_id": None, "old_text": "", "new_text": "", "classification": "FORMATTING_ONLY",
                        "categories": [], "explanation": "Clause boundaries changed but each clause reads the same.", "diff": []})
    overall = max((c["classification"] for c in changes), key=ORDER.index)
    conf, why = CONFIDENCE[overall]
    return {"classification": overall, "changes": changes, "confidence": {"value": conf, "basis": "heuristic", "explanation": why}}
