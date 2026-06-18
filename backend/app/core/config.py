from typing import Literal

from pydantic import model_validator
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # App
    environment: Literal["development", "staging", "production"] = "development"
    cors_origins: str = "http://localhost:3000"
    dev_bypass_auth: bool = False
    require_human_on_all: bool = False

    # Service-to-service auth (n8n → shim, shim → P3/P2)
    agent_flow_service_key: str = ""

    # Upstream tools the shim proxies
    doci_base_url: str = ""
    llc_base_url: str = ""

    # n8n resume webhook base (to continue a paused Wait node after approval)
    n8n_resume_base_url: str = ""

    # Supabase (run state + governance events)
    supabase_url: str = ""
    supabase_service_role_key: str = ""

    # Observability
    sentry_dsn: str = ""

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "case_sensitive": False,
    }

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @model_validator(mode="after")
    def validate_required_secrets(self) -> "Settings":
        if self.environment in ("staging", "production"):
            missing = [
                name
                for name, val in [
                    ("SUPABASE_URL", self.supabase_url),
                    ("SUPABASE_SERVICE_ROLE_KEY", self.supabase_service_role_key),
                    ("AGENT_FLOW_SERVICE_KEY", self.agent_flow_service_key),
                    ("DOCI_BASE_URL", self.doci_base_url),
                    ("LLC_BASE_URL", self.llc_base_url),
                ]
                if not val
            ]
            if missing:
                raise ValueError(
                    f"Missing required {self.environment} environment variables: "
                    f"{', '.join(missing)}"
                )
        return self


settings = Settings()
