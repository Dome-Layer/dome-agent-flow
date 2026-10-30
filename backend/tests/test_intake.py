"""Email intake (docs/email-intake.md): allowlist, DMARC, attachments, idempotency,
and the channel recorded on the run and in `invoice_received`.

Supabase, P3 and the governance writer are stubbed out; addresses are example.com.
"""

from __future__ import annotations

import base64
import hashlib
import json
from typing import Any, Optional

import pytest
from fastapi.testclient import TestClient

from app.api import intake as intake_api
from app.api import runs as runs_api
from app.api.deps import Principal, require_principal
from app.core.config import Settings, settings
from app.main import app
from app.models.runs import EmailAttachment, RunRecord
from app.services import intake

SERVICE = Principal(user_id=None, is_service=True)
APPROVER = "11111111-1111-1111-1111-111111111111"
TRUSTED = "mx.example.net"

PDF = b"%PDF-1.7\n1 0 obj\n<<>>\nendobj\n%%EOF"
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32
GIF = b"GIF89a" + b"\x00" * 16
TEXT = b"Please find the invoice attached."


def _b64(data: bytes) -> str:
    return base64.b64encode(data).decode()


def _auth(result: str = "pass", domain: str = "example.com", authserv: str = TRUSTED) -> str:
    return (
        f"Authentication-Results: {authserv}; spf=pass smtp.mailfrom={domain}; "
        f"dkim=pass header.d={domain}; dmarc={result} (p=REJECT sp=REJECT) header.from={domain}"
    )


def _email(**overrides: Any) -> dict:
    body: dict[str, Any] = {
        "message_id": "<invoice-42@mail.example.com>",
        "from_header": '"Accounts Payable" <ap@example.com>',
        "date": "Fri, 30 Oct 2026 09:15:00 +0100",
        "authentication_results": [_auth()],
        "attachments": [{"filename": "invoice.pdf", "content_base64": _b64(PDF)}],
    }
    body.update(overrides)
    return body


@pytest.fixture(autouse=True)
def _setup(monkeypatch: pytest.MonkeyPatch) -> Any:
    monkeypatch.setattr(settings, "approver_user_ids", APPROVER)
    monkeypatch.setattr(settings, "email_intake_allowed_senders", "ap@example.com, @example.org")
    monkeypatch.setattr(settings, "email_intake_trusted_authserv_ids", TRUSTED)
    monkeypatch.setattr(settings, "email_intake_require_dmarc", True)
    monkeypatch.setattr(settings, "email_intake_max_attachment_bytes", 1024)
    monkeypatch.setattr(settings, "email_intake_max_attachments", 3)
    monkeypatch.setattr(settings, "email_intake_hash_key", "test-hash-key")

    state: dict[str, Any] = {"runs": {}, "events": [], "extract_calls": 0}
    runs: dict[str, RunRecord] = state["runs"]

    def create_run_once(run: RunRecord) -> bool:
        if any(r.intake_key == run.intake_key for r in runs.values()):
            return False
        runs[run.workflow_run_id] = run
        return True

    def by_key(key: str) -> Optional[RunRecord]:
        return next((r for r in runs.values() if r.intake_key == key), None)

    def emit_event(**kw: Any) -> None:
        state["events"].append(kw)

    async def extract_invoice(*args: Any, **kwargs: Any) -> dict:
        state["extract_calls"] += 1
        return {"fields": {}}

    monkeypatch.setattr(runs_api.runs_svc, "create_run_once", create_run_once)
    monkeypatch.setattr(runs_api.runs_svc, "get_run_by_intake_key", by_key)
    monkeypatch.setattr(
        runs_api.runs_svc, "create_run", lambda run: runs.update({run.workflow_run_id: run})
    )
    monkeypatch.setattr(runs_api.runs_svc, "get_run", lambda rid: runs.get(rid))
    monkeypatch.setattr(runs_api.runs_svc, "update_run", lambda run: None)
    monkeypatch.setattr(intake_api.governance, "emit_event", emit_event)
    monkeypatch.setattr(runs_api.upstream, "extract_invoice", extract_invoice)
    app.dependency_overrides[require_principal] = lambda: SERVICE
    yield state
    app.dependency_overrides.clear()


client = TestClient(app)


def _post(body: dict) -> dict:
    res = client.post("/api/v1/intake/email", json=body)
    assert res.status_code == 200, res.text
    return res.json()


def _events(state: dict, action_type: str) -> list[dict]:
    return [e for e in state["events"] if e["action_type"] == action_type]


# ── Allowlist ───────────────────────────────────────────────────────────────


def test_exact_address_is_accepted(_setup: dict) -> None:
    result = _post(_email())
    assert result["outcome"] == "accepted"
    assert len(result["runs"]) == 1


