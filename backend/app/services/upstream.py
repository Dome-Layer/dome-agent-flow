"""Proxies to the upstream tools P3 (Document Intelligence) and P2 (LLM Council).

Both calls present `X-Service-Key` (service-to-service auth) and `X-Workflow-Run-Id`
so P3/P2 stamp their native governance events with the shared run id — giving P6 a
true cross-tool timeline. n8n never calls P3/P2 directly; only this shim does.
"""

from __future__ import annotations

from typing import Optional

import httpx

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)


def _service_headers(workflow_run_id: Optional[str]) -> dict[str, str]:
    headers = {"X-Service-Key": settings.agent_flow_service_key}
    if workflow_run_id:
        headers["X-Workflow-Run-Id"] = workflow_run_id
    return headers


async def extract_invoice(
    file_bytes: bytes,
    filename: str,
    content_type: Optional[str],
    workflow_run_id: str,
) -> dict:
    """POST the invoice file to P3 /api/extract (multipart)."""
    url = settings.doci_base_url.rstrip("/") + "/api/extract"
    files = {"file": (filename, file_bytes, content_type or "application/octet-stream")}
    async with httpx.AsyncClient(timeout=120.0) as client:
        resp = await client.post(url, files=files, headers=_service_headers(workflow_run_id))
        resp.raise_for_status()
        return resp.json()


async def council_deliberate(
    question: str,
    context: Optional[str],
    workflow_run_id: str,
) -> dict:
    """POST to P2 /deliberate/sync (the non-streaming verdict endpoint)."""
    url = settings.llc_base_url.rstrip("/") + "/deliberate/sync"
    body = {"question": question, "context": context}
    async with httpx.AsyncClient(timeout=180.0) as client:
        resp = await client.post(url, json=body, headers=_service_headers(workflow_run_id))
        resp.raise_for_status()
        return resp.json()


async def resume_n8n(resume_url: Optional[str], payload: dict) -> None:
    """Continue a paused n8n Wait node after a human decision. Best-effort."""
    if not resume_url:
        return
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            await client.post(resume_url, json=payload)
    except Exception as e:
        logger.warning("n8n_resume_failed", error=str(e), resume_url=resume_url)
