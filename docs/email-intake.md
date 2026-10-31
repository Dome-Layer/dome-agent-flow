# Email intake for the invoice flow

Status: design for the showcase named in the decision of 2026-09-28: during a live demo someone emails an
invoice to a dedicated mailbox and it appears in the approval queue, through the same governed pipeline as the
form. This note comes first in the PR; the code follows it.

## The flow

```
sender ──▶ mailbox (receiving MTA adds Authentication-Results)
             │  IMAP
             ▼
n8n  "On invoice email" (Email Trigger, IMAP, format Simple, attachments on)
     "Prepare intake"   (Code: From, Date, Message-ID, Authentication-Results, attachments as base64)
     "Email intake"     POST /api/v1/intake/email ──▶ shim decides (see below)
     "One item per run" (Code: one item per NEW run, with its attachment as binary)
     "Extract invoice (P3)" POST /runs/{id}/extract   (shim checks the file is the vetted attachment)
     "Evaluate rules"       POST /runs/{id}/rules
     "Route to council?" ─▶ "Council brief (P2)" POST /runs/{id}/council
                              │
                              ▼
            approval page queue (pending_approval), named human decides
```

Everything after `POST /intake/email` is the existing pipeline: the same endpoints, the same `workflow_run_id`
per run, the same governance events (`invoice_received`, P3 `extraction`, `rules_evaluated`, P2 `deliberation`,
`human_approval`, `invoice_approved` / `invoice_rejected`).

## What is checked where

| Check | n8n | shim |
|---|---|---|
| Mailbox credential, which folder, mark as read | yes (IMAP credential, `UNSEEN`, mark read) | no |
| Service key on every call | sends it | **enforces** (`/intake/email` accepts the service key only) |
| Sender on the allowlist | not needed (may pre-filter) | **decides** (`EMAIL_INTAKE_ALLOWED_SENDERS`, empty means nobody) |
| Sender authenticated (DMARC) | relays the header | **decides** (trusted `Authentication-Results` only) |
| Attachment type (PDF, PNG, JPEG, TIFF) | no | **decides**, by magic bytes, not by filename or declared type |
| Attachment size | no | **decides** (`EMAIL_INTAKE_MAX_ATTACHMENT_BYTES`) |
| Number of runs per email | no | **decides** (`EMAIL_INTAKE_MAX_ATTACHMENTS`) |
| Same email twice | IMAP `UNSEEN` and its last-UID memory | **decides** (`intake_key`, unique in the database) |
| File sent to P3 is the vetted one | sends the matching binary | **checks** SHA-256 at `/extract` for email runs |

The shim decides everything that matters because it is the part under test in CI, and because the n8n
canvas is editable by whoever runs the demo. n8n can drop mail early, but nothing it skips is a control.

## The choices, with reasons

### 1. A separate workflow file, sharing the shim calls

`workflows/invoice_email_intake.json` is a second workflow; `invoice_to_approval.json` (the form) is untouched.
The downstream nodes of the form workflow address their data with `$('Create run')` and
`$('On invoice upload')`; with a second trigger on the same canvas those references point at nodes that did
not run, and one email can carry several invoices, so the item shape differs too. A separate file keeps the form
path exactly as verified on 2026-09-28. The shared part is the shim's API, not the n8n nodes: both workflows call
the same `/extract`, `/rules` and `/council` endpoints, which is where the logic lives. An n8n sub-workflow
("Execute Workflow") would share the nodes as well, but it adds a workflow id to wire after every import, which is
the kind of step that breaks a demo.

### 2. The allowlist lives in the shim and fails closed

`EMAIL_INTAKE_ALLOWED_SENDERS` is a comma-separated list. An entry with a local part (`ap@example.com`) matches
that address only; an entry without one (`example.com` or `@example.com`) matches every address at exactly that
domain. Matching is case-insensitive and exact: `sub.example.com` is not covered by `example.com`, and a lookalike
domain never matches. Empty means accept nobody, the same rule as `APPROVER_USER_IDS`. The From header must hold
exactly one address; a group or several addresses is refused.

Advice for the maintainer: list exact addresses for public providers (never a domain such as a webmail provider's,
which would admit anyone with an account there); domains are for a company domain you control.

### 3. Spoofing: what the shim relies on

