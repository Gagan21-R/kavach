"""Scheduled Watchman run (Render cron job): re-check every policy that has a URL.

    python -m app.watchman.cron

Frozen accounts (Emergency Stop) are skipped. A failed fetch is recorded as UNKNOWN for that policy, and one
failure never stops the others.

When CC_WATCHMAN_WORKFLOW names a Render Workflows task (for example kavach-watchman-flow/check_all) and
RENDER_API_KEY is set, the cron job only starts that task, which checks every policy in parallel on its own
compute (app.watchman.workflow). If starting it fails, the cron job checks the policies itself as before.
"""
import logging
import os

from sqlalchemy import select

from app.db import SessionLocal
from app.models import PolicySource, User
from app.watchman.service import check_source

log = logging.getLogger("consent_court.watchman.cron")
OUTCOMES = ("checked", "changed", "unknown", "skipped_frozen", "errors")


def policy_ids() -> list[str]:
    with SessionLocal() as db:
        return list(db.execute(select(PolicySource.id).where(PolicySource.url.is_not(None))).scalars())


def check_one(pid: str, fetcher=None) -> list[str]:
    """Checks one policy in its own session; returns the counters it adds to (see OUTCOMES)."""
    with SessionLocal() as db:
        try:
            policy = db.get(PolicySource, pid)
            if policy is None:
                return []
            if db.get(User, policy.user_id).frozen:
                return ["skipped_frozen"]
            ev = check_source(db, policy, "system", None, **({"fetcher": fetcher} if fetcher else {}))
            db.commit()
            return ["checked"] + [k for k, s in (("changed", "CHANGED"), ("unknown", "UNKNOWN")) if ev.status == s]
        except Exception:
            db.rollback()
            log.exception("watchman check failed for policy %s", pid)
            return ["errors"]


def tally(outcomes) -> dict:
    counts = dict.fromkeys(OUTCOMES, 0)
    for keys in outcomes:
        for k in keys:
            counts[k] += 1
    return counts


def run(fetcher=None) -> dict:
    return tally(check_one(pid, fetcher) for pid in policy_ids())


def start_workflow(slug: str) -> str:
    from render import Render  # only needed when Render Workflows is configured

    return Render().workflows.start_task(slug, []).id


def main() -> dict:
    slug = os.environ.get("CC_WATCHMAN_WORKFLOW", "").strip()
    if slug and os.environ.get("RENDER_API_KEY"):
        try:
            return {"workflow": slug, "task_run": start_workflow(slug)}
        except Exception:
            log.exception("could not start Render workflow %s; checking here instead", slug)
    return run()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print(main())
