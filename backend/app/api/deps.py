"""Dual auth: a service key (n8n → shim) OR a Supabase user JWT (approval page → shim).

- `require_principal`: accepts either; used by the read endpoints, which then scope
  what a non-approver may see.
- `require_operator`: the service key or an approver; used by the pipeline steps,
  since each one makes paid model calls.
- `require_approver`: a signed-in human on `APPROVER_USER_IDS`; used by the decision.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from dome_core.auth import AuthError, make_supabase_fallback, verify_jwt
from fastapi import Depends, Header, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.config import settings
from app.core.logging import get_logger
from app.services.db import get_service_client

logger = get_logger(__name__)
_bearer = HTTPBearer(auto_error=False)
_network_fallback = make_supabase_fallback(lambda: get_service_client())


@dataclass
class Principal:
    user_id: Optional[str]
    is_service: bool


async def require_principal(
    x_service_key: Optional[str] = Header(default=None),
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_bearer),
) -> Principal:
    # Service path (n8n / internal).
    if x_service_key:
        if settings.agent_flow_service_key and x_service_key == settings.agent_flow_service_key:
            return Principal(user_id=None, is_service=True)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid service key")

    # Dev bypass (never set in staging/production).
    if settings.dev_bypass_auth:
        return Principal(user_id="00000000-0000-0000-0000-000000000000", is_service=False)

    # User path (approval page) — verify the Supabase JWT locally (DA-005).
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Authorization required"
        )
    try:
        principal = verify_jwt(
            credentials.credentials,
            supabase_url=settings.supabase_url,
            network_fallback=_network_fallback,
        )
        return Principal(user_id=principal.user_id, is_service=False)
    except AuthError as e:
        logger.warning("auth_error", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication failed"
        )


def is_approver(principal: Principal) -> bool:
    return (
        not principal.is_service
        and principal.user_id is not None
        and principal.user_id in settings.approver_id_set
    )


def can_see_all_runs(principal: Principal) -> bool:
    return principal.is_service or is_approver(principal)


async def require_operator(principal: Principal = Depends(require_principal)) -> Principal:
    """The service key (n8n) or an approver: the only callers allowed to spend on runs."""
    if principal.is_service or is_approver(principal):
        return principal
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN, detail="Agent Flow is limited to approvers"
    )


async def require_approver(principal: Principal = Depends(require_principal)) -> Principal:
    """A named human on the allowlist; owns the approval decision."""
    if principal.is_service or not principal.user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="A signed-in user is required"
        )
    if not is_approver(principal):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Only approvers can decide runs"
        )
    return principal
