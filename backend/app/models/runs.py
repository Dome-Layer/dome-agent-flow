"""Run-state + API request/response models for the Governed Agent Flow shim.

`invoice_runs` holds the mutable operational state of a run (one row per
`workflow_run_id`); `governance_events` holds the immutable audit trail.
"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel

from app.models.schemas import Invoice, PolicyDecision

# Lifecycle: a run advances through these states.
RUN_STATUSES = (
    "received",          # POST /runs
    "extracted",         # P3 extraction stored
    "council",           # routed to P2 (awaiting/!consulted)
    "pending_approval",  # waiting on a human
    "approved",          # terminal
    "rejected",          # terminal
)


class CreateRunRequest(BaseModel):
    source: str = "manual"            # "email" | "form" | "manual" | "webhook"
    filename: Optional[str] = None
    # n8n's Wait-node resume URL, stored so /decision can continue the paused run.
    resume_url: Optional[str] = None


class DecisionRequest(BaseModel):
    decision: str                     # "approve" | "reject"
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
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
