"""CRUD for `invoice_runs` (the mutable run state) via the Supabase service client.

When Supabase is unconfigured (local dev) the helpers degrade gracefully: writes are
no-ops and reads return empty, so the API still exercises the rules/normalise logic.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from app.core.logging import get_logger
from app.models.runs import RunRecord
from app.models.schemas import Invoice, PolicyDecision
from app.services.db import get_service_client

logger = get_logger(__name__)
_TABLE = "invoice_runs"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _to_row(run: RunRecord) -> dict:
    inv = run.invoice
    return {
        "workflow_run_id": run.workflow_run_id,
        "status": run.status,
        "source": run.source,
        "filename": run.filename,
        # Denormalised for cheap querying/filtering.
        "vendor": inv.vendor_name if inv else None,
        "amount": inv.amount if inv else None,
        "currency": inv.currency if inv else None,
        "category": inv.category if inv else None,
        "country": inv.country if inv else None,
        # Full structured state.
        "invoice": inv.model_dump(mode="json") if inv else None,
        "extraction": run.extraction,
        "decision": run.decision.model_dump(mode="json") if run.decision else None,
        "council": run.council,
        "approver_id": run.approver_id,
        "decision_note": run.decision_note,
        "resume_url": run.resume_url,
        "user_id": run.user_id,
        "created_at": run.created_at,
        "updated_at": run.updated_at,
    }


def _from_row(row: dict) -> RunRecord:
    return RunRecord(
        workflow_run_id=row["workflow_run_id"],
        status=row.get("status", "received"),
        source=row.get("source", "manual"),
        filename=row.get("filename"),
        invoice=Invoice.model_validate(row["invoice"]) if row.get("invoice") else None,
        extraction=row.get("extraction"),
        decision=PolicyDecision.model_validate(row["decision"]) if row.get("decision") else None,
        council=row.get("council"),
        approver_id=row.get("approver_id"),
        decision_note=row.get("decision_note"),
        resume_url=row.get("resume_url"),
        user_id=row.get("user_id"),
        created_at=row.get("created_at"),
        updated_at=row.get("updated_at"),
    )


def create_run(run: RunRecord) -> RunRecord:
    run.created_at = run.created_at or _now()
    run.updated_at = _now()
    client = get_service_client()
    if client is not None:
        client.table(_TABLE).insert(_to_row(run)).execute()
    return run


def update_run(run: RunRecord) -> RunRecord:
    run.updated_at = _now()
    client = get_service_client()
    if client is not None:
        row = _to_row(run)
        row.pop("created_at", None)  # never overwrite the original timestamp
        client.table(_TABLE).update(row).eq("workflow_run_id", run.workflow_run_id).execute()
    return run


def get_run(workflow_run_id: str) -> Optional[RunRecord]:
    client = get_service_client()
    if client is None:
        return None
    res = client.table(_TABLE).select("*").eq("workflow_run_id", workflow_run_id).limit(1).execute()
    rows = res.data or []
    return _from_row(rows[0]) if rows else None


def list_runs(status: Optional[str], user_id: Optional[str], is_service: bool) -> list[RunRecord]:
    client = get_service_client()
    if client is None:
        return []
    q = client.table(_TABLE).select("*")
    if status:
        q = q.eq("status", status)
    if not is_service and user_id:
        q = q.eq("user_id", user_id)
    res = q.order("created_at", desc=True).limit(200).execute()
    return [_from_row(r) for r in (res.data or [])]


def known_dedupe_keys(exclude: Optional[str] = None) -> set[str]:
    """Build the set of (vendor|number|amount) keys from prior runs for duplicate
    detection. Excludes the current run."""
    client = get_service_client()
    if client is None:
        return set()
    res = client.table(_TABLE).select("workflow_run_id,invoice").execute()
    keys: set[str] = set()
    for r in res.data or []:
        if r.get("workflow_run_id") == exclude or not r.get("invoice"):
            continue
        try:
            keys.add(Invoice.model_validate(r["invoice"]).dedupe_key())
        except Exception:
            continue
    return keys
