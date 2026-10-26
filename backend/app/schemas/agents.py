"""Typed output contracts for every court agent.

Every model output is parsed through validate_agent_output() before anything else reads it. Unknown fields,
missing citations, role mismatches and internally inconsistent verdicts are rejected, never repaired silently.
No contract has a field that grants authority: agents describe and recommend; only the Guardian decides.
"""
import json
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from app.vocab import Decision, PolicyCategory

HEX64 = r"^[0-9a-f]{64}$"


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class AgentName(StrEnum):
    SENTINEL = "sentinel"
    PROSECUTOR = "prosecutor"
    DEFENSE = "defense"
    EVIDENCE_CLERK = "evidence_clerk"
    JUDGE = "judge"
    WATCHMAN = "watchman"
    AUDITOR = "auditor"


class Severity(StrEnum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class EvidenceStatus(StrEnum):
    DIRECT = "DIRECT"  # the quoted text states it
    INTERPRETATION = "INTERPRETATION"  # follows from the text, but is a reading of it
    UNSUPPORTED = "UNSUPPORTED"  # no source text backs it


class AgentMeta(StrictModel):
    agent: AgentName
    agent_version: str = Field(min_length=1, max_length=40)
    model: str = Field(min_length=1, max_length=80)  # "offline-rules" for deterministic agents
    run_id: str = Field(min_length=1, max_length=64)
    policy_hash: str = Field(pattern=HEX64)
    errors: list[str] = Field(default_factory=list, max_length=50)


class SourceSpan(StrictModel):
    snapshot_id: str = Field(min_length=1, max_length=64)
    clause_id: str = Field(min_length=1, max_length=64)
    start: int = Field(ge=0)
    end: int = Field(gt=0)
    quote: str = Field(min_length=1, max_length=2000)

    @model_validator(mode="after")
    def _ordered(self):
        if self.end <= self.start:
            raise ValueError("span end must be after start")
        return self


class Finding(StrictModel):
    id: str = Field(min_length=1, max_length=64)
    category: PolicyCategory
    claim: str = Field(min_length=1, max_length=2000)
    severity: Severity
    status: EvidenceStatus
    citations: list[SourceSpan] = Field(default_factory=list, max_length=20)
    reasoning: str = Field(min_length=1, max_length=4000)

    @model_validator(mode="after")
    def _evidence_or_unsupported(self):
        if self.status != EvidenceStatus.UNSUPPORTED and not self.citations:
            raise ValueError("a finding must cite source text or be marked UNSUPPORTED")
        return self


# --- Sentinel -----------------------------------------------------------------


class SentinelSignal(StrictModel):
    id: str = Field(min_length=1, max_length=64)
    kind: Literal["hidden_text", "zero_width", "html_comment", "css_hidden", "instruction_to_agent", "suspicious_link", "other"]
    assessment: Literal["suspicious", "likely_benign", "unclear"]  # detection is not proof of malice
    severity: Severity
    excerpt: str = Field(max_length=2000)
    span: SourceSpan | None = None
    explanation: str = Field(min_length=1, max_length=2000)


class SentinelOutput(StrictModel):
    meta: AgentMeta
    sanitized_text_hash: str = Field(pattern=HEX64)
    signals: list[SentinelSignal] = Field(default_factory=list, max_length=500)
    limitations: list[str] = Field(min_length=1, max_length=20)


# --- Prosecutor / Defense / Clerk --------------------------------------------


class ProsecutorOutput(StrictModel):
    meta: AgentMeta
    charges: list[Finding] = Field(max_length=200)


class DefenseResponse(StrictModel):
    finding_id: str = Field(min_length=1, max_length=64)
    position: Literal["justified", "partially_justified", "not_justified", "insufficient_evidence"]
    argument: str = Field(min_length=1, max_length=4000)
    status: EvidenceStatus
    citations: list[SourceSpan] = Field(default_factory=list, max_length=20)

    @model_validator(mode="after")
    def _justification_needs_evidence(self):
        if self.position in ("justified", "partially_justified") and not self.citations:
            raise ValueError("a justification must cite source text")
        return self


class DefenseOutput(StrictModel):
    meta: AgentMeta
    responses: list[DefenseResponse] = Field(max_length=200)


class EvidenceCheck(StrictModel):
    finding_id: str = Field(min_length=1, max_length=64)
    citation_valid: bool
    support: Literal["direct", "interpretation", "unsupported", "contradicted"]
    note: str = Field(max_length=2000, default="")


class ClerkOutput(StrictModel):
    meta: AgentMeta
    checks: list[EvidenceCheck] = Field(max_length=400)


# --- Judge --------------------------------------------------------------------


class Confidence(StrictModel):
    component: Literal["clause_extraction", "data_classification", "evidence_support", "semantic_change", "decision_reliability"]
    value: float | None = Field(default=None, ge=0.0, le=1.0)
    basis: Literal["heuristic", "calibrated", "not_available"]
    explanation: str = Field(min_length=1, max_length=1000)

    @model_validator(mode="after")
    def _value_needs_basis(self):
        if self.basis == "not_available" and self.value is not None:
            raise ValueError("a confidence value requires a heuristic or calibrated basis")
        if self.basis != "not_available" and self.value is None:
            raise ValueError("value missing for a heuristic or calibrated confidence")
        return self


class CategoryAssessment(StrictModel):
    category: PolicyCategory
    risk_level: Literal["none", "low", "medium", "high", "unknown"]
    finding_ids: list[str] = Field(default_factory=list, max_length=100)
    explanation: str = Field(min_length=1, max_length=2000)


class Disagreement(StrictModel):
    finding_id: str = Field(min_length=1, max_length=64)
    prosecutor_view: str = Field(min_length=1, max_length=2000)
    defense_view: str = Field(min_length=1, max_length=2000)
    resolved: bool
    resolution: str = Field(default="", max_length=2000)


class RiskScore(StrictModel):
    value: int = Field(ge=0, le=100)
    method: str = Field(min_length=1, max_length=200)  # name of the documented, deterministic formula used
    inputs: dict[str, float]


class JudgeOutput(StrictModel):
    meta: AgentMeta
    recommendation: Decision  # advisory only; the Guardian never treats it as authorization
    headline: str = Field(default="", max_length=300)
    category_map: list[CategoryAssessment] = Field(max_length=8)
    questions_to_ask: list[str] = Field(default_factory=list, max_length=20)
    safer_choices: list[str] = Field(default_factory=list, max_length=20)
    agreements: list[str] = Field(default_factory=list, max_length=100)
    disagreements: list[Disagreement] = Field(default_factory=list, max_length=100)
    missing_information: list[str] = Field(default_factory=list, max_length=50)
    risk_score: RiskScore | None = None
    confidence: list[Confidence] = Field(default_factory=list, max_length=5)
    limitations: list[str] = Field(min_length=1, max_length=20)

    @model_validator(mode="after")
    def _consistency(self):
        cats = [c.category for c in self.category_map]
        if len(cats) != len(set(cats)):
            raise ValueError("each category may appear only once in category_map")
        if self.recommendation == Decision.ALLOW and any(not d.resolved for d in self.disagreements):
            raise ValueError("an unresolved disagreement cannot produce an ALLOW recommendation")
        if self.recommendation == Decision.ALLOW and self.missing_information:
            raise ValueError("missing information cannot produce an ALLOW recommendation")
        return self


# --- Watchman -----------------------------------------------------------------


class WatchmanChange(StrictModel):
    old_clause_id: str | None = Field(default=None, max_length=64)
    new_clause_id: str | None = Field(default=None, max_length=64)
    old_text: str = Field(default="", max_length=8000)
    new_text: str = Field(default="", max_length=8000)
    classification: Literal["FORMATTING_ONLY", "WORDING_NO_MATERIAL_CHANGE", "POTENTIALLY_MATERIAL", "AMBIGUOUS"]
    categories: list[PolicyCategory] = Field(default_factory=list, max_length=8)
    explanation: str = Field(min_length=1, max_length=2000)


class WatchmanOutput(StrictModel):
    meta: AgentMeta
    status: Literal["NO_CHANGE", "CHANGED", "UNKNOWN"]
    previous_hash: str = Field(pattern=HEX64)
    new_hash: str | None = Field(default=None, pattern=HEX64)
    changes: list[WatchmanChange] = Field(default_factory=list, max_length=500)
    error: str | None = Field(default=None, max_length=2000)

    @model_validator(mode="after")
    def _status_consistency(self):
        if self.status == "UNKNOWN":
            if self.new_hash is not None or not self.error:
                raise ValueError("UNKNOWN (failed retrieval) needs an error and no new hash")
        elif self.new_hash is None:
            raise ValueError("a completed comparison needs the new hash")
        if self.status == "NO_CHANGE" and (self.changes or self.new_hash != self.previous_hash):
            raise ValueError("NO_CHANGE requires identical hashes and no changes")
        if self.status == "CHANGED" and not self.changes:
            raise ValueError("CHANGED requires at least one change")
        return self


# --- Independent auditor ------------------------------------------------------


class AuditIssue(StrictModel):
    kind: Literal[
        "unsupported_claim", "wrong_citation", "self_contradiction", "agent_contradiction",
        "omitted_risk", "score_mismatch", "overreach", "schema",
    ]
    severity: Severity
    finding_id: str | None = Field(default=None, max_length=64)
    evidence: list[SourceSpan] = Field(default_factory=list, max_length=20)
    explanation: str = Field(min_length=1, max_length=2000)


class AuditorOutput(StrictModel):
    meta: AgentMeta
    verdict: Literal["PASS", "FAIL", "ABSTAIN"]
    issues: list[AuditIssue] = Field(default_factory=list, max_length=200)
    explanation: str = Field(min_length=1, max_length=4000)
    abstain_reason: str | None = Field(default=None, max_length=2000)

    @model_validator(mode="after")
    def _verdict_consistency(self):
        if self.verdict == "FAIL" and not self.issues:
            raise ValueError("FAIL requires at least one issue")
        if self.verdict == "ABSTAIN" and not self.abstain_reason:
            raise ValueError("ABSTAIN requires a reason")
        if self.verdict == "PASS" and any(i.severity in (Severity.HIGH, Severity.CRITICAL) for i in self.issues):
            raise ValueError("PASS cannot carry HIGH or CRITICAL issues")
        return self


CONTRACTS: dict[AgentName, type[StrictModel]] = {
    AgentName.SENTINEL: SentinelOutput,
    AgentName.PROSECUTOR: ProsecutorOutput,
    AgentName.DEFENSE: DefenseOutput,
    AgentName.EVIDENCE_CLERK: ClerkOutput,
    AgentName.JUDGE: JudgeOutput,
    AgentName.WATCHMAN: WatchmanOutput,
    AgentName.AUDITOR: AuditorOutput,
}


class AgentOutputError(Exception):
    def __init__(self, agent: AgentName, errors: list[str]):
        self.agent = agent
        self.errors = errors
        super().__init__(f"{agent} output rejected: {'; '.join(errors)}")


def validate_agent_output(agent: AgentName, raw: str | dict) -> StrictModel:
    """Parse and validate one agent's output. Raises AgentOutputError; never returns a partially valid object."""
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except json.JSONDecodeError as e:
            raise AgentOutputError(agent, [f"not valid JSON: {e.msg}"]) from None
    if not isinstance(raw, dict):
        raise AgentOutputError(agent, ["output must be a JSON object"])
    try:
        parsed = CONTRACTS[agent].model_validate(raw)
    except ValidationError as e:
        raise AgentOutputError(agent, [f"{'.'.join(map(str, err['loc']))}: {err['msg']}" for err in e.errors()]) from None
    if parsed.meta.agent != agent:
        # An output claiming another role (e.g. Sentinel output labelled "judge") is a role-escalation attempt.
        raise AgentOutputError(agent, [f"meta.agent is '{parsed.meta.agent}', expected '{agent}'"])
    return parsed
