# dome-agent-flow (P5, Governed Agent Flow)

A governed invoice-to-approval process across the DOME tools: an n8n workflow takes an invoice, Document
Intelligence (P3) extracts it, a data-driven rules engine decides, the LLM Council (P2) writes a decision brief
when needed, a named human approves or rejects, and every step lands in `governance_events` under one
`workflow_run_id`, which the Governance Dashboard (P6) shows as one timeline. DOME is a sole maintainer's
portfolio of governed AI tools for regulated businesses; the other tools are sibling repos in `Dome-Layer`.

**Status: a private demo run from staging** (decision of 2026-09-28). Staging is woken for a demo and torn down
after; there is no production service. Model calls are paid by the maintainer, so the shim's pipeline steps
accept only the n8n service key or an approver on `APPROVER_USER_IDS` (empty means nobody: fail closed).

## Layout

| Path | What |
|---|---|
| `backend/` | FastAPI shim (Python 3.12): `app/api/` routes (`runs.py`) and auth (`deps.py`); `app/services/` rules engine (`rules.py`, `policy.py`), normaliser, run state (`runs.py`, `db.py`), governance emit, P3 and P2 proxies (`upstream.py`); `policy.yaml` the default policy; `tests/` |
| `frontend/` | Next.js approval page (static export on a Cloudflare Worker, `agent-flow.staging.domelayer.com`) |
| `workflows/invoice_to_approval.json` | the n8n workflow (form trigger, then HTTP calls to the shim only) |
| `n8n/` | the self-hosted n8n image and its Railway config, with `README.md` on importing the workflow |

The shim owns the logic so it is testable in CI; n8n is the visible orchestrator and calls only the shim's JSON
API with the `X-Service-Key` header. Run state lives in `invoice_runs` (mutable); the audit trail is
`governance_events` (append-only). Governance action types, all `agent_id="agent-flow"`: `invoice_received`,
`rules_evaluated`, `human_approval`, `invoice_approved` / `invoice_rejected` (P3 adds `extraction`, P2
`deliberation`, joined by the `X-Workflow-Run-Id` header).

## Branches and deploys

- `main` mirrors `staging` and deploys nothing. `staging` deploys: a push touching `backend/**` builds the shim on
  Railway staging **and starts it, which bills until it is stopped**; a push touching `frontend/**` deploys the
  approval page through `deploy (Cloudflare)`.
- **Branch from `staging`, open the PR against `staging`** (protected, strict checks: `ci`, gitleaks). **Never push
  to `main`, never merge a PR that touches `backend/` yourself**: the maintainer merges those inside a staging
  window and tears down after.

## Commands

Backend (`cd backend`; what `ci` runs):

```bash
uv venv --python 3.12 .venv && uv pip install --python .venv -r requirements.txt -r requirements-dev.txt
.venv/bin/ruff check . && .venv/bin/ruff format --check .
.venv/bin/mypy .
.venv/bin/pytest
uvx pip-audit --no-deps -r requirements.txt
```

**Locks:** `requirements*.txt` are compiled from `requirements*.in` with
`uv pip compile requirements.in -o requirements.txt --python-version 3.12` (same for `-dev`), run from `backend/`.
`ci` re-compiles and fails if a lock does not match its input, so never hand-edit a lock.

Frontend (`cd frontend`): `npm ci`, `npx tsc -b --noEmit`, `npm run typecheck:worker`, `npm test`, `npm run build`,
`npm audit --omit=dev --audit-level=high`. `docker build backend/` must also pass.

## House rules

- **No em dashes or en dashes anywhere**: code, comments, copy, commit messages, PR text. `backend/tests/test_house_style.py`
  and `frontend/houseStyle.test.ts` fail on them. Hyphens are fine. British English.
- **`DEV_BYPASS_AUTH` must never be true outside a laptop**: it turns any anonymous request into a placeholder user
  that also passes the approver check, so anyone could approve or reject invoices.
- Never log or commit secrets. Settings come from environment variables (`app/core/config.py`); in docs and PRs,
  name variables, never values.
- Tests for every behaviour change; the rules engine is deterministic and fully unit-tested, keep it that way.
- The shim never calls model providers directly; it goes through P3 and P2 over HTTP.

## Done means

A PR against `staging` with `ci` green (backend, frontend, docker build), a description of what changed, what was
tested locally, and what still needs a run on staging (anything that needs n8n, P3, P2 or Supabase).
