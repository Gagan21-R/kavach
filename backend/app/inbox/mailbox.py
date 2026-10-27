"""Kavach's own monitoring mailbox (optional). Point platform sign-ups or newsletters at one inbox Kavach owns;
this job reads new mail over IMAP and re-checks the policies of every user tracking the sender.

    python -m app.inbox.mailbox

Needs CC_IMAP_HOST, CC_IMAP_USER, CC_IMAP_PASSWORD. Messages are marked read; nothing is deleted.
"""
import imaplib
import logging

from app.config import get_settings
from app.db import SessionLocal
from app.inbox import parse as email_parse
from app.inbox.service import handle

log = logging.getLogger("consent_court.inbox.mailbox")


def run(limit: int = 50) -> dict:
    s = get_settings()
    if not s.imap_host:
        return {"skipped": "CC_IMAP_HOST is not set"}
    counts = {"read": 0, "policy_updates": 0, "errors": 0}
    with imaplib.IMAP4_SSL(s.imap_host) as imap:
        imap.login(s.imap_user, s.imap_password)
        imap.select("INBOX")
        _, data = imap.search(None, "UNSEEN")
        for num in data[0].split()[:limit]:
            _, msg = imap.fetch(num, "(RFC822)")
            counts["read"] += 1
            with SessionLocal() as db:
                try:
                    signals = handle(db, email_parse.parse(msg[0][1]), "mailbox")
                    db.commit()
                    counts["policy_updates"] += bool(signals)
                except Exception:
                    db.rollback()
                    counts["errors"] += 1
                    log.exception("could not process message %s", num)
    return counts


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print(run())
