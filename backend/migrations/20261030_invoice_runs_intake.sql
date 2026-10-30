-- Email intake (docs/email-intake.md): how a run entered the flow, and the
-- idempotency key that stops one email from creating two runs.
-- Apply to staging before the shim that writes these columns starts there.

alter table public.invoice_runs
  add column if not exists intake jsonb,
  add column if not exists intake_key text;

-- NULLs stay distinct, so form and API runs (no key) are unaffected.
create unique index if not exists invoice_runs_intake_key_idx
  on public.invoice_runs (intake_key);
