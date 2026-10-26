"""Scheduled Watchman run (Render cron job): re-check every policy that has a URL.

    python -m app.watchman.cron

Frozen accounts (Emergency Stop) are skipped. A failed fetch is recorded as UNKNOWN for that policy, and one
failure never stops the others.
"""
import logging

from sqlalchemy import select

from app.db import SessionLocal
from app.models import PolicySource, User
from app.watchman.service import check_source

log = logging.getLogger("consent_court.watchman.cron")


def run(fetcher=None) -> dict:
    counts = {"checked": 0, "changed": 0, "unknown": 0, "skipped_frozen": 0, "errors": 0}
    with SessionLocal() as db:
        ids = list(db.execute(select(PolicySource.id).where(PolicySource.url.is_not(None))).scalars())
    for pid in ids:
        with SessionLocal() as db:
            try:
                policy = db.get(PolicySource, pid)
                if db.get(User, policy.user_id).frozen:
                    counts["skipped_frozen"] += 1
                    continue
                ev = check_source(db, policy, "system", None, **({"fetcher": fetcher} if fetcher else {}))
                db.commit()
                counts["checked"] += 1
                counts["changed"] += ev.status == "CHANGED"
                counts["unknown"] += ev.status == "UNKNOWN"
            except Exception:
                db.rollback()
                counts["errors"] += 1
                log.exception("watchman check failed for policy %s", pid)
    return counts


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print(run())
