"""Consent tokens: opaque, server-side, scoped capabilities.

Plaintext form is "cct_<jti>.<secret>"; only sha256(secret) is stored. Claims live in the database, never in the
token, so a token carries no personal data and can be revoked instantly.
"""
from datetime import datetime

from sqlalchemy import update
from sqlalchemy.orm import Session

from app.auth.crypto import constant_time_equal, make_compound_secret, sha256, split_compound_secret
from app.models import AgentClient, ConsentToken, PolicySource
from app.models._common import new_id


class TokenRejected(Exception):
    def __init__(self, code: str, message: str, token: ConsentToken | None = None):
        self.code = code
        self.message = message
        self.token = token
        super().__init__(f"{code}: {message}")


def issue(
    db: Session,
    *,
    user_id: str,
    agent_id: str,
    action: str,
    destination: str,
    purpose: str,
    data_categories: list[str],
    policy: PolicySource,
    constitution_version: int,
    issued_at: datetime,
    expires_at: datetime,
    max_uses: int,
    max_records: int,
    approval_id: str | None,
) -> tuple[str, ConsentToken]:
    jti = new_id()
    plaintext, secret_hash = make_compound_secret("cct", jti)
    token = ConsentToken(
        id=jti,
        secret_hash=secret_hash,
        user_id=user_id,
        agent_id=agent_id,
        action=action,
        destination=destination,
        purpose=purpose,
        data_categories=sorted(set(data_categories)),
        policy_source_id=policy.id,
        policy_hash=policy.current_hash,
        policy_version=policy.current_version,
        constitution_version=constitution_version,
        approval_id=approval_id,
        issued_at=issued_at,
        expires_at=expires_at,
        max_uses=max_uses,
        max_records=max_records,
    )
    db.add(token)
    return plaintext, token


def lookup(db: Session, plaintext: str) -> ConsentToken:
    parts = split_compound_secret("cct", plaintext or "")
    if parts is None:
        raise TokenRejected("INVALID_TOKEN", "consent token missing or malformed")
    jti, secret = parts
    token = db.get(ConsentToken, jti)
    if token is None or not constant_time_equal(token.secret_hash, sha256(secret)):
        raise TokenRejected("INVALID_TOKEN", "consent token not recognised")
    return token


def check_static(
    token: ConsentToken,
    *,
    agent: AgentClient,
    action: str,
    destination: str,
    purpose: str,
    data_categories: list[str],
    record_count: int,
    policy: PolicySource | None,
    now: datetime,
) -> None:
    """Every check that does not need the user's current rules. Order matters only for which reason is reported."""
    if token.agent_id != agent.id or token.user_id != agent.user_id:
        raise TokenRejected("WRONG_AGENT", "token was issued to a different agent", token)
    if token.revoked_at is not None:
        raise TokenRejected("REVOKED", f"token revoked: {token.revocation_reason or 'no reason given'}", token)
    if now >= token.expires_at:
        raise TokenRejected("EXPIRED", "token has expired", token)
    if action != token.action:
        raise TokenRejected("WRONG_ACTION", f"token authorizes '{token.action}', not '{action}'", token)
    if destination != token.destination:
        raise TokenRejected("WRONG_DESTINATION", f"token is bound to {token.destination}, not {destination}", token)
    if purpose != token.purpose:
        raise TokenRejected("WRONG_PURPOSE", f"token is for purpose '{token.purpose}', not '{purpose}'", token)
    extra = sorted(set(data_categories) - set(token.data_categories))
    if extra:
        raise TokenRejected("SCOPE_EXCEEDED", f"token does not cover data categories: {', '.join(extra)}", token)
    # Formatting-only and non-material wording changes keep tokens valid; a material change does not.
    if policy is None or policy.last_material_version > token.policy_version:
        raise TokenRejected("STALE_POLICY", "the destination's policy changed materially since this token was issued", token)
    if policy.requires_reassessment:
        raise TokenRejected("REASSESSMENT_REQUIRED", "the destination's policy is awaiting reassessment", token)
    if token.use_count >= token.max_uses:
        if token.max_uses == 1:
            raise TokenRejected("REPLAYED", "one-time token has already been used", token)
        raise TokenRejected("USAGE_EXHAUSTED", "token has no uses left", token)
    if token.records_used + record_count > token.max_records:
        raise TokenRejected(
            "BUDGET_EXCEEDED",
            f"request of {record_count} records exceeds remaining budget of {token.max_records - token.records_used}",
            token,
        )


def consume(db: Session, token: ConsentToken, record_count: int, now: datetime) -> None:
    """Atomically spends one use and the record budget. A single conditional UPDATE, so two concurrent requests
    cannot both pass a check made on stale in-memory values."""
    result = db.execute(
        update(ConsentToken)
        .where(
            ConsentToken.id == token.id,
            ConsentToken.revoked_at.is_(None),
            ConsentToken.expires_at > now,
            ConsentToken.use_count < ConsentToken.max_uses,
            ConsentToken.records_used + record_count <= ConsentToken.max_records,
        )
        .values(use_count=ConsentToken.use_count + 1, records_used=ConsentToken.records_used + record_count)
        .execution_options(synchronize_session=False)
    )
    if result.rowcount != 1:
        db.refresh(token)
        if token.revoked_at is not None:
            raise TokenRejected("REVOKED", "token was revoked", token)
        if now >= token.expires_at:
            raise TokenRejected("EXPIRED", "token has expired", token)
        if token.use_count >= token.max_uses:
            raise TokenRejected("REPLAYED" if token.max_uses == 1 else "USAGE_EXHAUSTED", "token already used up", token)
        raise TokenRejected("BUDGET_EXCEEDED", "record budget exhausted", token)
    db.refresh(token)
