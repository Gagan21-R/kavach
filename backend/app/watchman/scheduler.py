"""Automatic checks while the server runs: every CC_WATCH_INTERVAL_MINUTES Watchman re-checks every tracked policy
(cheaply, with ETag / Last-Modified where the site supports them) and reads Kavach's monitoring inbox if one is
configured. Started by app.serve; the separate cron job (python -m app.watchman.cron) does the same on hosts that
stop idle web servers."""
import logging
import threading
from datetime import timedelta

from app import clock
from app.config import get_settings

log = logging.getLogger("consent_court.watchman.scheduler")
state = {"running": False, "last_run_at": None, "next_run_at": None, "last_counts": None, "last_mailbox": None}
_stop = threading.Event()


def run_once() -> dict:
    from app.inbox import mailbox
    from app.watchman import cron

    counts = cron.run()
    try:
        mail = mailbox.run()
    except Exception as e:  # a mailbox outage must not stop policy checks
        log.exception("mailbox check failed")
        mail = {"error": type(e).__name__}
    now = clock.utcnow()
    state.update(last_run_at=now, last_counts=counts, last_mailbox=mail,
                 next_run_at=now + timedelta(minutes=get_settings().watch_interval_minutes))
    return {"policies": counts, "mailbox": mail}


def _loop() -> None:
    interval = get_settings().watch_interval_minutes * 60
    state["next_run_at"] = clock.utcnow() + timedelta(seconds=interval)
    while not _stop.wait(interval):
        try:
            run_once()
        except Exception:
            log.exception("scheduled Watchman run failed")


def start() -> None:
    if state["running"] or not get_settings().watch_scheduler_enabled:
        return
    state["running"] = True
    _stop.clear()
    threading.Thread(target=_loop, name="kavach-watchman", daemon=True).start()


def stop() -> None:
    _stop.set()
    state["running"] = False
