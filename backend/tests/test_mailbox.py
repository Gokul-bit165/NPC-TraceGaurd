"""Fetched-mail API: /api/emails lists what connectors delivered, /api/mail/sync asks n8n to fetch now."""
from __future__ import annotations

from unittest.mock import MagicMock, patch


H_ADMIN = {"x-role": "admin", "x-user": "Test Admin"}
H_USER = {"x-role": "user", "x-user": "u-nikhil"}


def test_emails_lists_scored_mail_for_staff(client):
    r = client.get("/api/emails?limit=5", headers=H_ADMIN)
    assert r.status_code == 200
    d = r.json()
    assert {"total", "items", "suspicious", "mailboxes", "newest", "auto_sync"} <= set(d)
    assert len(d["items"]) <= 5
    for m in d["items"]:
        assert {"id", "mailbox", "sender", "subject", "score", "band", "case_id"} <= set(m)


def test_emails_filters_by_band(client):
    d = client.get("/api/emails?band=critical", headers=H_ADMIN).json()
    assert all(m["band"] == "critical" for m in d["items"])


def test_emails_blocked_for_students(client):
    assert client.get("/api/emails", headers=H_USER).status_code == 403


def test_sync_requires_admin(client):
    assert client.post("/api/mail/sync", headers={"x-role": "analyst", "x-user": "a"}).status_code == 403


def test_sync_calls_n8n_and_returns_report(client):
    resp = MagicMock()
    resp.read.return_value = b'{"fetched": 3, "analysed": 3, "suspicious": 1}'
    resp.__enter__.return_value = resp
    with patch("urllib.request.urlopen", return_value=resp) as op:
        r = client.post("/api/mail/sync", headers=H_ADMIN)
    assert r.status_code == 200 and r.json()["fetched"] == 3
    assert op.call_args.args[0].full_url.endswith("/webhook/traceguard-gmail-sync")


def test_sync_reports_unreachable_n8n(client):
    with patch("urllib.request.urlopen", side_effect=OSError("down")):
        assert client.post("/api/mail/sync", headers=H_ADMIN).status_code == 502


def test_email_investigation_explains_the_score(client):
    items = client.get("/api/emails?limit=50", headers=H_ADMIN).json()["items"]
    top = max(items, key=lambda m: m["score"])
    d = client.get(f"/api/emails/{top['id']}/investigation", headers=H_ADMIN).json()
    assert {"email", "verdict", "analysis", "context", "case", "recommendations"} <= set(d)
    assert d["verdict"]["band"] in ("low", "medium", "high", "critical") and d["recommendations"]
    assert sum(e["points"] for e in d["analysis"]["ledger"] if e["side"] == "email") >= 0
    assert d["email"]["id"] == top["id"]


def test_email_investigation_404_and_student_block(client):
    assert client.get("/api/emails/nope/investigation", headers=H_ADMIN).status_code == 404
    assert client.get("/api/emails/nope/investigation", headers=H_USER).status_code == 403


def test_simulate_takeover_creates_correlated_case(client, monkeypatch):
    from app import services
    from app.db import SessionLocal
    monkeypatch.setenv("TRACEGUARD_REAL_USERS", "real.user@example.com")
    with SessionLocal() as db:
        services.upsert_user(db, "u-real-user", "Real User", "real.user@example.com", "", "student")
        db.commit()
    from datetime import datetime, timedelta, timezone
    when = (datetime.now(timezone.utc) - timedelta(hours=1)).strftime("%a, %d %b %Y %H:%M:%S +0000")
    eml = (f"From: IT <help@evil-support.top>\r\nTo: real.user@example.com\r\nSubject: Password expires today\r\nDate: {when}\r\n"
           "Content-Type: text/plain\r\n\r\nVerify your username and password now at http://campus-login.top/auth or your account will be closed.\r\n")
    assert client.post("/api/ingest/email", json={"recipient": "real.user@example.com", "raw_eml": eml}, headers=H_ADMIN).status_code == 200
    opts = client.get("/api/simulate/options", headers=H_ADMIN).json()
    assert {s["id"] for s in opts["scenarios"]} == {"normal", "takeover", "travel", "stuffing"}
    assert opts["mailboxes"][0]["email"] == "real.user@example.com"
    r = client.post("/api/simulate/logins", json={"mailbox": "real.user@example.com", "scenario": "takeover"}, headers=H_ADMIN)
    assert r.status_code == 200 and r.json()["baseline_added"] and r.json()["events"] > 30
    assert r.json()["cases"], r.json()
    case = next(c for c in client.get("/api/cases?limit=200", headers=H_ADMIN).json()["items"] if c["user"]["email"] == "real.user@example.com")
    d = client.get(f"/api/cases/{case['id']}/decision", headers=H_ADMIN).json()
    assert d["decision"]["code"] in ("contain", "verify") and d["reasons"] and d["steps"] and d["options"]
    assert all(s["why"] for s in d["steps"])


def test_simulate_validation_and_permissions(client):
    assert client.post("/api/simulate/logins", json={"mailbox": "nobody@x.com", "scenario": "takeover"}, headers=H_ADMIN).status_code == 404
    assert client.post("/api/simulate/logins", json={"mailbox": "x", "scenario": "bogus"}, headers=H_ADMIN).status_code == 400
    assert client.post("/api/simulate/logins", json={"mailbox": "x", "scenario": "normal"}, headers=H_USER).status_code == 403


def test_clear_simulated_logins_requires_real_mailbox(client):
    assert client.delete("/api/simulate/logins?mailbox=aisha.khan@kestrel.edu", headers=H_ADMIN).status_code == 403
    assert client.delete("/api/simulate/logins?mailbox=nobody@x.com", headers=H_ADMIN).status_code == 404


def test_batch_logins_are_scored_against_earlier_events_in_the_same_batch(client):
    """Regression: with autoflush off, every login in a batch used to be scored as 'low' because the batch's own history was invisible."""
    from app import services
    from app.db import SessionLocal
    from app.models import LoginRow
    from app import simulate
    with SessionLocal() as db:
        services.upsert_user(db, "u-batch", "Batch User", "batch@example.com", "", "student")
        db.commit()
    r = client.post("/api/simulate/logins", json={"mailbox": "batch@example.com", "scenario": "stuffing"}, headers=H_ADMIN)
    assert r.status_code == 200
    with SessionLocal() as db:
        top = db.query(LoginRow).filter(LoginRow.user_id == "u-batch").order_by(LoginRow.risk.desc()).first()
    assert top.risk >= 30, top.risk
