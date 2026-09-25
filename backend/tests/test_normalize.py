"""Tests for the P3-extraction → Invoice normaliser (pure, no I/O)."""

from typing import Optional

import pytest

from app.services.normalize import _parse_amount, invoice_from_extraction


def _result() -> dict:
    return {
        "extraction": {
            "overall_confidence": 0.88,
            "reference_keys": {"invoice": "INV-2026-001"},
            "document_profile": {"doc_type": "invoice", "currency": "EUR"},
            "fields": [
                {
                    "name": "Invoice Number",
                    "value": "INV-2026-001",
                    "confidence": 0.95,
                    "data_type": "identifier",
                },
                {"name": "Vendor", "value": "Acme GmbH", "confidence": 0.9, "data_type": "text"},
                {
                    "name": "Total Amount",
                    "value": "€12,500.00",
                    "confidence": 0.92,
                    "data_type": "currency",
                },
                {
                    "name": "Subtotal",
                    "value": "€10,000.00",
                    "confidence": 0.9,
                    "data_type": "currency",
                },
                {
                    "name": "VAT ID",
                    "value": "DE123456789",
                    "confidence": 0.85,
                    "data_type": "identifier",
                },
                {
                    "name": "PO Number",
                    "value": "PO-77",
                    "confidence": 0.8,
                    "data_type": "identifier",
                },
                {
                    "name": "Invoice Date",
                    "value": "2026-05-30",
                    "confidence": 0.9,
                    "data_type": "date",
                },
            ],
        }
    }


def test_maps_core_invoice_fields():
    inv = invoice_from_extraction(_result())
    assert inv.invoice_number == "INV-2026-001"
    assert inv.vendor_name == "Acme GmbH"
    assert inv.amount == 12500.0  # picks the grand total, not the subtotal
    assert inv.currency == "EUR"
    assert inv.vat_id == "DE123456789"
    assert inv.po_number == "PO-77"
    assert inv.country == "DE"  # inferred from the VAT id prefix
    assert inv.overall_confidence == 0.88


def test_amount_parsing_handles_eu_and_us_formats():
    assert _parse_amount("€1.234,56") == 1234.56
    assert _parse_amount("$1,234.56") == 1234.56
    assert _parse_amount("1000") == 1000.0


def test_caller_can_override_category():
    inv = invoice_from_extraction(_result(), category="it_hardware")
    assert inv.category == "it_hardware"


def test_accepts_bare_extraction_block():
    inv = invoice_from_extraction(_result()["extraction"])
    assert inv.invoice_number == "INV-2026-001"
    assert inv.amount == 12500.0


def _with_country(country: Optional[str], vat_id: Optional[str] = None) -> dict:
    fields = []
    if country is not None:
        fields.append({"name": "Vendor Country", "value": country, "data_type": "text"})
    if vat_id is not None:
        fields.append({"name": "VAT ID", "value": vat_id, "data_type": "identifier"})
    return {"extraction": {"fields": fields}}


@pytest.mark.parametrize(
    ("stated", "expected"),
    [
        ("Germany", "DE"),  # used to truncate to GE (Georgia)
        ("Deutschland", "DE"),
        ("Germania", "DE"),
        ("Switzerland", "CH"),  # used to truncate to SW
        ("United Kingdom", "GB"),  # used to truncate to UN
        ("Regno Unito", "GB"),
        ("U.K.", "GB"),
        ("Belarus", "BY"),  # used to truncate to BE (Belgium)
        ("Bielorussia", "BY"),
        ("España", "ES"),
        ("the Netherlands", "NL"),
        ("  france ", "FR"),
        ("DE", "DE"),
        ("de", "DE"),
        ("UK", "GB"),
    ],
)
def test_country_name_or_code_maps_to_iso(stated, expected):
    inv = invoice_from_extraction(_with_country(stated))
    assert inv.country == expected
    assert inv.stated_country == expected


def test_unknown_country_value_is_left_unset():
    inv = invoice_from_extraction(_with_country("Narnia"))
    assert inv.country is None
    assert inv.stated_country is None


def test_unknown_country_value_falls_back_to_vat_prefix():
    inv = invoice_from_extraction(_with_country("Narnia", vat_id="DE123456789"))
    assert inv.country == "DE"
    assert inv.stated_country is None


def test_vat_prefix_wins_when_it_disagrees_and_stated_country_is_kept():
    inv = invoice_from_extraction(_with_country("Italy", vat_id="DE123456789"))
    assert inv.country == "DE"
    assert inv.stated_country == "IT"


@pytest.mark.parametrize(
    ("vat_id", "expected"),
    [
        ("EL123456789", "GR"),  # Greece's VAT prefix is not its ISO code
        ("XI123456789", "GB"),
        ("CHE-123.456.789 MWST", "CH"),
        ("IVA 12345678901", None),  # "IV" is not a country
        ("12345678901", None),
    ],
)
def test_vat_prefix_fallback_only_trusts_known_prefixes(vat_id, expected):
    inv = invoice_from_extraction(_with_country(None, vat_id=vat_id))
    assert inv.country == expected


def test_sanctioned_stated_country_survives_a_foreign_vat_id():
    inv = invoice_from_extraction(_with_country("Belarus", vat_id="DE123456789"))
    assert inv.country == "DE"
    assert inv.stated_country == "BY"  # screened by the high_risk_country rule
