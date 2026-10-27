"""One review per website.

Kavach takes a domain, finds its privacy policy and terms (known URLs for popular platforms, otherwise the links in
the site's footer), puts each document through all six agents and combines them into one verdict for the site:
recommendation, risk score, confidence, the riskiest practices with the sentence each comes from, and how the site
compares with the user's preferences. The per-agent steps are kept for anyone who wants to see how it was decided.
"""
from collections import Counter

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import clock
from app.acquire import discover as disc
from app.acquire import service as acq
from app.acquire.catalogue import service_for_domain
from app.acquire.tracking import LABEL, site_domain
from app.court.agents import score_from_map
from app.court.report import summarize, trial
from app.models import AnalysisRun, PolicySource, User
from app.preferences import site_verdict

_LEVEL = {"none": 0, "unknown": 1, "low": 2, "medium": 3, "high": 4}
_REC = {"ALLOW": 0, "REVIEW": 1, "BLOCK": 2}
REC_WORDS = {"ALLOW": "Looks reasonable", "REVIEW": "Needs your review", "BLOCK": "Not recommended"}


def kind_of(url: str, title: str = "") -> str:
    import re

    return "terms" if re.search(r"terms|conditions|agreement|\btos\b|eula", f"{url} {title}", re.I) else "privacy"


def documents_for(domain: str) -> tuple[str, list[dict]]:
    """(site name, [{kind, url, ota}]) for a registrable domain."""
    svc = service_for_domain(domain)
    if svc is not None:
        return svc["name"], [{"kind": d["kind"], "url": d["url"], "ota": d["ota"]} for d in svc["docs"]]
    found = disc.discover(domain)
    return domain, [{"kind": k, "url": found[k], "ota": None} for k in ("privacy", "terms") if found.get(k)]


def how_decided(result: dict) -> list[dict]:
    """The six agents' work in one line each."""
    if result["status"] != "COMPLETED":
        return [{"agent": "Auditor", "text": "An agent's output failed validation, so nothing was verified."}]
    sus = [s for s in result["sentinel"]["signals"] if s["assessment"] == "suspicious"]
    charges = result["prosecutor"]["charges"]
    pos = Counter(r["position"] for r in result["defense"]["responses"])
    checks = [c for c in result["clerk"]["checks"] if c["note"].startswith("prosecution")]
    j, a = result["judge"], result["auditor"]
    return [
        {"agent": "Sentinel", "text": "Found instructions hidden for AI agents." if sus else "No hidden instructions for AI agents."},
        {"agent": "Prosecutor", "text": f"Raised {len(charges)} finding(s) across {len({c['category'] for c in charges})} kinds of data practice."},
        {"agent": "Defense", "text": f"Justified {pos['justified']}, partly justified {pos['partially_justified']}, "
                                     f"could not justify {pos['not_justified'] + pos['insufficient_evidence']}."},
        {"agent": "Evidence clerk", "text": f"Checked {sum(c['citation_valid'] for c in checks)} of {len(checks)} quotes word for word against the source."},
        {"agent": "Judge", "text": f"{REC_WORDS[j['recommendation']]}, risk {j['risk_score']['value'] if j.get('risk_score') else '—'}/100."},
        {"agent": "Auditor", "text": f"{a['verdict']}: {a['explanation']}"},
    ]


def _scope(db: Session, user_id: str, site: str):
    from app.engine.scope import scope_for

    return scope_for(db, user_id, site)


def _tracked(db: Session, user_id: str, url: str) -> PolicySource | None:
    return db.execute(select(PolicySource).where(PolicySource.user_id == user_id, PolicySource.url == url)).scalar_one_or_none()


def combine(name: str, domain: str, docs: list[dict], scope, now) -> dict:
    """Merge per-document trials into one verdict for the site."""
    done = [d for d in docs if d.get("result") and d["result"]["status"] == "COMPLETED"]
    if not done:
        return {"status": "UNKNOWN", "recommendation": None, "risk_score": None, "confidence": None, "audit": None,
                "headline": f"We couldn't read {name}'s policies.", "factors": [], "missing": [],
                "reasons": [d.get("error") or "No policy found." for d in docs] or ["We couldn't find a privacy policy or terms for this site."],
                "hidden_instructions": False}
    merged: dict[str, dict] = {}
    for d in done:
        for c in d["result"]["judge"]["category_map"]:
            if c["category"] not in merged or _LEVEL[c["risk_level"]] > _LEVEL[merged[c["category"]]["risk_level"]]:
                merged[c["category"]] = c
    category_map = list(merged.values())
    score, _ = score_from_map(category_map)
    reports = [(d, summarize(d["result"])) for d in done]
    factors: dict[str, dict] = {}
    for d, rep in reports:
        for f in rep["factors"]:
            if f["category"] not in factors or _LEVEL[f["level"]] > _LEVEL[factors[f["category"]]["level"]]:
                factors[f["category"]] = {**f, "source": LABEL[d["kind"]]}
    worst_doc, worst = max(reports, key=lambda x: (_REC[x[1]["recommendation"]], x[1]["risk_score"] or 0))
    highs = sum(1 for c in category_map if c["risk_level"] == "high")
    rec = max([r["recommendation"] for _, r in reports] + (["BLOCK"] if highs >= 2 else []), key=_REC.get)
    hidden = any(r["hidden_instructions"] for _, r in reports)
    prefs = site_verdict(scope.rules, {"status": "COMPLETED", "judge": {"category_map": category_map},
                                 "summary": {"sentinel_suspicious": hidden, "headline": worst["headline"], "risk_score": score}},
                         domain, now, scope.deny_unlisted)
    confidences = [r["confidence"] for _, r in reports if r["confidence"] is not None]
    audits = {r["audit_verdict"] for _, r in reports}
    return {
        "status": prefs["status"], "reasons": prefs["reasons"],
        "recommendation": rec, "recommendation_words": REC_WORDS[rec], "risk_score": score,
        "confidence": round(sum(confidences) / len(confidences)) if confidences else None,
        "audit": "PASS" if audits == {"PASS"} else "FAIL" if "FAIL" in audits else "ABSTAIN",
        "headline": worst["headline"], "hidden_instructions": hidden,
        "factors": sorted(factors.values(), key=lambda f: -_LEVEL[f["level"]]),
        "missing": sorted({m for _, r in reports for m in r["missing"]}),
        "rules": {"group_id": scope.group.id if scope.group else None, "label": scope.label},
    }


