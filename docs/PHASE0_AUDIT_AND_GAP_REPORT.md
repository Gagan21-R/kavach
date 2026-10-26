# Consent Court 2.0 — Phase 0 Repository Audit & Gap Report

Date: 2026-10-26 · Status: **audit complete, implementation not started**

## 1. What was inspected

| Location | Finding |
|---|---|
| `HackmanX/` (working folder) | Only `Opera Browser.lnk`. No source, no git repo, no README, no tests. |
| `Desktop/Hackathon/` | Other projects only (`code-blue-arena`, `ghostkey`, `krisis`, `resume`, …). None reference Consent Court. |
| Desktop + Downloads, text search for `Prosecutor`, `Watchman`, `Consent Court` in `.py/.ts/.tsx/.js/.md` | No matches. |
| GitHub | Not checked — `gh` CLI is not installed. |
| `Downloads/Consent Court — Hackman X 2026.pdf` (6 pages, 20 Oct) | Concept doc: 3 problems, 6 agents, Guardian API, 8 categories, demo plan, stack, 24-hour plan. |
| `Downloads/Consent_Court_2_Download_Package.zip` (6 byte-identical copies) | `Consent_Court_2_PRD.md/.docx`, `Consent_Court_2_Master_Prompt.md/.docx`. PRD states: *"Proposed requirements; not implemented or validated."* |

Toolchain available: Python 3.13.7 (via `py`, not `python`), Node 24.16 / npm. No git repo initialized.

**Conclusion: there is no existing Consent Court implementation on this machine.** The "existing project" is the design in the PDF. Every item in the requirements is therefore *Missing* in code. The Master Prompt says: *"If repository is unavailable, request access rather than fabricating modifications"* — so implementation is paused pending the decision in §7.

## 2. Baseline tests

None exist. **0 tests run, 0 passed, 0 failed.** There is no regression baseline to preserve.

## 3. Feature matrix

"Designed" = described in the PDF; "Specified" = added by PRD 2.0 / master prompt. Code status is *Missing* for every row.

| # | Capability | Source | Code |
|---|---|---|---|
| 1 | Policy paste + analysis pipeline | Designed | Missing |
| 2 | Sentinel (hidden text, zero-width, HTML comments, injection rules + LLM classifier) | Designed | Missing |
| 3 | Prosecutor / Defense debate with mandatory citations | Designed | Missing |
| 4 | Evidence Clerk (span linking, confidence) | Designed | Missing |
| 5 | Judge (8-category trade-off map, risk score, safer choice, questions) | Designed | Missing |
| 6 | Watchman (snapshots, semantic diff, re-trial of changed clauses, cron) | Designed | Missing |
| 7 | Agent Guardian REST endpoint (+ optional MCP, Playwright demo agent, trap page) | Designed | Missing |
| 8 | Courtroom UI with streamed debate | Designed | Missing |
| 9 | Independent Auditor (PASS/FAIL/ABSTAIN) | Specified | Missing |
| 10 | Personal Consent Constitution (ALLOW/DENY/REQUIRE_APPROVAL, versioned) | Specified | Missing |
| 11 | Scoped consent tokens (jti, audience, purpose, policy hash, budget, replay, revocation) | Specified | Missing |
| 12 | Data Flow Observatory + lineage + pre-egress enforcement | Specified | Missing |
| 13 | Confidence components & calibration | Specified | Missing |
| 14 | Emergency Stop + incident states + recovery | Specified | Missing |
| 15 | Authentication, sessions, step-up, passkeys, tenant isolation | Specified | Missing |
| 16 | Synthetic Red Team Lab with seeded scenarios + metrics | Specified | Missing |
| 17 | Explainer chatbot (read-only, tenant-scoped) | Specified | Missing |
| 18 | Change recommendations + editable email drafts (never auto-send) | Specified | Missing |
| 19 | Audit log / event store | Specified | Missing |
| 20 | Render deployment (web + cron + Postgres) | Designed | Missing |

## 4. Conflicts between the source documents (need a ruling)

