from sqlalchemy import update

from app import audit_log
from app.models import AuditEvent
from tests.conftest import execute_body


def test_hash_chain_verifies_and_detects_tampering(granted, Session):
    _, agent, _, _, token, _ = granted()
    agent.post("/gateway/execute", json=execute_body(), headers={"X-Consent-Token": token})
    with Session() as db:
        assert audit_log.verify_chain(db) == (True, None)
        victim = db.query(AuditEvent).filter_by(event_type="token.issued").one()
        db.execute(update(AuditEvent).where(AuditEvent.seq == victim.seq).values(details={"max_uses": 999}))
        db.commit()
        ok, bad_id = audit_log.verify_chain(db)
    assert not ok and bad_id == victim.id


def test_deleting_an_event_breaks_the_chain(granted, Session):
    granted()
    with Session() as db:
        middle = db.query(AuditEvent).order_by(AuditEvent.seq).all()[2]
        db.delete(middle)
        db.commit()
        assert audit_log.verify_chain(db)[0] is False


def test_scrub_redacts_secrets_recursively():
    out = audit_log.scrub({"password": "x", "nested": {"api_key": "k", "ok": 1}, "list": [{"consent_token": "t"}], "payload": {"a": 1}})
    assert out == {"password": "[redacted]", "nested": {"api_key": "[redacted]", "ok": 1},
                   "list": [{"consent_token": "[redacted]"}], "payload": "[redacted]"}


def test_audit_events_carry_correlation_id(make_actor):
    user = make_actor()
    r = user.client.post("/consent/rules", json={"effect": "DENY", "data_categories": ["location"]},
                         headers={"X-Request-ID": "req-123"})
    assert r.headers["X-Request-ID"] == "req-123"
    event = user.client.get("/audit/events?event_type=consent.rule.created").json()[0]
    assert event["correlation_id"] == "req-123"


def test_failed_logins_are_audited_without_the_password(make_actor, app):
    from fastapi.testclient import TestClient

    user = make_actor("victim@example.com")
    TestClient(app).post("/auth/login", json={"email": "victim@example.com", "password": "guess-guess-guess"})
    events = user.client.get("/audit/events?event_type=auth.login_failed").json()
    assert len(events) == 1 and "guess" not in str(events)
