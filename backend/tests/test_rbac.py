"""RBAC tests: prove that role isolation is enforced end-to-end.

Invariants tested
-----------------
1.  A *user* cannot read another user's case   (cross-user isolation).
2.  A *user* cannot read the full cases list without identifying themselves.
3.  An *analyst* cannot change settings        (PUT /api/config).
4.  An *analyst* cannot load login batches     (POST /api/ingest/logins).
5.  An *analyst* can approve actions.
6.  An *admin*   can change settings.
7.  An unknown role is rejected (400).
8.  A *user* can read their own case.
9.  A *user* cannot read someone else's case (403).
"""
import pytest

# ---------------------------------------------------------------------------
# Header helpers
# ---------------------------------------------------------------------------

ANALYST = {"x-role": "analyst", "x-user": "Test Analyst"}
ADMIN   = {"x-role": "admin",   "x-user": "Test Admin"}


def user_headers(user_id: str, name: str = "Student") -> dict:
    return {"x-role": "user", "x-user": name, "x-user-id": user_id}


# ---------------------------------------------------------------------------
# Helper: pick a case that belongs to a specific scenario
# ---------------------------------------------------------------------------

def case_by_scenario(client, key, headers=ANALYST):
    items = client.get("/api/cases?limit=200", headers=headers).json()["items"]
    return next((c for c in items if c["scenario"] == key), None)


# ---------------------------------------------------------------------------
# 1 & 2 – user cannot read another user's case
# ---------------------------------------------------------------------------

def test_user_cannot_read_another_users_case(client):
    """A user-role principal is rejected when fetching someone else's case."""
    # Get a real case via an analyst
    resp = client.get("/api/cases?limit=200", headers=ANALYST)
    assert resp.status_code == 200
    cases = resp.json()["items"]
    assert cases, "seed must produce at least one case"

    victim = cases[0]
    victim_user_id = victim["user"]["id"]
    case_id = victim["id"]

    # An unrelated user tries to read it → 403
    attacker_headers = user_headers("attacker-uid-9999", "Attacker")
    r = client.get(f"/api/cases/{case_id}", headers=attacker_headers)
    assert r.status_code == 403, (
        f"Expected 403 but got {r.status_code}: user should not access another user's case"
    )


def test_user_cannot_read_cases_without_user_id(client):
    """A user-role request with no X-User-Id must be rejected (400)."""
    r = client.get("/api/cases", headers={"x-role": "user", "x-user": "Anonymous"})
    assert r.status_code == 400


def test_user_can_read_own_case(client):
    """A user-role principal may fetch their own case detail."""
    # Find a case via analyst, then read it as the case's own user
    cases = client.get("/api/cases?limit=200", headers=ANALYST).json()["items"]
    assert cases
    target = cases[0]
    uid = target["user"]["id"]
    case_id = target["id"]

    r = client.get(f"/api/cases/{case_id}", headers=user_headers(uid))
    assert r.status_code == 200, (
        f"Expected 200 but got {r.status_code}: user should be able to read their own case"
    )
    assert r.json()["case"]["id"] == case_id


def test_user_case_list_scoped_to_own_user(client):
    """GET /api/cases as a user returns only that user's cases."""
    cases = client.get("/api/cases?limit=200", headers=ANALYST).json()["items"]
    assert cases
    uid = cases[0]["user"]["id"]

    r = client.get("/api/cases", headers=user_headers(uid))
    assert r.status_code == 200
    items = r.json()["items"]
    # Every returned case must belong to this user
    assert all(c["user"]["id"] == uid for c in items), (
        "User-role case list leaked another user's case"
    )


# ---------------------------------------------------------------------------
# 3 – analyst cannot change settings
# ---------------------------------------------------------------------------

def test_analyst_cannot_change_settings(client):
    """PUT /api/config must return 403 for analyst role."""
    r = client.put("/api/config", json={"overrides": {}}, headers=ANALYST)
    assert r.status_code == 403, (
        f"Expected 403 but got {r.status_code}: analyst must not change settings"
    )


def test_admin_can_change_settings(client):
    """PUT /api/config with safe overrides succeeds for admin role."""
    # force=True bypasses scenario regression check so the test is self-contained
    r = client.put("/api/config", json={"overrides": {}, "force": True}, headers=ADMIN)
    assert r.status_code == 200, (
        f"Expected 200 but got {r.status_code}: admin should be able to save config"
    )


# ---------------------------------------------------------------------------
# 4 – analyst cannot load login batches
# ---------------------------------------------------------------------------

def test_analyst_cannot_ingest_logins(client):
    """POST /api/ingest/logins must return 403 for analyst role."""
    batch = [{"user_id": "u-test", "ts": "2026-01-15T12:00:00Z", "ip": "1.2.3.4",
              "country": "US", "city": "Boston", "device": "Windows|Chrome", "success": True}]
    r = client.post("/api/ingest/logins", json=batch, headers=ANALYST)
    assert r.status_code == 403, (
        f"Expected 403 but got {r.status_code}: analyst must not ingest logins"
    )


def test_admin_can_ingest_logins(client):
    """POST /api/ingest/logins succeeds for admin role."""
    batch = [{"user_id": "u-rbac-test", "ts": "2026-01-15T12:00:00Z", "ip": "10.0.0.1",
              "country": "US", "city": "Boston", "device": "Windows|Chrome", "success": True}]
    r = client.post("/api/ingest/logins", json=batch, headers=ADMIN)
    assert r.status_code == 200


# ---------------------------------------------------------------------------
# 5 – analyst can approve actions
# ---------------------------------------------------------------------------

def test_analyst_can_approve_action(client):
    """An analyst may POST to /api/cases/{id}/actions/{id} to approve/reject."""
    c = case_by_scenario(client, "impossible_travel")
    if c is None:
        pytest.skip("impossible_travel scenario not present in seed")

    case_detail = client.get(f"/api/cases/{c['id']}", headers=ANALYST).json()
    pending = [a for a in case_detail["actions"] if a["status"] == "proposed" and a["requires_approval"]]
    if not pending:
        pytest.skip("no pending approvable actions in impossible_travel case")

    action_id = pending[0]["id"]
    r = client.post(
        f"/api/cases/{c['id']}/actions/{action_id}",
        json={"decision": "approve"},
        headers=ANALYST,
    )
    assert r.status_code == 200, (
        f"Expected 200 but got {r.status_code}: analyst should be able to approve actions"
    )


# ---------------------------------------------------------------------------
# 6 – unknown role is rejected
# ---------------------------------------------------------------------------

def test_unknown_role_rejected(client):
    """An X-Role value that is not admin/analyst/user must return 400."""
    r = client.get("/api/cases", headers={"x-role": "superuser", "x-user": "Hacker"})
    assert r.status_code == 400
