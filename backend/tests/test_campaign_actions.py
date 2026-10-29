"""Tests for campaign-wide action approvals, removals, undo capability,
and analyst notifications (real-time high/critical alerts and daily summary).
"""
from datetime import datetime, timezone
import pytest
from sqlalchemy import select

from app.db import SessionLocal, reset_db
from app.engine.counter import reset_cross_user_counter
from app.engine.notifications import get_notification_sender
from app.models import ActionRow, AuditRow, CaseRow, EmailRow, NotificationRow
from app import seed, services

FIXED_NOW = datetime(2026, 1, 15, 15, 0, tzinfo=timezone.utc)
H = {"X-Role": "analyst", "X-User": "Jane Analyst"}
ADMIN = {"X-Role": "admin", "X-User": "Admin"}


@pytest.fixture()
def client():
    from fastapi.testclient import TestClient
    from app.main import app

    reset_db()
    reset_cross_user_counter()
    get_notification_sender().clear()
    with SessionLocal() as db:
        seed.seed(db, now=FIXED_NOW, n_background=20, n_legit_emails=100, verbose=False)
    with TestClient(app) as c:
        yield c


def test_preview_campaign_affected_users(client):
    """Verify preview of affected recipients and proposed actions for a campaign."""
    camps = client.get("/api/campaigns", headers=H).json()
    assert len(camps) > 0
    key = camps[0]["key"]

    r = client.get(f"/api/campaigns/{key}", headers=H)
    assert r.status_code == 200
    data = r.json()
    assert data["campaign_key"] == key
    assert len(data["recipients"]) >= 2
    assert "sender" in data and "subject" in data
    assert any(a["code"] == "block_sender_domain" for a in data["actions"])
    assert any(a["code"] == "remove_from_mailboxes" and not a["reversible"] for a in data["actions"])
    assert any(a["code"] == "send_user_alert" and a["reversible"] for a in data["actions"])


def test_approve_campaign_action_for_all_recipients(client):
    """Verify approving one action for the whole campaign:

    - Blocks sender and links
    - Purges message everywhere
    - Alerts every recipient
    - Creates one audit entry per user
    """
    camps = client.get("/api/campaigns", headers=H).json()
    key = camps[0]["key"]

    preview = client.get(f"/api/campaigns/{key}", headers=H).json()
    expected_users = [r["user_id"] for r in preview["recipients"]]

    # Execute campaign action
    resp = client.post(f"/api/campaigns/{key}/action", json={"note": "Approved by analyst"}, headers=H)
    assert resp.status_code == 200
    res_data = resp.json()
    assert res_data["status"] == "approved"
    assert res_data["affected_count"] == len(expected_users)
    assert res_data["audit_entries_recorded"] == len(expected_users)

    # Verify database state for each recipient
    with SessionLocal() as db:
        for uid in expected_users:
            case = db.scalar(select(CaseRow).where(CaseRow.user_id == uid).order_by(CaseRow.id.desc()))
            assert case is not None

            # 4 actions exist and are approved
            actions = db.scalars(select(ActionRow).where(ActionRow.case_id == case.id)).all()
            codes = {a.code: a for a in actions}
            assert "block_sender_domain" in codes and codes["block_sender_domain"].status == "approved"
            assert "block_urls" in codes and codes["block_urls"].status == "approved"
            assert "remove_from_mailboxes" in codes and codes["remove_from_mailboxes"].status == "approved"
            assert "send_user_alert" in codes and codes["send_user_alert"].status == "approved"

            # Alert notification exists for user
            notif = db.scalar(select(NotificationRow).where(NotificationRow.user_id == uid).order_by(NotificationRow.id.desc()))
            assert notif is not None
            assert "Phishing message removed" in notif.title

            # Exactly one audit entry recorded per user for campaign_action_approved
            audits = db.scalars(
                select(AuditRow).where(AuditRow.case_id == case.id, AuditRow.event == "campaign_action_approved")
            ).all()
            assert len(audits) == 1
            assert audits[0].actor == "Jane Analyst"


def test_remove_users_from_list_before_approval(client):
    """Verify that an analyst can exclude users from the campaign action."""
    camps = client.get("/api/campaigns", headers=H).json()
    key = camps[0]["key"]

    preview = client.get(f"/api/campaigns/{key}", headers=H).json()
    all_users = [r["user_id"] for r in preview["recipients"]]
    assert len(all_users) >= 2
    excluded = [all_users[0]]

    # Approve with first user excluded
    resp = client.post(f"/api/campaigns/{key}/action", json={"excluded_user_ids": excluded}, headers=H)
    assert resp.status_code == 200
    res_data = resp.json()
    assert res_data["affected_count"] == len(all_users) - 1
    assert all_users[0] not in res_data["affected_users"]

    # Verify excluded user received no campaign action audit
    with SessionLocal() as db:
        exc_case = db.scalar(select(CaseRow).where(CaseRow.user_id == excluded[0]))
        if exc_case:
            audits = db.scalars(select(AuditRow).where(AuditRow.case_id == exc_case.id, AuditRow.event == "campaign_action_approved")).all()
            assert len(audits) == 0


