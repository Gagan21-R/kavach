from datetime import datetime

from sqlalchemy import JSON, Boolean, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base, UTCDateTime
from app.models._common import new_id, now


class ExtensionClient(Base):
    """A browser extension paired with the user's account. It authenticates with its own key (X-Extension-Key)."""

    __tablename__ = "extension_clients"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    name: Mapped[str] = mapped_column(String(120))
    key_hash: Mapped[str] = mapped_column(String(64))
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=now)
    last_seen_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)


class SiteVisit(Base):
    """A website the user opened while the extension was on. Only the site's domain is stored, never the page."""

    __tablename__ = "site_visits"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    domain: Mapped[str] = mapped_column(String(253))
    first_seen_at: Mapped[datetime] = mapped_column(UTCDateTime, default=now)
    last_seen_at: Mapped[datetime] = mapped_column(UTCDateTime, default=now)
    visit_count: Mapped[int] = mapped_column(Integer, default=1)
    # LOOKING / TRACKED / NOT_FOUND
    status: Mapped[str] = mapped_column(String(20), default="LOOKING")
    policy_source_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    verdict: Mapped[dict] = mapped_column(JSON, default=dict)
    consent_moments: Mapped[int] = mapped_column(Integer, default=0)
    note: Mapped[str] = mapped_column(Text, default="")


class EmailSignal(Base):
    """A "we're updating our terms" email. Only headers, matched phrases and policy links are kept, never the body."""

    __tablename__ = "email_signals"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), index=True, nullable=True)
    channel: Mapped[str] = mapped_column(String(20))  # forward / upload / mailbox
    from_address: Mapped[str] = mapped_column(String(320), default="")
    from_domain: Mapped[str] = mapped_column(String(253), default="")
    subject: Mapped[str] = mapped_column(String(500), default="")
    service_name: Mapped[str] = mapped_column(String(200), default="")
    is_policy_update: Mapped[bool] = mapped_column(Boolean, default=False)
    authenticated: Mapped[bool] = mapped_column(Boolean, default=False)
    matched_phrases: Mapped[list] = mapped_column(JSON, default=list)
    links: Mapped[list] = mapped_column(JSON, default=list)
    actions: Mapped[list] = mapped_column(JSON, default=list)
    received_at: Mapped[datetime] = mapped_column(UTCDateTime, default=now)


class FetchCache(Base):
    """One shared copy of each fetched policy page, so many users tracking it cause one request to the site."""

    __tablename__ = "fetch_cache"

    url: Mapped[str] = mapped_column(String(2048), primary_key=True)
    ok: Mapped[bool] = mapped_column(Boolean)
    text: Mapped[str] = mapped_column(Text, default="")
    method: Mapped[str] = mapped_column(String(30), default="")
    source_url: Mapped[str] = mapped_column(String(2048), default="")
    error: Mapped[str] = mapped_column(Text, default="")
    attempts: Mapped[list] = mapped_column(JSON, default=list)
    # Validators from the site's last full response, sent back on re-checks so an unchanged page costs a 304.
    etag: Mapped[str] = mapped_column(String(300), default="", server_default="")
    last_modified: Mapped[str] = mapped_column(String(100), default="", server_default="")
    fetched_at: Mapped[datetime] = mapped_column(UTCDateTime, default=now)


class Notification(Base):
    """Something new the user should look at: a policy change, a risky site review, an agent waiting for a decision.
    Read notifications drop out of the panel."""

    __tablename__ = "notifications"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    kind: Mapped[str] = mapped_column(String(40))
    title: Mapped[str] = mapped_column(String(300))
    body: Mapped[str] = mapped_column(Text, default="")
    tone: Mapped[str] = mapped_column(String(20), default="info")  # bad / warn / info
    section: Mapped[str] = mapped_column(String(40), default="")  # where "Open" takes the user
    ref_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=now)
    read_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
