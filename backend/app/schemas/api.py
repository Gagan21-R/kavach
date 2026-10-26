"""Request/response models for the HTTP API."""
import re
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.engine.hosts import normalize_host
from app.vocab import DataCategory, Decision, ProtectedAction, Purpose, RuleEffect

_EMAIL = re.compile(r"^[^@\s]{1,64}@[^@\s]+\.[^@\s]+$")


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


def _host(v: str) -> str:
    host = normalize_host(v)
    if host is None:
        raise ValueError("must be a valid hostname, e.g. maps.example.com")
    return host


# --- auth ---------------------------------------------------------------------


class Credentials(Strict):
    email: str = Field(max_length=320)
    password: str = Field(min_length=1, max_length=256)

    @field_validator("email")
    @classmethod
    def _email(cls, v: str) -> str:
        v = v.strip().lower()
        if not _EMAIL.match(v):
            raise ValueError("invalid email address")
        return v


class StepUpIn(Strict):
    password: str = Field(min_length=1, max_length=256)


class UserOut(BaseModel):
    id: str
    email: str
    constitution_version: int


class LoginOut(BaseModel):
    user: UserOut
    csrf_token: str
    expires_at: datetime


# --- agents -------------------------------------------------------------------


class AgentIn(Strict):
    name: str = Field(min_length=1, max_length=120)


class AgentOut(BaseModel):
    id: str
    name: str
    active: bool
    created_at: datetime


class AgentCreatedOut(AgentOut):
    api_key: str  # shown exactly once


# --- consent rules ------------------------------------------------------------

CategoryOrAny = DataCategory | Literal["*"]
PurposeOrAny = Purpose | Literal["*"]
ActionOrAny = ProtectedAction | Literal["*"]


class RuleIn(Strict):
    effect: RuleEffect
    data_categories: list[CategoryOrAny] = Field(min_length=1, max_length=20)
    purposes: list[PurposeOrAny] = Field(default_factory=list, max_length=20)
    recipients: list[str] = Field(default_factory=list, max_length=50)
    actions: list[ActionOrAny] = Field(default_factory=list, max_length=10)
    description: str = Field(default="", max_length=1000)
    expires_at: datetime | None = None

    @field_validator("recipients")
    @classmethod
    def _recipients(cls, v: list[str]) -> list[str]:
        out = []
        for item in v:
            item = item.strip().lower()
            if item == "*":
                out.append(item)
            elif item.startswith("*."):
                out.append("*." + _host(item[2:]))
            else:
                out.append(_host(item))
        return out

    @field_validator("expires_at")
    @classmethod
    def _aware(cls, v: datetime | None) -> datetime | None:
        if v is not None and v.tzinfo is None:
            raise ValueError("expires_at must include a timezone")
        return v


class RuleOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    effect: str
    data_categories: list[str]
    purposes: list[str]
    recipients: list[str]
    actions: list[str]
    description: str
    expires_at: datetime | None
    active: bool
    supersedes_id: str | None
    constitution_version: int
    created_at: datetime
    revoked_at: datetime | None


# --- policies -----------------------------------------------------------------


class PolicyIn(Strict):
    name: str = Field(min_length=1, max_length=200)
    url: str | None = Field(default=None, max_length=2048)
    domain: str | None = Field(default=None, max_length=253)
    locale: str | None = Field(default=None, max_length=35)
    text: str = Field(min_length=1, max_length=500_000)

    @model_validator(mode="after")
    def _domain(self):
        source = self.domain or self.url
        if not source:
            raise ValueError("provide url or domain")
        self.domain = _host(source)
        if self.url is not None and not self.url.lower().startswith(("http://", "https://")):
            raise ValueError("url must be http(s)")
        return self


class SnapshotIn(Strict):
    text: str = Field(min_length=1, max_length=500_000)


class PolicyOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    url: str | None
    domain: str
    locale: str | None
    current_snapshot_id: str | None
    current_hash: str | None
    current_version: int
    last_material_version: int
    requires_reassessment: bool
    current_analysis_id: str | None
    watch_status: str
    watch_error: str | None
    last_checked_at: datetime | None
    created_at: datetime


class SnapshotOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    version: int
    content_hash: str
    retrieved_at: datetime
    length: int
    classification: str | None


# --- guardian -----------------------------------------------------------------


class ActionIn(Strict):
    action: ProtectedAction
    destination: str = Field(max_length=253)
    purpose: Purpose
    data_categories: list[DataCategory] = Field(min_length=1, max_length=20)

    @field_validator("destination")
    @classmethod
    def _dest(cls, v: str) -> str:
        return _host(v)


class GuardianIn(ActionIn):
    policy_source_id: str = Field(min_length=1, max_length=32)


class AuthorizeIn(GuardianIn):
    ttl_seconds: int | None = Field(default=None, ge=1)
    max_uses: int = Field(default=1, ge=1)
    max_records: int = Field(default=1, ge=1, le=1_000_000)
    approval_id: str | None = Field(default=None, max_length=32)


class CategoryOutcomeOut(BaseModel):
    category: str
    decision: Decision
    sensitive: bool
    matched_rule_ids: list[str]
    deciding_rule_ids: list[str]
    reason: str


class EvaluationOut(BaseModel):
    decision: Decision
    approvable: bool
    reasons: list[str]
    outcomes: list[CategoryOutcomeOut]
    deciding_rule_ids: list[str]
    constitution_version: int
    policy_hash: str | None = None
    evaluation_id: str | None = None


class TokenOut(BaseModel):
    id: str
    agent_id: str
    action: str
    destination: str
    purpose: str
    data_categories: list[str]
    policy_source_id: str
    policy_hash: str
    issued_at: datetime
    expires_at: datetime
    max_uses: int
    use_count: int
    max_records: int
    records_used: int
    revoked_at: datetime | None
    revocation_reason: str | None
    approval_id: str | None


class AuthorizeOut(BaseModel):
    decision: Decision
    evaluation: EvaluationOut
    token: str | None = None  # plaintext, shown once
    token_info: TokenOut | None = None
    approval_request_id: str | None = None


class RevokeIn(Strict):
    token_id: str | None = Field(default=None, max_length=32)
    agent_id: str | None = Field(default=None, max_length=32)
    all: bool = False
    reason: str = Field(default="revoked by user", max_length=500)

    @model_validator(mode="after")
    def _one_target(self):
        if sum([self.token_id is not None, self.agent_id is not None, self.all]) != 1:
            raise ValueError("specify exactly one of token_id, agent_id or all=true")
        return self


class ApprovalOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    agent_id: str
    action: str
    destination: str
    purpose: str
    data_categories: list[str]
    policy_source_id: str
    policy_hash: str
    status: str
    reason: str
    created_at: datetime
    decided_at: datetime | None
    expires_at: datetime


# --- gateway ------------------------------------------------------------------


class GatewayIn(ActionIn):
    record_count: int = Field(default=1, ge=1, le=1_000_000)
    # Labelled data being sent. Categories inherited through its lineage must all be declared and covered.
    asset_id: str | None = Field(default=None, max_length=32)
    # Forwarded to the adapter, never stored or logged; only its hash is recorded.
    payload: dict | None = None


class GatewayOut(BaseModel):
    executed: bool
    decision: Decision
    token_id: str
    adapter: str
    simulated: bool
    result: dict


# --- audit --------------------------------------------------------------------


class AuditEventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    seq: int
    id: str
    actor_type: str
    actor_id: str | None
    event_type: str
    target_type: str | None
    target_id: str | None
    decision: str | None
    details: dict
    correlation_id: str | None
    created_at: datetime
