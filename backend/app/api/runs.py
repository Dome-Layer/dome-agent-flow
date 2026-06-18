"""The Governed Agent Flow run API.

n8n drives a run through these clean JSON endpoints (it never touches P3/P2/Supabase
directly); the branded approval page reads pending runs and posts the human decision.
Every step emits a `workflow_run_id`-stamped governance event.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Optional

from dome_core.governance import hash_input_text
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status

from app.api.deps import Principal, require_principal, require_user
from app.core.config import settings
from app.core.logging import get_logger
from app.models.runs import CouncilRequest, CreateRunRequest, DecisionRequest, RunRecord
from app.services import governance
from app.services import runs as runs_svc
from app.services import upstream
from app.services.normalize import invoice_from_extraction
from app.services.rules import evaluate

logger = get_logger(__name__)
router = APIRouter(prefix="/runs", tags=["runs"])

_STATUS_FOR_DECISION = {
    "auto_approve": "approved",
    "reject": "rejected",
    "route_to_council": "council",
    "require_human": "pending_approval",
}


def _gen_run_id() -> str:
    return f"invoice-{datetime.now(timezone.utc):%Y-%m-%d}-{uuid.uuid4().hex[:8]}"


def _load(workflow_run_id: str) -> RunRecord:
    run = runs_svc.get_run(workflow_run_id)
    if run is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail=f"Run {workflow_run_id} not found")
    return run


def _council_question(run: RunRecord) -> str:
    inv = run.invoice
    return (
        f"Should we approve invoice {inv.invoice_number or '?'} from "
        f"{inv.vendor_name or 'an unknown vendor'} for {inv.amount} {inv.currency or ''} "
        f"(category {inv.category or 'n/a'}, vendor country {inv.country or 'n/a'})? "
        f"What approval level and additional checks are warranted?"
    )


def _council_context(run: RunRecord) -> str:
    d = run.decision
    flags = ", ".join(d.rules_triggered) if d and d.rules_triggered else "none"
    return f"Policy engine decision: {d.decision if d else 'n/a'}. Triggered rules: {flags}."


def _emit_terminal(run: RunRecord, *, approved: bool, approver_id: Optional[str],
                   note: Optional[str]) -> None:
    run.approver_id = approver_id
    run.decision_note = note
    run.status = "approved" if approved else "rejected"
    inv = run.invoice
    if approver_id:
        governance.emit_event(
            action_type="human_approval",
            workflow_run_id=run.workflow_run_id,
            input_hash=hash_input_text(run.workflow_run_id),
            input_type="approval_decision",
            output_summary=f"Human {'approved' if approved else 'rejected'} the invoice",
            human_in_loop="completed",
            user_id=approver_id,
            metadata={"note": note},
        )
    governance.emit_event(
        action_type="invoice_approved" if approved else "invoice_rejected",
        workflow_run_id=run.workflow_run_id,
        input_hash=hash_input_text(run.workflow_run_id),
        input_type="workflow_outcome",
        output_summary=("Invoice approved" if approved else "Invoice rejected")
        + (f": {note}" if note else ""),
        human_in_loop="completed" if approver_id else "not_required",
        user_id=approver_id,
        confidence=inv.overall_confidence if inv else None,
        metadata={
            "vendor": inv.vendor_name if inv else None,
            "amount": inv.amount if inv else None,
            "currency": inv.currency if inv else None,
            "auto": approver_id is None,
        },
    )


@router.post("")
async def create_run(
    body: CreateRunRequest, principal: Principal = Depends(require_principal)
) -> RunRecord:
    run = RunRecord(
        workflow_run_id=_gen_run_id(),
        status="received",
        source=body.source,
        filename=body.filename,
        resume_url=body.resume_url,
        user_id=principal.user_id,
    )
    runs_svc.create_run(run)
    governance.emit_event(
        action_type="invoice_received",
        workflow_run_id=run.workflow_run_id,
        input_hash=hash_input_text(body.filename or run.workflow_run_id),
        input_type="invoice_pdf",
        output_summary=f"Invoice run received via {body.source}: {body.filename or '—'}",
    )
    return run


@router.post("/{workflow_run_id}/extract")
async def extract(
    workflow_run_id: str,
    file: UploadFile = File(...),
    category: Optional[str] = Form(default=None),
    principal: Principal = Depends(require_principal),
) -> RunRecord:
    run = _load(workflow_run_id)
    data = await file.read()
    result = await upstream.extract_invoice(
        data, file.filename or "invoice", file.content_type, workflow_run_id
    )
    run.extraction = result
    run.invoice = invoice_from_extraction(result, category=category)
    run.status = "extracted"
    runs_svc.update_run(run)
    # P3 emits its own `extraction` governance event (stamped with workflow_run_id).
    return run


@router.post("/{workflow_run_id}/rules")
async def rules(
    workflow_run_id: str, principal: Principal = Depends(require_principal)
) -> RunRecord:
    run = _load(workflow_run_id)
    if run.invoice is None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT,
                            detail="Run has no extracted invoice yet")

    known = runs_svc.known_dedupe_keys(exclude=workflow_run_id)
    decision = evaluate(
        run.invoice,
        known_keys=known,
        require_human_on_all=settings.require_human_on_all or None,
    )
    run.decision = decision
    run.status = _STATUS_FOR_DECISION[decision.decision]

    governance.emit_event(
        action_type="rules_evaluated",
        workflow_run_id=workflow_run_id,
        input_hash=hash_input_text(run.invoice.dedupe_key()),
        input_type="extraction_result",
        output_summary=f"Policy decision: {decision.decision}"
        + (f" ({decision.required_role})" if decision.required_role else ""),
        rules_applied=decision.rules_applied,
        rules_triggered=decision.rules_triggered,
        confidence=run.invoice.overall_confidence,
        human_in_loop=decision.human_in_loop,
        metadata={
            "decision": decision.decision,
            "required_role": decision.required_role,
            "amount": run.invoice.amount,
            "currency": run.invoice.currency,
            "category": run.invoice.category,
            "country": run.invoice.country,
        },
    )

    if decision.decision == "auto_approve":
        _emit_terminal(run, approved=True, approver_id=None, note="Auto-approved under policy")
    elif decision.decision == "reject":
        _emit_terminal(run, approved=False, approver_id=None, note="Auto-rejected by policy")

    runs_svc.update_run(run)
    return run


@router.post("/{workflow_run_id}/council")
async def council(
    workflow_run_id: str,
    body: Optional[CouncilRequest] = None,
    principal: Principal = Depends(require_principal),
) -> RunRecord:
    run = _load(workflow_run_id)
    if run.invoice is None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT,
                            detail="Run has no extracted invoice yet")
    body = body or CouncilRequest()
    verdict = await upstream.council_deliberate(
        body.question or _council_question(run),
        body.context or _council_context(run),
        workflow_run_id,
    )
    run.council = verdict
    run.status = "pending_approval"
    runs_svc.update_run(run)
    # P2 emits its own `deliberation` governance event (stamped with workflow_run_id).
    return run


@router.post("/{workflow_run_id}/decision")
async def decision(
    workflow_run_id: str,
    body: DecisionRequest,
    principal: Principal = Depends(require_user),
) -> RunRecord:
    run = _load(workflow_run_id)
    if run.status in ("approved", "rejected"):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Run already finalised")

    approved = body.decision.strip().lower() == "approve"
    _emit_terminal(run, approved=approved, approver_id=principal.user_id, note=body.note)
    runs_svc.update_run(run)
    await upstream.resume_n8n(
        run.resume_url,
        {"workflow_run_id": workflow_run_id,
         "decision": "approve" if approved else "reject",
         "approver_id": principal.user_id},
    )
    return run


@router.get("")
async def list_runs(
    status: Optional[str] = None, principal: Principal = Depends(require_principal)
) -> dict:
    items = runs_svc.list_runs(
        status=status, user_id=principal.user_id, is_service=principal.is_service
    )
    return {"runs": items, "total": len(items)}


@router.get("/{workflow_run_id}")
async def get_run(
    workflow_run_id: str, principal: Principal = Depends(require_principal)
) -> RunRecord:
    return _load(workflow_run_id)
