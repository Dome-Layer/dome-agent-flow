"""Loads and models the invoice-approval policy.

The committed `policy.yaml` is the default; a per-tenant override row from the
Supabase `approval_policies` table can be merged on top at runtime (see
`Policy.merged_with`). The policy is pure data — the engine in `rules.py` reads it.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import yaml
from pydantic import BaseModel

# policy.yaml lives at the backend root: app/services/policy.py -> parents[2].
_DEFAULT_POLICY_PATH = Path(__file__).resolve().parents[2] / "policy.yaml"


class AmountTier(BaseModel):
    max: Optional[float] = None  # null = unbounded ceiling
    role: str


class CategoryPolicy(BaseModel):
    auto_ceiling: float = 0.0
    require_po: bool = False


class CouncilPolicy(BaseModel):
    cross_border: bool = True
    new_vendor_over: float = 10000.0
    low_confidence_below: float = 0.60


class Policy(BaseModel):
    version: int = 1
    home_country: str = "IT"
    base_currency: str = "EUR"
    low_confidence_threshold: float = 0.60
    max_future_days: int = 5
    max_age_years: int = 2
    amount_tiers: list[AmountTier] = []
    categories: dict[str, CategoryPolicy] = {}
    allowed_currencies: dict[str, list[str]] = {}
    high_risk_countries: list[str] = []
    vat_formats: dict[str, str] = {}
    vendor_allowlist: list[str] = []
    council: CouncilPolicy = CouncilPolicy()
    require_human_on_all: bool = False

    # ── Derived helpers the engine relies on ─────────────────────────────────

    def global_auto_ceiling(self) -> float:
        for tier in self.amount_tiers:
            if tier.role == "auto":
                return tier.max if tier.max is not None else float("inf")
        return 0.0

    def role_for_amount(self, amount: Optional[float]) -> str:
        if amount is None:
            return "cfo"  # unknown amount → maximum scrutiny
        for tier in self.amount_tiers:
            if tier.max is None or amount <= tier.max:
                return tier.role
        return "cfo"

    def category_auto_ceiling(self, category: Optional[str]) -> float:
        """Effective auto-approve ceiling for a category — categories only tighten
        the global ceiling, never raise it."""
        global_ceiling = self.global_auto_ceiling()
        if category and category in self.categories:
            return min(global_ceiling, self.categories[category].auto_ceiling)
        return global_ceiling

    def is_new_vendor(self, vendor_name: Optional[str]) -> bool:
        if not vendor_name:
            return True
        allow = {v.strip().lower() for v in self.vendor_allowlist}
        return vendor_name.strip().lower() not in allow

    def merged_with(self, override: Optional[dict]) -> "Policy":
        """Return a copy with a per-tenant override dict shallow-merged on top."""
        if not override:
            return self
        data = self.model_dump()
        data.update({k: v for k, v in override.items() if v is not None})
        return Policy.model_validate(data)


def load_policy(path: Optional[Path] = None) -> Policy:
    source = Path(path) if path else _DEFAULT_POLICY_PATH
    data = yaml.safe_load(source.read_text()) or {}
    return Policy.model_validate(data)