A From header is easy to fake, so a match on the allowlist alone is not enough. The shim also requires a
**DMARC pass** recorded by the receiving mailbox:

- n8n relays the `Authentication-Results` header (RFC 8601) that the receiving mail server added.
- The shim trusts a header only if its authserv-id (the first token, for example `mx.example.com`) is on
  `EMAIL_INTAKE_TRUSTED_AUTHSERV_IDS`. A header that names any other authserv-id is ignored. Empty means no header
  is trusted, so nothing passes (fail closed).
- In a trusted header it requires `dmarc=pass`, and when the header names `header.from`, that domain must equal the
  From domain. DMARC pass means SPF or DKIM passed **and** aligned with the From domain, which is what ties the
  visible sender to the domain's own mail servers. The check holds whatever policy (`p=`) the domain publishes.
- The verdict (`pass`, `fail`, `none`) is recorded on the run and in the governance event.

`EMAIL_INTAKE_REQUIRE_DMARC` (default true) can be switched off **only in `ENVIRONMENT=development`**; the shim
refuses to start otherwise, as it does for `DEV_BYPASS_AUTH`.

Why the n8n trigger uses the Simple format: in that format n8n keeps the *first* value of each header, which for
`Authentication-Results` is the topmost one, the one the receiving server prepended. The Resolved format keeps the
*last* one, which is the one a sender could have planted. (Read in `packages/nodes-base/nodes/EmailReadImap/v2/utils.ts`
at `n8n@2.29.7`.) If n8n hands over a planted header, it names a foreign authserv-id and is ignored, so the error
case is a refusal, not an acceptance.

What remains a risk for a demo:

- **A receiver that does not strip forged headers.** RFC 8601 section 5 asks a receiver to remove incoming
  `Authentication-Results` that claim its own authserv-id. The large providers do; confirm it for the chosen
  mailbox in the staging window (send a message with a planted header and check what arrives).
- **Forwarding.** With Cloudflare Email Routing (option A below) the final mailbox sees Cloudflare as the sending
  host, so SPF does not align and DMARC depends on the sender's DKIM signature surviving the hop (it does when the
  message is not modified) or on the final mailbox trusting Cloudflare's ARC seal. Test with the real senders.
- **A compromised or shared allowlisted mailbox** passes every check. The human approval gate is the control that
  remains, and the rules engine still applies (duplicates, amounts, vendor list).
- **n8n is trusted to relay headers faithfully.** It holds the service key; anyone with the key can call
  `/intake/email` with made-up headers. That is the same trust the form path already places in n8n.
- **Domain entries admit anyone at that domain.**

### 4. Intake metadata on the run

Every run now carries `intake` (a JSON column) and email runs an `intake_key` (unique):

| Field | Form | Email | Why |
|---|---|---|---|
| `channel` | `form` (or `api` for a direct call) | `email` | also in the `invoice_received` event metadata |
| `received_at` | shim clock | shim clock | when the governed flow took the invoice in; the sender's Date header is not trustworthy |
| `sent_at` | | the Date header, as sent | context only |
| `message_id_hash` | | SHA-256 of the Message-ID | idempotency and correlation without storing the id |
| `sender_domain` | | e.g. `example.com` | enough to see which supplier sent it |
| `sender_hash` | | HMAC-SHA256 of the address, keyed | see below |
| `dmarc` | | `pass` / `fail` / `none` | the authentication verdict the decision used |
| `attachment_index`, `attachment_sha256`, `content_type` | | per run | binds the run to one attachment |

**Idempotency.** `intake_key = SHA-256("email|" + Message-ID + "|" + attachment SHA-256)`. Before creating a run the
shim looks the key up; a database unique index catches two deliveries racing each other. The same email processed
twice returns the existing runs with `duplicate: true` and creates nothing. If a message has no Message-ID (rare,
but legal), the shim falls back to a hash of the From address and the Date header. A *different* email carrying
the same invoice gets its own run, and the rules engine's duplicate check (vendor, number, amount) flags it, as it
would for the form.

