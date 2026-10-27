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


# --- test history: every run is recorded for the dashboard's Test history (see app/testhistory.py) ----------------

_run = {"tests": [], "docs": {}}


def pytest_sessionstart(session):
    import time

    _run.update(start=time.time(), tests=[], docs={})


def pytest_collection_modifyitems(items):
    for item in items:
        doc = getattr(getattr(item, "obj", None), "__doc__", None)
        _run["docs"][item.nodeid] = " ".join(doc.split()) if doc else ""


def pytest_runtest_logreport(report):
    # One entry per test: the call phase, or setup/teardown when that is what failed or skipped.
    if report.when != "call" and report.outcome == "passed":
        return
    if report.when != "call" and any(t["id"] == report.nodeid for t in _run["tests"]):
        return
    from app.testhistory import area_of, humanize

    outcome = report.outcome if report.when == "call" or report.outcome == "skipped" else "error"
    _run["tests"].append({"id": report.nodeid, "area": area_of(report.nodeid), "name": humanize(report.nodeid.split("::")[-1]),
                          "doc": _run["docs"].get(report.nodeid, ""), "outcome": outcome, "duration_s": round(report.duration, 3),
                          "message": report.longreprtext[-2500:] if report.failed else ""})


def pytest_sessionfinish(session, exitstatus):
    import json
    import os
    import secrets
    import subprocess
    import sys
    import time
    from datetime import datetime, timezone

    from app.testhistory import history_dir

    if session.config.option.collectonly or os.environ.get("KAVACH_NO_TEST_HISTORY") or not _run["tests"]:
        return

    def git(*args):
        try:
            return subprocess.run(["git", *args], capture_output=True, text=True, timeout=5, cwd=session.config.rootpath).stdout.strip()
        except (OSError, subprocess.SubprocessError):
            return ""

    started = datetime.fromtimestamp(_run["start"], tz=timezone.utc)
    tests = _run["tests"]
    totals = {k: sum(t["outcome"] == k for t in tests) for k in ("passed", "failed", "error", "skipped")}
    record = {"id": f"{started:%Y%m%d-%H%M%S}-{secrets.token_hex(2)}", "kind": "pytest", "started_at": started.isoformat(),
              "duration_s": round(time.time() - _run["start"], 2), "exit_status": int(exitstatus),
              "commit": git("rev-parse", "--short", "HEAD") or None, "dirty": bool(git("status", "--porcelain")),
              "python": sys.version.split()[0], "args": session.config.invocation_params.args[:20],
              "totals": {"total": len(tests), **totals}, "tests": tests}
    d = history_dir()
    try:
        d.mkdir(parents=True, exist_ok=True)
        (d / f"{record['id']}.json").write_text(json.dumps(record, indent=1), encoding="utf-8")
        with open(d.parent / "history.log", "a", encoding="utf-8") as log:
            log.write(f"{started:%Y-%m-%d %H:%M:%S} UTC  {totals['passed']}/{len(tests)} passed  {totals['failed'] + totals['error']} failed  "
                      f"{record['duration_s']}s  commit {record['commit'] or '-'}{'+changes' if record['dirty'] else ''}  {record['id']}\n")
    except OSError as e:  # never fail a test run because the history couldn't be written
        print(f"\n[test history] not saved: {e}")