| Topic | PDF (v1) | PRD / master prompt (v2) | Proposed resolution |
|---|---|---|---|
| Watchman outcome wording | "voids the old verdict"; demo line *"Your consent … no longer covers this"* | Must not declare consent legally void | Demo line becomes: *"Your earlier approval was assessed against the old wording. This change isn't covered — re-approval required under your rules."* Tokens bound to the old hash are suspended. |
| Auditor outcomes | — | Prompt: PASS/FAIL/ABSTAIN · PRD: PASS/CHALLENGE/ABSTAIN | PASS / FAIL / ABSTAIN (FAIL = challenge) |
| Rule outcome name | — | REQUIRE_APPROVAL vs ASK | REQUIRE_APPROVAL |
| Watchman labels | — | Prompt: 5 classes · PRD: 4 | Prompt's 5: `FORMATTING_ONLY`, `WORDING_NO_MATERIAL_CHANGE`, `POTENTIALLY_MATERIAL`, `AMBIGUOUS`, `UNKNOWN` (fetch failed) |
| Storage | SQLite snapshots | PostgreSQL for deployed state | SQLAlchemy + Alembic; SQLite for local dev/tests, Postgres on Render |
| API paths | `/guardian` only | Prompt §18 and PRD §17 differ | Prompt §18 as base, plus PRD routes it lacks (`/consent/rules`, `/watchman/*`, `/provider-requests/draft`, `/chat/explain`) |
| Orchestration | LangGraph or custom loop | Bounded, typed, deterministic | Custom deterministic orchestrator (simpler to bound, time out and test than LangGraph) |

## 5. Proposed architecture (greenfield)

```
HackmanX/
  backend/                 FastAPI, Python 3.13
    app/
      main.py              app factory, routers, middleware (auth, rate limit, correlation id)
      config.py            env settings (pydantic-settings)
      db.py, models/       SQLAlchemy models, every tenant table has user_id
      schemas/             Pydantic contracts for every agent + API
      auth/                password (argon2) + server sessions, step-up, WebAuthn later
      agents/              sentinel, prosecutor, defense, clerk, judge, watchman, auditor
      llm/                 provider adapters (primary + independent auditor), deterministic fallback
      engine/              constitution rule evaluation (deterministic, no LLM)
      guardian/            evaluate / authorize / token issue / validate / revoke
      gateway/             the ONLY egress path for protected actions; token check at boundary
      dataflow/            labels, lineage registry, flow events
      watchman/            fetch (SSRF-safe), normalize, hash, diff, classify
      incidents/           emergency stop, incident state machine, recovery
      redteam/             seeded scenarios + runner + metrics
      chat/                read-only explainer
      drafts/              email draft generator
      audit_log.py         append-only event log
    alembic/               migrations
    tests/                 pytest: unit, integration, acceptance (§19 of master prompt)
  frontend/                React + Vite + Tailwind
  fixtures/                synthetic policies, trap page
  docs/                    this report, threat model, API, runbook, demo script
  render.yaml
```

Decision precedence (enforced in `engine/` + `guardian/`, never by an LLM):
**explicit user DENY > emergency stop > missing/failed check (auditor fail/abstain, stale policy, unknown destination) → REVIEW/BLOCK > REQUIRE_APPROVAL > model recommendation.**

## 6. Threat model (initial)

| Threat | Control |
|---|---|
| Prompt injection in policy/webpage | Sentinel flags; policy text only ever passed as quoted data; agents have no tools; Guardian is deterministic |
| Excessive agent authority | Agents return JSON only; token issuance & egress are server functions with no LLM path |
| Token replay / stale authorization | Server-side opaque tokens, jti one-time use, atomic usage counter, policy-hash binding, revocation epoch |
| Gateway bypass | Protected adapters only callable through `gateway.execute()`; test asserts no other route reaches them |
| Cross-user access | `user_id` filter in a single repository layer; tests for A-reads-B on every resource |
| SSRF in Watchman fetch | Scheme allowlist, DNS resolve + block private/loopback/link-local ranges, size + time limits, no redirects to blocked ranges |
| Secret/PII leakage | No raw payloads in flow events (labels + hashes); log scrubber; tokens stored hashed |
| LLM outage / malformed output | Schema validation, bounded retries, timeout → ABSTAIN → REVIEW (fail closed) |
| DB / auth outage | Protected actions fail closed (503 + BLOCK), never ALLOW |
| Credential theft | argon2 hashing, short sessions, step-up for rule changes/recovery, rate limits |

