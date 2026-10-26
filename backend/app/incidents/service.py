"""Emergency Stop: contain first, investigate, then recover deliberately.

Containment freezes protected actions and revokes credentials. It never deletes records: deleting local data
cannot recall copies an attacker already took, and it destroys the evidence needed to understand what happened.
Recovery needs fresh re-authentication and an explicit confirmation, and does not restore revoked tokens or
agent keys: new ones must be issued, which is the credential rotation.
"""
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app import audit_log, clock
from app.errors import APIError, not_found
from app.models import AgentClient, AuthSession, ConsentToken, Incident, User

EXTERNAL_LIMITS = (
    "Data already delivered to other companies before the stop cannot be recalled by Consent Court. "
    "Use the data access and deletion request drafts to ask those companies directly."
)


def _event(incident: Incident, state: str, note: str) -> None:
    incident.timeline = [*incident.timeline, {"at": clock.utcnow().isoformat(), "state": state, "note": note}]


def activate(db: Session, user: User, current_session_id: str, *, reason: str, revoke_tokens: bool = True,
             revoke_agents: bool = False, revoke_other_sessions: bool = True, pause_monitoring: bool = True) -> Incident:
    if user.frozen and user.active_incident_id:
        raise APIError(409, "ALREADY_ACTIVE", "Emergency Stop is already active", incident_id=user.active_incident_id)
    now = clock.utcnow()
    incident = Incident(user_id=user.id, state="SUSPECTED", reason=reason, actions=[], timeline=[])
    db.add(incident)
    db.flush()
    _event(incident, "SUSPECTED", f"Emergency Stop requested: {reason}")
    actions = [{"step": "freeze_protected_actions", "detail": "Guardian and gateway refuse every protected action", "count": None}]
    user.frozen = True
    user.active_incident_id = incident.id
    if revoke_tokens:
        n = db.execute(update(ConsentToken).where(ConsentToken.user_id == user.id, ConsentToken.revoked_at.is_(None))
                       .values(revoked_at=now, revocation_reason=f"emergency stop {incident.id}")
                       .execution_options(synchronize_session=False)).rowcount
        actions.append({"step": "revoke_tokens", "detail": "All active consent tokens revoked", "count": n})
    if revoke_agents:
        agent_ids = list(db.execute(select(AgentClient.id).where(AgentClient.user_id == user.id, AgentClient.active.is_(True))).scalars())
        db.execute(update(AgentClient).where(AgentClient.id.in_(agent_ids)).values(active=False, revoked_at=now)
                   .execution_options(synchronize_session=False))
        actions.append({"step": "revoke_agent_keys", "detail": "Agent API keys disabled; issue new keys after recovery", "count": len(agent_ids)})
    if revoke_other_sessions:
        n = db.execute(update(AuthSession).where(AuthSession.user_id == user.id, AuthSession.id != current_session_id,
                                                 AuthSession.revoked_at.is_(None))
                       .values(revoked_at=now).execution_options(synchronize_session=False)).rowcount
        actions.append({"step": "revoke_other_sessions", "detail": "Signed out every other device", "count": n})
    if pause_monitoring:
        actions.append({"step": "pause_scheduled_checks", "detail": "Scheduled Watchman checks skip this account while frozen", "count": None})
    actions.append({"step": "preserve_evidence", "detail": "Audit log, flow events and token history are kept unchanged", "count": None})
    incident.actions = actions
    incident.state = "CONTAINED"
    incident.contained_at = clock.utcnow()
    _event(incident, "CONTAINED", "Containment steps completed")
    audit_log.record(db, "incident.contained", user_id=user.id, actor_type="user", actor_id=user.id,
                     target_type="incident", target_id=incident.id, decision="BLOCK",
                     details={"reason": reason, "actions": [{"step": a["step"], "count": a["count"]} for a in actions]})
    return incident


def owned_incident(db: Session, user_id: str, incident_id: str) -> Incident:
    i = db.get(Incident, incident_id)
    if i is None or i.user_id != user_id:
        raise not_found("incident")
    return i


def add_note(db: Session, user: User, incident_id: str, note: str) -> Incident:
    incident = owned_incident(db, user.id, incident_id)
    if incident.state == "RESOLVED":
        raise APIError(409, "INCIDENT_RESOLVED", "incident is already resolved")
    incident.state = "INVESTIGATING"
    _event(incident, "INVESTIGATING", note)
    audit_log.record(db, "incident.note", user_id=user.id, actor_type="user", actor_id=user.id, target_type="incident",
                     target_id=incident.id, details={"note": note[:500]})
    return incident


def recover(db: Session, user: User, incident_id: str, *, confirmation: str, findings: str) -> Incident:
    incident = owned_incident(db, user.id, incident_id)
    if incident.state == "RESOLVED":
        raise APIError(409, "INCIDENT_RESOLVED", "incident is already resolved")
    if confirmation != "RESTORE":
        raise APIError(422, "CONFIRMATION_REQUIRED", "type RESTORE to confirm recovery")
    incident.state = "RECOVERING"
    _event(incident, "RECOVERING", f"Recovery started. Findings: {findings}")
    user.frozen = False
    user.active_incident_id = None
    incident.state = "RESOLVED"
    incident.resolved_at = clock.utcnow()
    _event(incident, "RESOLVED", "Protected actions re-enabled. Revoked tokens and keys stay revoked; issue new ones as needed.")
    audit_log.record(db, "incident.resolved", user_id=user.id, actor_type="user", actor_id=user.id, target_type="incident",
                     target_id=incident.id, details={"findings": findings[:1000]})
    return incident


def incident_out(i: Incident) -> dict:
    return {"id": i.id, "state": i.state, "reason": i.reason, "actions": i.actions, "timeline": i.timeline,
            "created_at": i.created_at, "contained_at": i.contained_at, "resolved_at": i.resolved_at,
            "external_limits": EXTERNAL_LIMITS}
