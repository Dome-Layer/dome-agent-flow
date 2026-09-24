# Self-hosted n8n: DOME Governed Agent Flow

n8n is the *visible* orchestrator for P5. Its nodes call **only** the agent-flow shim's
clean JSON API (never P3/P2/Supabase directly). Self-hosted on **Railway** (Docker),
consistent with the rest of the portfolio; staging is stopped-by-default to save cost and
brought up for demos.

## Deploy (Railway)

Staging only, stopped by default, brought up for demos (decision 2026-09-24: no production n8n
for now; production P5 is the shim plus the approval page).

1. New Railway service in the **Agent Flow** project, **staging** environment, from the image
   `n8nio/n8n:2.29.7` (the same pin as this directory's `Dockerfile`, DA-034). Deploying from the
   image avoids setting a root directory; the Dockerfile adds nothing but the pin and `EXPOSE`.
2. Add a **Postgres** database in the same project and environment for n8n's own state.
3. Set environment variables:

| Var | Value |
|---|---|
| `N8N_ENCRYPTION_KEY` | a long random string (encrypts the credential store). **Never rotate it** once credentials exist, or they become unreadable |
| `DB_TYPE` | `postgresdb` |
| `DB_POSTGRESDB_HOST` / `_PORT` / `_DATABASE` / `_USER` / `_PASSWORD` | Railway reference variables to the Postgres service (`${{Postgres.PGHOST}}` etc.) |
| `N8N_HOST` | the service's generated `*.up.railway.app` domain |
| `N8N_PROTOCOL` | `https` |
| `N8N_PORT` | `5678` |
| `WEBHOOK_URL` | `https://<N8N_HOST>/` (the form trigger's public URL is built from this) |
| `N8N_PROXY_HOPS` | `1` (Railway terminates TLS in front of the container) |

**Stale guidance removed (2026-09-24).** Earlier versions of this file listed
`N8N_BASIC_AUTH_ACTIVE` / `_USER` / `_PASSWORD`. Basic auth was removed in n8n 1.0; those vars are
silently ignored. n8n 2.x requires an **owner account**, created through the setup screen on first
load (or pre-provisioned from env vars, 2.17.0+). The owner is a human task: whoever runs the demo
creates it and keeps the password in their own password manager.

Also removed: `AGENTFLOW_SHIM_BASE`. n8n 2.0 made `N8N_BLOCK_ENV_ACCESS_IN_NODE` default to `true`,
so any `$env.X` expression throws `access to env vars denied` (confirmed in
`packages/workflow/src/workflow-data-proxy-env-provider.ts` at `n8n@2.29.7`). Rather than switch that
security default off, the workflow now reads the shim URL from a **Config** node at the top of the
canvas. To point it at a different shim, edit that one node.

4. Create an n8n **credential** of type *Header Auth* named **"Agent Flow Service Key"**:
   `Name = X-Service-Key`, `Value = <AGENT_FLOW_SERVICE_KEY>` (the same secret the shim and
   P3/P2 share). The committed workflow references this credential by name; the value is
   never committed.

## Import the workflow

Import [`../workflows/invoice_to_approval.json`](../workflows/invoice_to_approval.json) into
the n8n editor. After import, confirm in the UI:
- each **HTTP Request** node uses the *Agent Flow Service Key* credential (the committed id is a
  placeholder, `REPLACE_IN_N8N`, so each node needs the credential re-selected once);
- the **Config** node's `shimBase` is the shim you mean to hit;
- the **Extract** node forwards the form's uploaded file (binary property `Invoice_file`, derived
  from the form field label "Invoice file") as the multipart `file` field the shim expects;
- the workflow is **activated/published**; the form trigger's production URL only answers while it is.

## Triggers

- **Form trigger** (committed default): a hosted upload form at the workflow's form URL;
  reliable for live demos.
- **Email trigger (IMAP)**: add an *Email Trigger (IMAP)* node on a dedicated AP inbox for
  the realistic "vendor emails an invoice" entry; wire its attachment into the same
  *Create run → Extract* path.

## Flow

`trigger → Config → POST /runs → POST /runs/{id}/extract → POST /runs/{id}/rules → IF route_to_council
→ POST /runs/{id}/council`. Auto-approved/rejected runs finalise in `/rules`; human-needed
runs sit in `pending_approval` for the branded approval page (`agent-flow.domelayer.com`),
which the shim finalises and records. Every step is emitted to `governance_events` with one
shared `workflow_run_id`, so P6 reconstructs the run as a single cross-tool timeline.

> Optional: to make n8n *wait* for the human inline, add a **Wait** (resume-on-webhook) node
> after the council step and pass `{{$execution.resumeUrl}}` as `resume_url` when creating the
> run; the shim's `/decision` endpoint will resume it. The default workflow omits this; the
> approval page + shim complete the trail out-of-band.
