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
