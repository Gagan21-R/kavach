# Consent Court 2.0 — Architecture (as built through Milestone 1)

## Trust boundaries

```
 Browser (human) ── HttpOnly session cookie + X-CSRF-Token ──┐
                                                             ▼
 AI agent ── X-Agent-Key ──► FastAPI ──► Guardian service ──► Constitution engine (deterministic)
                │                │              │
                │                │              └─► consent token issue / revoke
                └─ X-Consent-Token ──► Gateway executor ──► adapters (simulated in M1)
                                         │
                                 Audit log (append-only, hash-chained)
```

- **Untrusted:** policy text, webpage content, agent requests, and (from M2) all model output. Policy text is stored and quoted as data and is never interpreted as instructions.
- **Privileged, deterministic, server-side only:** rule evaluation, token issuance, gateway execution, rule changes, approvals. No model has a code path into these.
- **Agents (court agents, M2+)** return JSON only, validated by `app/schemas/agents.py`. No contract has a field that grants authority.

## Decision precedence

Enforced in `app/engine/constitution.py` and `app/guardian/service.py`:

1. Any matching user **DENY** → **BLOCK**. This applies even when a narrower ALLOW also matches, and even when the policy has problems.
2. Policy problems → **REVIEW**, which the user cannot approve. The problems are: no snapshot on record, a change awaiting reassessment, or a destination outside the referenced policy's domain.
3. **REQUIRE_APPROVAL** rule, or no rule covers the category → **REVIEW**, which the user can approve. Nothing is allowed by default.
4. Every requested category covered by **ALLOW** → **ALLOW**.
5. *(M4)* Emergency Stop will sit above all of these.

Missing essential fields (action, destination, purpose, categories) → REVIEW, not approvable.

## Step-up authentication

A fresh password login counts as a step-up for 5 minutes (`CC_STEP_UP_TTL_MINUTES`).

| Requires step-up (loosens protection) | No step-up needed (tightens protection) |
|---|---|
| Create an ALLOW rule | Create a DENY or REQUIRE_APPROVAL rule |
| Edit any rule | Revoke an ALLOW rule |
| Revoke a DENY or REQUIRE_APPROVAL rule | Revoke tokens or agents |
| Approve an approval request | Deny an approval request |
| Register an agent | Log out or revoke all sessions |
| Mark a changed policy as reassessed | |

Passkeys/WebAuthn are planned for P2 (PRD §20). Voice is never used as an authentication factor.

## Consent tokens

- **Format:** opaque `cct_<jti>.<secret>`. Only `sha256(secret)` is stored, and the token carries no personal data. Claims live server-side: user, agent, action, destination, purpose, categories, policy hash, constitution version, expiry, max uses, max records, approval id.
- **Expiry:** each token expires at whichever comes first: the requested TTL (capped at `CC_TOKEN_MAX_TTL_SECONDS`), the earliest expiry of the ALLOW rules that justified it, or the approval's expiry.
- **Gateway checks**, in this order:
  1. Token exists and its secret matches.
  2. It belongs to this agent and user.
  3. It is not revoked and not expired.
  4. The action, destination and purpose match exactly.
  5. The requested categories are within the token's categories.
  6. The policy hash equals the current hash, and the policy is not awaiting reassessment.
  7. Uses and records remain.
  8. The user's **current** rules are re-evaluated. A new DENY gives `RULES_NOW_DENY`, and a removed ALLOW gives `AUTHORIZATION_NO_LONGER_VALID`.
  9. One conditional `UPDATE` spends the use and the record budget atomically. This stops concurrent replay and budget bypass.
  10. Only then is the adapter called.
- **Fail closed:** any exception before step 10 returns 503 with `decision: BLOCK`, and the adapter is not called.
- **Revocation limits:** revoking a token stops future use only. It cannot recall data already delivered.

## Bypass resistance

- `app/gateway/adapters.py` is imported only by `app/gateway/executor.py`, and the executor only by `app/routers/gateway.py`. `tests/test_gateway.py` asserts both through static import analysis.
- Adapters refuse calls without the gateway's pass object. This is defence in depth: Python cannot make that object truly private, so the import rule above is the real control.

## Instrumentation boundary

Only actions sent through `POST /gateway/execute` are controlled and observed. Nothing outside this process is visible, including third-party processing, the agent's own network access, and uninstrumented tools. An agent that has its own internet access and ignores the gateway is outside the guarantee. M4 adds flow lineage for instrumented operations only.

## Threat model (M1 controls and their tests)

| Threat | Control | Test |
|---|---|---|
| Prompt injection gaining authority | Guardian inputs are closed enums plus a host; no model or recommendation field exists | `test_guardian.py::test_model_recommendations_have_no_channel_into_guardian` |
| Malformed or escalated agent output | Strict schemas, `extra=forbid`, role check on `meta.agent` | `test_contracts.py` |
| Token replay / over-budget | One-time default; atomic conditional UPDATE | `test_tokens.py` (replay, budget, atomic stale-read cases) |
| Stale authorization | Policy-hash binding; rules re-evaluated at the gateway | `test_tokens.py::test_stale_policy_token_rejected`, `test_deny_added_after_issuance_blocks_at_the_boundary` |
| Wrong scope | Exact action, destination and purpose match; category subset | `test_tokens.py::test_wrong_scope_rejected` |
| Cross-user access | Ownership checks return 404 on every resource; tokens bound to agent | `test_isolation.py` |
| Gateway bypass | Import-graph assertion; adapter pass object | `test_gateway.py` |
| DB / auth outage | Fail-closed handlers return 503 BLOCK | `test_gateway.py::test_database_outage_blocks_every_entry_point` |
| CSRF on cookie sessions | `SameSite=Strict` plus required `X-CSRF-Token` on writes | `test_auth.py` |
| Credential stuffing | argon2id, constant-time unknown-user path, rate limit | `test_auth.py::test_login_wrong_password_and_rate_limit` |
| Log tampering | Hash-chained audit log | `test_audit.py` |
| Sensitive data in logs | Payloads never stored (hash only); secret-like keys scrubbed | `test_gateway.py::test_raw_payload_is_never_stored`, `test_audit.py` |

The mutation checks run during M1 disabled four controls one at a time: the destination check, the boundary re-evaluation, DENY handling, and the atomic use-count and budget guards. The suite failed for each of them.

## Known limitations (M1)

- The rate limiter is in-process: limits are not shared across workers and reset on restart.
- The audit hash chain is global and assumes a single writer. Concurrent writers on PostgreSQL could fork it. A per-tenant chain or advisory lock is needed before scaling out.
- `POST /auth/register` returns 409 for an existing email, which reveals that the account exists. This was accepted for the prototype.
- Any policy text change requires reassessment, including formatting-only changes. Watchman (M3) will relax this for verified formatting-only changes.
- Adapters are simulated, so no real egress exists yet.
- There is no admin role yet; one is needed for M4 incident recovery.
