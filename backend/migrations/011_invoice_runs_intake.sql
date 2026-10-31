-- Email intake (docs/email-intake.md): how a run entered the flow, and the
-- idempotency key that stops one email from creating two runs.
-- Applied to staging (dome-platform-staging) on 2026-10-31, tracked in
-- public.dome_schema_migrations. Production: not yet (no production service).

alter table public.invoice_runs
  add column if not exists intake jsonb,
  add column if not exists intake_key text;

-- NULLs stay distinct, so form and API runs (no key) are unaffected.
create unique index if not exists invoice_runs_intake_key_idx
  on public.invoice_runs (intake_key);
