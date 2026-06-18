"""Emit append-only governance events for the agent-flow steps.

Mirrors the house pattern (dome-document-intelligence `services/governance.py`):
build a `dome_core.governance.GovernanceEvent`, insert into `governance_events` via
the Supabase service-role client, and never let a DB failure break the flow (DA-003).

P3 and P2 emit their OWN native events (`extraction` / `deliberation`) stamped with
the same `workflow_run_id`, so the shim only emits the agent-flow-specific steps.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from dome_core.governance import GovernanceEvent

from app.core.logging import get_logger
from app.services.db import get_service_client

logger = get_logger(__name__)

AGENT_ID = "agent-flow"  # DA-013 frozen canonical id

# Columns that exist on governance_events; extra keys are dropped before insert.
_COLUMNS = {
    "agent_id", "action_type", "timestamp", "input_hash", "input_type",
    "output_summary", "rules_applied", "rules_triggered", "confidence",
    "human_in_loop", "user_id", "workflow_run_id", "metadata",
}


def emit_event(
    *,
    action_type: str,
    workflow_run_id: str,
    input_hash: str,
    input_type: str,
    output_summary: str,
    rules_applied: Optional[list[str]] = None,
    rules_triggered: Optional[list[str]] = None,
    confidence: Optional[float] = None,
    human_in_loop: str = "not_required",
    user_id: Optional[str] = None,
    metadata: Optional[dict] = None,
) -> GovernanceEvent:
    event = GovernanceEvent(
        agent_id=AGENT_ID,
        action_type=action_type,
        timestamp=datetime.now(timezone.utc),
        input_hash=input_hash,
        input_type=input_type,
        output_summary=output_summary[:200],
        rules_applied=rules_applied or [],
        rules_triggered=rules_triggered or [],
        confidence=confidence,
        human_in_loop=human_in_loop,
        user_id=user_id,
        workflow_run_id=workflow_run_id,
        metadata=metadata or {},
    )
    try:
        client = get_service_client()
        if client is not None:
            payload = {
                "agent_id": event.agent_id,
                "action_type": event.action_type,
                "timestamp": event.timestamp.isoformat(),
                "input_hash": event.input_hash,
                "input_type": event.input_type,
                "output_summary": event.output_summary,
                "rules_applied": event.rules_applied,
                "rules_triggered": event.rules_triggered,
                "confidence": event.confidence,
                "human_in_loop": event.human_in_loop,
                "user_id": event.user_id,
                "workflow_run_id": event.workflow_run_id,
                "metadata": event.metadata,
            }
            client.table("governance_events").insert(
                {k: v for k, v in payload.items() if k in _COLUMNS}
            ).execute()
            logger.info("governance_event", action_type=action_type, workflow_run_id=workflow_run_id)
    except Exception as e:  # never break the flow on an audit-write failure
        logger.error("governance_event_failed", error=str(e), action_type=action_type)
    return event
