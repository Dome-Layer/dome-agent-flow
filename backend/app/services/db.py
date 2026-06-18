"""Supabase service-role client (run state + governance writes).

Uses dome-core's optional-client helper so the app starts cleanly when Supabase is
unconfigured (local dev) and returns None instead of raising.
"""

from __future__ import annotations

from dome_core.db import get_db_optional

from app.core.config import settings


def get_service_client():
    return get_db_optional(
        url=settings.supabase_url,
        service_role_key=settings.supabase_service_role_key,
    )
