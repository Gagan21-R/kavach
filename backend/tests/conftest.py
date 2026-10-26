from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from sqlalchemy import create_engine

from app import clock, ratelimit
from app.db import Base, get_db
from app.gateway import adapters
from app.main import create_app

PASSWORD = "correct horse battery staple"
POLICY_TEXT = "MapsCo collects your location to provide navigation. We do not sell location data."


@pytest.fixture
def engine():
    eng = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)

    @event.listens_for(eng, "connect")
    def _fk(conn, _):
        conn.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(eng)
    yield eng
    eng.dispose()


@pytest.fixture
def Session(engine):
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


@pytest.fixture
def app(Session):
    application = create_app()

    def _get_db():
        db = Session()
        try:
            yield db
        finally:
            db.close()

    application.dependency_overrides[get_db] = _get_db
    return application


@pytest.fixture(autouse=True)
def _reset_state():
    ratelimit.reset()
    adapters.CALL_LOG.clear()
    yield
    adapters.CALL_LOG.clear()


class FrozenClock:
    def __init__(self):
        self.now = datetime(2026, 10, 26, 12, 0, tzinfo=timezone.utc)

    def __call__(self):
        return self.now

    def advance(self, **kw):
        self.now += timedelta(**kw)


@pytest.fixture
def frozen(monkeypatch):
    fc = FrozenClock()
    monkeypatch.setattr(clock, "utcnow", fc)
    return fc


class Actor:
    """A signed-in human with a browser-like client (cookie + CSRF header)."""

    def __init__(self, app, email):
        self.app = app
        self.client = TestClient(app)
        r = self.client.post("/auth/register", json={"email": email, "password": PASSWORD})
        assert r.status_code == 201, r.text
        self.user_id = r.json()["id"]
        r = self.client.post("/auth/login", json={"email": email, "password": PASSWORD})
        assert r.status_code == 200, r.text
        self.client.headers["X-CSRF-Token"] = r.json()["csrf_token"]

    def step_up(self):
        r = self.client.post("/auth/step-up", json={"password": PASSWORD})
        assert r.status_code == 200, r.text

    def rule(self, effect, categories, purposes=(), recipients=(), actions=(), expires_at=None, expect=201):
        body = {"effect": effect, "data_categories": list(categories), "purposes": list(purposes),
                "recipients": list(recipients), "actions": list(actions)}
        if expires_at is not None:
            body["expires_at"] = expires_at.isoformat()
        r = self.client.post("/consent/rules", json=body)
        assert r.status_code == expect, r.text
        return r.json()

    def policy(self, domain="maps.example.com", text=POLICY_TEXT):
        r = self.client.post("/policies", json={"name": domain, "domain": domain, "text": text})
        assert r.status_code == 201, r.text
        return r.json()["id"]

    def agent(self, name="demo-agent"):
        r = self.client.post("/agents", json={"name": name})
        assert r.status_code == 201, r.text
        data = r.json()
        client = TestClient(self.app)
        client.headers["X-Agent-Key"] = data["api_key"]
        return data["id"], client


@pytest.fixture
def make_actor(app):
    counter = {"n": 0}

    def _make(email=None):
        counter["n"] += 1
        return Actor(app, email or f"user{counter['n']}@example.com")

    return _make


def action(policy_id, destination="maps.example.com", purpose="navigation", categories=("location",), act="transfer_data", **extra):
    return {"action": act, "destination": destination, "purpose": purpose,
            "data_categories": list(categories), "policy_source_id": policy_id, **extra}


def execute_body(destination="maps.example.com", purpose="navigation", categories=("location",), act="transfer_data", record_count=1, payload=None):
    body = {"action": act, "destination": destination, "purpose": purpose,
            "data_categories": list(categories), "record_count": record_count}
    if payload is not None:
        body["payload"] = payload
    return body


@pytest.fixture
def granted(make_actor):
    """A user who allows location for navigation to maps.example.com, with an agent holding a fresh token."""

    def _granted(**authorize_extra):
        user = make_actor()
        user.rule("ALLOW", ["location"], purposes=["navigation"], recipients=["maps.example.com"])
        policy_id = user.policy()
        agent_id, agent = user.agent()
        r = agent.post("/guardian/authorize", json=action(policy_id, **authorize_extra))
        assert r.status_code == 201, r.text
        return user, agent, agent_id, policy_id, r.json()["token"], r.json()["token_info"]

    return _granted
