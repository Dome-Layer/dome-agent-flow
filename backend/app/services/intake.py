"""Email intake decisions (docs/email-intake.md): who may send, whether the sender
is authenticated, which attachments become runs, and the idempotency key.

Pure functions over the request and the settings, so every decision is unit-tested
without n8n, a mailbox or Supabase. The endpoint in `app/api/intake.py` wires them up.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import re
from dataclasses import dataclass
from email.utils import getaddresses, parsedate_to_datetime
from typing import Optional

from app.models.runs import EmailAttachment, IgnoredAttachment

# Magic bytes of the formats P3 extracts invoices from. The declared type and the
# filename are ignored: a renamed file is judged by its content.
ACCEPTED_TYPES: tuple[tuple[bytes, str], ...] = (
    (b"%PDF-", "application/pdf"),
    (b"\x89PNG\r\n\x1a\n", "image/png"),
    (b"\xff\xd8\xff", "image/jpeg"),
    (b"II*\x00", "image/tiff"),
    (b"MM\x00*", "image/tiff"),
)

_COMMENT = re.compile(r"\([^()]*\)")
_HEADER_NAME = re.compile(r"^\s*authentication-results\s*:", re.IGNORECASE)


@dataclass(frozen=True)
class AcceptedAttachment:
    index: int
    filename: Optional[str]
    content_type: str
    sha256: str
    size: int


def sniff_content_type(data: bytes) -> Optional[str]:
    for magic, content_type in ACCEPTED_TYPES:
        if data.startswith(magic):
            return content_type
    return None


def parse_sender(from_header: str) -> Optional[str]:
    """The single address in a From header, lowercased; None for none, several, or
    a malformed one. Display names are dropped and play no part in the decision."""
    addresses = [addr for _, addr in getaddresses([from_header or ""]) if addr]
    if len(addresses) != 1:
        return None
    address = addresses[0].strip().lower()
    local, sep, domain = address.rpartition("@")
    if not sep or not local or not domain or "." not in domain or "@" in local:
        return None
    return address


def sender_domain(address: str) -> str:
    return address.rpartition("@")[2]


def sender_allowed(address: str, addresses: frozenset[str], domains: frozenset[str]) -> bool:
    """Exact address or exact domain, case-insensitive. Subdomains are not implied.
    Both sets empty means nobody is allowed (fail closed)."""
    address = address.lower()
    return address in addresses or sender_domain(address) in domains


def dmarc_verdict(
    authentication_results: list[str], trusted_ids: frozenset[str], from_domain: str
) -> str:
    """ "pass" if a header from a trusted authserv-id records dmarc=pass for the From
    domain; "fail" if a trusted header records another DMARC result; else "none".
    Headers naming any other authserv-id are ignored: a sender can write those."""
    verdict = "none"
    for header in authentication_results:
        value = _COMMENT.sub("", _HEADER_NAME.sub("", header or ""))
        parts = [p.strip() for p in value.split(";")]
        authserv = parts[0].split()[0].lower() if parts and parts[0].split() else ""
        if authserv not in trusted_ids:
            continue
        for part in parts[1:]:
            tokens = part.split()
            if not tokens or not tokens[0].lower().startswith("dmarc="):
                continue
            result = tokens[0].split("=", 1)[1].lower()
            props = dict(t.lower().split("=", 1) for t in tokens[1:] if "=" in t)
            domain_ok = props.get("header.from", from_domain) == from_domain
            if result == "pass" and domain_ok:
                return "pass"
            verdict = "fail"
    return verdict


def select_attachments(
    attachments: list[EmailAttachment], *, max_bytes: int, max_count: int
) -> tuple[list[AcceptedAttachment], list[IgnoredAttachment]]:
    """One accepted entry per distinct invoice file; everything else with a reason."""
    accepted: list[AcceptedAttachment] = []
    ignored: list[IgnoredAttachment] = []
    seen: set[str] = set()
    # Refuse an oversized attachment before decoding it: base64 is 4 chars per 3 bytes.
    max_encoded = (max_bytes + 2) // 3 * 4
    for index, attachment in enumerate(attachments):
        encoded = "".join(attachment.content_base64.split())
        if len(encoded) > max_encoded:
            ignored.append(IgnoredAttachment(attachment_index=index, reason="too_large"))
            continue
        try:
            data = base64.b64decode(encoded, validate=True)
        except (binascii.Error, ValueError):
            ignored.append(IgnoredAttachment(attachment_index=index, reason="undecodable"))
            continue
        reason = None
        content_type = sniff_content_type(data)
        digest = hashlib.sha256(data).hexdigest()
        if not data:
            reason = "empty"
        elif len(data) > max_bytes:
            reason = "too_large"
        elif content_type is None:
            reason = "unsupported_type"
        elif digest in seen:
            reason = "duplicate"
        elif len(accepted) >= max_count:
            reason = "too_many"
        if reason is not None or content_type is None:
            ignored.append(
                IgnoredAttachment(attachment_index=index, reason=reason or "unsupported_type")
            )
            continue
        seen.add(digest)
        accepted.append(
            AcceptedAttachment(
                index=index,
                filename=attachment.filename,
                content_type=content_type,
                sha256=digest,
                size=len(data),
            )
        )
    return accepted, ignored


def normalise_message_id(message_id: Optional[str]) -> Optional[str]:
    value = (message_id or "").strip().strip("<>").strip()
    return value or None


def message_hash(message_id: Optional[str], sender: str, date: Optional[str]) -> str:
    """Stable id of one email. Falls back to sender and Date when there is no
    Message-ID (legal, if rare)."""
    mid = normalise_message_id(message_id)
    basis = f"mid|{mid}" if mid else f"nomid|{sender}|{(date or '').strip()}"
    return hashlib.sha256(basis.encode("utf-8")).hexdigest()


def intake_key(msg_hash: str, attachment_sha256: str) -> str:
    return hashlib.sha256(f"email|{msg_hash}|{attachment_sha256}".encode()).hexdigest()


def sender_hash(address: str, key: str) -> Optional[str]:
    """Keyed hash of the address: whoever holds the key can confirm which allowlisted
    address sent a run, a reader of the table cannot reverse it. No key, no hash."""
    if not key:
        return None
    return hmac.new(key.encode(), address.lower().encode(), hashlib.sha256).hexdigest()


def parse_sent_at(date: Optional[str]) -> Optional[str]:
    if not date:
        return None
    try:
        return parsedate_to_datetime(date).isoformat()
    except (TypeError, ValueError, IndexError):
        return None