def review(db: Session, user: User, domain: str, page: dict | None = None) -> dict:
    """page = {"url", "title", "text"}: the document the user is reading in their own browser (extension)."""
    host = disc.normalize_domain(domain)
    site = site_domain(host)
    name, docs = documents_for(site)
    # A document the user already tracks wins over a freshly discovered address for the same kind.
    for p in db.execute(select(PolicySource).where(PolicySource.user_id == user.id)).scalars():
        if p.url and site_domain(p.domain) == site:
            kind = kind_of(p.url, p.name)
            docs = [d for d in docs if d["kind"] != kind] + [{"kind": kind, "url": p.url, "ota": None}]
    if page:
        kind = kind_of(page["url"], page.get("title", ""))
        docs = [d for d in docs if d["kind"] != kind or d["url"] == page["url"]]
        if not any(d["url"] == page["url"] for d in docs):
            docs.append({"kind": kind, "url": page["url"], "ota": None, "page": page})
        else:
            docs = [{**d, "page": page} if d["url"] == page["url"] else d for d in docs]
    out_docs = []
    for d in sorted(docs, key=lambda d: d["kind"]):
        entry = {"kind": d["kind"], "label": LABEL[d["kind"]], "url": d["url"], "tracked": False, "policy_id": None, "error": None}
        policy = _tracked(db, user.id, d["url"])
        run = db.get(AnalysisRun, policy.current_analysis_id) if policy and policy.current_analysis_id else None
        if run is not None:
            entry.update(result=run.result, tracked=True, policy_id=policy.id, source="Tracked by Kavach",
                         version=policy.current_version, changed=policy.requires_reassessment)
        elif d.get("page"):
            entry.update(result=trial(d["page"]["text"][:acq.MAX_TEXT], name), source="Read from your browser")
        else:
            got = acq.acquire_cached(db, d["url"], d["ota"])
            if got.ok:
                entry.update(result=trial(got.text, name), source=acq.METHOD_LABELS.get(got.method, got.method))
            else:
                entry.update(error=f"We couldn't get this document: {got.error}", source="Unavailable")
        out_docs.append(entry)
    verdict = combine(name, site, out_docs, _scope(db, user.id, site), clock.utcnow())
    documents = []
    for e in out_docs:
        r = e.pop("result", None)
        s = summarize(r) if r else None
        documents.append({**e, "recommendation": s and s["recommendation"], "risk_score": s and s["risk_score"],
                          "confidence": s and s["confidence"], "audit": s and s["audit_verdict"],
                          "how_decided": how_decided(r) if r else []})
    found = [d for d in documents if not d["error"]]
    return {"domain": site, "name": name, **verdict, "documents": documents,
            "tracked": bool(found) and all(d["tracked"] for d in found), "any_tracked": any(d["tracked"] for d in documents),
            "checked_at": clock.utcnow().isoformat()}


def track_site(db: Session, user: User, domain: str, page: dict | None = None) -> list[PolicySource]:
    """Track every policy of the site (Watchman takes over from here). The server's own copy is preferred so later
    re-checks compare like with like; the user's copy is used only when the site blocks the server."""
    from app.acquire.tracking import track_url
    from app.audit_log import record
    from app.watchman import service as watchman

    host = disc.normalize_domain(domain)
    site = site_domain(host)
    name, docs = documents_for(site)
    if page:
        kind = kind_of(page["url"], page.get("title", ""))
        docs = [d for d in docs if d["kind"] != kind] + [{"kind": kind, "url": page["url"], "ota": None, "page": page}]
    tracked = []
    for d in docs:
        policy, got = track_url(db, user, name=f"{name} {LABEL[d['kind']]}", domain=site, url=d["url"], ota=d["ota"])
        if policy is None and d.get("page") and len(d["page"]["text"]) >= 400:
            policy = watchman.create_policy(db, user, name=f"{name} {LABEL[d['kind']]}", domain=site,
                                            text=d["page"]["text"][:acq.MAX_TEXT], url=d["url"], locale="en")
            record(db, "policy.acquired", user_id=user.id, actor_type="user", actor_id=user.id, target_type="policy",
                   target_id=policy.id, details={"method": "BROWSER", "server_error": got.error})
        if policy is not None:
            tracked.append(policy)
    return tracked


def tracked_summary(db: Session, user: User, site: str, policies: list[PolicySource]) -> dict:
    """The combined verdict for a tracked site from its stored analyses (no fetching)."""
    docs = []
    for p in policies:
        run = db.get(AnalysisRun, p.current_analysis_id) if p.current_analysis_id else None
        if run is not None:
            docs.append({"kind": kind_of(p.url or "", p.name), "result": run.result})
    svc = service_for_domain(site)
    return combine(svc["name"] if svc else site, site, docs, _scope(db, user.id, site), clock.utcnow())
