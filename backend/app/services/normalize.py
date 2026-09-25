"""Normalise a P3 (Document Intelligence) extraction into a canonical `Invoice`.

P3 returns generic `name`/`value`/`data_type` fields; the rules engine reasons over
named invoice slots. This mapper is heuristic (field-name matching + light parsing)
and pure, so it is unit-tested without any I/O.
"""

from __future__ import annotations

import re
import unicodedata
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

# VAT-number prefixes that identify a country. EU prefixes are ISO codes except
# Greece (EL) and Northern Ireland (XI); GB, CH and NO use their own schemes.
# A prefix outside this set (e.g. the "IV" of "IVA 123...") says nothing.
_VAT_PREFIX_COUNTRY: dict[str, str] = {
    **{
        code: code
        for code in (
            "AT BE BG CY CZ DE DK EE ES FI FR HR HU IE IT LT LU LV MT NL PL PT RO SE SI SK GB CH NO"
        ).split()
    },
    "EL": "GR",
    "XI": "GB",
}

# Two-letter values that are common on invoices but are not ISO 3166-1 codes.
_COUNTRY_CODE_ALIASES = {"UK": "GB", "EL": "GR"}

# Full country names (English, Italian and a few native forms) for the countries
# the default policy names plus the EU and nearby trading partners. Keys are folded
# by `_fold_country` (lowercase, no accents, punctuation collapsed).
_COUNTRY_NAMES_BY_CODE: dict[str, tuple[str, ...]] = {
    # policy.yaml home / allowed-currency countries
    "IT": ("italy", "italia", "italian republic", "repubblica italiana"),
    "DE": ("germany", "germania", "deutschland", "federal republic of germany"),
    "FR": ("france", "francia", "french republic"),
    "ES": ("spain", "spagna", "espana", "kingdom of spain"),
    "GB": (
        "united kingdom",
        "united kingdom of great britain and northern ireland",
        "great britain",
        "britain",
        "england",
        "scotland",
        "wales",
        "northern ireland",
        "uk",
        "regno unito",
        "gran bretagna",
        "inghilterra",
    ),
    "US": (
        "united states",
        "united states of america",
        "usa",
        "us",
        "america",
        "stati uniti",
        "stati uniti d america",
    ),
    "CH": ("switzerland", "svizzera", "schweiz", "suisse", "swiss confederation"),
    # policy.yaml high-risk / sanctioned countries
    "IR": ("iran", "islamic republic of iran", "repubblica islamica dell iran"),
    "KP": (
        "north korea",
        "democratic people s republic of korea",
        "dprk",
        "corea del nord",
        "repubblica popolare democratica di corea",
    ),
    "SY": ("syria", "syrian arab republic", "siria", "repubblica araba siriana"),
    "RU": ("russia", "russian federation", "federazione russa"),
    "BY": ("belarus", "republic of belarus", "bielorussia", "byelorussia"),
    # rest of the EU, EEA and nearby
    "AT": ("austria", "osterreich"),
    "BE": ("belgium", "belgio", "belgique", "belgie"),
    "BG": ("bulgaria",),
    "HR": ("croatia", "croazia", "hrvatska"),
    "CY": ("cyprus", "cipro"),
    "CZ": ("czech republic", "czechia", "repubblica ceca", "cechia"),
    "DK": ("denmark", "danimarca", "danmark"),
    "EE": ("estonia",),
    "FI": ("finland", "finlandia", "suomi"),
    "GR": ("greece", "grecia", "hellas"),
    "HU": ("hungary", "ungheria", "magyarorszag"),
    "IE": ("ireland", "irlanda", "republic of ireland", "eire"),
    "LV": ("latvia", "lettonia"),
    "LT": ("lithuania", "lituania"),
    "LU": ("luxembourg", "lussemburgo"),
    "MT": ("malta",),
    "NL": ("netherlands", "paesi bassi", "olanda", "holland", "nederland"),
    "PL": ("poland", "polonia", "polska"),
    "PT": ("portugal", "portogallo"),
    "RO": ("romania",),
    "SK": ("slovakia", "slovacchia", "slovak republic"),
    "SI": ("slovenia",),
    "SE": ("sweden", "svezia", "sverige"),
    "NO": ("norway", "norvegia", "norge"),
    "SM": ("san marino",),
    "VA": ("vatican", "vatican city", "holy see", "citta del vaticano", "vaticano"),
    "LI": ("liechtenstein",),
    "MC": ("monaco",),
}
_COUNTRY_NAMES: dict[str, str] = {
    name: code for code, names in _COUNTRY_NAMES_BY_CODE.items() for name in names
}


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


def _fold_country(value: str) -> str:
    """Lowercase, strip accents, drop dots ("U.K." -> "uk") and collapse any other
    punctuation to single spaces, so "España" and "Stati Uniti d'America" match."""
    ascii_only = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode()
    s = ascii_only.lower().replace(".", "")
    s = re.sub(r"[^a-z]+", " ", s).strip()
    return s.removeprefix("the ")


def _parse_country(value: Any) -> Optional[str]:
    """ISO 3166-1 alpha-2 code for an extracted country value, or None.

    Accepts a two-letter code as-is (plus the UK/EL aliases) or a known full name.
    Anything else returns None rather than guessing: truncating "Germany" to "GE"
    (Georgia) or "Belarus" to "BE" (Belgium) is worse than no country, because an
    unset country lets the VAT-prefix fallback run."""
    raw = str(value).strip()
    if re.fullmatch(r"[A-Za-z]{2}", raw):
        code = raw.upper()
        return _COUNTRY_CODE_ALIASES.get(code, code)
    return _COUNTRY_NAMES.get(_fold_country(raw))


def _country_from_vat(vat_id: Optional[str]) -> Optional[str]:
    """Country implied by a VAT id prefix, or None if the prefix is not a known one."""
    if not vat_id:
        return None
    m = _VAT_COUNTRY_RE.match(re.sub(r"[\s.\-]", "", vat_id).upper())
    return _VAT_PREFIX_COUNTRY.get(m.group(1)) if m else None


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
        if inv.stated_country is None and _matches(name, _COUNTRY_HINTS):
            inv.stated_country = _parse_country(value)
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

    # Resolve the vendor country. A recognised VAT prefix wins over the stated
    # country: it is a structured identifier, while a "country" field may belong to
    # the buyer's address. The stated value stays on `stated_country` so the
    # high-risk screen still sees it when the two disagree.
    inv.country = _country_from_vat(inv.vat_id) or inv.stated_country

    return inv
