"""The invoice-approval rules engine.

Deterministic, pure (no I/O, no hidden clock), and unit-tested. Each rule inspects
an `Invoice` against the loaded `Policy` and returns zero or more `RuleFlag`s. The
engine then applies an explicit decision precedence to produce a `PolicyDecision`:

    reject  >  (four-eyes override)  >  auto_approve  >  route_to_council  >  require_human

The output's `rules_applied` / `rules_triggered` / `decision` are written verbatim
into a `rules_evaluated` governance event, so the policy decision is auditable in P6.

Pattern intentionally mirrors dome-document-intelligence's `validation.py`
(rule_id + severity + pure function), extended with invoice-policy dimensions
(amount tier, category, country, vendor, PO, VAT, currency, duplicate, date).
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Callable, Optional

from app.models.schemas import ROLE_ORDER, Invoice, PolicyDecision, RuleFlag
from app.services.policy import Policy, load_policy


def _escalate(role: str, floor: str) -> str:
    """Return the higher of two approver roles per ROLE_ORDER."""
    return role if ROLE_ORDER.index(role) >= ROLE_ORDER.index(floor) else floor


# ── Individual rules ──────────────────────────────────────────────────────────
# Signature: (invoice, policy, ctx) -> list[RuleFlag]. ctx = {"known_keys", "today"}.


def _missing_invoice_number(inv: Invoice, policy: Policy, ctx: dict) -> list[RuleFlag]:
    if not inv.invoice_number:
        return [RuleFlag(rule_id="missing_invoice_number", severity="error",
                         message="No invoice number — cannot de-duplicate or reconcile.")]
    return []


def _missing_vendor(inv: Invoice, policy: Policy, ctx: dict) -> list[RuleFlag]:
    if not inv.vendor_name:
        return [RuleFlag(rule_id="missing_vendor", severity="error",
                         message="No vendor identified on the invoice.")]
    return []


def _missing_amount(inv: Invoice, policy: Policy, ctx: dict) -> list[RuleFlag]:
    if inv.amount is None or inv.amount <= 0:
        return [RuleFlag(rule_id="missing_amount", severity="error",
                         message="Invoice amount is missing or non-positive.")]
    return []


def _high_risk_country(inv: Invoice, policy: Policy, ctx: dict) -> list[RuleFlag]:
    if inv.country and inv.country.upper() in {c.upper() for c in policy.high_risk_countries}:
        return [RuleFlag(rule_id="high_risk_country", severity="error",
                         message=f"Vendor country {inv.country} is on the high-risk / sanctioned list.")]
    return []


def _duplicate_invoice(inv: Invoice, policy: Policy, ctx: dict) -> list[RuleFlag]:
    if inv.invoice_number and inv.dedupe_key() in ctx.get("known_keys", set()):
        return [RuleFlag(rule_id="duplicate_invoice", severity="error",
                         message="An invoice with the same vendor, number and amount was already processed.")]
    return []


def _new_vendor(inv: Invoice, policy: Policy, ctx: dict) -> list[RuleFlag]:
    if policy.is_new_vendor(inv.vendor_name):
        return [RuleFlag(rule_id="new_vendor", severity="warning",
                         message="Vendor is not on the allowlist — KYC / first-payment review required.")]
    return []


def _category_over_auto_ceiling(inv: Invoice, policy: Policy, ctx: dict) -> list[RuleFlag]:
    if inv.amount is not None and inv.amount > policy.category_auto_ceiling(inv.category):
        return [RuleFlag(rule_id="category_over_auto_ceiling", severity="warning",
                         message=f"Amount {inv.amount:.2f} exceeds the auto-approval ceiling for "
                                 f"category '{inv.category or 'default'}'.")]
    return []


def _missing_po(inv: Invoice, policy: Policy, ctx: dict) -> list[RuleFlag]:
    cat = policy.categories.get(inv.category) if inv.category else None
    if cat and cat.require_po and not inv.po_number:
        return [RuleFlag(rule_id="missing_po", severity="warning",
                         message=f"Category '{inv.category}' requires a purchase order, but none was found.")]
    return []


def _currency_not_allowed(inv: Invoice, policy: Policy, ctx: dict) -> list[RuleFlag]:
    if inv.country and inv.currency:
        allowed = policy.allowed_currencies.get(inv.country.upper())
        if allowed and inv.currency.upper() not in {c.upper() for c in allowed}:
            return [RuleFlag(rule_id="currency_not_allowed", severity="warning",
                             message=f"Currency {inv.currency} is unexpected for vendor country "
                                     f"{inv.country} (allowed: {', '.join(allowed)}).")]
    return []


def _vat_id_invalid(inv: Invoice, policy: Policy, ctx: dict) -> list[RuleFlag]:
    import re

    if inv.country and inv.country.upper() in policy.vat_formats:
        pattern = policy.vat_formats[inv.country.upper()]
        candidate = (inv.vat_id or "").replace(" ", "").upper()
        if not candidate or not re.match(pattern, candidate):
            return [RuleFlag(rule_id="vat_id_invalid", severity="warning",
                             message=f"VAT id '{inv.vat_id or '—'}' is missing or invalid for "
                                     f"country {inv.country}.")]
    return []


def _cross_border(inv: Invoice, policy: Policy, ctx: dict) -> list[RuleFlag]:
    if inv.country and inv.country.upper() != policy.home_country.upper():
        return [RuleFlag(rule_id="cross_border", severity="info",
                         message=f"Cross-border invoice (vendor in {inv.country}, "
                                 f"entity in {policy.home_country}).")]
    return []


def _future_invoice_date(inv: Invoice, policy: Policy, ctx: dict) -> list[RuleFlag]:
    if inv.invoice_date and inv.invoice_date > ctx["today"] + timedelta(days=policy.max_future_days):
        return [RuleFlag(rule_id="future_invoice_date", severity="warning",
                         message=f"Invoice date {inv.invoice_date} is more than "
                                 f"{policy.max_future_days} days in the future.")]
    return []


def _stale_invoice_date(inv: Invoice, policy: Policy, ctx: dict) -> list[RuleFlag]:
    cutoff = ctx["today"] - timedelta(days=365 * policy.max_age_years)
    if inv.invoice_date and inv.invoice_date < cutoff:
        return [RuleFlag(rule_id="stale_invoice_date", severity="info",
                         message=f"Invoice date {inv.invoice_date} is older than "
                                 f"{policy.max_age_years} years.")]
    return []


def _low_confidence(inv: Invoice, policy: Policy, ctx: dict) -> list[RuleFlag]:
    if inv.overall_confidence < policy.low_confidence_threshold:
        return [RuleFlag(rule_id="low_extraction_confidence", severity="warning",
                         message=f"Extraction confidence {inv.overall_confidence:.0%} is below the "
                                 f"{policy.low_confidence_threshold:.0%} threshold.")]
    return []


# Order is the audit order; it does not affect the decision (precedence is explicit below).
RULES: list[tuple[str, Callable[[Invoice, Policy, dict], list[RuleFlag]]]] = [
    ("missing_invoice_number", _missing_invoice_number),
    ("missing_vendor", _missing_vendor),
    ("missing_amount", _missing_amount),
    ("high_risk_country", _high_risk_country),
    ("duplicate_invoice", _duplicate_invoice),
    ("new_vendor", _new_vendor),
    ("category_over_auto_ceiling", _category_over_auto_ceiling),
    ("missing_po", _missing_po),
    ("currency_not_allowed", _currency_not_allowed),
    ("vat_id_invalid", _vat_id_invalid),
    ("cross_border", _cross_border),
    ("future_invoice_date", _future_invoice_date),
    ("stale_invoice_date", _stale_invoice_date),
    ("low_extraction_confidence", _low_confidence),
]


def evaluate(
    invoice: Invoice,
    policy: Optional[Policy] = None,
    *,
    known_keys: Optional[set[str]] = None,
    today: Optional[date] = None,
    require_human_on_all: Optional[bool] = None,
) -> PolicyDecision:
    """Run every rule, then apply the decision precedence."""
    policy = policy or load_policy()
    ctx = {"known_keys": known_keys or set(), "today": today or date.today()}

    flags: list[RuleFlag] = []
    for _id, fn in RULES:
        flags.extend(fn(invoice, policy, ctx))

    rules_applied = [rid for rid, _ in RULES]
    triggered = {f.rule_id for f in flags}
    rules_triggered = [rid for rid in rules_applied if rid in triggered]
    reasons = [f.message for f in flags]

    tier_role = policy.role_for_amount(invoice.amount)
    force_human = policy.require_human_on_all if require_human_on_all is None else require_human_on_all

    def _decide(decision: str, role: Optional[str], hil: str) -> PolicyDecision:
        return PolicyDecision(
            decision=decision, required_role=role, human_in_loop=hil,
            amount_tier_role=tier_role, flags=flags, rules_applied=rules_applied,
            rules_triggered=rules_triggered, reasons=reasons,
        )

    # 1. Hard reject — sanctioned / high-risk country.
    if "high_risk_country" in triggered:
        return _decide("reject", None, "required")

    # 2. Four-eyes override — nothing auto-approves.
    if force_human:
        return _decide("require_human", _escalate(tier_role, "manager"), "required")

    council = (
        (policy.council.cross_border and "cross_border" in triggered)
        or (policy.is_new_vendor(invoice.vendor_name)
            and invoice.amount is not None
            and invoice.amount > policy.council.new_vendor_over)
        or (invoice.overall_confidence < policy.council.low_confidence_below)
    )

    # Any warning/error, or an amount above the auto tier, blocks auto-approval.
    blockers = any(f.severity in ("warning", "error") for f in flags) or tier_role != "auto"

    # 3. Auto-approve — clean, low-value, no council trigger.
    if not blockers and not council:
        return _decide("auto_approve", None, "not_required")

    # 4. Route to the LLM Council first (it precedes the human decision).
    if council:
        return _decide("route_to_council", _escalate(tier_role, "manager"), "required")

    # 5. Otherwise a named human owns the decision.
    return _decide("require_human", _escalate(tier_role, "manager"), "required")
