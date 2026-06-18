# dome-agent-flow — P5 Governed Agent Flow

Self-hosted **n8n** workflow that runs a real, *governed* **invoice-to-approval**
process across the DOME tools and emits an auditable trail that the Governance
Dashboard (P6) reconstructs as a single cross-tool run. P5 completes the platform's
**build → execute → observe** story.

## The chain

```
invoice ─▶ n8n (email/form trigger)
            │
            ├─▶ P3 Document Intelligence   — extract invoice fields + confidence
            ├─▶ rules engine (this repo)   — policy decision: auto / council / human / reject
            ├─▶ P2 LLM Council             — multi-model decision brief (ambiguous/high-value)
            ├─▶ human-in-the-loop gate     — branded approval page (this repo)
            └─▶ governance_events          — one workflow_run_id per invoice → P6 timeline
```

n8n is the *visible* orchestrator; its nodes call only the **backend shim** (FastAPI),
which owns the robust, CI-testable logic: the data-driven **rules engine**, run state
(`invoice_runs`), governance emit, and proxies to P3/P2. Mutable run state lives in
`invoice_runs`; the immutable audit trail is append-only `governance_events`.

## Layout

| Path | What |
|---|---|
| `backend/` | FastAPI shim — rules engine, endpoints, governance emit, P3/P2 proxies |
| `backend/policy.yaml` | the committed default invoice-approval policy (per-tenant override in Supabase `approval_policies`) |
| `frontend/` | Next.js branded approval page (the human gate) → `agent-flow.domelayer.com` |
| `n8n/` | self-hosted n8n Docker image + Railway config |
| `workflows/` | committed n8n workflow JSON (`invoice_to_approval.json`) |

## Rules engine

`backend/app/services/rules.py` evaluates an invoice against `policy.yaml` across
amount tier, purchase category, country/VAT, vendor allowlist, PO match, currency,
duplicate detection and date sanity, returning one of
`auto_approve` / `route_to_council` / `require_human:<role>` / `reject`. The decision
plus `rules_applied` / `rules_triggered` is written into a `rules_evaluated` governance
event, so the policy decision itself is auditable.

```bash
cd backend
uv venv --python 3.12 .venv && uv pip install --python .venv pydantic pyyaml pytest
.venv/bin/pytest -q          # deterministic rules-engine tests
```

## Deploy

Backend shim + n8n on **Railway** (Docker); approval page on **Vercel**; shared EU
**Supabase**. Staging-first per `dome-docs/runbooks/staging-deploy.md`. See
`dome-docs/sprints/SPRINT_4_P5_AGENT_FLOW.md` for the full spec.
