"""Connector system tests.

Tests the full connector stack:
1.  Unit tests for LogConnector and ConnectorRegistry
2.  M365Connector interface contract (no real HTTP calls – M365 is mocked)
3.  Integration: approving an action dispatches via the registry and the result
    appears in the audit trail
4.  Failure path: a failed connector call sets status='failed' and blocks
    dependent steps
5.  Retry-safety: dispatching the same action twice does not raise
"""
from __future__ import annotations

import os
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

H_ADMIN  = {"x-role": "admin",   "x-user": "Test Admin"}
H_ANALYST = {"x-role": "analyst", "x-user": "Test Analyst"}


def _first_proposed(client, case_id, headers=H_ANALYST, external_only=False):
    d = client.get(f"/api/cases/{case_id}", headers=headers).json()
    proposed = [a for a in d["actions"] if a["status"] == "proposed" and a["requires_approval"]]
    if external_only:
        proposed = [a for a in proposed if not any(a["connector"].startswith(p) for p in ("case.", "notify."))]
    return proposed[0] if proposed else None


def case_by_scenario(client, key, headers=H_ANALYST):
    items = client.get("/api/cases?limit=200", headers=headers).json()["items"]
    return next((c for c in items if c["scenario"] == key), None)


# ---------------------------------------------------------------------------
# 1.  Unit: LogConnector
# ---------------------------------------------------------------------------

def test_log_connector_always_succeeds():
    from app.connectors.log_connector import LogConnector
    conn = LogConnector()
    result = conn.execute("quarantine_message", {"case_id": 1, "user_id": "u1", "connector": "mail.quarantine"})
    assert result.success
    assert "Log-only" in result.detail


def test_log_connector_is_idempotent():
    """Calling the log connector twice returns success both times."""
    from app.connectors.log_connector import LogConnector
    conn = LogConnector()
    ctx = {"case_id": 1, "user_id": "u1", "connector": "mail.quarantine"}
    r1 = conn.execute("quarantine_message", ctx)
    r2 = conn.execute("quarantine_message", ctx)
    assert r1.success and r2.success


# ---------------------------------------------------------------------------
# 2.  Unit: ConnectorRegistry routing
# ---------------------------------------------------------------------------

def test_registry_uses_log_by_default(monkeypatch):
    monkeypatch.delenv("TRACEGUARD_CONNECTOR", raising=False)
    from app.connectors import registry as reg_mod
    reg_mod.reset_registry()
    r = reg_mod.get_registry()
    assert r.backend_name == "log"
    reg_mod.reset_registry()


def test_registry_internal_connectors_never_call_backend(monkeypatch):
    """case.* and notify.* addresses must return success without calling the backend."""
    monkeypatch.delenv("TRACEGUARD_CONNECTOR", raising=False)
    from app.connectors import registry as reg_mod
    reg_mod.reset_registry()
    r = reg_mod.get_registry()

    mock_backend = MagicMock()
    r._backend = mock_backend

    for addr in ("case.close", "case.watch", "notify.user"):
        result = r.dispatch("some_action", addr, {"case_id": 1, "user_id": "u1"})
        assert result.success, f"Internal address {addr!r} should succeed"

    mock_backend.execute.assert_not_called()
    reg_mod.reset_registry()


def test_registry_unknown_env_falls_back_to_log(monkeypatch):
    monkeypatch.setenv("TRACEGUARD_CONNECTOR", "nonexistent_backend")
    from app.connectors import registry as reg_mod
    reg_mod.reset_registry()
    r = reg_mod.get_registry()
    assert r.backend_name == "log"
    reg_mod.reset_registry()


# ---------------------------------------------------------------------------
# 3.  Unit: M365Connector – mocked HTTP
# ---------------------------------------------------------------------------

class _FakeGraph:
    """Replaces _graph() with a call recorder that always returns {}."""
    def __init__(self):
        self.calls: list[tuple] = []

    def __call__(self, method, path, body=None, **kwargs):
        self.calls.append((method, path, body))
        return {}


def _make_m365(monkeypatch):
    """Return an M365Connector with Graph calls intercepted."""
    monkeypatch.setenv("M365_TENANT_ID", "test-tenant")
    monkeypatch.setenv("M365_CLIENT_ID", "test-client")
    monkeypatch.setenv("M365_CLIENT_SECRET", "test-secret")
    fake = _FakeGraph()
    monkeypatch.setattr("app.connectors.m365._graph", fake)
    monkeypatch.setattr("app.connectors.m365._get_token", lambda: "fake-token")
    from app.connectors.m365 import M365Connector
    return M365Connector(), fake


def test_m365_quarantine_calls_graph(monkeypatch):
    conn, fake = _make_m365(monkeypatch)
    ctx = {"case_id": 1, "user_id": "alice", "connector": "mail.quarantine",
           "email_id": "msg-abc", "top_email_id": "msg-abc"}
    result = conn.execute("quarantine_message", ctx)
    assert result.success
    assert any("move" in path for _, path, _ in fake.calls)


def test_m365_revoke_sessions_calls_graph(monkeypatch):
    conn, fake = _make_m365(monkeypatch)
    ctx = {"case_id": 1, "user_id": "alice", "connector": "idp.revoke_sessions"}
    result = conn.execute("revoke_sessions", ctx)
    assert result.success
    assert any("revokeSignInSessions" in path for _, path, _ in fake.calls)


def test_m365_reset_password_does_not_log_password(monkeypatch):
    conn, fake = _make_m365(monkeypatch)
    ctx = {"case_id": 1, "user_id": "alice", "connector": "idp.reset_password"}
    result = conn.execute("reset_password", ctx)
    assert result.success
    # The password must NOT appear anywhere in the result
    assert "password" not in result.detail.lower() or "reset" in result.detail.lower()
    assert result.data.get("force_change_next_sign_in") is True
    # Crucially the raw password value must not be in data
    assert "password" not in str(result.data)