def test_domain_entry_accepts_any_address_at_that_domain(_setup: dict) -> None:
    result = _post(
        _email(
            from_header="billing@example.org",
            authentication_results=[_auth(domain="example.org")],
        )
    )
    assert result["outcome"] == "accepted"


def test_allowlist_is_case_insensitive() -> None:
    addresses, domains = frozenset({"ap@example.com"}), frozenset({"example.org"})
    assert intake.sender_allowed("AP@Example.COM", addresses, domains)
    assert intake.parse_sender("Accounts <AP@EXAMPLE.COM>") == "ap@example.com"
    assert intake.sender_allowed(
        intake.parse_sender("Billing@Example.ORG") or "", addresses, domains
    )


def test_other_address_at_an_address_only_domain_is_refused() -> None:
    assert not intake.sender_allowed(
        "someone@example.com", frozenset({"ap@example.com"}), frozenset()
    )


def test_subdomain_is_not_implied() -> None:
    assert not intake.sender_allowed("ap@mail.example.org", frozenset(), frozenset({"example.org"}))


def test_bare_and_at_prefixed_domains_mean_the_same(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        settings, "email_intake_allowed_senders", " AP@example.com ,example.org,@example.net, "
    )
    assert settings.email_allowed_addresses == frozenset({"ap@example.com"})
    assert settings.email_allowed_domains == frozenset({"example.org", "example.net"})


def test_empty_allowlist_accepts_nobody(_setup: dict, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "email_intake_allowed_senders", "")
    result = _post(_email())
    assert result["outcome"] == "rejected"
    assert result["reason"] == "sender_not_allowed"
    assert _setup["runs"] == {}


def test_sender_not_on_list_is_rejected_with_an_event_and_no_run(_setup: dict) -> None:
    result = _post(
        _email(from_header="eve@example.net", authentication_results=[_auth(domain="example.net")])
    )
    assert result["outcome"] == "rejected"
    assert result["reason"] == "sender_not_allowed"
    assert _setup["runs"] == {}
    (event,) = _events(_setup, "intake_rejected")
    assert event["workflow_run_id"] == result["intake_event_id"]
    assert event["workflow_run_id"].startswith("intake-")
    assert event["metadata"]["channel"] == "email"
    assert event["metadata"]["sender_domain"] == "example.net"
    assert not _events(_setup, "invoice_received")


def test_display_name_plays_no_part() -> None:
    assert intake.parse_sender('"ap@example.com" <eve@example.net>') == "eve@example.net"


@pytest.mark.parametrize(
    "header", ["", "not an address", "ap@example.com, eve@example.net", "ap@localhost"]
)
def test_from_header_must_hold_one_valid_address(_setup: dict, header: str) -> None:
    assert intake.parse_sender(header) is None
    result = _post(_email(from_header=header))
    assert result["reason"] == "invalid_sender"
    assert _setup["runs"] == {}


# ── Authentication (DMARC) ──────────────────────────────────────────────────


def test_dmarc_pass_from_trusted_authserv() -> None:
    assert intake.dmarc_verdict([_auth()], frozenset({TRUSTED}), "example.com") == "pass"


def test_header_from_an_untrusted_authserv_is_ignored(_setup: dict) -> None:
    planted = _auth(authserv="mx.attacker.example")
    assert intake.dmarc_verdict([planted], frozenset({TRUSTED}), "example.com") == "none"
    result = _post(_email(authentication_results=[planted]))
    assert result["reason"] == "authentication_failed"
    assert _setup["runs"] == {}


def test_dmarc_fail_is_rejected(_setup: dict) -> None:
    assert intake.dmarc_verdict([_auth("fail")], frozenset({TRUSTED}), "example.com") == "fail"
    result = _post(_email(authentication_results=[_auth("fail")]))
    assert result["reason"] == "authentication_failed"
    assert _events(_setup, "intake_rejected")[0]["metadata"]["dmarc"] == "fail"


def test_dmarc_pass_for_another_domain_does_not_count() -> None:
    header = _auth(domain="example.net")
    assert intake.dmarc_verdict([header], frozenset({TRUSTED}), "example.com") == "fail"


def test_no_trusted_authserv_configured_fails_closed(
    _setup: dict, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "email_intake_trusted_authserv_ids", "")
    assert _post(_email())["reason"] == "authentication_failed"


def test_authserv_id_with_version_and_no_header_prefix() -> None:
    header = f"{TRUSTED.upper()} 1; dmarc=pass header.from=example.com"
    assert intake.dmarc_verdict([header], frozenset({TRUSTED}), "example.com") == "pass"