## 7. Missing inputs / decisions (blocking)

1. **Is the Consent Court code somewhere else** (a teammate's laptop, a GitHub repo)? If yes, I need it before writing anything — the prompt requires preserving existing work. If no, I'll build greenfield in `HackmanX/`.
2. **LLM keys**: which providers do you have keys for (Anthropic, Gemini, other)? The independent auditor should use a *different* provider than the primary. Without keys, the system runs on deterministic rule-based agents (clearly labelled "offline mode"), which still lets every enforcement test pass.
3. **Scope vs time**: the PDF plans a 24-hour build starting today. The full master prompt is weeks of work. Recommended: deliver P0 + the three PDF demo moments first, then P1, and mark anything unfinished as such.
4. **Auth**: start with email + password sessions and a re-enter-password step-up; add WebAuthn passkeys in P2 (PRD priority). Voice is out.

## 8. Implementation sequence (if greenfield)

| Milestone | Delivers | Acceptance tests covered |
|---|---|---|
| M1 Contracts & core enforcement | Backend skeleton, DB models, auth + tenant isolation, agent schemas, Constitution engine, Guardian evaluate/authorize/revoke, tokens, gateway, audit log | AC 2, 3, 4, 14, 19 |
| M2 Court pipeline | Sentinel (deterministic HTML/zero-width/injection), Prosecutor/Defense/Clerk/Judge with LLM + offline mode, citation verifier, Independent Auditor | AC 1, 2, 8, 9 |
| M3 Watchman | SSRF-safe fetch, snapshots, normalize/hash, clause diff, 5-class classifier, token suspension on material change, recommendations | AC 5, 6, 7 |
| M4 Data flow + Emergency | Labels, lineage, pre-egress flow evaluation, emergency stop/recover, incident log | AC 11, 12, 13, 17, 18 |
| M5 Red Team Lab | Seeded scenario set (all categories in §13), runner, metrics report | AC 10 |
| M6 UX | React courtroom, constitution editor, observatory graph, Watchman timeline, emergency center, lab, chatbot, email drafts | AC 15, 16 |
| M7 Validate & deploy | Full test run, `render.yaml`, smoke test, docs, demo script | AC 20 |

### M1 file-level tasks

- `backend/pyproject.toml`, `app/main.py`, `app/config.py`, `app/db.py`
- `app/models/{user,session,consent_rule,policy,token,flow,audit,incident}.py`, first Alembic migration
- `app/auth/{passwords,sessions,deps}.py` — register/login/logout, `current_user`, step-up
- `app/schemas/agents.py` — Finding, Citation, AgentOutput, AuditVerdict, Decision
- `app/engine/constitution.py` — deterministic rule matcher with explanation
- `app/guardian/{service,tokens}.py`, `app/gateway/executor.py`, `app/audit_log.py`
- Routers: `/auth`, `/consent/rules`, `/guardian/{evaluate,authorize,revoke}`, `/audit/events`
- Tests: `test_isolation.py` (A vs B), `test_constitution.py` (DENY beats ALLOW, missing info → REVIEW), `test_tokens.py` (expired, revoked, replayed, wrong destination, wrong purpose, over budget, stale policy hash), `test_gateway.py` (prohibited action blocked before adapter runs; DB failure → fail closed)

## 9. Risks

- Scope far exceeds a 24-hour window; partial delivery must be labelled honestly.
- Model-reported confidence is uncalibrated until a labelled set exists; the Red Team Lab doubles as that set, so tuning cases and holdout cases must be kept separate.
- Render free tier: ephemeral disk (SQLite unsuitable in production), cold starts, cron minimums.
- "Instrumented flows" covers only adapters routed through our gateway; nothing outside it is visible.
- No legal review: all outputs are explainable signals, not legal advice (as the PDF already states).