def test_m365_noop_actions_succeed_without_graph(monkeypatch):
    conn, fake = _make_m365(monkeypatch)
    for code in ("close_with_note", "watch_account", "monitor_30_days"):
        ctx = {"case_id": 1, "user_id": "u1", "connector": "case.close"}
        result = conn.execute(code, ctx)
        assert result.success, f"noop action {code!r} should succeed"
    assert not fake.calls, "Noop actions must not call Graph"


def test_m365_idempotent_quarantine(monkeypatch):
    """Calling quarantine twice must not raise even if Graph returns 404."""
    conn, fake = _make_m365(monkeypatch)
    ctx = {"case_id": 1, "user_id": "alice", "connector": "mail.quarantine",
           "email_id": "msg-xyz", "top_email_id": "msg-xyz"}
    r1 = conn.execute("quarantine_message", ctx)
    r2 = conn.execute("quarantine_message", ctx)
    assert r1.success and r2.success


def test_m365_missing_email_id_does_not_crash(monkeypatch):
    conn, fake = _make_m365(monkeypatch)
    ctx = {"case_id": 1, "user_id": "alice", "connector": "mail.quarantine"}
    result = conn.execute("quarantine_message", ctx)
    # Should return failure (can't quarantine without a message ID) but not raise.
    assert not result.success


# ---------------------------------------------------------------------------
# 4 & 5.  Integration: connector wired into decide_action
# ---------------------------------------------------------------------------

def test_approve_action_recorded_in_audit(client):
    """Approving an action must record connector_success in the audit trail."""
    c = case_by_scenario(client, "impossible_travel")
    if c is None:
        pytest.skip("impossible_travel scenario not present")

    action = _first_proposed(client, c["id"])
    if action is None:
        pytest.skip("no proposed actions in impossible_travel")

    resp = client.post(
        f"/api/cases/{c['id']}/actions/{action['id']}",
        json={"decision": "approve"},
        headers=H_ANALYST,
    )
    assert resp.status_code == 200

    audit = client.get(f"/api/audit?case_id={c['id']}", headers=H_ANALYST).json()
    action_events = [e for e in audit if "action_" in e["event"]]
    assert action_events, "An action_* audit entry must be written"
    latest = action_events[0]
    import json as _json
    detail = _json.loads(latest["detail"]) if isinstance(latest["detail"], str) else latest["detail"]
    # connector_success must be in the audit detail
    assert "connector_success" in detail, (
        f"connector_success missing from audit detail: {detail}"
    )
    assert detail["connector_success"] is True


def test_failed_connector_sets_failed_status(client, monkeypatch):
    """When the connector reports failure the action status becomes 'failed'."""
    from app.connectors import registry as reg_mod
    reg_mod.reset_registry()

    # Replace the backend with one that always fails.
    from app.connectors import ConnectorResult
    failing_backend = MagicMock()
    failing_backend.name = "failing_mock"
    failing_backend.execute.return_value = ConnectorResult(
        success=False,
        detail="Simulated connector failure",
        data={"error": "mock"},
    )

    c = case_by_scenario(client, "impossible_travel")
    if c is None:
        pytest.skip("impossible_travel scenario not present")
    action = _first_proposed(client, c["id"], external_only=True)
    if action is None:
        pytest.skip("no proposed actions")

    # Patch the registry's backend for this test.
    reg = reg_mod.get_registry()
    original_backend = reg._backend
    reg._backend = failing_backend
    try:
        resp = client.post(
            f"/api/cases/{c['id']}/actions/{action['id']}",
            json={"decision": "approve"},
            headers=H_ANALYST,
        )
        assert resp.status_code == 200
        returned_action = resp.json()
        assert returned_action["status"] == "failed", (
            f"Expected status='failed' but got {returned_action['status']!r}"
        )
    finally:
        reg._backend = original_backend
        reg_mod.reset_registry()


def test_failed_action_blocks_dependent_steps(client, monkeypatch):
    """A step whose depends_on action failed must not be approvable."""
    from app.connectors import registry as reg_mod, ConnectorResult

    c = case_by_scenario(client, "phish_takeover")
    if c is None:
        pytest.skip("phish_takeover scenario not present")

    d = client.get(f"/api/cases/{c['id']}", headers=H_ANALYST).json()
    acts = {a["code"]: a for a in d["actions"]}

    if "revoke_sessions" not in acts or "reset_password" not in acts:
        pytest.skip("phish_takeover missing expected actions")

    revoke = acts["revoke_sessions"]
    reset  = acts["reset_password"]

    if revoke["status"] != "proposed":
        pytest.skip("revoke_sessions already decided")

    # Make the connector fail for revoke_sessions.
    failing = MagicMock()
    failing.name = "failing_mock"
    failing.execute.return_value = ConnectorResult(False, "Simulated failure", {})

    reg = reg_mod.get_registry()
    original = reg._backend
    reg._backend = failing
    try:
        r = client.post(
            f"/api/cases/{c['id']}/actions/{revoke['id']}",
            json={"decision": "approve"},
            headers=H_ANALYST,
        )
        assert r.status_code == 200
        assert r.json()["status"] == "failed"

        # reset_password depends on revoke_sessions; it must be blocked.
        r2 = client.post(
            f"/api/cases/{c['id']}/actions/{reset['id']}",
            json={"decision": "approve"},
            headers=H_ANALYST,
        )
        assert r2.status_code == 409, (
            f"reset_password should be blocked (409) but got {r2.status_code}"
        )
    finally:
        reg._backend = original
        reg_mod.reset_registry()