**The sender's address is personal data, so it is not stored.** Stored: the domain, which identifies a company
rather than a person in the normal case, and a keyed hash of the full address. The keyed hash (HMAC with
`EMAIL_INTAKE_HASH_KEY`) lets someone who holds the key confirm which allowlisted address sent a run, by hashing
each address on the list, while a reader of the table without the key cannot reverse it with a list of likely
addresses, which a plain SHA-256 would allow. If `EMAIL_INTAKE_HASH_KEY` is empty, no hash is stored at all, only
the domain. The subject, body, recipient list and display name are not stored or logged; logs carry the domain
only. The filename is stored, as it already is for the form.

The mailbox itself still holds the full message. That is outside the shim: see the retention point under open
decisions.

### 5. Attachments

- Accepted types, detected by magic bytes: PDF, PNG, JPEG and TIFF (`app/services/intake.py`,
  `ACCEPTED_TYPES`). These are the formats Azure Document Intelligence takes for invoices and that P3 is understood
  to accept; confirm against P3's own list in the staging window. Extensions and declared MIME types are ignored,
  so a renamed executable is refused and a PDF named `scan.bin` is accepted.
- One run per accepted attachment. Identical attachments in one email count once.
- Other attachments (signature logos are common) are ignored and listed in the response with a reason:
  `unsupported_type`, `too_large`, `empty`, `undecodable`, `duplicate`, `too_many`.
- Size limit `EMAIL_INTAKE_MAX_ATTACHMENT_BYTES` (default 10 MiB) per attachment; at most
  `EMAIL_INTAKE_MAX_ATTACHMENTS` (default 5) runs per email, so one message cannot fan out into many paid
  extractions.
- At `/extract`, an email run accepts only a file whose SHA-256 equals the recorded attachment hash.

### 6. Outcomes when nothing is accepted

The response is always HTTP 200 with an `outcome`, because a refused email is a business outcome, not a fault;
n8n then simply has no run items to continue with. No run row is created, and no P3 or P2 call is made.

| Outcome | Reason | Governance event |
|---|---|---|
| `rejected` | `invalid_sender` (no single parsable From address) | `intake_rejected` |
| `rejected` | `sender_not_allowed` | `intake_rejected` |
| `rejected` | `authentication_failed` (no trusted DMARC pass) | `intake_rejected` |
| `rejected` | `no_usable_attachment` | `intake_rejected` |
| `duplicate` | every attachment already has a run | none (logged) |
| `accepted` | at least one new run | `invoice_received` per run, `channel: email` |

**Proposed action type: `intake_rejected`** (`agent_id="agent-flow"`). None of the existing types fit: they all
describe a run, and a refused email has none. The event gets its own id (`intake-YYYY-MM-DD-xxxxxxxx`) as its
`workflow_run_id`, so P6 shows each refusal as a one-step timeline instead of an orphan, and no `invoice_runs` row
appears in the approval queue. Metadata: channel, reason, sender domain, DMARC verdict, attachment counts. The
name is channel-neutral so a future webhook intake can reuse it. P6 may need to learn the label.

Refusals are not deduplicated (there is no row to look up), so a refused email processed twice yields two events.
For an audit trail that is acceptable: each one records a real attempt.

## The mailbox: options for the maintainer (not decided)

No account is created by this PR. Three workable shapes:

**A. Cloudflare Email Routing on `domelayer.com`, forwarding to a mailbox n8n reads over IMAP.**
An address such as `invoices@` on a domain already managed in Cloudflare, routed to an existing mailbox.
Free and quick, no new MX provider. But it is forwarding: SPF breaks at the hop and DMARC rests on DKIM surviving
or on ARC (see the risks above); the authserv-id to trust is the *final* mailbox's; and the destination still
needs IMAP, ideally a dedicated account so demo mail never mixes with personal mail. Note that Email Routing takes
over the MX records of the (sub)domain it is enabled on, so use a subdomain if `domelayer.com` already receives
mail elsewhere.

**B. A dedicated hosted mailbox on a subdomain (for example `invoices.domelayer.com`) at an EU mail provider with
IMAP.** Direct delivery, so the provider's own `Authentication-Results` carries a stable authserv-id and SPF works
as designed; data stays in the EU; a DPA comes with the account. Costs a small monthly fee and one more vendor to
list. Avoid providers that expose IMAP only through a local bridge, which n8n on Railway cannot run.

**C. A free consumer mailbox dedicated to the demo.** Zero setup, reliable authentication headers, IMAP with an
app password. It is not on `domelayer.com`, so it looks less finished on stage, and the processor is typically
outside the EU, which sits awkwardly with the "regulated European businesses" pitch.

