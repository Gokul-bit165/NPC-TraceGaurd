from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class UserRow(Base):
    __tablename__ = "users"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(120), default="")
    email: Mapped[str] = mapped_column(String(200), default="", index=True)
    dept: Mapped[str] = mapped_column(String(120), default="")
    role: Mapped[str] = mapped_column(String(20), default="student")


class LoginRow(Base):
    __tablename__ = "login_events"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(String(64), index=True)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    ip: Mapped[str] = mapped_column(String(64), default="", index=True)
    country: Mapped[str] = mapped_column(String(8), default="")
    city: Mapped[str] = mapped_column(String(80), default="")
    asn: Mapped[int | None] = mapped_column(Integer, nullable=True)
    device: Mapped[str] = mapped_column(String(120), default="")
    success: Mapped[bool] = mapped_column(Boolean, default=True)
    is_attack_ip: Mapped[bool] = mapped_column(Boolean, default=False)
    risk: Mapped[int] = mapped_column(Integer, default=0)
    risk_band: Mapped[str] = mapped_column(String(10), default="low", index=True)
    flags: Mapped[str] = mapped_column(Text, default="")        # comma-separated reason codes at ingest time
    __table_args__ = (
        Index("ix_login_user_ts", "user_id", "ts"),
        Index("ix_login_ip_ts", "ip", "ts"),
        Index("ix_login_dev_ip_succ", "device", "ip", "success"),
        Index("ix_login_risk_ts", "risk_band", "ts"),
    )


class EmailRow(Base):
    __tablename__ = "email_events"
    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(64), index=True)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    sender: Mapped[str] = mapped_column(String(200), default="")
    subject: Mapped[str] = mapped_column(String(300), default="")
    reply_to: Mapped[str] = mapped_column(String(200), default="")
    auth_json: Mapped[str] = mapped_column(Text, default="{}")
    links_json: Mapped[str] = mapped_column(Text, default="[]")
    body_text: Mapped[str] = mapped_column(Text, default="")
    hidden_text: Mapped[str] = mapped_column(Text, default="")
    has_headers: Mapped[bool] = mapped_column(Boolean, default=False)
    raw: Mapped[str] = mapped_column(Text, default="")
    risk: Mapped[int] = mapped_column(Integer, default=0)
    risk_band: Mapped[str] = mapped_column(String(10), default="low", index=True)
    probability: Mapped[float | None] = mapped_column(Float, nullable=True)
    campaign_key: Mapped[str] = mapped_column(String(20), default="", index=True)
    __table_args__ = (
        Index("ix_email_user_recv", "user_id", "received_at"),
        Index("ix_email_camp_recv", "campaign_key", "received_at"),
    )


class CaseRow(Base):
    __tablename__ = "cases"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(String(64), index=True)
    as_of: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    score: Mapped[int] = mapped_column(Integer, index=True)
    email_score: Mapped[int] = mapped_column(Integer, default=0)
    login_score: Mapped[int] = mapped_column(Integer, default=0)
    band: Mapped[str] = mapped_column(String(10), index=True)
    status: Mapped[str] = mapped_column(String(20), default="open", index=True)  # open|investigating|resolved|auto_closed|false_positive
    correlated: Mapped[bool] = mapped_column(Boolean, default=False)
    low_confidence: Mapped[bool] = mapped_column(Boolean, default=False)
    campaign_key: Mapped[str | None] = mapped_column(String(20), nullable=True, index=True)
    campaign_size: Mapped[int] = mapped_column(Integer, default=1)
    headline: Mapped[str] = mapped_column(String(200), default="")
    assignee: Mapped[str | None] = mapped_column(String(80), nullable=True)
    verdict: Mapped[str | None] = mapped_column(String(20), nullable=True)       # true_positive | false_positive
    scenario_key: Mapped[str | None] = mapped_column(String(40), nullable=True)
    top_email_id: Mapped[str | None] = mapped_column(String(40), nullable=True)
    result_json: Mapped[str] = mapped_column(Text, default="{}")
    narrative_json: Mapped[str] = mapped_column(Text, default="{}")
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    __table_args__ = (
        Index("ix_case_user_status", "user_id", "status"),
        Index("ix_case_band_status", "band", "status"),
        Index("ix_case_score_camp", "score", "campaign_size"),
    )


class ActionRow(Base):
    __tablename__ = "actions"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    case_id: Mapped[int] = mapped_column(ForeignKey("cases.id"), index=True)
    order: Mapped[int] = mapped_column(Integer)
    code: Mapped[str] = mapped_column(String(40))
    label: Mapped[str] = mapped_column(String(200))
    detail: Mapped[str] = mapped_column(Text, default="")
    reversible: Mapped[bool] = mapped_column(Boolean, default=True)
    requires_approval: Mapped[bool] = mapped_column(Boolean, default=True)
    connector: Mapped[str] = mapped_column(String(40), default="")
    depends_on: Mapped[str | None] = mapped_column(String(40), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="proposed")   # proposed|approved|rejected|auto_done
    decided_by: Mapped[str | None] = mapped_column(String(80), nullable=True)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    note: Mapped[str] = mapped_column(Text, default="")
    __table_args__ = (
        Index("ix_action_case_status", "case_id", "status"),
    )


class AuditRow(Base):
    __tablename__ = "audit_log"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    actor: Mapped[str] = mapped_column(String(80))
    role: Mapped[str] = mapped_column(String(20), default="system")
    event: Mapped[str] = mapped_column(String(60), index=True)
    case_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    detail: Mapped[str] = mapped_column(Text, default="")
    __table_args__ = (
        Index("ix_audit_case_ts", "case_id", "ts"),
    )


class FeedbackRow(Base):
    __tablename__ = "feedback"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    case_id: Mapped[int] = mapped_column(Integer, index=True)
    verdict: Mapped[str] = mapped_column(String(20))
    codes: Mapped[str] = mapped_column(Text, default="")
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    actor: Mapped[str] = mapped_column(String(80), default="")


class NotificationRow(Base):
    """In-app message for the student/staff user. In production this also goes out by email or push."""
    __tablename__ = "notifications"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(String(64), index=True)
    case_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    title: Mapped[str] = mapped_column(String(200))
    body: Mapped[str] = mapped_column(Text, default="")
    acknowledged: Mapped[str | None] = mapped_column(String(20), nullable=True)   # it_was_me | not_me