def test_dmarc_can_be_off_in_development_only() -> None:
    assert Settings(environment="development", email_intake_require_dmarc=False)
    with pytest.raises(ValueError, match="EMAIL_INTAKE_REQUIRE_DMARC"):
        Settings(
            environment="staging",
            email_intake_require_dmarc=False,
            supabase_url="https://x.supabase.co",
            supabase_service_role_key="key",
            agent_flow_service_key="key",
            doci_base_url="https://doci.example.com",
            llc_base_url="https://llc.example.com",
        )


# ── Attachments ─────────────────────────────────────────────────────────────


def _att(data: bytes, name: str = "file") -> EmailAttachment:
    return EmailAttachment(filename=name, content_base64=_b64(data))


def test_attachment_filtering_by_content_not_name() -> None:
    accepted, ignored = intake.select_attachments(
        [
            _att(PDF, "invoice.pdf"),
            _att(GIF, "logo.gif"),
            _att(TEXT, "invoice.pdf"),  # named like a PDF, is not one
            _att(PNG, "scan.bin"),  # named oddly, is a PNG
            _att(b"", "empty.pdf"),
            EmailAttachment(filename="x.pdf", content_base64="!!not base64!!"),
        ],
        max_bytes=1024,
        max_count=5,
    )
    assert [(a.index, a.content_type) for a in accepted] == [
        (0, "application/pdf"),
        (3, "image/png"),
    ]
    assert [(i.attachment_index, i.reason) for i in ignored] == [
        (1, "unsupported_type"),
        (2, "unsupported_type"),
        (4, "empty"),
        (5, "undecodable"),
    ]


def test_jpeg_and_tiff_are_accepted() -> None:
    for data, kind in [
        (b"\xff\xd8\xff\xe0" + b"\x00" * 8, "image/jpeg"),
        (b"II*\x00" + b"\x00" * 8, "image/tiff"),
        (b"MM\x00*" + b"\x00" * 8, "image/tiff"),
    ]:
        assert intake.sniff_content_type(data) == kind


def test_size_limit_duplicates_and_count_cap() -> None:
    big = b"%PDF-" + b"0" * 2000
    pdfs = [PDF + bytes([n]) for n in range(4)]
    accepted, ignored = intake.select_attachments(
        [_att(big), _att(pdfs[0]), _att(pdfs[0]), *[_att(p) for p in pdfs[1:]]],
        max_bytes=1024,
        max_count=2,
    )
    assert [a.index for a in accepted] == [1, 3]
    assert [(i.attachment_index, i.reason) for i in ignored] == [
        (0, "too_large"),
        (2, "duplicate"),
        (4, "too_many"),
        (5, "too_many"),
    ]


def test_one_run_per_invoice_attachment(_setup: dict) -> None:
    result = _post(
        _email(
            attachments=[
                {"filename": "a.pdf", "content_base64": _b64(PDF)},
                {"filename": "logo.gif", "content_base64": _b64(GIF)},
                {"filename": "b.png", "content_base64": _b64(PNG)},
            ]
        )
    )
    assert result["outcome"] == "accepted"
    assert [r["attachment_index"] for r in result["runs"]] == [0, 2]
    assert result["ignored"] == [{"attachment_index": 1, "reason": "unsupported_type"}]
    assert len(_setup["runs"]) == 2
    assert len(_events(_setup, "invoice_received")) == 2


def test_no_usable_attachment_is_rejected_without_a_model_call(_setup: dict) -> None:
    result = _post(_email(attachments=[{"filename": "note.txt", "content_base64": _b64(TEXT)}]))
    assert result["outcome"] == "rejected"
    assert result["reason"] == "no_usable_attachment"
    assert _setup["runs"] == {}
    assert _setup["extract_calls"] == 0
    (event,) = _events(_setup, "intake_rejected")
    assert event["metadata"]["ignored"] == ["unsupported_type"]


def test_email_without_attachments_is_rejected(_setup: dict) -> None:
    assert _post(_email(attachments=[]))["reason"] == "no_usable_attachment"


# ── Idempotency ─────────────────────────────────────────────────────────────


def test_same_email_twice_makes_one_run(_setup: dict) -> None:
    first = _post(_email())
    second = _post(_email())
    assert first["outcome"] == "accepted"
    assert second["outcome"] == "duplicate"
    assert second["runs"][0]["duplicate"] is True
    assert second["runs"][0]["workflow_run_id"] == first["runs"][0]["workflow_run_id"]
    assert len(_setup["runs"]) == 1
    assert len(_events(_setup, "invoice_received")) == 1


def test_message_id_brackets_and_whitespace_do_not_matter(_setup: dict) -> None:
    _post(_email(message_id="<invoice-42@mail.example.com>"))
    assert _post(_email(message_id="  invoice-42@mail.example.com "))["outcome"] == "duplicate"


