"""Scheduled Watchman job and the single-origin production app."""
from fastapi.testclient import TestClient

from app import db as app_db
from app.demo import fixtures as fx
from app.watchman import cron
from app.watchman.fetch import FetchResult


def test_cron_checks_url_policies_and_skips_frozen(make_actor, Session, monkeypatch):
    monkeypatch.setattr(cron, "SessionLocal", Session)
    a, b = make_actor(), make_actor()
    a.client.post("/policies", json={"name": "MapsCo", "url": "https://maps.example.com/privacy", "text": fx.MAPSCO["text"]})
    a.client.post("/policies", json={"name": "NoUrl", "domain": "nourl.example", "text": fx.MAPSCO["text"]})
    b.client.post("/policies", json={"name": "Frozen", "url": "https://frozen.example/privacy", "text": fx.MAPSCO["text"]})
    b.client.post("/emergency-stop/activate", json={"reason": "drill"})
    counts = cron.run(fetcher=lambda url: FetchResult(True, text=fx.MAPSCO_BETRAYAL, final_url=url))
    assert counts == {"checked": 1, "changed": 1, "unknown": 0, "skipped_frozen": 1, "errors": 0}
    failing = cron.run(fetcher=lambda url: FetchResult(False, error="HTTP 503"))
    assert failing["unknown"] == 1


def test_postgres_urls_are_normalized():
    assert app_db.normalize_url("postgres://u:p@h/db") == "postgresql+psycopg://u:p@h/db"
    assert app_db.normalize_url("postgresql://u:p@h/db") == "postgresql+psycopg://u:p@h/db"
    assert app_db.normalize_url("sqlite:///x.db") == "sqlite:///x.db"


def test_production_app_serves_api_under_api_prefix_with_security_headers(app, monkeypatch):
    from app import serve

    root = TestClient(serve.app)
    r = root.get("/")
    assert r.status_code == 200
    assert "frame-ancestors 'none'" in r.headers.get("content-security-policy", "")
    assert root.get("/api/health").json()["status"] in ("ok", "degraded")
    assert root.get("/api/auth/me").status_code == 401
    assert root.get("/../backend/app/config.py").status_code in (200, 404)
    assert "CC_" not in root.get("/../backend/app/config.py").text


def test_render_workflow_checks_every_policy_in_parallel(make_actor, Session, monkeypatch):
    import asyncio
    import functools

    from app.watchman import workflow
    from app.watchman.service import check_source

    class FakeRenderRuntime:  # stands in for Render: runs each subtask's function, failing one policy every time
        def __init__(self, bad):
            self.bad, self.calls = bad, []

        async def run(self, task, *args):
            self.calls.append((task.name, args))
            if args and args[0] == self.bad:
                raise RuntimeError("retries exhausted")
            return task.func(self, *args)

    monkeypatch.setattr(cron, "SessionLocal", Session)
    monkeypatch.setattr(cron, "check_source", functools.partial(
        check_source, fetcher=lambda url: FetchResult(True, text=fx.MAPSCO_BETRAYAL, final_url=url)))
    a, b = make_actor(), make_actor()
    ids = [a.client.post("/policies", json={"name": f"Site{i}", "url": f"https://s{i}.example/privacy",
                                            "text": fx.MAPSCO["text"]}).json()["id"] for i in range(3)]
    b.client.post("/policies", json={"name": "Frozen", "url": "https://frozen.example/privacy", "text": fx.MAPSCO["text"]})
    b.client.post("/emergency-stop/activate", json={"reason": "drill"})
    rt = FakeRenderRuntime(bad=ids[0])
    result = asyncio.run(workflow.check_all.func(rt))
    assert result == {"policies": 4, "checked": 2, "changed": 2, "unknown": 0, "skipped_frozen": 1, "errors": 1}
    assert len(rt.calls) == 4 and {name for name, _ in rt.calls} == {"check_policy"}


def test_cron_starts_the_workflow_when_configured_and_falls_back_when_it_cannot(monkeypatch):
    monkeypatch.setattr(cron, "run", lambda: {"checked": 0})
    monkeypatch.delenv("CC_WATCHMAN_WORKFLOW", raising=False)
    assert cron.main() == {"checked": 0}  # not configured: checks here
    monkeypatch.setenv("CC_WATCHMAN_WORKFLOW", "kavach-watchman-flow/check_all")
    monkeypatch.setenv("RENDER_API_KEY", "test-key")
    monkeypatch.setattr(cron, "start_workflow", lambda slug: "trn-123")
    assert cron.main() == {"workflow": "kavach-watchman-flow/check_all", "task_run": "trn-123"}

    def down(slug):
        raise ConnectionError("render api unreachable")

    monkeypatch.setattr(cron, "start_workflow", down)
    assert cron.main() == {"checked": 0}  # Render unreachable: still checks
