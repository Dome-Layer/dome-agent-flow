"""Run-state + API request/response models for the Governed Agent Flow shim.

`invoice_runs` holds the mutable operational state of a run (one row per
`workflow_run_id`); `governance_events` holds the immutable audit trail.
"""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel

from app.models.schemas import Invoice, PolicyDecision

# Lifecycle: a run advances through these states.
RUN_STATUSES = (
    "received",  # POST /runs
    "extracted",  # P3 extraction stored
    "council",  # routed to P2 (awaiting/!consulted)
    "pending_approval",  # waiting on a human
    "approved",  # terminal
    "rejected",  # terminal
)


class IntakeMetadata(BaseModel):
    """How an invoice entered the flow (docs/email-intake.md). Stored on the run as
    `intake`; the sender's address is never stored, only its domain and a keyed hash."""

    channel: Literal["form", "email", "api"]
    received_at: str  # shim clock, ISO 8601 UTC
    sent_at: Optional[str] = None  # the email's Date header, as sent
    message_id_hash: Optional[str] = None
    sender_domain: Optional[str] = None
    sender_hash: Optional[str] = None
    dmarc: Optional[str] = None  # "pass" | "fail" | "none"
    attachment_index: Optional[int] = None
    attachment_sha256: Optional[str] = None
    content_type: Optional[str] = None


class EmailAttachment(BaseModel):
    filename: Optional[str] = None
    content_base64: str


class EmailIntakeRequest(BaseModel):
    """One email as n8n's IMAP trigger read it. Subject and body are not sent."""

    message_id: Optional[str] = None
    from_header: str = ""
    date: Optional[str] = None
    # Authentication-Results header values, topmost first.
    authentication_results: list[str] = []
    attachments: list[EmailAttachment] = []


class IntakeRunRef(BaseModel):
    workflow_run_id: str
    attachment_index: int
    filename: Optional[str] = None
    duplicate: bool = False


class IgnoredAttachment(BaseModel):
    attachment_index: int
    reason: str  # unsupported_type | too_large | empty | undecodable | duplicate | too_many


class EmailIntakeResult(BaseModel):
    outcome: Literal["accepted", "duplicate", "rejected"]
    # invalid_sender | sender_not_allowed | authentication_failed | no_usable_attachment
    reason: Optional[str] = None
    # The id an `intake_rejected` governance event was filed under.
    intake_event_id: Optional[str] = None
    runs: list[IntakeRunRef] = []
    ignored: list[IgnoredAttachment] = []


class CreateRunRequest(BaseModel):
    source: str = "manual"  # "email" | "form" | "manual" | "webhook"
    filename: Optional[str] = None
    # n8n's Wait-node resume URL, stored so /decision can continue the paused run.
    resume_url: Optional[str] = None


class DecisionRequest(BaseModel):
    decision: str  # "approve" | "reject"
    note: Optional[str] = None


class CouncilRequest(BaseModel):
    # Optional override; by default the shim composes the question from the invoice.
    question: Optional[str] = None
    context: Optional[str] = None


class RunRecord(BaseModel):
    workflow_run_id: str
    status: str
    source: str = "manual"
    filename: Optional[str] = None
    invoice: Optional[Invoice] = None
    extraction: Optional[dict] = None
    decision: Optional[PolicyDecision] = None
    council: Optional[dict] = None
    approver_id: Optional[str] = None
    decision_note: Optional[str] = None
    resume_url: Optional[str] = None
    user_id: Optional[str] = None
    intake: Optional[IntakeMetadata] = None
    # Idempotency key of an email run: the same email twice never makes two runs.
    intake_key: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
