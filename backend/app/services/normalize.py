"""Normalise a P3 (Document Intelligence) extraction into a canonical `Invoice`.

P3 returns generic `name`/`value`/`data_type` fields; the rules engine reasons over
named invoice slots. This mapper is heuristic (field-name matching + light parsing)
and pure, so it is unit-tested without any I/O.
"""

from __future__ import annotations

import re
from datetime import date, datetime
from typing import Any, Optional

from app.models.schemas import Invoice

# Field-name hints (matched against a lowercased, separator-normalised field name).
_NUMBER_HINTS = ("invoice number", "invoice no", "invoice #", "invoice id", "invoice num")
_VENDOR_HINTS = ("vendor", "supplier", "seller", "biller", "from", "company", "issued by")
_AMOUNT_HINTS = ("total", "amount due", "grand total", "balance due", "amount", "total due")
_VAT_HINTS = ("vat", "tax id", "tax number", "partita iva", "p.iva", "piva", "ust-id", "tax_id")
_PO_HINTS = ("po number", "purchase order", "po no", "p.o.", "po #", "order number")
_CATEGORY_HINTS = ("category", "expense type", "cost center", "gl code", "account")
_COUNTRY_HINTS = ("country",)
_INVOICE_DATE_HINTS = ("invoice date", "issue date", "date of issue", "document date")
_DUE_DATE_HINTS = ("due date", "payment due", "payment date", "due")

_VAT_COUNTRY_RE = re.compile(r"^([A-Z]{2})")


def _norm(name: str) -> str:
    return re.sub(r"[_\-]+", " ", (name or "").strip().lower())


def _matches(name: str, hints: tuple[str, ...]) -> bool:
    n = _norm(name)
    return any(h in n for h in hints)


def _parse_amount(value: str) -> Optional[float]:
    if value is None:
        return None
    # Strip currency symbols/letters/spaces; handle both 1,234.56 and 1.234,56.
    raw = re.sub(r"[^\d.,-]", "", str(value)).strip()
    if not raw:
        return None
    if "," in raw and "." in raw:
        # The rightmost separator is the decimal separator.
        if raw.rfind(",") > raw.rfind("."):
            raw = raw.replace(".", "").replace(",", ".")
        else:
            raw = raw.replace(",", "")
    elif "," in raw:
        # Comma as decimal if it looks like one (two trailing digits), else thousands.
        raw = raw.replace(",", ".") if re.search(r",\d{2}$", raw) else raw.replace(",", "")
    try:
        return float(raw)
    except ValueError:
        return None


def _parse_date(value: str) -> Optional[date]:
    if not value:
        return None
    value = str(value).strip()
    for fmt in (
        "%Y-%m-%d",
        "%d/%m/%Y",
        "%m/%d/%Y",
        "%d-%m-%Y",
        "%d.%m.%Y",
        "%d %B %Y",
        "%B %d, %Y",
    ):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            continue
    return None


def invoice_from_extraction(result: dict[str, Any], *, category: Optional[str] = None) -> Invoice:
    """Map a P3 result (full DocumentIntelligenceResult or its `extraction` block)
    onto an `Invoice`. `category` may be supplied by the caller (e.g. n8n) when the
    document itself doesn't carry one."""
    extraction = result.get("extraction", result) if isinstance(result, dict) else {}
    fields: list[dict] = extraction.get("fields", []) or []
    profile: dict = extraction.get("document_profile", {}) or {}
    reference_keys: dict = extraction.get("reference_keys", {}) or {}

    inv = Invoice(
        overall_confidence=float(extraction.get("overall_confidence", 1.0) or 1.0),
        currency=profile.get("currency"),
        category=category,
    )

    # Currency fields: prefer one whose name looks like a total, else the largest.
    currency_candidates: list[tuple[str, float]] = []

    for f in fields:
        name = f.get("name", "")
        value = f.get("value")
        dtype = f.get("data_type", "text")
        if value in (None, ""):
            continue

        if inv.invoice_number is None and _matches(name, _NUMBER_HINTS):
            inv.invoice_number = str(value)
        if inv.vendor_name is None and _matches(name, _VENDOR_HINTS):
            inv.vendor_name = str(value)
        if inv.vat_id is None and _matches(name, _VAT_HINTS):
            inv.vat_id = str(value)
        if inv.po_number is None and _matches(name, _PO_HINTS):
            inv.po_number = str(value)
        if category is None and inv.category is None and _matches(name, _CATEGORY_HINTS):
            inv.category = _norm(str(value)).replace(" ", "_")
        if inv.country is None and _matches(name, _COUNTRY_HINTS):
            inv.country = str(value).strip().upper()[:2]
        if inv.invoice_date is None and _matches(name, _INVOICE_DATE_HINTS):
            inv.invoice_date = _parse_date(value)
        if inv.due_date is None and _matches(name, _DUE_DATE_HINTS):
            inv.due_date = _parse_date(value)

        if dtype == "currency":
            amount = _parse_amount(value)
            if amount is not None:
                currency_candidates.append((name, amount))

    # Choose the invoice amount.
    if currency_candidates:
        totals = [(n, a) for n, a in currency_candidates if _matches(n, _AMOUNT_HINTS)]
        inv.amount = (
            max(totals, key=lambda t: t[1])[1]
            if totals
            else max(currency_candidates, key=lambda t: t[1])[1]
        )

    # Fall back to reference_keys for an invoice / PO number.
    if inv.invoice_number is None:
        for k, v in reference_keys.items():
            if _matches(k, _NUMBER_HINTS) or _norm(k) in ("invoice", "invoice id"):
                inv.invoice_number = str(v)
                break
    if inv.po_number is None:
        for k, v in reference_keys.items():
            if _matches(k, _PO_HINTS):
                inv.po_number = str(v)
                break

    # Infer vendor country from the VAT id prefix if not stated explicitly.
    if inv.country is None and inv.vat_id:
        m = _VAT_COUNTRY_RE.match(inv.vat_id.replace(" ", "").upper())
        if m:
            inv.country = m.group(1)

    return inv
