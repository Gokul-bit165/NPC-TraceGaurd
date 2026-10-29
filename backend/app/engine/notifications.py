"""Analyst notifications for new High and Critical incidents, and daily summary digests.

Supports Email and Chat (webhook/Slack/Teams) channels.
Uses FakeNotificationSender by default so no real messages are sent in tests or local runs.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any, Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..models import CaseRow, EmailRow, UserRow


class Channel(str, Enum):
    EMAIL = "email"
    CHAT = "chat"
    BOTH = "both"


@dataclass
class NotificationMessage:
    id: str
    title: str
    body: str
    severity: str  # "high", "critical", "summary", "info"
    channel: str   # "email", "chat"
    recipient: str
    case_id: Optional[int] = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "body": self.body,
            "severity": self.severity,
            "channel": self.channel,
            "recipient": self.recipient,
            "case_id": self.case_id,
            "created_at": self.created_at.isoformat(),
            "metadata": self.metadata,
        }


class NotificationSender:
    """Interface for sending notifications to analysts."""

    def send(self, message: NotificationMessage) -> bool:
        raise NotImplementedError


class FakeNotificationSender(NotificationSender):
    """In-memory notification sender for tests and development. Never sends real messages."""

    def __init__(self) -> None:
        self.sent_messages: list[NotificationMessage] = []

    def send(self, message: NotificationMessage) -> bool:
        self.sent_messages.append(message)
        return True

    def clear(self) -> None:
        self.sent_messages.clear()

    def get_messages(
        self,
        severity: Optional[str] = None,
        case_id: Optional[int] = None,
        channel: Optional[str] = None,
    ) -> list[NotificationMessage]:
        out = self.sent_messages
        if severity:
            out = [m for m in out if m.severity == severity]
        if case_id is not None:
            out = [m for m in out if m.case_id == case_id]
        if channel:
            out = [m for m in out if m.channel == channel]
        return out


# Global singleton sender
_SENDER: NotificationSender = FakeNotificationSender()


def get_notification_sender() -> FakeNotificationSender:
    """Return the active notification sender (defaults to FakeNotificationSender)."""
    global _SENDER
    if not isinstance(_SENDER, FakeNotificationSender):
        # Always return FakeNotificationSender in test/demo mode
        _SENDER = FakeNotificationSender()
    return _SENDER


def set_notification_sender(sender: NotificationSender) -> None:
    global _SENDER
    _SENDER = sender


def notify_analysts_case(
    case: CaseRow,
    user: Optional[UserRow] = None,
    channel: str = "both",
    headline: str = "",
) -> list[NotificationMessage]:
    """Dispatch real-time email/chat notifications to analysts for High and Critical cases."""
    if case.band not in ("high", "critical"):
        return []

    sender = get_notification_sender()
    analyst_email = os.environ.get("TRACEGUARD_ANALYST_EMAIL", "soc-alerts@kestrel.edu")
    analyst_chat_channel = os.environ.get("TRACEGUARD_CHAT_CHANNEL", "#soc-incidents")
    user_name = user.name if user else case.user_id

    subject = f"[{case.band.upper()}] Incident #{case.id} - {user_name}: {headline or case.headline}"
    body_lines = [
        f"TraceGuard Security Alert: {case.band.upper()} Severity Incident",
        "",
        f"Case ID:        #{case.id}",
        f"Target User:    {user_name} ({user.email if user else case.user_id})",
        f"Severity Score: {case.score}/100 ({case.band.title()})",
        f"Email Score:    {case.email_score} | Login Score: {case.login_score}",
        f"Status:         {case.status.title()}",
        f"Correlated:     {'Yes (Email + Login sequence)' if case.correlated else 'No'}",
        f"Campaign Size:  {case.campaign_size} recipients" if case.campaign_size > 1 else "",
        f"Headline:       {headline or case.headline}",
        "",
        "Action Required: Review evidence and approve recommended containment steps.",
    ]
    body = "\n".join(line for line in body_lines if line is not None)

    created_msgs = []
    channels_to_send = ["email", "chat"] if channel == "both" else [channel]

    for ch in channels_to_send:
        recipient = analyst_email if ch == "email" else analyst_chat_channel
        msg = NotificationMessage(
            id=f"notif-{case.id}-{ch}-{len(sender.sent_messages)}",
            title=subject,
            body=body,
            severity=case.band,
            channel=ch,
            recipient=recipient,
            case_id=case.id,
            metadata={
                "score": case.score,
                "band": case.band,
                "campaign_key": case.campaign_key,
                "user_id": case.user_id,
            },
        )
        sender.send(msg)
        created_msgs.append(msg)

    return created_msgs


def generate_daily_summary(db: Session, date: Optional[datetime] = None) -> tuple[str, dict[str, Any]]:
    """Build daily summary briefing text and KPI metrics for analysts."""
    ref_date = date or datetime.now(timezone.utc)
    day_start = datetime(ref_date.year, ref_date.month, ref_date.day, 0, 0, 0, tzinfo=timezone.utc)
    day_end = day_start + timedelta(days=1)

    # Query cases created on this day
    cases_today = db.scalars(
        select(CaseRow)
        .where(CaseRow.created_at >= day_start, CaseRow.created_at < day_end)
        .order_by(CaseRow.score.desc())
    ).all()

    high_crit_cases = [c for c in cases_today if c.band in ("high", "critical")]
    users = {u.id: u for u in db.scalars(select(UserRow)).all()}

    # Phishing campaigns active
    active_campaigns = db.execute(
        select(EmailRow.campaign_key, func.count(func.distinct(EmailRow.user_id)))
        .where(EmailRow.received_at >= day_start, EmailRow.campaign_key != "")
        .group_by(EmailRow.campaign_key)
    ).all()

    summary_lines = [
        f"# TraceGuard Daily SOC Incident Summary ({day_start.strftime('%Y-%m-%d')})",
        "",
        "## Key Metrics",
        f"- Total Cases Opened: {len(cases_today)}",
        f"- Critical Incidents: {sum(1 for c in cases_today if c.band == 'critical')}",
        f"- High Severity Cases: {sum(1 for c in cases_today if c.band == 'high')}",
        f"- Active Phishing Campaigns: {len(active_campaigns)}",
        "",
        "## High and Critical Incidents Requiring Action",
    ]

    if not high_crit_cases:
        summary_lines.append("No High or Critical incidents opened today. All systems normal.")
    else:
        for c in high_crit_cases:
            u = users.get(c.user_id)
            name = u.name if u else c.user_id
            camp_info = f" [Campaign of {c.campaign_size}]" if c.campaign_size > 1 else ""
            summary_lines.append(
                f"- **Case #{c.id}** ({c.band.upper()} - Score {c.score}): {name} - {c.headline}{camp_info} (Status: {c.status})"
            )

    summary_lines.append("")
    summary_lines.append("SOC Analyst Portal: https://traceguard.kestrel.edu/cases")
    summary_text = "\n".join(summary_lines)

    meta = {
        "date": day_start.strftime("%Y-%m-%d"),
        "total_cases": len(cases_today),
        "high_or_critical": len(high_crit_cases),
        "active_campaigns": len(active_campaigns),
    }
    return summary_text, meta


def send_daily_summary(
    db: Session,
    date: Optional[datetime] = None,
    channel: str = "both",
) -> list[NotificationMessage]:
    """Generate and send daily summary briefing to analysts."""
    summary_text, meta = generate_daily_summary(db, date)
    sender = get_notification_sender()
    analyst_email = os.environ.get("TRACEGUARD_ANALYST_EMAIL", "soc-alerts@kestrel.edu")
    analyst_chat_channel = os.environ.get("TRACEGUARD_CHAT_CHANNEL", "#soc-incidents")
    date_str = meta["date"]

    title = f"TraceGuard Daily SOC Summary - {date_str} ({meta['high_or_critical']} High/Critical)"
    channels_to_send = ["email", "chat"] if channel == "both" else [channel]
    sent_msgs = []

    for ch in channels_to_send:
        recipient = analyst_email if ch == "email" else analyst_chat_channel
        msg = NotificationMessage(
            id=f"summary-{date_str}-{ch}",
            title=title,
            body=summary_text,
            severity="summary",
            channel=ch,
            recipient=recipient,
            metadata=meta,
        )
        sender.send(msg)
        sent_msgs.append(msg)

    return sent_msgs
