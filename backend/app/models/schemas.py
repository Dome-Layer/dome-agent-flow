"""Domain models for the Governed Agent Flow (P5).

The rules engine reasons over an `Invoice` (a P3 extraction normalised onto the
canonical invoice fields) and emits a deterministic `PolicyDecision`.
"""

from __future__ import annotations

from datetime import date
from typing import Optional

from pydantic import BaseModel

# Severity + approver-role orderings (used for escalation comparisons).
SEVERITY_ORDER = {"info": 0, "warning": 1, "error": 2}
ROLE_ORDER = ["auto", "manager", "director", "cfo"]


class Invoice(BaseModel):
    """An invoice normalised from a P3 (Document Intelligence) extraction into the
    canonical fields the policy engine reasons about."""

    invoice_number: Optional[str] = None
    vendor_name: Optional[str] = None
    amount: Optional[float] = None        # invoice total, in `currency`
    currency: Optional[str] = None        # ISO 4217, e.g. "EUR"
    category: Optional[str] = None        # purchase category, e.g. "professional_services"
    country: Optional[str] = None         # vendor country, ISO 3166-1 alpha-2
    vat_id: Optional[str] = None          # vendor VAT / tax id
    po_number: Optional[str] = None       # purchase-order reference, if any
    invoice_date: Optional[date] = None
    due_date: Optional[date] = None
    overall_confidence: float = 1.0       # P3 extraction confidence (0..1)

    def dedupe_key(self) -> str:
        """Stable key for duplicate-invoice detection: vendor + number + amount."""
        vendor = (self.vendor_name or "").strip().lower()
        number = (self.invoice_number or "").strip().lower()
        amount = f"{self.amount:.2f}" if self.amount is not None else ""
        return f"{vendor}|{number}|{amount}"


class RuleFlag(BaseModel):
    rule_id: str
    severity: str            # "info" | "warning" | "error"
    message: str


class PolicyDecision(BaseModel):
    """The deterministic output of the rules engine for one invoice."""

    decision: str                          # auto_approve | route_to_council | require_human | reject
    required_role: Optional[str] = None    # manager | director | cfo (when a human is needed)
    human_in_loop: str                     # not_required | required
    amount_tier_role: str                  # raw amount-tier role (auto|manager|director|cfo)
    flags: list[RuleFlag] = []
    rules_applied: list[str] = []
    rules_triggered: list[str] = []
    reasons: list[str] = []
