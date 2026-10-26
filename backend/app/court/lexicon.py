"""Deterministic vocabulary the offline agents use. Keyword rules are transparent but brittle: the Red Team Lab
measures where they fail, and an LLM-backed agent can replace any of them behind the same contracts."""
import re

from app.vocab import PolicyCategory as PC

CATEGORY_PATTERNS: dict[PC, re.Pattern] = {
    PC.LOCATION: re.compile(r"\b(location|gps|geo-?location|whereabouts|precise position)\b", re.I),
    # Plural only: "contact us" is not your address book (Red Team case POL-03 caught this).
    PC.CONTACTS: re.compile(r"\b(contacts|address book|phone ?book|contact list)\b", re.I),
    PC.BIOMETRICS: re.compile(r"\b(biometric\w*|face ?prints?|fingerprints?|facial (recognition|geometry)|voice ?prints?|iris scans?)\b", re.I),
    PC.THIRD_PARTY_SHARING: re.compile(r"\b(sell|sold|selling|share|shared|sharing|disclose|disclosed|transfer(red)?|rent)\b.{0,80}\b(third[- ]part(y|ies)|partners?|affiliates?|advertisers?|data brokers?|vendors?|others)\b|\b(sell|sold|selling)\b", re.I),
    PC.RETENTION: re.compile(r"\b(retain\w*|retention|keep|kept|store[sd]?|storage)\b", re.I),
    PC.DELETION: re.compile(r"\b(delet\w*|eras\w*|remov\w*)\b", re.I),
    PC.ADVERTISING: re.compile(r"\b(advertis\w*|ads|ad network|targeted|marketing|promotional)\b", re.I),
    PC.AI_TRAINING: re.compile(r"\b(train(ing)?\b.{0,40}\b(model|ai|algorithm)s?|machine learning|artificial intelligence|ai (partners?|models?|systems?)|large language model)", re.I),
}

# Words that raise the stakes of a clause. Used for severity and for Watchman's "risk signature".
RISK_TERMS = re.compile(
    r"\b(sell|sold|selling|rent|data brokers?|third[- ]part(y|ies)|partners?|affiliates?|indefinite(ly)?|forever|"
    r"permanent(ly)?|train\w*|ai|biometric\w*|without (your )?consent|all (of )?your|any purpose|precise|"
    r"cannot|can't|unable|not (be )?able|may retain|advertis\w*|targeted)\b",
    re.I,
)
HIGH_RISK = re.compile(
    r"\b(sell|sold|selling|data brokers?|indefinite(ly)?|forever|biometric\w*|ai partners?|train\w*\b.{0,30}\b(model|ai)|"
    r"all (of )?your contacts|without (your )?consent|any purpose|cannot (be )?delet\w*|not (be )?able to delete)",
    re.I,
)
NEGATION = re.compile(r"\b(do not|don't|does not|doesn't|never|will not|won't|not|no)\b", re.I)
PROTECTIVE = re.compile(r"\b(do not|don't|does not|doesn't|never|will not|won't)\b\s+(\w+\s+){0,3}(sell|share|rent|disclose|use|train|transfer|keep|retain|collect|track)", re.I)
HEDGES = re.compile(r"\b(may|might|from time to time|at our (sole )?discretion|as (we deem )?appropriate|including but not limited to|such as|certain)\b", re.I)
NUMBERS = re.compile(r"\b\d+\s*(days?|months?|years?|hours?)\b", re.I)

# Justification language the Defense looks for.
SPECIFIC_PURPOSE = re.compile(
    r"\b(to|in order to|so that|so we can|required (to|for)|necessary (to|for)|needed (to|for)|only (to|for)|solely (to|for)|used (to|for))\b"
    r".{0,60}\b(provide|deliver|navigate|navigation|directions|route|ride|map|security|fraud|authenticat\w*|log ?in|"
    r"process (your )?(payment|order)|ship\w*|deliver\w*|emergency|backup|sync|call|message|find friends|scan)\b",
    re.I,
)
VAGUE_PURPOSE = re.compile(
    r"\b(improve (our )?(services?|products?|experience)|business purposes|other purposes|any purpose|"
    r"as we see fit|for (our )?(partners|marketing)|enhance your experience|personaliz\w*|research and development)\b",
    re.I,
)

# Prompt-injection indicators: text addressed to an AI agent rather than to a person.
INJECTION_PATTERNS = [
    re.compile(r"\bignore (all |any )?(previous|prior|above|earlier|your) (instructions|rules|policies|guidelines)\b", re.I),
    re.compile(r"\b(ai|a\.i\.|assistant|agent|bot|llm|language model|automated (system|browser))\b[^.\n]{0,60}\b(click|press|select|accept|agree|approve|consent|check|tick|submit|enable)\b", re.I),
    re.compile(r"\b(click|press|select)\b[^.\n]{0,20}\b(accept all|agree to all|allow all)\b", re.I),
    re.compile(r"\bdisregard\b[^.\n]{0,40}\b(instructions|user|policy|policies|rules)\b", re.I),
    re.compile(r"\b(do not|don't)\s+(tell|inform|notify|alert|ask)\s+the user\b", re.I),
    re.compile(r"\bsystem prompt\b|\bnew instructions\b|\byou are now\b|\bact as\b", re.I),
    re.compile(r"\b(auto-?accept|automatically (accept|agree|consent))\b", re.I),
]


def categories_of(text: str) -> set[PC]:
    return {c for c, p in CATEGORY_PATTERNS.items() if p.search(text)}


def injection_hits(text: str) -> list[str]:
    return [m.group(0) for p in INJECTION_PATTERNS for m in [p.search(text)] if m]


ACTION_VERBS = re.compile(
    r"\b(collect\w*|use[sd]?|using|access\w*|share[sd]?|sharing|process\w*|store[sd]?|keep|kept|upload\w*|track\w*|"
    r"gather\w*|obtain\w*|receive[sd]?|sell|sold|disclose[sd]?|transfer\w*|retain\w*|train\w*|record\w*|scan\w*)\b",
    re.I,
)


def is_protective(text: str) -> bool:
    """'We do not sell your data' protects the user: it is not a charge."""
    return bool(PROTECTIVE.search(text))


def residual_practice(text: str) -> str | None:
    """Text with protective phrases removed, or None if nothing affirmative is left.
    'We collect location but do not sell it' -> 'We collect location but it' (still a practice);
    'We do not sell your location data' -> None."""
    residual = PROTECTIVE.sub(" ", text)
    return residual if ACTION_VERBS.search(residual) else None


def risk_signature(text: str) -> tuple:
    t = text.lower()
    return (
        frozenset(c.value for c in categories_of(t)),
        frozenset(m.group(0).lower() for m in RISK_TERMS.finditer(t)),
        bool(NEGATION.search(t)),
        frozenset(m.group(0).lower().replace(" ", "") for m in NUMBERS.finditer(t)),
    )
