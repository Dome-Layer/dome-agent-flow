"""Dual auth: a service key (n8n → shim) OR a Supabase user JWT (approval page → shim).

- `require_principal` — accepts either; used by the n8n-facing run endpoints.
- `require_user`     — demands a signed-in human; used by the approval decision.
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


async def require_user(principal: Principal = Depends(require_principal)) -> Principal:
    """For endpoints that must be owned by a named human (the approval decision)."""
    if principal.is_service or not principal.user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="A signed-in user is required"
        )
    return principal
