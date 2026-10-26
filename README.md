# Consent Court 2.0

A multi-agent system that reads privacy policies, argues over them, enforces each user's own consent rules, and keeps watching the policies after the user agrees. It works for people and for the AI agents acting on their behalf.

> Findings are explainable signals, not legal advice.

## Status

| Milestone | Scope | State |
|---|---|---|
| **M1 Contracts & core enforcement** | Auth, tenant isolation, agent output contracts, Personal Consent Constitution, Guardian, consent tokens, protected-action gateway, audit log | **Done: 90 tests passing** |
| M2 Court pipeline | Sentinel, Prosecutor, Defense, Evidence Clerk, Judge, Independent Auditor | Not started |
| M3 Watchman | SSRF-safe fetch, semantic diff, 5-class change labels, recommendations | Not started |
| M4 Data flow + Emergency Stop | Lineage, flow evaluation, incident workflow | Not started |
| M5 Red Team Lab | Seeded scenarios and metrics | Not started |
| M6 UX | React courtroom, dashboards, chatbot, email drafts | Not started |
| M7 Validate & deploy | Render, smoke tests, demo script | Not started |

Details: [docs/PHASE0_AUDIT_AND_GAP_REPORT.md](docs/PHASE0_AUDIT_AND_GAP_REPORT.md) · [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)

## Core rule

An AI agent cannot perform a protected action unless the user's own rules allow it, the agent holds a current, scoped consent token for exactly that action, and the gateway re-checks both at the moment of execution. A user's DENY rule always wins, and no LLM output can override it.

## Run locally (Windows, Python 3.13)

```bash
cd backend
py -3.13 -m venv .venv
.venv/Scripts/python.exe -m pip install -r requirements.txt
.venv/Scripts/alembic.exe upgrade head
.venv/Scripts/python.exe -m uvicorn app.main:app --reload
```

API docs: http://127.0.0.1:8000/docs

On macOS or Linux, use `python3 -m venv .venv` and `.venv/bin/...` instead.

## Tests

```bash
cd backend
.venv/Scripts/python.exe -m pytest
```

End-to-end check against a running server:

```bash
cd backend
.venv/Scripts/python.exe scripts/smoke_m1.py http://127.0.0.1:8000
```

## API (Milestone 1)

| Who | Endpoint | Purpose |
|---|---|---|
| Human | `POST /auth/register`, `/auth/login`, `/auth/logout`, `/auth/step-up`, `GET /auth/me`, `POST /auth/sessions/revoke-all` | Session auth (HttpOnly cookie plus `X-CSRF-Token`) |
| Human | `POST/GET /agents`, `POST /agents/{id}/revoke` | Register AI agents; the API key is shown once |
| Human | `GET/POST /consent/rules`, `PUT/DELETE /consent/rules/{id}`, `GET /consent/rules/{id}/history`, `POST /consent/check` | Personal Consent Constitution |
| Human | `POST/GET /policies`, `GET /policies/{id}`, `POST/GET /policies/{id}/snapshots`, `GET /policies/{id}/snapshots/{sid}`, `POST /policies/{id}/reassess` | Versioned policy snapshots |
| Human | `GET /guardian/tokens`, `POST /guardian/revoke`, `GET /guardian/approvals`, `POST /guardian/approvals/{id}/approve` or `/deny` | Oversight of agent authority |
| Human | `GET /audit/events` | The user's own audit trail |
| Agent | `POST /guardian/evaluate`, `POST /guardian/authorize` | Dry run; request a consent token (`X-Agent-Key`) |
| Agent | `POST /gateway/execute` | The only way to run a protected action (`X-Agent-Key` plus `X-Consent-Token`) |

In M1, every gateway adapter is **simulated**: it performs no network I/O and reports `"simulated": true`.

## Repository layout

```
backend/
  app/           FastAPI application (see docs/ARCHITECTURE.md)
  alembic/       database migrations
  tests/         pytest suite
  scripts/       smoke test
docs/            audit report, architecture, threat model
```
