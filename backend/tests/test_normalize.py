"""Tests for the P3-extraction → Invoice normaliser (pure, no I/O)."""

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
