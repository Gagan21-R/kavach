from datetime import datetime

from sqlalchemy import JSON, Boolean, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base, UTCDateTime
from app.models._common import new_id, now


class PolicySource(Base):
    """A privacy policy the user tracks. Policy text is untrusted data and is never executed or obeyed."""

    __tablename__ = "policy_sources"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    name: Mapped[str] = mapped_column(String(200))
    url: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    # Host the policy governs; destinations outside it are not covered by this policy.
    domain: Mapped[str] = mapped_column(String(253))
    locale: Mapped[str | None] = mapped_column(String(35), nullable=True)
    current_snapshot_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    current_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    current_version: Mapped[int] = mapped_column(Integer, default=0)
    # Version number of the last snapshot Watchman judged material (or ambiguous). Tokens issued under an
    # earlier version are stale; formatting-only and non-material wording changes do not bump it.
    last_material_version: Mapped[int] = mapped_column(Integer, default=1)
    requires_reassessment: Mapped[bool] = mapped_column(Boolean, default=False)
    current_analysis_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    watch_status: Mapped[str] = mapped_column(String(20), default="OK")  # OK / UNKNOWN
    watch_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_checked_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=now)


class PolicySnapshot(Base):
    __tablename__ = "policy_snapshots"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    source_id: Mapped[str] = mapped_column(ForeignKey("policy_sources.id"), index=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    version: Mapped[int] = mapped_column(Integer)
    content_hash: Mapped[str] = mapped_column(String(64))
    text: Mapped[str] = mapped_column(Text)
    classification: Mapped[str | None] = mapped_column(String(40), nullable=True)  # vs previous version; None for v1
    retrieved_at: Mapped[datetime] = mapped_column(UTCDateTime, default=now)


class AnalysisRun(Base):
    """One court trial of one snapshot. `result` holds every validated agent output and the debate transcript."""

    __tablename__ = "analysis_runs"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    source_id: Mapped[str] = mapped_column(ForeignKey("policy_sources.id"), index=True)
    snapshot_id: Mapped[str] = mapped_column(ForeignKey("policy_snapshots.id"))
    snapshot_version: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(20))  # COMPLETED / FAILED
    recommendation: Mapped[str] = mapped_column(String(20))
    audit_verdict: Mapped[str] = mapped_column(String(20))
    risk_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    sentinel_suspicious: Mapped[bool] = mapped_column(Boolean, default=False)
    headline: Mapped[str] = mapped_column(Text, default="")
    result: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=now)


class WatchEvent(Base):
    """One Watchman check: a comparison between versions, or a failed retrieval (UNKNOWN, never UNCHANGED)."""

    __tablename__ = "watch_events"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    source_id: Mapped[str] = mapped_column(ForeignKey("policy_sources.id"), index=True)
    status: Mapped[str] = mapped_column(String(20))  # NO_CHANGE / CHANGED / UNKNOWN
    classification: Mapped[str | None] = mapped_column(String(40), nullable=True)
    from_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    to_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    output: Mapped[dict] = mapped_column(JSON, default=dict)
    affected_rule_ids: Mapped[list] = mapped_column(JSON, default=list)
    affected_token_ids: Mapped[list] = mapped_column(JSON, default=list)
    recommendations: Mapped[list] = mapped_column(JSON, default=list)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=now)
