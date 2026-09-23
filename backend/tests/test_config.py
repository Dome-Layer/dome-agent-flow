"""Tests for the Settings startup guards (app.core.config)."""

import pytest

from app.core.config import Settings


def _base(**overrides: object) -> dict:
    base = {
        "supabase_url": "https://x.supabase.co",
        "supabase_service_role_key": "key",
        "agent_flow_service_key": "key",
        "doci_base_url": "https://doci.example.com",
        "llc_base_url": "https://llc.example.com",
    }
    base.update(overrides)
    return base


def test_dev_bypass_auth_allowed_in_development() -> None:
    settings = Settings(environment="development", dev_bypass_auth=True)
    assert settings.dev_bypass_auth is True


def test_dev_bypass_auth_rejected_in_staging() -> None:
    with pytest.raises(ValueError, match="DEV_BYPASS_AUTH"):
        Settings(**_base(environment="staging", dev_bypass_auth=True))


def test_dev_bypass_auth_rejected_in_production() -> None:
    with pytest.raises(ValueError, match="DEV_BYPASS_AUTH"):
        Settings(**_base(environment="production", dev_bypass_auth=True))


def test_dev_bypass_auth_false_allowed_in_staging() -> None:
    settings = Settings(**_base(environment="staging", dev_bypass_auth=False))
    assert settings.dev_bypass_auth is False
