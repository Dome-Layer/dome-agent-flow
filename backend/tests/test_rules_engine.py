"""Deterministic tests for the invoice-approval rules engine.

Mirrors dome-document-intelligence's rule-test discipline: one assertion per
policy path, fixed clock, committed policy.yaml. No I/O, no LLM, CI-safe.
"""

from datetime import date

import pytest

from app.models.schemas import Invoice
from app.services.policy import load_policy
from app.services.rules import evaluate

TODAY = date(2026, 6, 17)


@pytest.fixture(scope="module")
def policy():
    return load_policy()


def _inv(**overrides) -> Invoice:
    """A clean, auto-approvable baseline: small, domestic, known vendor."""
    base = dict(
        invoice_number="INV-1001",
        vendor_name="Initech Srl",  # on the allowlist
        amount=500.0,
        currency="EUR",
        category="office_supplies",
        country="IT",  # == home_country
        vat_id="IT12345678901",
        po_number="PO-1",
        invoice_date=date(2026, 6, 1),
        overall_confidence=0.95,
    )
    base.update(overrides)
    return Invoice(**base)


def test_clean_small_domestic_auto_approves(policy):
    d = evaluate(_inv(), policy, today=TODAY)
    assert d.decision == "auto_approve"
    assert d.human_in_loop == "not_required"
    assert d.rules_triggered == []


def test_amount_tier_boundary_is_inclusive(policy):
    assert evaluate(_inv(amount=1000.0), policy, today=TODAY).amount_tier_role == "auto"
    assert evaluate(_inv(amount=1000.01), policy, today=TODAY).amount_tier_role == "manager"


def test_manager_tier_requires_human(policy):
    d = evaluate(_inv(amount=5000.0, category="professional_services"), policy, today=TODAY)
    assert d.decision == "require_human"
    assert d.required_role == "manager"


def test_director_tier_requires_human(policy):
    d = evaluate(_inv(amount=15000.0, category="professional_services"), policy, today=TODAY)
    assert d.decision == "require_human"
    assert d.required_role == "director"


def test_high_risk_country_rejected(policy):
    d = evaluate(_inv(country="RU"), policy, today=TODAY)
    assert d.decision == "reject"
    assert "high_risk_country" in d.rules_triggered


def test_cross_border_routes_to_council(policy):
    # Acme GmbH is allowlisted; DE vendor with valid DE VAT — only cross_border fires.
    d = evaluate(
        _inv(vendor_name="Acme GmbH", country="DE", vat_id="DE123456789"), policy, today=TODAY
    )
    assert d.decision == "route_to_council"
    assert "cross_border" in d.rules_triggered


def test_new_vendor_blocks_auto_and_requires_human(policy):
    d = evaluate(_inv(vendor_name="Brand New Vendor Srl"), policy, today=TODAY)
    assert d.decision == "require_human"
    assert d.required_role == "manager"
    assert "new_vendor" in d.rules_triggered


def test_new_vendor_large_routes_to_council(policy):
    d = evaluate(
        _inv(vendor_name="Brand New Vendor Srl", amount=20000.0, category="professional_services"),
        policy,
        today=TODAY,
    )
    assert d.decision == "route_to_council"


def test_low_confidence_routes_to_council(policy):
    d = evaluate(_inv(overall_confidence=0.40), policy, today=TODAY)
    assert d.decision == "route_to_council"
    assert "low_extraction_confidence" in d.rules_triggered


def test_duplicate_invoice_blocks(policy):
    inv = _inv()
    d = evaluate(inv, policy, today=TODAY, known_keys={inv.dedupe_key()})
    assert "duplicate_invoice" in d.rules_triggered
    assert d.decision == "require_human"


def test_missing_critical_fields_require_human(policy):
    d = evaluate(_inv(invoice_number=None, amount=None), policy, today=TODAY)
    assert d.decision == "require_human"
    assert "missing_invoice_number" in d.rules_triggered
    assert "missing_amount" in d.rules_triggered


def test_capex_is_never_auto_approved(policy):
    d = evaluate(_inv(amount=100.0, category="capex", po_number=None), policy, today=TODAY)
    assert d.decision == "require_human"
    assert "category_over_auto_ceiling" in d.rules_triggered
    assert "missing_po" in d.rules_triggered


def test_it_hardware_missing_po(policy):
    d = evaluate(_inv(category="it_hardware", po_number=None, amount=200.0), policy, today=TODAY)
    assert "missing_po" in d.rules_triggered
    assert d.decision == "require_human"


def test_invalid_vat_blocks_auto(policy):
    d = evaluate(_inv(vat_id="NOT-A-VAT"), policy, today=TODAY)
    assert "vat_id_invalid" in d.rules_triggered
    assert d.decision == "require_human"


def test_currency_mismatch_blocks_auto(policy):
    d = evaluate(_inv(currency="USD"), policy, today=TODAY)
    assert "currency_not_allowed" in d.rules_triggered
    assert d.decision == "require_human"


def test_require_human_on_all_override(policy):
    d = evaluate(_inv(), policy, today=TODAY, require_human_on_all=True)
    assert d.decision == "require_human"
    assert d.required_role == "manager"


def test_future_dated_invoice_flagged(policy):
    d = evaluate(_inv(invoice_date=date(2026, 7, 31)), policy, today=TODAY)
    assert "future_invoice_date" in d.rules_triggered
    assert d.decision == "require_human"
