"""Access rules for the private-demo shim (DOME_DECISIONS 2026-09-28).

Covers who may spend (the pipeline steps), who may decide, and what a
non-approver may read. Supabase and the upstream tools are stubbed out.
"""

from __future__ import annotations

from typing import Any, Optional

import pytest
from fastapi.testclient import TestClient

from app.api import runs as runs_api
from app.api.deps import Principal, require_principal
from app.core.config import settings
from app.main import app
from app.models.runs import RunRecord

APPROVER = "11111111-1111-1111-1111-111111111111"
OUTSIDER = "22222222-2222-2222-2222-222222222222"
SERVICE = Principal(user_id=None, is_service=True)


def _as(principal: Principal) -> None:
    app.dependency_overrides[require_principal] = lambda: principal


def _user(user_id: str) -> Principal:
    return Principal(user_id=user_id, is_service=False)


@pytest.fixture(autouse=True)
def _setup(monkeypatch: pytest.MonkeyPatch) -> Any:
    monkeypatch.setattr(settings, "approver_user_ids", APPROVER)

    store: dict[str, RunRecord] = {
        "run-unowned": RunRecord(workflow_run_id="run-unowned", status="pending_approval"),
        "run-outsider": RunRecord(
            workflow_run_id="run-outsider", status="pending_approval", user_id=OUTSIDER
        ),
    }
    seen: dict[str, Any] = {}

    def list_runs(status: Optional[str], user_id: Optional[str], see_all: bool) -> list:
        seen["see_all"] = see_all
        runs = list(store.values())
        return runs if see_all else [r for r in runs if user_id and r.user_id == user_id]

    monkeypatch.setattr(runs_api.runs_svc, "list_runs", list_runs)
    monkeypatch.setattr(runs_api.runs_svc, "get_run", lambda rid: store.get(rid))
    monkeypatch.setattr(runs_api.runs_svc, "create_run", lambda run: None)
    monkeypatch.setattr(runs_api.runs_svc, "update_run", lambda run: None)
    monkeypatch.setattr(runs_api.governance, "emit_event", lambda **kw: None)

    async def no_resume(*args: Any, **kwargs: Any) -> None:
        return None

    monkeypatch.setattr(runs_api.upstream, "resume_n8n", no_resume)
    yield seen
    app.dependency_overrides.clear()


client = TestClient(app)


# ── Spending: the pipeline steps ────────────────────────────────────────────


def test_service_key_can_create_run() -> None:
    _as(SERVICE)
    assert client.post("/api/v1/runs", json={"source": "form"}).status_code == 200


def test_approver_can_create_run() -> None:
    _as(_user(APPROVER))
    assert client.post("/api/v1/runs", json={"source": "api"}).status_code == 200


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("post", "/api/v1/runs"),
        ("post", "/api/v1/runs/run-unowned/rules"),
        ("post", "/api/v1/runs/run-unowned/council"),
    ],
)
def test_non_approver_cannot_spend(method: str, path: str) -> None:
    _as(_user(OUTSIDER))
    kwargs = {"json": {"source": "api"}} if path.endswith("/runs") else {}
    assert getattr(client, method)(path, **kwargs).status_code == 403


def test_non_approver_cannot_extract() -> None:
    _as(_user(OUTSIDER))
    res = client.post(
        "/api/v1/runs/run-unowned/extract", files={"file": ("x.pdf", b"%PDF", "application/pdf")}
    )
    assert res.status_code == 403


# ── Deciding ────────────────────────────────────────────────────────────────


def test_approver_can_decide() -> None:
    _as(_user(APPROVER))
    res = client.post("/api/v1/runs/run-unowned/decision", json={"decision": "approve"})
    assert res.status_code == 200


def test_non_approver_cannot_decide_even_own_run() -> None:
    _as(_user(OUTSIDER))
    res = client.post("/api/v1/runs/run-outsider/decision", json={"decision": "approve"})
    assert res.status_code == 403


def test_service_key_cannot_decide() -> None:
    _as(SERVICE)
    res = client.post("/api/v1/runs/run-unowned/decision", json={"decision": "approve"})
    assert res.status_code == 403


def test_empty_allowlist_fails_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "approver_user_ids", "")
    _as(_user(APPROVER))
    res = client.post("/api/v1/runs/run-unowned/decision", json={"decision": "approve"})
    assert res.status_code == 403


# ── Reading ─────────────────────────────────────────────────────────────────


def test_approver_lists_every_run(_setup: dict) -> None:
    _as(_user(APPROVER))
    ids = {r["workflow_run_id"] for r in client.get("/api/v1/runs").json()["runs"]}
    assert ids == {"run-unowned", "run-outsider"}
    assert _setup["see_all"] is True


def test_non_approver_lists_only_own_runs(_setup: dict) -> None:
    _as(_user(OUTSIDER))
    ids = {r["workflow_run_id"] for r in client.get("/api/v1/runs").json()["runs"]}
    assert ids == {"run-outsider"}
    assert _setup["see_all"] is False


def test_non_approver_cannot_open_someone_elses_run() -> None:
    _as(_user(OUTSIDER))
    assert client.get("/api/v1/runs/run-unowned").status_code == 404
    assert client.get("/api/v1/runs/run-outsider").status_code == 200


def test_approver_list_parsing_ignores_blanks(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "approver_user_ids", f" {APPROVER} , ,{OUTSIDER}")
    assert settings.approver_id_set == frozenset({APPROVER, OUTSIDER})
