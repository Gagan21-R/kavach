from datetime import datetime

from sqlalchemy import Boolean, ForeignKey, Integer, String, Text
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
    requires_reassessment: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=now)


class PolicySnapshot(Base):
    __tablename__ = "policy_snapshots"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    source_id: Mapped[str] = mapped_column(ForeignKey("policy_sources.id"), index=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    version: Mapped[int] = mapped_column(Integer)
    content_hash: Mapped[str] = mapped_column(String(64))
    text: Mapped[str] = mapped_column(Text)
    retrieved_at: Mapped[datetime] = mapped_column(UTCDateTime, default=now)
