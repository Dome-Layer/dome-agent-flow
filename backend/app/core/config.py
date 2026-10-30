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

    # Who may run the pipeline as a person and approve or reject invoices:
    # comma-separated Supabase user ids. Empty means nobody (fail closed).
    # Agent Flow is a private demo (DOME_DECISIONS 2026-09-28): every run makes
    # paid model calls, and anyone can sign up to DOME, so a signed-in user is
    # not enough on its own.
    approver_user_ids: str = ""

    # Email intake (docs/email-intake.md). Comma-separated sender addresses
    # (ap@example.com) and/or domains (example.com or @example.com). Empty means
    # accept nobody (fail closed), like APPROVER_USER_IDS.
    email_intake_allowed_senders: str = ""
    # authserv-ids of the receiving mailbox whose Authentication-Results header is
    # trusted for the DMARC verdict. Empty means none is trusted, so nothing passes.
    email_intake_trusted_authserv_ids: str = ""
    # Require a trusted DMARC pass. May only be false in development.
    email_intake_require_dmarc: bool = True
    email_intake_max_attachment_bytes: int = 10 * 1024 * 1024
    # At most this many runs (paid extractions) per email.
    email_intake_max_attachments: int = 5
    # HMAC key for the stored sender hash. Empty means no hash is stored, domain only.
    email_intake_hash_key: str = ""

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

    @property
    def approver_id_set(self) -> frozenset[str]:
        return frozenset(u.strip() for u in self.approver_user_ids.split(",") if u.strip())

    @property
    def email_allowed_addresses(self) -> frozenset[str]:
        return frozenset(e for e in _csv_lower(self.email_intake_allowed_senders) if "@" in e[1:])

    @property
    def email_allowed_domains(self) -> frozenset[str]:
        return frozenset(
            e.lstrip("@") for e in _csv_lower(self.email_intake_allowed_senders) if "@" not in e[1:]
        )

    @property
    def email_trusted_authserv_ids(self) -> frozenset[str]:
        return frozenset(_csv_lower(self.email_intake_trusted_authserv_ids))

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

    @model_validator(mode="after")
    def validate_dev_bypass_auth(self) -> "Settings":
        # DEV_BYPASS_AUTH authenticates any anonymous request as a placeholder user,
        # opening the /runs endpoints to anyone (and the human approval decision too,
        # if that placeholder id is ever put on APPROVER_USER_IDS). Nothing else enforced "development only": a
        # true value reaching staging or production would defeat the governance
        # gate the showcase is built on.
        if self.dev_bypass_auth and self.environment != "development":
            raise ValueError(
                "DEV_BYPASS_AUTH must not be true outside environment=development "
                f"(got environment={self.environment!r})"
            )
        return self

    @model_validator(mode="after")
    def validate_email_dmarc(self) -> "Settings":
        # Without the DMARC check the allowlist trusts a From header, which anyone can
        # write, so a spoofed email could start paid runs.
        if not self.email_intake_require_dmarc and self.environment != "development":
            raise ValueError(
                "EMAIL_INTAKE_REQUIRE_DMARC must not be false outside environment=development "
                f"(got environment={self.environment!r})"
            )
        return self


def _csv_lower(value: str) -> list[str]:
    return [v.strip().lower() for v in value.split(",") if v.strip()]


settings = Settings()
