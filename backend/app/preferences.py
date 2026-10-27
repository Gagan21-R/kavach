"""First-run preferences in plain language, turned into ordinary Constitution rules.

The user answers one question per kind of data and use: "OK", "Ask me" or "Never". Each answer becomes an
ALLOW, REQUIRE_APPROVAL or DENY rule, so the Guardian, Watchman and the browser extension all enforce the same
thing. Site verdicts then compare what a site's policy says it does with those answers.
"""
from app.engine import constitution
from app.engine.constitution import ActionRequest
from app.vocab import Decision, RuleEffect

DATA_GROUPS = {
    "basic": {"label": "Name, email and phone", "categories": ["name", "email", "phone"]},
    "location": {"label": "Location", "categories": ["location"]},
    "contacts": {"label": "Contacts", "categories": ["contacts"]},
    "media": {"label": "Photos and messages", "categories": ["photos", "messages"]},
    "browsing": {"label": "Browsing and device data", "categories": ["browsing_history", "device_id", "preferences"]},
    "money": {"label": "Payment and ID details", "categories": ["financial", "government_id"]},
    "health": {"label": "Health data", "categories": ["health"]},
    "biometrics": {"label": "Face and fingerprints", "categories": ["biometrics"]},
}
USES = {
    "service": {"label": "To run the service I signed up for", "purposes": ["service_delivery", "account_management", "security", "navigation"]},
    "ads": {"label": "For ads and marketing", "purposes": ["advertising", "marketing"]},
    "sharing": {"label": "Shared with or sold to other companies", "purposes": ["third_party_sharing"]},
    "ai": {"label": "To train AI models", "purposes": ["ai_training", "research"]},
    "analytics": {"label": "For analytics and personalisation", "purposes": ["analytics", "personalization"]},
}
CHOICES = {"OK": RuleEffect.ALLOW, "ASK": RuleEffect.REQUIRE_APPROVAL, "NEVER": RuleEffect.DENY}
_SENSITIVE = {"location", "contacts", "media", "money", "health", "biometrics"}


def default_choices() -> dict[str, dict[str, str]]:
    """A balanced starting point: everyday use is fine, sensitive data needs asking, selling and AI training don't happen."""
    out = {}
    for g in DATA_GROUPS:
        sensitive = g in _SENSITIVE
        out[g] = {
            "service": "ASK" if g in {"biometrics", "health"} else "OK",
            "ads": "NEVER" if sensitive else "ASK",
            "sharing": "NEVER",
            "ai": "NEVER" if sensitive else "ASK",
            "analytics": "NEVER" if sensitive else "OK",
        }
    return out


def rules_from_choices(choices: dict[str, dict[str, str]]) -> list[dict]:
    """One rule per (use, answer), listing every data category that got that answer."""
    grouped: dict[tuple[str, str], list[str]] = {}
    for g, per_use in choices.items():
        if g not in DATA_GROUPS:
            continue
        for use, answer in per_use.items():
            if use in USES and answer in CHOICES:
                grouped.setdefault((use, answer), []).extend(DATA_GROUPS[g]["categories"])
    rules = []
    for (use, answer), cats in sorted(grouped.items()):
        word = {"OK": "OK", "ASK": "Ask me first", "NEVER": "Never"}[answer]
        rules.append({
            "effect": CHOICES[answer].value,
            "data_categories": sorted(set(cats)),
            "purposes": USES[use]["purposes"],
            "description": f"Preferences: {word} — {USES[use]['label'].lower()}",
        })
    return rules


# What a policy category says the site does, as the (data, use) questions it raises for the user.
_PROBES = {
    "location": [("location", "service_delivery"), ("location", "advertising")],
    "contacts": [("contacts", "service_delivery")],
    "biometrics": [("biometrics", "service_delivery")],
    "third_party_sharing": [("email", "third_party_sharing"), ("browsing_history", "third_party_sharing")],
    "advertising": [("browsing_history", "advertising"), ("device_id", "advertising")],
    "ai_training": [("messages", "ai_training"), ("photos", "ai_training")],
}
_PLAIN = {
    "location": "uses your location", "contacts": "reads your contacts", "biometrics": "uses face or fingerprint data",
    "third_party_sharing": "shares your data with other companies", "advertising": "uses your data for ads",
    "ai_training": "may use your content to train AI",
}


def site_verdict(rules, analysis: dict | None, domain: str, now, deny_unlisted: str | None = None) -> dict:
    """Compares a site's analysed policy with the user's answers.

    CONFLICT: the policy describes something the user said "Never" to. CAUTION: something the user wants to be
    asked about, or a high-risk finding. OK: nothing the user objected to. Based on keyword analysis of the
    policy, so it is a signal to look closer, not a legal finding.
    """
    if not analysis or analysis.get("status") != "COMPLETED":
        return {"status": "UNKNOWN", "reasons": ["We could not analyse this site's policy yet."]}
    cmap = {c["category"]: c for c in analysis["judge"]["category_map"]}
    conflicts, cautions = [], []
    for cat, probes in _PROBES.items():
        level = cmap.get(cat, {}).get("risk_level", "none")
        if level in ("none", "low", "unknown"):
            continue
        worst = None
        for data, purpose in probes:
            res = constitution.evaluate(rules, ActionRequest("accept_terms", domain, purpose, (data,)), now, deny_unlisted)
            if res.decision == Decision.BLOCK:
                worst = "BLOCK"
                break
            if res.decision == Decision.REVIEW and res.deciding_rule_ids:
                worst = worst or "ASK"
        text = f"This site {_PLAIN[cat]} ({level} risk)"
        if worst == "BLOCK":
            conflicts.append(text + " — you said never.")
        elif worst == "ASK" or level == "high":
            cautions.append(text + (" — you asked to be asked." if worst == "ASK" else "."))
    if analysis["summary"].get("sentinel_suspicious"):
        conflicts.insert(0, "The policy page contains hidden instructions aimed at AI agents.")
    status = "CONFLICT" if conflicts else "CAUTION" if cautions else "OK"
    reasons = conflicts + cautions or ["Nothing in this policy goes against your preferences."]
    return {"status": status, "reasons": reasons[:6], "headline": analysis["summary"].get("headline", ""),
            "risk_score": analysis["summary"].get("risk_score")}
