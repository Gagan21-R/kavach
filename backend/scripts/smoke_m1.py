"""End-to-end smoke test of Milestone 1 against a RUNNING server (not the test client).

    python scripts/smoke_m1.py http://127.0.0.1:8000

Creates a throwaway user, so run it only against a local or demo deployment.
"""
import sys
import uuid

import httpx

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8000"
PASSWORD = "smoke-test-" + uuid.uuid4().hex


def check(label, response, status):
    ok = response.status_code == status
    print(f"{'PASS' if ok else 'FAIL'}  {label}: HTTP {response.status_code}")
    if not ok:
        print("      ", response.text[:400])
        sys.exit(1)
    return response.json() if response.content else None


def main():
    user = httpx.Client(base_url=BASE, timeout=10)
    check("health", user.get("/health"), 200)
    email = f"smoke-{uuid.uuid4().hex[:8]}@example.com"
    check("register", user.post("/auth/register", json={"email": email, "password": PASSWORD}), 201)
    login = check("login", user.post("/auth/login", json={"email": email, "password": PASSWORD}), 200)
    user.headers["X-CSRF-Token"] = login["csrf_token"]

    check("rule: allow location for navigation to maps.example.com", user.post("/consent/rules", json={
        "effect": "ALLOW", "data_categories": ["location"], "purposes": ["navigation"], "recipients": ["maps.example.com"]}), 201)
    check("rule: deny location for advertising", user.post("/consent/rules", json={
        "effect": "DENY", "data_categories": ["location"], "purposes": ["advertising"]}), 201)
    policy = check("policy snapshot", user.post("/policies", json={
        "name": "MapsCo", "domain": "maps.example.com", "text": "MapsCo uses your location for navigation."}), 201)
    agent_data = check("register agent", user.post("/agents", json={"name": "smoke-agent"}), 201)

    agent = httpx.Client(base_url=BASE, timeout=10, headers={"X-Agent-Key": agent_data["api_key"]})
    req = {"action": "transfer_data", "destination": "maps.example.com", "purpose": "navigation",
           "data_categories": ["location"], "policy_source_id": policy["id"]}
    blocked = check("authorize location for advertising -> BLOCK", agent.post("/guardian/authorize", json={**req, "purpose": "advertising"}), 403)
    assert blocked["decision"] == "BLOCK"
    issued = check("authorize location for navigation -> token", agent.post("/guardian/authorize", json=req), 201)

    body = {k: v for k, v in req.items() if k != "policy_source_id"} | {"record_count": 1, "payload": {"lat": 12.97}}
    headers = {"X-Consent-Token": issued["token"]}
    done = check("gateway execute (simulated egress)", agent.post("/gateway/execute", json=body, headers=headers), 200)
    assert done["simulated"] is True
    replay = check("replay same token -> rejected", agent.post("/gateway/execute", json=body, headers=headers), 403)
    assert replay["error"]["code"] == "REPLAYED"

    events = check("audit trail", user.get("/audit/events?limit=100"), 200)
    print(f"      {len(events)} audit events, latest: {events[0]['event_type']}")
    print("ALL SMOKE CHECKS PASSED")


if __name__ == "__main__":
    main()
