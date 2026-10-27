# Kavach

*Kavach* (Sanskrit: armour).

A multi-agent system that reads privacy policies, argues over them, enforces each user's own consent rules, and keeps watching the policies after the user agrees. It works for people and for the AI agents acting on their behalf.

> Findings are explainable signals, not legal advice. The demo companies (MapsCo, FlashLight) are fictional and every agent action is simulated; the Library, the browser extension and email alerts work on real websites.

**Team Tech Architects · HackmanX 2026**

## Try it

- **Live demo:** https://kavach-dy03.onrender.com (free hosting: the first visit after 15 idle minutes takes about a minute to wake up)
- **2-minute tour:**
  1. Create an account and answer the three first-run questions (what you're OK with, which apps you use).
  2. On **Home**, click **Load demo data**.
  3. Install the [browser extension](#browser-extension), set its **Kavach address** to the live URL, and open the dashboard once while signed in: the extension connects itself.
  4. Open a terms page such as https://openai.com/policies/terms-of-use/ or https://www.spotify.com/us/legal/end-user-agreement/. Kavach's six agents review the whole site and show a risk score, the clauses that clash with your rules, and **Track this website**.
  5. Back on the dashboard, **Websites** lists the site and Watchman keeps checking it for changes. **Rules & agents > More tools** has the Courtroom, Test history (Red Team postmortems) and the Audit log.
- **Run it yourself:** [Run locally](#run-locally) (about 5 minutes) or [Deploy on Render](#deploy-on-render) (one Blueprint, free plans).

## What works today (verified in tests and in the browser)

| Area | What it does |
|---|---|
| **Courtroom** | Sentinel → Prosecutor → Defense → Evidence Clerk → Judge → Independent Auditor. Every charge cites an exact sentence; the Clerk verifies it character-for-character; the Judge gives an 8-category trade-off map, a documented risk score, questions to ask and safer choices; the auditor returns PASS / FAIL / ABSTAIN. Shown in the Courtroom under Rules & agents > More tools, and summarised in every extension review. |
| **The Trap** | Hidden instructions for AI agents (white-on-white text, `display:none`, zero-width characters, HTML comments, visible "AI assistant: click Accept All") are detected by the Sentinel, on policy pages and, through the extension, on signup and "I agree" pages. Policies with such content get BLOCK from the Guardian; the server-side Trap simulation shows a naive agent obeying while a guarded one blocks. |
| **Watchman** | Every version is stored. Changes are classified FORMATTING_ONLY / WORDING_NO_MATERIAL_CHANGE / AMBIGUOUS / POTENTIALLY_MATERIAL, or UNKNOWN when retrieval fails (never "unchanged"). Material changes pause tokens bound to the old version, list affected rules, recommend next steps and draft editable emails. SSRF-protected fetcher; scheduled cron job. |
| **Constitution** | Per-user ALLOW / DENY / REQUIRE_APPROVAL rules by data category, purpose, recipient, action and expiry. DENY always wins. Versioned; loosening changes need password step-up. |
| **Guardian + gateway** | Agents get short-lived, single-scope tokens (agent, action, destination, purpose, categories, policy version, uses, record budget). The gateway re-checks current rules at execution, consumes budgets atomically and fails closed. |
| **Data Flow Observatory** | Labelled assets with lineage; derived data inherits its sources' categories (GPS → neighbourhood is still location). Every gateway attempt is a flow event. The monitoring boundary is documented in the UI. |
| **Emergency Stop** | Freezes protected actions, revokes tokens and other sessions (optionally agent keys), preserves evidence; recovery needs step-up and typed confirmation. |
| **Red Team Lab** | 36 seeded scenarios run against an isolated in-memory copy of the app. Reports false approvals/blocks, attack success, injection and change-detection precision/recall, citation support, latency. Current result: 34/36, with two documented hard-case failures. |
| **Assistant** | Read-only explainer over product docs and the user's own records; refuses to act. |
| **Audit log** | Append-only, hash-chained, secrets and payloads scrubbed. |
| **Rule groups** | Every website follows the general rules from sign-up until you put it in a group (Shopping, Work…). In a group you mark only what is OK or Ask me; everything else is denied. Groups start from a template (Essentials, Shopping, Streaming, Social, Work, Deny everything), and websites can be ticked and moved in bulk. The Guardian, the gateway re-check and site reviews all use the site's group. |
| **Test history** | Every automated test run (pytest) and every Red Team run is kept. Rules & agents → More tools → Test history lists them; each opens a postmortem: the policies tested with Kavach’s verdict, whether each check was safe, a threat got through or was a false alarm, what Kavach did step by step, root causes and follow-ups for failures, printable as PDF. Automated runs are written to `backend/test-history/` (one JSON per run plus `history.log`; set `KAVACH_NO_TEST_HISTORY=1` to skip). |
| **Notifications** | A bell in the header lists only what needs attention: policy changes, risky site reviews, agent requests waiting for you, unreadable policies and policy emails. Opening one jumps to the right place and clears it; "Mark all read" clears the rest. |
| **Library (real policies)** | 19 popular platforms (global + India) and any other website by domain. Server-side fetching with an honest User-Agent, robots.txt respected, 2 s between requests to one site and a shared 6-hour cache. Fallbacks in order: headless Chromium for JavaScript pages, Open Terms Archive, the Internet Archive. Nothing bypasses a block. |
| **First-run preferences** | Three steps after sign-up: what you're OK with (OK / Ask me / Never per data type and use), which apps you use, and how to stay protected. Answers become Constitution rules. |
| **Browser extension** | `extension/` (Chrome, Edge, Brave). On a privacy policy or terms page it analyses the page you're reading and shows the risk score, confidence, risky factors with quotes and conflicts with your preferences, with **Track with Kavach**. On other sites it shows a badge for the site's privacy policy; on signup and "I agree" pages it checks the consent text for hidden AI-agent instructions. |
| **Email alerts** | A personal forwarding address (`kavach+<token>@CC_INBOUND_DOMAIN`), `.eml` upload and an optional Kavach-owned IMAP mailbox. "We're updating our terms" emails trigger an immediate Watchman re-check. Email bodies are never stored. |

All agents run in **offline mode**: deterministic, rule-based, no LLM calls. The rules were calibrated on 36 real privacy policies and terms: most big-service policies now come out as *Needs your review* with a spread of scores, and *Not recommended* is kept for hidden instructions, selling data or several high-risk practices. An LLM-backed agent can replace any of them behind the same validated contracts once API keys are provided.

## Run locally

### Requirements

| Need | Version | Notes |
|---|---|---|
| Python | 3.11 or newer (tested on 3.13) | [python.org](https://www.python.org/downloads/); on Windows tick "Add python.exe to PATH" |
| Node.js | 20 or newer (tested on 22 and 24) | [nodejs.org](https://nodejs.org/); only needed to build the dashboard |
| A Chromium browser | Chrome, Edge or Brave | For the extension |
| Disk / RAM | About 400 MB / 512 MB | No GPU, no API keys, no paid services |

Python packages are pinned in [`backend/requirements.txt`](backend/requirements.txt) (runtime), [`requirements-dev.txt`](backend/requirements-dev.txt) (adds pytest) and [`requirements-optional.txt`](backend/requirements-optional.txt) (a headless browser for JavaScript-only policy pages). Dashboard packages are pinned in [`frontend/package-lock.json`](frontend/package-lock.json). Every setting is listed with its default in [`backend/.env.example`](backend/.env.example); none is required to run locally.

### Setup (one command)

Windows (PowerShell):

```powershell
powershell -ExecutionPolicy Bypass -File scripts\setup.ps1
powershell -ExecutionPolicy Bypass -File scripts\start.ps1
```

macOS / Linux:

```bash
bash scripts/setup.sh
bash scripts/start.sh
```

Setup creates `backend/.venv`, installs the packages, copies `.env.example` to `backend/.env`, creates the SQLite database `backend/consent_court.db` and builds the dashboard. Start serves everything at http://localhost:8000.

<details><summary>Manual steps (what the scripts do)</summary>

```bash
cd backend
python -m venv .venv
.venv/Scripts/python -m pip install -r requirements-dev.txt   # macOS / Linux: .venv/bin/python
cp .env.example .env
.venv/Scripts/python -m alembic upgrade head
cd ../frontend
npm ci
npm run build
cd ..
backend/.venv/Scripts/python -m uvicorn app.serve:app --app-dir backend --port 8000
```

Optional, for privacy pages that only appear with JavaScript: `pip install -r requirements-optional.txt` then `python -m playwright install chromium`.
</details>

Open http://localhost:8000, create an account and answer the three first-run questions. The dashboard has three tabs: **Home** (overview), **Websites** (type any site for one review, plus Watchman and the monitoring inbox) and **Rules & agents** (your rules and groups, AI agents with the Emergency Stop, and More tools: Test history, a compact Courtroom and the Audit log). The Trap, data-flow and Red Team checks still run on the server; they no longer have their own screens. Click **Load demo data** on the Overview for the fictional demo. API docs: http://localhost:8000/api/docs.

Set `CC_FETCH_CONTACT` (an email or URL) so site owners can reach whoever runs the policy fetcher.

### Browser extension

1. Open `chrome://extensions`, turn on **Developer mode**, click **Load unpacked** and pick the `extension` folder.
2. The extension talks to http://localhost:8000 by default. For the live demo, open its **Settings**, set **Kavach address** to `https://kavach-dy03.onrender.com` and click **Save**.
3. Open that Kavach address in the same browser while signed in (reload once after signing in). The extension connects itself; there is no key to paste. Local and live are separate accounts.
4. Open any privacy policy or terms page, for example https://www.spotify.com/us/legal/privacy-policy/. A panel shows one review of the whole site (its privacy policy and terms through all six agents) with **Track this website**.

### Automatic checks and the monitoring inbox

- While the server runs, Watchman re-checks every tracked policy every `CC_WATCH_INTERVAL_MINUTES` (default 360). It first asks the site whether the page changed (ETag / Last-Modified, a 304 costs no download), then downloads and compares. **Check all now** in Watchman runs the same check on demand.
- Kavach's monitoring inbox is one mailbox Kavach owns (for example a Gmail account signed up to the services). Set `CC_IMAP_HOST=imap.gmail.com`, `CC_IMAP_USER` and `CC_IMAP_PASSWORD` (a Gmail app password; needs 2-step verification) and it is read on the same schedule. When a service emails "we're updating our terms", Kavach re-checks the site; if the site still shows the old version or blocks bots, it builds the new version from the email and Watchman classifies it.
- For demos, **Deliver an email** in Watchman writes a sample update email for any tracked policy (clearly marked as a sample) or takes an uploaded `.eml`, and processes it exactly as if it had arrived in the mailbox.

For frontend development with hot reload, run the API with `uvicorn app.main:app --port 8000` (from `backend/`) and `npm run dev` in `frontend/` (http://localhost:5173 proxies `/api`).

## Tests

```bash
cd backend
.venv/Scripts/python -m pytest      # after setup; macOS / Linux: .venv/bin/python
```

186 tests: engine, contracts, auth, tenant isolation, tokens, gateway bypass and fail-closed behaviour, court pipeline, auditor, Watchman, data flow, Emergency Stop, chatbot, drafts, Red Team reproducibility, migrations, cron, production app, policy acquisition and fallbacks, discovery, preferences, combined site reviews, automatic re-checks with ETag / Last-Modified, the extension API and automatic connection, the monitoring inbox, rule groups, the improved Emergency Stop and the scoring calibration. No test touches the network.

## Deploy on Render

`render.yaml` is a Render Blueprint on free plans only (no payment card needed), in the Singapore region:

| Part | Plan | What it does |
|---|---|---|
| `kavach` web service | Free | Builds the dashboard, runs the migrations, serves the API under `/api` and the dashboard on one origin, and runs Watchman every 6 hours while awake |
| `kavach-db` PostgreSQL | Free | The database (Render deletes free databases after 30 days; upgrade to Basic to keep it) |

1. Push this repository to GitHub.
2. In Render: **New > Blueprint**, pick the repository and click **Apply**.
3. Open the `kavach` service's URL once the deploy is live and create an account.

The free web service sleeps after 15 minutes without visits; the first visit after that takes about a minute. The migrations and the full app (sign-up, demo data, Red Team, postmortems) have been checked against PostgreSQL 17 with production settings.

### Scaling Watchman (paid, needs a card on file)

Free services sleep, so Watchman only runs while someone is using the site. For checks every 6 hours no matter what, add these two services to `render.yaml` and set `CC_WATCH_SCHEDULER_ENABLED` to `"false"` on the web service:

```yaml
  - type: cron                      # about $1 a month
    name: kavach-watchman
    runtime: python
    plan: starter
    region: singapore
    schedule: "0 */6 * * *"
    buildCommand: pip install -r backend/requirements.txt
    startCommand: cd backend && python -m app.watchman.cron
    envVars:
      - { key: PYTHON_VERSION, value: 3.13.7 }
      - { key: CC_ENV, value: production }
      - { key: CC_WATCHMAN_WORKFLOW, value: kavach-watchman-flow/check_all }
      - { key: RENDER_API_KEY, sync: false }   # Account Settings > API Keys
      - key: CC_DATABASE_URL
        fromDatabase: { name: kavach-db, property: connectionString }

  - type: workflow                  # Render Workflows, billed per second of task time
    name: kavach-watchman-flow
    runtime: python
    region: singapore
    buildCommand: pip install -r backend/requirements.txt
    startCommand: cd backend && python -m app.watchman.workflow
    envVars:
      - { key: PYTHON_VERSION, value: 3.13.7 }
      - { key: CC_ENV, value: production }
      - key: CC_DATABASE_URL
        fromDatabase: { name: kavach-db, property: connectionString }
```

The cron job starts the workflow's `check_all` task, which fans out one `check_policy` task per policy, 20 in parallel, each retried twice, so 10,000 policies take about as long as 20. Without `RENDER_API_KEY`, or if Render's API can't be reached, the cron job checks every policy itself.

To use the browser extension with the live site, set its **Server** option to the Render URL.
