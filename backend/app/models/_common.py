import uuid

from app import clock


def new_id() -> str:
    return uuid.uuid4().hex


def now():
    return clock.utcnow()
