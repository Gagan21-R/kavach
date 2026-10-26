from datetime import datetime

from sqlalchemy import JSON, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base, UTCDateTime
from app.models._common import new_id, now


class DataAsset(Base):
    """A labelled piece of user data (metadata only, never the raw value). Derived assets keep links to their
    sources so restrictions on the source follow the derived data."""

    __tablename__ = "data_assets"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    label: Mapped[str] = mapped_column(String(200))
    categories: Mapped[list] = mapped_column(JSON)  # declared on this asset
    source: Mapped[str] = mapped_column(String(200), default="")  # e.g. "device:gps"
    derived_from: Mapped[list] = mapped_column(JSON, default=list)
    transformation: Mapped[str] = mapped_column(String(200), default="")
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=now)


class FlowEvent(Base):
    """Every attempted protected flow through the gateway, blocked or completed."""

    __tablename__ = "flow_events"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    agent_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    asset_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    action: Mapped[str] = mapped_column(String(40))
    destination: Mapped[str] = mapped_column(String(253))
    purpose: Mapped[str] = mapped_column(String(40))
    declared_categories: Mapped[list] = mapped_column(JSON)
    effective_categories: Mapped[list] = mapped_column(JSON)
    decision: Mapped[str] = mapped_column(String(20))
    outcome: Mapped[str] = mapped_column(String(40))  # BLOCKED_BEFORE_EXECUTION / COMPLETED / ADAPTER_FAILED
    code: Mapped[str | None] = mapped_column(String(40), nullable=True)
    reason: Mapped[str] = mapped_column(Text, default="")
    token_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    records: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=now)


class Incident(Base):
    __tablename__ = "incidents"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    state: Mapped[str] = mapped_column(String(20))  # SUSPECTED / CONTAINED / INVESTIGATING / RECOVERING / RESOLVED
    reason: Mapped[str] = mapped_column(Text)
    actions: Mapped[list] = mapped_column(JSON, default=list)  # containment steps taken, with counts
    timeline: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=now)
    contained_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)


class RedTeamRun(Base):
    __tablename__ = "red_team_runs"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    seed: Mapped[int] = mapped_column(Integer)
    summary: Mapped[dict] = mapped_column(JSON)
    results: Mapped[list] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=now)
