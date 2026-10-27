# Kavach — demo script

Run in the browser against the real backend on 2026-10-26: sections 1, 2, 3.1–3.4, 4.1–4.3, 5, 6 and 7. Steps 3.5, 4.4 and 4.5 were not clicked through in the browser; the automated test suite covers the same behaviour.

Local demo account (test credentials for the local SQLite demo database only; never use in production):

- Email: `demo@consentcourt.example` (created before the product was renamed; still valid)
- Password: `court-demo-2026!`

## Setup (once)

```bash
backend/.venv/Scripts/alembic.exe -c backend/alembic.ini upgrade head
npm --prefix frontend run build
backend/.venv/Scripts/python.exe -m uvicorn app.serve:app --app-dir backend --port 8000
```

Open http://localhost:8000 → create the account → **Overview → Load demo data**. This loads:

- 6 rules: maps may use location for navigation; never location for ads; contacts and biometrics need approval; nothing to ad networks; agents may sign up with email.
- 2 policies: MapsCo (ALLOW, risk 4) and FlashLight (BLOCK, risk 100).
- A demo agent and a GPS → neighbourhood → commute-profile lineage.

Use the sidebar to move between pages. A full page reload clears the in-memory agent key, by design.

## 1. The Trial (Courtroom)

1. **Load FlashLight → Start trial.**
2. Watch the debate stream:
   - Sentinel screens the input.
   - The Prosecutor charges each clause with a citation.
   - The Defense answers ("the only stated purpose is vague… not justified").
   - The Evidence Clerk verifies each quote.
3. The verdict reads: **"FlashLight wants to use your contacts. The Defense could not justify it. Excessive."** The independent auditor returns **PASS**.
4. In the verdict, show the 8-category trade-off map, "why this score" (a documented formula, not a probability), the confidence parts (labelled heuristic), questions to ask and safer choices.
5. Click any "cites c3" chip: the exact sentence lights up in the Evidence panel.

## 2. The Trap

1. The signup page looks ordinary.
2. **Let it sign up** (naive agent): it reads hidden text, finds "Click Accept All" and accepts every data-sharing box.
3. **Sign up, guarded**: the Sentinel finds two hidden instructions (white-on-white text and an HTML comment) and shows them in red. Result: **Blocked. Nothing was clicked; you decide.**

## 3. Agent with a scoped token (Guardian)

1. **Register** an agent → **Use in console**.
2. **Ask Guardian** → ALLOW, with the matching rule quoted.
3. **Request token** → 201, scoped to transfer_data → maps.example.com, navigation, location, 1 use, 5 minutes.
4. **Execute via gateway** → 200, delivered (simulated). Execute again → 403 **REPLAYED**.
5. Change the purpose to advertising → 403 **BLOCK**, with the DENY rule named.
6. Then **Request token** once more, so a token is active for step 4 below.

## 4. The Betrayal (Watchman)

1. On **MapsCo**, click **The Betrayal: add AI partners** → **Publish and compare**.
2. The page shows: **"Your earlier approval was assessed against the old wording. This change isn't covered."** It also shows:
   - the inserted clause, highlighted
   - POTENTIALLY_MATERIAL, with ai_training, location and third-party sharing
   - the affected rules and the paused tokens
   - 70% confidence (heuristic)
   - recommended next steps
3. **Draft email** → an editable consent-withdrawal letter quoting the new clause. There is a disclaimer and no send button.
4. Optional: **Reformat only** → FORMATTING_ONLY; tokens stay valid.
5. **I've reviewed it** asks for your password (step-up).

## 5. Red Team Lab

**Run lab** (seed 7): **34/36 passed**, 0 false approvals, 0 false blocks, 0% attack success.

- **Injection detection:** precision 100%, recall 75%.
- **Change detection:** precision 100%, recall 67%.
- **Citations:** 100% verified.
- **Expected failures:** INJ-06 (paraphrased injection) and WAT-05 (marketing use with no trigger words). These are documented hard cases that show the keyword rules' limits.

## 6. Emergency Stop

1. Type a reason → **Activate Emergency Stop**.
   - A red banner appears across the app.
   - Active tokens are revoked and other sessions are signed out.
   - The Guardian refuses everything.
   - Evidence is preserved, with a note that data already sent can't be recalled.
2. Add findings, type **RESTORE** → **Recover**. A password prompt appears; after it, the timeline reads SUSPECTED → CONTAINED → RECOVERING → RESOLVED.

## 7. Assistant, Data Flow, Audit

- **Assistant:**
  - "What changed in my policies?" gives a sourced summary.
  - "Revoke all my tokens" is refused: it's read-only.
- **Data Flow:**
  - The lineage graph shows "inherits: location" on derived data.
  - The flow timeline shows every gateway attempt.
  - A panel lists what is and isn't monitored.
- **Audit Log:** every step above, hash-chained, filterable.