def test_undo_campaign_action_reverses_only_reversible_actions(client):
    """Verify that campaign action can be undone:

    - Reversible actions (block_sender_domain, block_urls, send_user_alert) are undone
    - Irreversible action (remove_from_mailboxes) is retained as approved
    - Records one audit entry per user
    """
    camps = client.get("/api/campaigns", headers=H).json()
    key = camps[0]["key"]

    # First approve
    client.post(f"/api/campaigns/{key}/action", json={}, headers=H)

    # Then undo
    undo_resp = client.post(f"/api/campaigns/{key}/undo", json={"note": "Mistake, reversing"}, headers=H)
    assert undo_resp.status_code == 200
    undo_data = undo_resp.json()
    assert undo_data["status"] == "undone"
    assert "remove_from_mailboxes" in undo_data["retained_irreversible_actions"]
    assert "block_sender_domain" in undo_data["reversed_actions"]

    preview = client.get(f"/api/campaigns/{key}", headers=H).json()
    affected_users = [r["user_id"] for r in preview["recipients"]]

    with SessionLocal() as db:
        for uid in affected_users:
            case = db.scalar(select(CaseRow).where(CaseRow.user_id == uid).order_by(CaseRow.id.desc()))
            assert case is not None
            actions = {a.code: a for a in db.scalars(select(ActionRow).where(ActionRow.case_id == case.id)).all()}

            # Reversible actions were reverted to proposed
            assert actions["block_sender_domain"].status == "proposed"
            assert actions["block_urls"].status == "proposed"
            assert actions["send_user_alert"].status == "proposed"

            # Irreversible message purge remains approved
            assert actions["remove_from_mailboxes"].status == "approved"

            # One undo audit entry per user
            undo_audits = db.scalars(
                select(AuditRow).where(AuditRow.case_id == case.id, AuditRow.event == "campaign_action_undone")
            ).all()
            assert len(undo_audits) == 1


def test_undo_individual_action(client):
    """Verify that individual case actions can be undone if reversible, and blocked if irreversible."""
    # Find a case with actions
    cases = client.get("/api/cases", headers=H).json()["items"]
    case_id = cases[0]["id"]
    detail = client.get(f"/api/cases/{case_id}", headers=H).json()
    actions = detail["actions"]

    rev_act = next((a for a in actions if a["reversible"] and a["status"] == "proposed"), None)
    if not rev_act:
        # Pick any proposed action and make it reversible
        rev_act = actions[0]

    # Approve it
    client.post(f"/api/cases/{case_id}/actions/{rev_act['id']}", json={"decision": "approve"}, headers=H)

    if rev_act["reversible"]:
        # Undo it
        r_undo = client.post(f"/api/cases/{case_id}/actions/{rev_act['id']}/undo", json={"note": "Mistake"}, headers=H)
        assert r_undo.status_code == 200
        assert r_undo.json()["status"] == "proposed"
    else:
        r_undo = client.post(f"/api/cases/{case_id}/actions/{rev_act['id']}/undo", json={}, headers=H)
        assert r_undo.status_code == 400


def test_analyst_notifications_for_high_and_critical_cases(client):
    """Verify that new High and Critical cases trigger analyst notifications via fake sender."""
    from app.engine.email_parse import parse_eml
    from app import scenarios as sc

    sender = get_notification_sender()
    sender.clear()

    # Create a new user with a high-scoring phishing email
    with SessionLocal() as db:
        now = FIXED_NOW
        raw = sc.eml(
            from_name="Payroll Office",
            from_addr="payroll@kestrel-payroll.top",
            to="u-alert-target@kestrel.edu",
            subject="Salary revision letter: action needed",
            html='<p>Confirm password: <a href="http://kestrel-payroll.top/letter">https://payroll.kestrel.edu/letter</a></p>',
            when=now,
            reply_to="payroll.kestrel@outlook.com",
            spf="fail",
            dkim="none",
            dmarc="fail",
        )
        services.upsert_user(db, "u-alert-target", name="Alert Target", email="u-alert-target@kestrel.edu")
        em = parse_eml(raw, "u-alert-target", now)
        services.add_email(db, em)
        db.flush()
        case = services.reanalyze_user(db, "u-alert-target", actor="test", as_of=now)
        db.commit()

    assert case is not None
    assert case.band in ("high", "critical")

    # Verify notifications were sent to fake sender
    sent = sender.get_messages()
    assert len(sent) > 0
    assert any(m.severity in ("high", "critical") for m in sent)
    assert any(m.channel == "email" for m in sent)
    assert any(m.channel == "chat" for m in sent)
    assert any("Alert Target" in m.title or "u-alert-target" in m.title for m in sent)


def test_daily_summary_notification_endpoint(client):
    """Verify daily summary generation and notification dispatch."""
    # Preview daily summary
    preview = client.get("/api/notifications/daily-summary", headers=H)
    assert preview.status_code == 200
    assert "TraceGuard Daily SOC Incident Summary" in preview.json()["summary"]

    # Trigger sending daily summary
    sender = get_notification_sender()
    sender.clear()
    resp = client.post("/api/notifications/daily-summary", json={"channel": "both"}, headers=H)
    assert resp.status_code == 200
    assert resp.json()["sent"] == 2  # email + chat

    sent = sender.get_messages(severity="summary")
    assert len(sent) == 2
    assert "Daily SOC Summary" in sent[0].title
