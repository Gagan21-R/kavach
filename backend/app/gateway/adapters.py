"""Protected-action adapters. ONLY app.gateway.executor may import this module (enforced by tests/test_gateway.py).

Milestone 1 ships simulated adapters: they perform no network I/O and report simulated=True, so the demo can
never leak data to a real third party. Real egress adapters plug in here later behind the same gateway.
"""
import hashlib
import json
from dataclasses import dataclass

# Capability the executor passes after every check has succeeded. Python cannot make it truly private, so the
# real guarantee is architectural: routers never import this module, and the test suite asserts that.
_GATEWAY_PASS = object()

# Test hook: every adapter invocation is appended here so tests can prove a blocked action never ran.
CALL_LOG: list[dict] = []


@dataclass(frozen=True)
class AuthorizedAction:
    token_id: str
    user_id: str
    agent_id: str
    action: str
    destination: str
    purpose: str
    data_categories: tuple[str, ...]
    record_count: int


class AdapterNotAuthorized(RuntimeError):
    pass


def _payload_digest(payload: dict | None) -> str | None:
    if payload is None:
        return None
    return hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()


def simulated_egress(act: AuthorizedAction, payload: dict | None, gateway_pass: object) -> dict:
    if gateway_pass is not _GATEWAY_PASS:
        raise AdapterNotAuthorized("adapters may only be invoked by the gateway")
    CALL_LOG.append({"token_id": act.token_id, "action": act.action, "destination": act.destination})
    return {
        "simulated": True,
        "delivered_to": act.destination,
        "action": act.action,
        "records": act.record_count,
        "payload_sha256": _payload_digest(payload),
    }


ADAPTERS = {
    "transfer_data": ("simulated_egress", simulated_egress),
    "accept_terms": ("simulated_egress", simulated_egress),
    "submit_form": ("simulated_egress", simulated_egress),
    "create_account": ("simulated_egress", simulated_egress),
    "send_message": ("simulated_egress", simulated_egress),
}
