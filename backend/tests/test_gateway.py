"""Gateway bypass resistance and fail-closed behaviour (acceptance tests 3, 17, 19)."""
import ast
import json
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import sessionmaker

from app.db import get_db
from app.gateway import adapters
from app.guardian import tokens
from app.models import AuditEvent, TokenUse
from tests.conftest import execute_body

APP_DIR = Path(__file__).resolve().parents[1] / "app"


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
            names.update(f"{node.module}.{a.name}" for a in node.names)
    return names


def test_only_the_executor_imports_adapters():
    importers = sorted(
        str(p.relative_to(APP_DIR)).replace("\\", "/")
        for p in APP_DIR.rglob("*.py")
        if "app.gateway.adapters" in _imports(p)
    )
    assert importers == ["gateway/executor.py"]


def test_only_the_gateway_router_reaches_the_executor():
    importers = sorted(
        str(p.relative_to(APP_DIR)).replace("\\", "/")
        for p in APP_DIR.rglob("*.py")
        if "app.gateway.executor" in _imports(p)
    )
    assert importers == ["routers/gateway.py"]


def test_adapter_refuses_calls_without_gateway_pass():
    act = adapters.AuthorizedAction("t", "u", "a", "transfer_data", "x.example", "navigation", ("location",), 1)
    with pytest.raises(adapters.AdapterNotAuthorized):
        adapters.simulated_egress(act, None, object())
    assert adapters.CALL_LOG == []


def test_every_protected_action_has_an_adapter():
    from app.vocab import ProtectedAction

    assert set(adapters.ADAPTERS) == {a.value for a in ProtectedAction}


def test_gateway_requires_agent_key(granted, app):
    from fastapi.testclient import TestClient

    _, _, _, _, token, _ = granted()
    r = TestClient(app).post("/gateway/execute", json=execute_body(), headers={"X-Consent-Token": token})
    assert r.status_code == 401
    assert adapters.CALL_LOG == []


def test_authorization_failure_fails_closed(granted, monkeypatch):
    _, agent, _, _, token, _ = granted()

    def broken_lookup(*_a, **_k):
        raise OperationalError("SELECT", {}, Exception("database is locked"))

    monkeypatch.setattr(tokens, "lookup", broken_lookup)
    r = agent.post("/gateway/execute", json=execute_body(), headers={"X-Consent-Token": token})
    assert r.status_code == 503
    err = r.json()["error"]
    assert err["code"] == "AUTHORIZATION_UNAVAILABLE" and err["decision"] == "BLOCK" and err["executed"] is False
    assert adapters.CALL_LOG == []


def test_unexpected_error_in_checks_fails_closed(granted, monkeypatch):
    _, agent, _, _, token, _ = granted()
    monkeypatch.setattr(tokens, "consume", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")))
    r = agent.post("/gateway/execute", json=execute_body(), headers={"X-Consent-Token": token})
    assert r.status_code == 503 and adapters.CALL_LOG == []


def test_database_outage_blocks_every_entry_point(granted, app, tmp_path):
    _, agent, _, policy_id, token, _ = granted()
    # A database URL that cannot be opened stands in for an outage.
    dead = create_engine(f"sqlite:///{tmp_path}/missing-dir/db.sqlite")
    DeadSession = sessionmaker(bind=dead)

    def _dead_db():
        db = DeadSession()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = _dead_db
    for path, body in [
        ("/gateway/execute", execute_body()),
        ("/guardian/authorize", {"action": "transfer_data", "destination": "maps.example.com", "purpose": "navigation",
                                 "data_categories": ["location"], "policy_source_id": policy_id}),
    ]:
        r = agent.post(path, json=body, headers={"X-Consent-Token": token})
        assert r.status_code == 503, (path, r.text)
        assert r.json()["error"]["decision"] == "BLOCK"
    assert adapters.CALL_LOG == []


def test_adapter_failure_keeps_budget_spent(granted, monkeypatch):
    _, agent, _, _, token, _ = granted()

    def failing(act, payload, gateway_pass):
        raise ConnectionError("downstream unavailable")

    monkeypatch.setitem(adapters.ADAPTERS, "transfer_data", ("simulated_egress", failing))
    r = agent.post("/gateway/execute", json=execute_body(), headers={"X-Consent-Token": token})
    assert r.status_code == 502 and r.json()["error"]["code"] == "ADAPTER_FAILED"
    monkeypatch.undo()
    retry = agent.post("/gateway/execute", json=execute_body(), headers={"X-Consent-Token": token})
    assert retry.json()["error"]["code"] == "REPLAYED"


def test_raw_payload_is_never_stored(granted, Session):
    _, agent, _, _, token, _ = granted()
    secret_value = "12.971599,77.594566"
    r = agent.post("/gateway/execute", json=execute_body(payload={"gps": secret_value}), headers={"X-Consent-Token": token})
    assert r.status_code == 200
    assert r.json()["result"]["payload_sha256"]
    with Session() as db:
        stored = json.dumps([e.details for e in db.query(AuditEvent)]) + json.dumps([u.detail for u in db.query(TokenUse)])
    assert secret_value not in stored