For a showcase aimed at European regulated businesses, B tells the best story; A is the cheapest to try first.
Whichever is chosen, set `EMAIL_INTAKE_TRUSTED_AUTHSERV_IDS` to the authserv-id seen in a real delivered message.

### Chosen for the first demos: A, free, one new account

The constraints (2026-10-31): professional on stage, free, as few new accounts as possible.

```
presenter's existing mailbox ──▶ invoices@domelayer.com (Cloudflare Email Routing, existing account)
                                          │ forwards
                                          ▼
                      one new free Gmail account, used for nothing else ◀── n8n, IMAP
```

- **What the audience sees:** an address on `domelayer.com`. The Gmail account behind it is never shown.
- **New accounts:** one, the dedicated Gmail account. Cloudflare and the sender's mailbox already exist.
- **Why not forward to the presenter's own mailbox (zero new accounts):** an IMAP app password opens the whole
  account, so n8n would hold the key to personal mail, and a Gmail filter limiting n8n to one label does not
  narrow what the credential can read. Gmail also tends to hide a message that comes back to the account that
  sent it.
- **Sender:** the presenter's existing personal address, on `EMAIL_INTAKE_ALLOWED_SENDERS` as an **exact address**
  (never the provider's domain). Add a guest's exact address on the day if someone else should send one.
- **Trusted authserv-id:** expected to be `mx.google.com`, since the dedicated Gmail account evaluates the mail;
  confirm it from the first delivered test message.
- **Sending as `@domelayer.com`** would need an outgoing mail service; Cloudflare Email Routing only receives.
  Not needed: the recipient address is the one on screen.
- **Privacy:** Google holds the forwarded originals, outside the EU. Acceptable for a private demo; empty the
  inbox after each demo and cover it in the privacy policy line. Moving to option B later only changes the
  routing destination, the IMAP credential and `EMAIL_INTAKE_TRUSTED_AUTHSERV_IDS`.

## Privacy policy (website repo)

Probably yes, a line is needed. Today the policy (in the website repo, not changed here) covers the form. Email
intake adds: invoices received by email at the demo address are processed by DOME's tools, the attachments are
sent to the document extraction service, DOME stores the sender's domain and a pseudonymous keyed hash of the
address (not the address, subject or body), and the mailbox keeps the original message for a stated period. Flagged
for the maintainer; the wording belongs with the rest of the policy.

## Open decisions for the maintainer

1. Mailbox: A with a dedicated Gmail destination for the first demos (above); whether to move to B later.
2. Retention in the mailbox: the full messages sit there. Suggest a rule that deletes after the demo, or empties
   the folder at teardown.
3. Whether to set `EMAIL_INTAKE_HASH_KEY` (pseudonymous linkability) or leave it empty (domain only).
4. The privacy policy line above.
5. Whether P6 should label `intake_rejected` specially.
6. Category: the form asks for one, an email does not. Email runs go to the rules engine without a category, as an
   API run would. A later change could read it from the subject line against a fixed list.

## Settings (names only)

| Setting | Default | Meaning |
|---|---|---|
| `EMAIL_INTAKE_ALLOWED_SENDERS` | empty (nobody) | addresses and/or domains |
| `EMAIL_INTAKE_TRUSTED_AUTHSERV_IDS` | empty (nothing trusted) | authserv-ids of the receiving mailbox |
| `EMAIL_INTAKE_REQUIRE_DMARC` | true | false only allowed in development |
| `EMAIL_INTAKE_MAX_ATTACHMENT_BYTES` | 10485760 | per attachment |
| `EMAIL_INTAKE_MAX_ATTACHMENTS` | 5 | runs per email |
| `EMAIL_INTAKE_HASH_KEY` | empty (no sender hash) | HMAC key for the sender hash |

## Database change

`backend/migrations/011_invoice_runs_intake.sql` adds `intake jsonb` and `intake_key text` with a unique index
to `invoice_runs`. Applied to staging on 2026-10-31 and recorded in `dome_schema_migrations` as
`011_invoice_runs_intake.sql`. Any other database needs it **before** this shim starts there: the shim writes
`intake` on every new run, form runs included.
