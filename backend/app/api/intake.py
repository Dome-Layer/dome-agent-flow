"""Email intake: n8n's IMAP trigger hands over one email; the shim decides.

The decisions (allowlist, DMARC, attachments, idempotency) are in
`app/services/intake.py`; this endpoint applies them in order, creates one run per
accepted invoice attachment and files the governance events. A refused email makes
no run and no paid model call (docs/email-intake.md).
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends

from app.api.deps import Principal, require_service
from app.api.runs import gen_run_id
from app.core.config import settings
from app.core.logging import get_logger
from app.models.runs import (
    EmailIntakeRequest,
    EmailIntakeResult,
    IgnoredAttachment,
    IntakeMetadata,
    IntakeRunRef,
    RunRecord,
)
from app.services import governance, intake
from app.services import runs as runs_svc

logger = get_logger(__name__)
router = APIRouter(prefix="/intake", tags=["intake"])

_REJECTION_SUMMARY = {
    "invalid_sender": "no single valid From address",
    "sender_not_allowed": "sender not on the allowlist",
    "authentication_failed": "no trusted DMARC pass for the sender",
    "no_usable_attachment": "no usable invoice attachment",
}


def _reject(
    reason: str,
    *,
    msg_hash: str,
    domain: Optional[str],
    dmarc: Optional[str],
    attachment_count: int,
    ignored: Optional[list[IgnoredAttachment]] = None,
) -> EmailIntakeResult:
    event_id = f"intake-{datetime.now(timezone.utc):%Y-%m-%d}-{uuid.uuid4().hex[:8]}"
    ignored = ignored or []
    governance.emit_event(
        action_type="intake_rejected",
        workflow_run_id=event_id,
        input_hash=msg_hash,
        input_type="email",
        output_summary=f"Email intake rejected: {_REJECTION_SUMMARY[reason]}",
        metadata={
            "channel": "email",
            "reason": reason,
            "sender_domain": domain,
            "dmarc": dmarc,
            "attachments": attachment_count,
            "ignored": [i.reason for i in ignored],
        },
    )
    logger.info("email_intake_rejected", reason=reason, sender_domain=domain, event_id=event_id)
    return EmailIntakeResult(
        outcome="rejected", reason=reason, intake_event_id=event_id, ignored=ignored
    )


@router.post("/email")
async def email_intake(
    body: EmailIntakeRequest, principal: Principal = Depends(require_service)
) -> EmailIntakeResult:
    received_at = datetime.now(timezone.utc).isoformat()
    address = intake.parse_sender(body.from_header)
    domain = intake.sender_domain(address) if address else None
    msg_hash = intake.message_hash(body.message_id, address or "", body.date)
    count = len(body.attachments)

    if address is None or domain is None:
        return _reject(
            "invalid_sender", msg_hash=msg_hash, domain=None, dmarc=None, attachment_count=count
        )
    if not intake.sender_allowed(
        address, settings.email_allowed_addresses, settings.email_allowed_domains
    ):
        return _reject(
            "sender_not_allowed",
            msg_hash=msg_hash,
            domain=domain,
            dmarc=None,
            attachment_count=count,
        )
    dmarc = intake.dmarc_verdict(
        body.authentication_results, settings.email_trusted_authserv_ids, domain
    )
    if settings.email_intake_require_dmarc and dmarc != "pass":
        return _reject(
            "authentication_failed",
            msg_hash=msg_hash,
            domain=domain,
            dmarc=dmarc,
            attachment_count=count,
        )

    accepted, ignored = intake.select_attachments(
        body.attachments,
        max_bytes=settings.email_intake_max_attachment_bytes,
        max_count=settings.email_intake_max_attachments,
    )
    if not accepted:
        return _reject(
            "no_usable_attachment",
            msg_hash=msg_hash,
            domain=domain,
            dmarc=dmarc,
            attachment_count=count,
            ignored=ignored,
        )

    sent_at = intake.parse_sent_at(body.date)
    s_hash = intake.sender_hash(address, settings.email_intake_hash_key)
    refs: list[IntakeRunRef] = []
    for att in accepted:
        key = intake.intake_key(msg_hash, att.sha256)
        existing = runs_svc.get_run_by_intake_key(key)
        if existing is None:
            meta = IntakeMetadata(
                channel="email",
                received_at=received_at,
                sent_at=sent_at,
                message_id_hash=msg_hash,
                sender_domain=domain,
                sender_hash=s_hash,
                dmarc=dmarc,
                attachment_index=att.index,
                attachment_sha256=att.sha256,
                content_type=att.content_type,
            )
            run = RunRecord(
                workflow_run_id=gen_run_id(),
                status="received",
                source="email",
                filename=att.filename,
                intake=meta,
                intake_key=key,
            )
            if runs_svc.create_run_once(run):
                _emit_received(run.workflow_run_id, meta, att)
                refs.append(
                    IntakeRunRef(
                        workflow_run_id=run.workflow_run_id,
                        attachment_index=att.index,
                        filename=att.filename,
                    )
                )
                continue
            # Lost a race with a second delivery of the same email.
            existing = runs_svc.get_run_by_intake_key(key)
            if existing is None:
                logger.error("email_intake_key_conflict", attachment_index=att.index)
                continue
        refs.append(
            IntakeRunRef(
                workflow_run_id=existing.workflow_run_id,
                attachment_index=att.index,
                filename=existing.filename,
                duplicate=True,
            )
        )

    outcome = "accepted" if any(not r.duplicate for r in refs) else "duplicate"
    logger.info(
        "email_intake",
        outcome=outcome,
        sender_domain=domain,
        runs=len([r for r in refs if not r.duplicate]),
        duplicates=len([r for r in refs if r.duplicate]),
        ignored=len(ignored),
    )
    return EmailIntakeResult(outcome=outcome, runs=refs, ignored=ignored)


def _emit_received(
    workflow_run_id: str, meta: IntakeMetadata, att: intake.AcceptedAttachment
) -> None:
    governance.emit_event(
        action_type="invoice_received",
        workflow_run_id=workflow_run_id,
        input_hash=att.sha256,
        input_type="invoice_pdf" if att.content_type == "application/pdf" else "invoice_image",
        output_summary=f"Invoice run received via email: {att.filename or 'N/A'}",
        metadata={
            "channel": "email",
            "received_at": meta.received_at,
            "sender_domain": meta.sender_domain,
            "dmarc": meta.dmarc,
            "attachment_index": att.index,
            "content_type": att.content_type,
            "size_bytes": att.size,
        },
    )
