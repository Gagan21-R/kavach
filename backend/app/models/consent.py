from datetime import datetime

from sqlalchemy import JSON, Boolean, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base, UTCDateTime
from app.models._common import new_id, now


class ConsentRule(Base):
    """One clause of a user's Personal Consent Constitution.

    Rules are immutable: an edit creates a new row that supersedes the old one, so history is never lost.
    Empty lists for purposes/recipients/actions mean "any".
    """

    __tablename__ = "consent_rules"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    effect: Mapped[str] = mapped_column(String(20))
    data_categories: Mapped[list] = mapped_column(JSON)
    purposes: Mapped[list] = mapped_column(JSON, default=list)
    recipients: Mapped[list] = mapped_column(JSON, default=list)
    actions: Mapped[list] = mapped_column(JSON, default=list)
    description: Mapped[str] = mapped_column(Text, default="")
    expires_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    supersedes_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    constitution_version: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=now)
    revoked_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)


class ApprovalRequest(Base):
    """Created when a rule says REQUIRE_APPROVAL. The user approves the exact scope, then the agent may request a token."""

    __tablename__ = "approval_requests"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    agent_id: Mapped[str] = mapped_column(ForeignKey("agent_clients.id"))
    action: Mapped[str] = mapped_column(String(40))
    destination: Mapped[str] = mapped_column(String(253))
    purpose: Mapped[str] = mapped_column(String(40))
    data_categories: Mapped[list] = mapped_column(JSON)
    policy_source_id: Mapped[str] = mapped_column(ForeignKey("policy_sources.id"))
    policy_hash: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(20), default="PENDING")  # PENDING / APPROVED / DENIED / USED
    reason: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=now)
    decided_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    expires_at: Mapped[datetime] = mapped_column(UTCDateTime)


class ConsentToken(Base):
    """Opaque, server-side capability. Only the hash of the secret is stored; no personal data in the token."""

    __tablename__ = "consent_tokens"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)  # jti
    secret_hash: Mapped[str] = mapped_column(String(64))
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    agent_id: Mapped[str] = mapped_column(ForeignKey("agent_clients.id"), index=True)
    action: Mapped[str] = mapped_column(String(40))
    destination: Mapped[str] = mapped_column(String(253))
    purpose: Mapped[str] = mapped_column(String(40))
    data_categories: Mapped[list] = mapped_column(JSON)
    policy_source_id: Mapped[str] = mapped_column(ForeignKey("policy_sources.id"))
    policy_hash: Mapped[str] = mapped_column(String(64))
    policy_version: Mapped[int] = mapped_column(Integer, default=1)
    constitution_version: Mapped[int] = mapped_column(Integer)
    approval_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    issued_at: Mapped[datetime] = mapped_column(UTCDateTime, default=now)
    expires_at: Mapped[datetime] = mapped_column(UTCDateTime)
    max_uses: Mapped[int] = mapped_column(Integer, default=1)
    use_count: Mapped[int] = mapped_column(Integer, default=0)
    max_records: Mapped[int] = mapped_column(Integer, default=1)
    records_used: Mapped[int] = mapped_column(Integer, default=0)
    revoked_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    revocation_reason: Mapped[str | None] = mapped_column(Text, nullable=True)


class TokenUse(Base):
    """Every attempt to use a token at the gateway, accepted or rejected."""

    __tablename__ = "token_uses"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    token_id: Mapped[str | None] = mapped_column(String(32), index=True, nullable=True)
    user_id: Mapped[str | None] = mapped_column(String(32), index=True, nullable=True)
    agent_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    outcome: Mapped[str] = mapped_column(String(30))  # ACCEPTED or a rejection code
    records: Mapped[int] = mapped_column(Integer, default=0)
    detail: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=now)
