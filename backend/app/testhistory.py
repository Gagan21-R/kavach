"""Test history: every automated test run and every Red Team run, with a postmortem report for each.

Automated runs (pytest) are written by tests/conftest.py as one JSON file per run under CC_TEST_HISTORY_DIR
(default backend/test-history/pytest). Red Team runs are stored in the database (red_team_runs) per user.
"""
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.deps import UserContext, current_user
from app.db import get_db
from app.errors import not_found
from app.models import RedTeamRun
from app.redteam import lab

router = APIRouter(prefix="/test-history", tags=["test history"])
_RUN_ID = re.compile(r"^[0-9]{8}-[0-9]{6}-[a-z0-9]{4}$")

# What each test file covers, in words a mentor would recognise.
AREAS = {
    "test_acquisition": "Fetching real policies", "test_audit": "Audit log", "test_auth": "Sign-in and sessions",
    "test_constitution": "Consent rules engine", "test_contracts": "API contracts", "test_court": "Court (six agents)",
    "test_court_calibration": "Court scoring on real policies", "test_cron_and_serve": "Scheduled checks and production app",
    "test_gateway": "Gateway (data leaving)", "test_groups": "Rule groups, notifications and test history",
    "test_guardian": "Guardian (agent requests)", "test_isolation": "Keeping users apart", "test_migrations": "Database migrations",
    "test_operations": "Emergency Stop, data flow, Red Team and assistant", "test_sites": "Website reviews, extension and email alerts",
    "test_tokens": "One-time agent permissions", "test_watchman": "Watchman (policy changes)",
}


def history_dir() -> Path:
    return Path(os.environ.get("CC_TEST_HISTORY_DIR") or Path(__file__).resolve().parents[1] / "test-history") / "pytest"


def humanize(test_name: str) -> str:
    words = test_name.removeprefix("test_").replace("_", " ").strip()
    return words[:1].upper() + words[1:]


def area_of(path: str) -> str:
    stem = Path(path.split("::")[0]).stem
    return AREAS.get(stem, humanize(stem))


def _pytest_runs() -> list[dict]:
    d = history_dir()
    if not d.is_dir():
        return []
    out = []
    for f in sorted(d.glob("*.json"), reverse=True)[:100]:
        try:
            r = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        t = r.get("totals", {})
        out.append({"id": r["id"], "kind": "pytest", "title": "Automated tests", "created_at": r["started_at"],
                    "total": t.get("total", 0), "passed": t.get("passed", 0), "failed": t.get("failed", 0) + t.get("error", 0),
                    "skipped": t.get("skipped", 0), "duration_s": r.get("duration_s"), "commit": r.get("commit"),
                    "dirty": r.get("dirty")})
    return out


def _utc(dt: datetime) -> str:
    return (dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)).isoformat()


@router.get("")
def runs(ctx: UserContext = Depends(current_user), db: Session = Depends(get_db)):
    rt = db.execute(select(RedTeamRun).where(RedTeamRun.user_id == ctx.user.id).order_by(RedTeamRun.created_at.desc()).limit(50)).scalars()
    items = [{"id": r.id, "kind": "redteam", "title": "Red Team attack run", "created_at": _utc(r.created_at),
              "total": r.summary["total"], "passed": r.summary["passed"], "failed": r.summary["failed"] + r.summary["abstained"],
              "skipped": 0, "duration_s": r.summary.get("total_seconds"), "commit": None, "dirty": None,
              "missed": sum(1 for x in r.results if lab.explain(x)["outcome"] == "MISSED")} for r in rt]
    items += _pytest_runs()
    items.sort(key=lambda x: x["created_at"], reverse=True)
    return {"runs": items, "pytest_dir_found": history_dir().is_dir()}


@router.get("/redteam/{run_id}")
def redteam_report(run_id: str, ctx: UserContext = Depends(current_user), db: Session = Depends(get_db)):
    r = db.get(RedTeamRun, run_id)
    if r is None or r.user_id != ctx.user.id:
        raise not_found("run")
    results = [{**x, **lab.explain(x), "policies": x.get("policies"), "steps": x.get("steps")} for x in r.results]
    order = {"MISSED": 0, "FALSE_ALARM": 1, "INCONCLUSIVE": 2, "SAFE": 3}
    results.sort(key=lambda x: (order[x["outcome"]], x["id"]))
    policies: dict[tuple, dict] = {}
    for x in sorted(results, key=lambda x: x["id"]):
        for p in x.get("policies") or []:
            key = (p["name"], p["text"])
            if key not in policies:
                same = sum(1 for n, _ in policies if n == p["name"])
                policies[key] = {**p, "name": p["name"] + (f" {same + 1}" if same else ""), "scenarios": []}
            if x["id"] not in policies[key]["scenarios"]:
                policies[key]["scenarios"].append(x["id"])
    return {"id": r.id, "kind": "redteam", "seed": r.seed, "created_at": _utc(r.created_at), "summary": r.summary,
            "traced": any(x.get("steps") is not None for x in results), "results": results,
            "policies": list(policies.values()),
            "counts": {k: sum(1 for x in results if x["outcome"] == k) for k in order}}


@router.get("/pytest/{run_id}")
def pytest_report(run_id: str, ctx: UserContext = Depends(current_user)):
    if not _RUN_ID.match(run_id):
        raise not_found("run")
    f = history_dir() / f"{run_id}.json"
    if not f.is_file():
        raise not_found("run")
    r = json.loads(f.read_text(encoding="utf-8"))
    areas: dict[str, dict] = {}
    for t in r["tests"]:
        a = areas.setdefault(t["area"], {"area": t["area"], "total": 0, "passed": 0, "failed": 0, "tests": []})
        a["total"] += 1
        a["passed"] += t["outcome"] == "passed"
        a["failed"] += t["outcome"] in ("failed", "error")
        a["tests"].append(t)
    r["areas"] = sorted(areas.values(), key=lambda a: (-a["failed"], a["area"]))
    r["failures"] = [t for t in r["tests"] if t["outcome"] in ("failed", "error")]
    r.pop("tests")
    return r
