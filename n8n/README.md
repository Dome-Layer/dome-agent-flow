# Self-hosted n8n — DOME Governed Agent Flow

n8n is the *visible* orchestrator for P5. Its nodes call **only** the agent-flow shim's
clean JSON API (never P3/P2/Supabase directly). Self-hosted on **Railway** (Docker),
consistent with the rest of the portfolio; staging is stopped-by-default to save cost and
brought up for demos.

## Deploy (Railway)

1. New Railway service from this `n8n/` directory (uses the Dockerfile + `railway.toml`).
2. Add a **Postgres** plugin in the same project for n8n's own state.
3. Set environment variables:

| Var | Value |
|---|---|
| `N8N_ENCRYPTION_KEY` | a long random string (encrypts the credential store) |
| `DB_TYPE` | `postgresdb` |
| `DB_POSTGRESDB_HOST` / `_PORT` / `_DATABASE` / `_USER` / `_PASSWORD` | from the Railway Postgres plugin |
| `N8N_HOST` | `agent-flow-n8n.up.railway.app` (or the custom domain) |
| `N8N_PROTOCOL` | `https` |
| `WEBHOOK_URL` | `https://<N8N_HOST>/` |
| `N8N_BASIC_AUTH_ACTIVE` | `true` |
| `N8N_BASIC_AUTH_USER` / `_PASSWORD` | demo login for the n8n editor |
| `AGENTFLOW_SHIM_BASE` | the shim backend base URL, e.g. `https://agent-flow-backend.up.railway.app` |

4. Create an n8n **credential** of type *Header Auth* named **"Agent Flow Service Key"**:
   `Name = X-Service-Key`, `Value = <AGENT_FLOW_SERVICE_KEY>` (the same secret the shim and
   P3/P2 share). The committed workflow references this credential by name — the value is
   never committed.

## Import the workflow

Import [`../workflows/invoice_to_approval.json`](../workflows/invoice_to_approval.json) into
the n8n editor. After import, confirm in the UI:
- each **HTTP Request** node uses the *Agent Flow Service Key* credential;
- the **Extract** node forwards the uploaded file as the binary `invoice` field;
- the base URL expressions resolve to `{{$env.AGENTFLOW_SHIM_BASE}}`.

## Triggers

- **Form trigger** (committed default) — a hosted upload form at the workflow's form URL;
  reliable for live demos.
- **Email trigger (IMAP)** — add an *Email Trigger (IMAP)* node on a dedicated AP inbox for
  the realistic "vendor emails an invoice" entry; wire its attachment into the same
  *Create run → Extract* path.

## Flow

`trigger → POST /runs → POST /runs/{id}/extract → POST /runs/{id}/rules → IF route_to_council
→ POST /runs/{id}/council`. Auto-approved/rejected runs finalise in `/rules`; human-needed
runs sit in `pending_approval` for the branded approval page (`agent-flow.domelayer.com`),
which the shim finalises and records. Every step is emitted to `governance_events` with one
shared `workflow_run_id`, so P6 reconstructs the run as a single cross-tool timeline.

> Optional: to make n8n *wait* for the human inline, add a **Wait** (resume-on-webhook) node
> after the council step and pass `{{$execution.resumeUrl}}` as `resume_url` when creating the
> run — the shim's `/decision` endpoint will resume it. The default workflow omits this; the
> approval page + shim complete the trail out-of-band.
