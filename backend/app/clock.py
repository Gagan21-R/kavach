"""Single source of "now" so tests can move time. Always call clock.utcnow(), never import the function."""
from datetime import datetime, timezone


def utcnow() -> datetime:
    return datetime.now(timezone.utc)