def test_a_different_email_with_the_same_invoice_is_a_new_run(_setup: dict) -> None:
    _post(_email())
    assert _post(_email(message_id="<resend-1@mail.example.com>"))["outcome"] == "accepted"
    assert len(_setup["runs"]) == 2


def test_new_attachment_on_a_replayed_email_only_adds_that_run(_setup: dict) -> None:
    _post(_email())
    result = _post(
        _email(
            attachments=[
                {"filename": "invoice.pdf", "content_base64": _b64(PDF)},
                {"filename": "b.png", "content_base64": _b64(PNG)},
            ]
        )
    )
    assert result["outcome"] == "accepted"
    assert [r["duplicate"] for r in result["runs"]] == [True, False]


def test_missing_message_id_falls_back_to_sender_and_date(_setup: dict) -> None:
    assert _post(_email(message_id=None))["outcome"] == "accepted"
    assert _post(_email(message_id=None))["outcome"] == "duplicate"
    assert intake.message_hash(None, "ap@example.com", "d1") != intake.message_hash(
        None, "ap@example.com", "d2"
    )


def test_lost_race_is_reported_as_duplicate(_setup: dict, monkeypatch: pytest.MonkeyPatch) -> None:
    first = _post(_email())
    existing = next(iter(_setup["runs"].values()))
    calls = {"n": 0}

    def by_key_late(key: str) -> Optional[RunRecord]:
        calls["n"] += 1  # not visible on the first look, visible after the insert fails
        return existing if calls["n"] > 1 else None

    monkeypatch.setattr(runs_api.runs_svc, "get_run_by_intake_key", by_key_late)
    second = _post(_email())
    assert second["outcome"] == "duplicate"
    assert second["runs"][0]["workflow_run_id"] == first["runs"][0]["workflow_run_id"]
    assert len(_setup["runs"]) == 1


# ── Channel and stored metadata ─────────────────────────────────────────────


def test_email_channel_recorded_on_run_and_event(_setup: dict) -> None:
    result = _post(_email())
    run = _setup["runs"][result["runs"][0]["workflow_run_id"]]
    assert run.source == "email"
    assert run.intake.channel == "email"
    assert run.intake.sender_domain == "example.com"
    assert run.intake.dmarc == "pass"
    assert run.intake.attachment_sha256 == hashlib.sha256(PDF).hexdigest()
    assert run.intake.sent_at == "2026-10-30T09:15:00+01:00"
    assert run.intake.received_at
    (event,) = _events(_setup, "invoice_received")
    assert event["metadata"]["channel"] == "email"
    assert event["input_hash"] == hashlib.sha256(PDF).hexdigest()


def test_sender_address_is_never_stored(_setup: dict) -> None:
    _post(_email())
    _post(_email(from_header="eve@example.net"))
    stored = json.dumps(
        [r.model_dump(mode="json") for r in _setup["runs"].values()] + _setup["events"],
        default=str,
    ).lower()
    assert "ap@example.com" not in stored
    assert "eve@example.net" not in stored
    assert "accounts payable" not in stored


def test_sender_hash_is_keyed_and_optional() -> None:
    assert intake.sender_hash("ap@example.com", "") is None
    h = intake.sender_hash("AP@example.com", "k1")
    assert h == intake.sender_hash("ap@example.com", "k1")
    assert h != intake.sender_hash("ap@example.com", "k2")
    assert h != hashlib.sha256(b"ap@example.com").hexdigest()


def test_form_channel_recorded(_setup: dict) -> None:
    res = client.post("/api/v1/runs", json={"source": "form", "filename": "inv.pdf"})
    assert res.status_code == 200
    assert res.json()["intake"]["channel"] == "form"


def test_direct_api_run_is_not_labelled_email(_setup: dict) -> None:
    res = client.post("/api/v1/runs", json={"source": "email"})
    assert res.json()["intake"]["channel"] == "api"


# ── Access and the extract binding ──────────────────────────────────────────


def test_only_the_service_key_may_submit_email(_setup: dict) -> None:
    app.dependency_overrides[require_principal] = lambda: Principal(
        user_id=APPROVER, is_service=False
    )
    assert client.post("/api/v1/intake/email", json=_email()).status_code == 403
    assert _setup["runs"] == {}


def test_email_run_extracts_only_the_vetted_attachment(_setup: dict) -> None:
    run_id = _post(_email())["runs"][0]["workflow_run_id"]
    url = f"/api/v1/runs/{run_id}/extract"
    other = client.post(url, files={"file": ("invoice.pdf", PDF + b"x", "application/pdf")})
    assert other.status_code == 409
    assert _setup["extract_calls"] == 0
    same = client.post(url, files={"file": ("invoice.pdf", PDF, "application/pdf")})
    assert same.status_code == 200
    assert _setup["extract_calls"] == 1
