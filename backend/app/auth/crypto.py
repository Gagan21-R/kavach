import hashlib
import hmac
import secrets

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

_hasher = PasswordHasher()
# Verified against when the email is unknown, so login timing does not reveal which accounts exist.
_DUMMY_HASH = _hasher.hash("not-a-real-password-placeholder")


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password_hash: str | None, password: str) -> bool:
    try:
        return _hasher.verify(password_hash or _DUMMY_HASH, password) and password_hash is not None
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def random_secret(nbytes: int = 32) -> str:
    return secrets.token_urlsafe(nbytes)


def sha256(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def constant_time_equal(a: str, b: str) -> bool:
    return hmac.compare_digest(a.encode(), b.encode())


def make_compound_secret(prefix: str, record_id: str) -> tuple[str, str]:
    """Returns (plaintext "<prefix>_<id>.<secret>", sha256 of the secret part). Plaintext is shown once, never stored."""
    secret = random_secret()
    return f"{prefix}_{record_id}.{secret}", sha256(secret)


def split_compound_secret(prefix: str, value: str) -> tuple[str, str] | None:
    if not value or not value.startswith(prefix + "_") or "." not in value:
        return None
    record_id, _, secret = value[len(prefix) + 1 :].partition(".")
    if not record_id or not secret or len(record_id) > 64:
        return None
    return record_id, secret
