"""Case workflow: ingest events, (re)analyse a user, keep the queue, record decisions, write the audit log."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import and_, func, select
from sqlalchemy.orm import Session

from .engine import config as cfgmod
from .engine import explain, respond
from .engine.email_signals import analyze_email
from .engine.pipeline import analyze_case
from .engine.types import CaseResult, EmailEvent, GlobalContext, Link, LoginEvent
from .models import (ActionRow, AuditRow, CaseRow, EmailRow, FeedbackRow, LoginRow, NotificationRow, UserRow, utcnow)
from .connectors.registry import get_registry

ACTIVE = ("open", "investigating")
HISTORY_DAYS = 120
HISTORY_ROWS = 3000


def aware(dt: Optional[datetime]) -> Optional[datetime]:
    if dt is None:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


# ---------------------------------------------------------------- audit
def audit(db: Session, actor: str, role: str, event: str, case_id: Optional[int] = None, detail: dict | str = "") -> None:
    db.add(AuditRow(actor=actor, role=role, event=event, case_id=case_id,
                    detail=detail if isinstance(detail, str) else json.dumps(detail, default=str)))


# ---------------------------------------------------------------- row <-> event
def login_from_row(r: LoginRow) -> LoginEvent:
    return LoginEvent(user_id=r.user_id, ts=aware(r.ts), ip=r.ip, country=r.country, city=r.city, asn=r.asn, device=r.device,
                      success=r.success, is_attack_ip=r.is_attack_ip, id=str(r.id))


def email_from_row(r: EmailRow) -> EmailEvent:
    return EmailEvent(id=r.id, user_id=r.user_id, received_at=aware(r.received_at), sender=r.sender, subject=r.subject,
                      body_text=r.body_text, reply_to=r.reply_to, auth=json.loads(r.auth_json or "{}"),
                      links=[Link(**l) for l in json.loads(r.links_json or "[]")], has_headers=r.has_headers,
                      hidden_text=r.hidden_text, raw=r.raw)


def upsert_user(db: Session, user_id: str, name: str = "", email: str = "", dept: str = "", role: str = "student") -> UserRow:
    u = db.get(UserRow, user_id)
    if u is None:
        u = UserRow(id=user_id, name=name or user_id, email=email, dept=dept, role=role)
        db.add(u)
    else:
        if name:
            u.name = name
        if email:
            u.email = email
        if dept:
            u.dept = dept
    return u


def resolve_user(db: Session, ident: str) -> Optional[UserRow]:
    """Find a user by id, e-mail address or exact name."""
    if not ident:
        return None
    u = db.get(UserRow, ident)
    if u:
        return u
    return db.scalar(select(UserRow).where(func.lower(UserRow.email) == ident.lower())) or \
        db.scalar(select(UserRow).where(func.lower(UserRow.name) == ident.lower()))


# ---------------------------------------------------------------- ingest
def add_login(db: Session, ev: LoginEvent, risk: int = 0, band: str = "low", flags: Optional[list[str]] = None) -> LoginRow:
    row = LoginRow(user_id=ev.user_id, ts=ev.ts, ip=ev.ip, country=ev.country, city=ev.city, asn=ev.asn, device=ev.device,
                   success=ev.success, is_attack_ip=ev.is_attack_ip, risk=risk, risk_band=band, flags=",".join(flags or []))
    db.add(row)
    return row


def score_new_login(db: Session, ev: LoginEvent, cfg: dict) -> tuple[int, str, list[str]]:
    """Score a login that is arriving now against the user's stored history (30 minute window)."""
    import copy
    from .engine.login_signals import analyze_logins
    c = copy.deepcopy(cfg)
    c["login"]["window_hours"] = 0.5
    hist_rows = db.scalars(select(LoginRow).where(LoginRow.user_id == ev.user_id, LoginRow.ts < ev.ts).order_by(LoginRow.ts.desc()).limit(300)).all()
    hist = [login_from_row(r) for r in reversed(hist_rows)] + [ev]
    ctx = ctx_for(db, ev.user_id, [ev] + hist[-20:], ev.ts, extra=[ev])
    res = analyze_logins(hist, c, ctx, ev.ts)
    return res.score, cfgmod.band_of(res.score, c), [e.code for e in res.ledger if e.points > 0]


def ctx_for(db: Session, user_id: str, window_events: list[LoginEvent], as_of: datetime, extra: Optional[list[LoginEvent]] = None) -> GlobalContext:
    start = as_of - timedelta(hours=24)
    ips = {e.ip for e in window_events if e.ip and start < e.ts <= as_of}
    ctx = GlobalContext()
    unsaved = {(e.ip, e.device, e.success) for e in (extra or [])}     # events not yet in the table still count for this user
    for ip in ips:
        users = set(db.scalars(select(LoginRow.user_id).where(LoginRow.ip == ip, LoginRow.ts > start, LoginRow.ts <= as_of).distinct()).all())
        if any(u[0] == ip for u in unsaved):
            users.add(user_id)
        ctx.ip_user_counts[ip] = len(users)
    pairs = {(e.device, e.ip) for e in window_events if e.device and e.ip and e.success and start < e.ts <= as_of}
    for dev, ip in pairs:
        users = set(db.scalars(select(LoginRow.user_id).where(LoginRow.device == dev, LoginRow.ip == ip, LoginRow.success.is_(True)).distinct()).all())
        if (ip, dev, True) in unsaved:
            users.add(user_id)
        ctx.device_user_counts[f"{dev}@{ip}"] = len(users)
    return ctx


def add_email(db: Session, em: EmailEvent, cfg: Optional[dict] = None) -> tuple[EmailRow, "object"]:
    cfg = cfg or cfgmod.get()
    an = analyze_email(em, cfg)
    row = EmailRow(id=em.id, user_id=em.user_id, received_at=em.received_at, sender=em.sender, subject=em.subject[:300], reply_to=em.reply_to,
                   auth_json=json.dumps(em.auth), links_json=json.dumps([{"href": l.href, "text": l.text} for l in em.links]),
                   body_text=em.body_text[:20000], hidden_text=em.hidden_text[:5000], has_headers=em.has_headers, raw=em.raw,
                   risk=an.score, risk_band=cfgmod.band_of(min(an.score, cfg["correlation"]["email_only_ceiling"]), cfg), probability=an.probability, campaign_key=an.campaign_key)
    db.merge(row)
    return row, an


# ---------------------------------------------------------------- analysis
def _hash(result: CaseResult) -> str:
    return hashlib.sha1(json.dumps([result.score, result.email_score, result.login_score, [(e.code, e.points) for e in result.ledger]]).encode()).hexdigest()


def campaign_size(db: Session, key: Optional[str], since: datetime) -> int:
    if not key:
        return 1
    n = db.scalar(select(func.count(func.distinct(EmailRow.user_id))).where(EmailRow.campaign_key == key, EmailRow.received_at >= since)) or 1
    return max(int(n), 1)


def analyze_user(db: Session, user_id: str, cfg: Optional[dict] = None, as_of: Optional[datetime] = None,
                 disabled: Optional[set[str]] = None) -> CaseResult:
    cfg = cfg or cfgmod.get()
    last_login = db.scalar(select(func.max(LoginRow.ts)).where(LoginRow.user_id == user_id))
    last_mail = db.scalar(select(func.max(EmailRow.received_at)).where(EmailRow.user_id == user_id))
    stamps = [aware(x) for x in (last_login, last_mail) if x]
    as_of = as_of or (max(stamps) if stamps else utcnow())
    l_rows = db.scalars(select(LoginRow).where(LoginRow.user_id == user_id, LoginRow.ts >= as_of - timedelta(days=HISTORY_DAYS), LoginRow.ts <= as_of)
                        .order_by(LoginRow.ts.desc()).limit(HISTORY_ROWS)).all()
    logins = [login_from_row(r) for r in reversed(l_rows)]
    e_rows = db.scalars(select(EmailRow).where(EmailRow.user_id == user_id, EmailRow.received_at >= as_of - timedelta(hours=cfg["email"]["window_hours"]),
                                               EmailRow.received_at <= as_of)).all()
    emails = [email_from_row(r) for r in e_rows]
    win_start = as_of - timedelta(hours=cfg["login"]["window_hours"])
    ctx = ctx_for(db, user_id, [l for l in logins if l.ts > win_start], as_of)
    return analyze_case(user_id, emails, logins, cfg, ctx, as_of=as_of, disabled_login_signals=disabled)


def reanalyze_user(db: Session, user_id: str, actor: str = "system", scenario_key: Optional[str] = None,
                   as_of: Optional[datetime] = None) -> Optional[CaseRow]:
    cfg = cfgmod.get()
    res = analyze_user(db, user_id, cfg, as_of)
    user = db.get(UserRow, user_id)
    name = user.name if user else user_id
    if res.score < cfg["triage"]["case_min_score"]:
        return None
    existing = db.scalar(select(CaseRow).where(CaseRow.user_id == user_id, CaseRow.status.in_(ACTIVE)).order_by(CaseRow.id.desc()))
    since = res.as_of - timedelta(hours=cfg["email"]["window_hours"])
    size = campaign_size(db, res.campaign_key, since)
    narrative = explain.narrate(res, name)
    payload = {
        "ledger": res.ledger_dicts(), "timeline": res.timeline, "suspicious_login": res.suspicious_login, "extras": res.extras,
        "text_terms": res.text_terms, "text_probability": res.text_probability, "not_evaluated": res.not_evaluated,
        "low_confidence_reason": res.low_confidence_reason, "login_refs": res.login_refs, "email_ids": res.email_ids,
        "sig": _hash(res),
    }
    if existing is not None:
        prev = json.loads(existing.result_json or "{}")
        if prev.get("sig") == payload["sig"]:
            existing.updated_at = utcnow()
            return existing
        old_band = existing.band
        case = existing
    else:
        case, old_band = CaseRow(user_id=user_id, as_of=res.as_of, created_at=utcnow()), None
        db.add(case)
    case.as_of = res.as_of
    case.updated_at = utcnow()
    case.score, case.email_score, case.login_score, case.band = res.score, res.email_score, res.login_score, res.band
    case.correlated, case.low_confidence = res.correlated, res.low_confidence
    case.campaign_key, case.campaign_size, case.top_email_id = res.campaign_key, size, res.top_email_id
    case.headline = narrative["headline"]
    case.result_json, case.narrative_json = json.dumps(payload), json.dumps(narrative)
    if scenario_key:
        case.scenario_key = scenario_key
    db.flush()

    # ---- actions: keep decided ones, replace the proposed ones with the current recommendation
    decided = {a.code for a in db.scalars(select(ActionRow).where(ActionRow.case_id == case.id, ActionRow.status != "proposed")).all()}
    for a in db.scalars(select(ActionRow).where(ActionRow.case_id == case.id, ActionRow.status == "proposed")).all():
        db.delete(a)
    for act in respond.recommend(res, size):
        if act.code in decided:
            continue
        row = ActionRow(case_id=case.id, order=act.order, code=act.code, label=act.label, detail=act.detail, reversible=act.reversible,
                        requires_approval=act.requires_approval, connector=act.connector, depends_on=act.depends_on)
        if not act.requires_approval:
            row.status, row.decided_by, row.decided_at = "auto_done", "traceguard", utcnow()
            row.note = "Reversible step run automatically (log-only connector in this build)."
            if act.code == "send_user_alert":
                db.add(NotificationRow(user_id=user_id, case_id=case.id, title="Security check: was this you?",
                                       body=respond.user_alert(res, name, res_subject(res))))
        db.add(row)
    if res.band == "low":
        case.status, case.resolved_at = "auto_closed", utcnow()
        audit(db, "traceguard", "system", "auto_closed", case.id, {"score": res.score})
    else:
        if case.status == "auto_closed":
            case.status, case.resolved_at = "open", None
        audit(db, actor, "system" if actor == "system" else actor, "case_opened" if existing is None else "case_updated", case.id,
              {"score": res.score, "band": res.band, "from_band": old_band})
        if old_band and cfgmod.band_rank(res.band) > cfgmod.band_rank(old_band):
            audit(db, "traceguard", "system", "escalated", case.id, {"from": old_band, "to": res.band})
    return case


def res_subject(res: CaseResult) -> Optional[str]:
    te = res.extras.get("top_email")
    return te["subject"] if te else None


# ---------------------------------------------------------------- decisions
class WorkflowError(Exception):
    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


def decide_action(db: Session, case_id: int, action_id: int, decision: str, actor: str, role: str, note: str = "") -> ActionRow:
    if decision not in {"approve", "reject"}:
        raise WorkflowError("decision must be approve or reject")
    a = db.get(ActionRow, action_id)
    if a is None or a.case_id != case_id:
        raise WorkflowError("action not found", 404)
    if a.status != "proposed":
        raise WorkflowError(f"action is already {a.status}", 409)
    if decision == "approve" and a.depends_on:
        dep = db.scalar(select(ActionRow).where(ActionRow.case_id == case_id, ActionRow.code == a.depends_on))
        if dep is not None and dep.status not in {"approved", "auto_done"}:
            raise WorkflowError(f"'{a.label}' must wait until '{dep.label}' is approved: a live token survives a password reset", 409)

    a.status = "approved" if decision == "approve" else "rejected"
    a.decided_by, a.decided_at, a.note = actor, utcnow(), note
    case = db.get(CaseRow, case_id)
    if case.status == "open":
        case.status = "investigating"
        case.assignee = case.assignee or actor

    # ---- call the real connector if the decision is approve ----
    connector_result = None
    if decision == "approve":
        # Build context from the case and any available email data.
        top_email = db.get(EmailRow, case.top_email_id) if case.top_email_id else None
        links = []
        sender_domain = ""
        if top_email:
            try:
                link_data = json.loads(top_email.links_json or "[]")
                links = [lnk.get("href", "") for lnk in link_data if lnk.get("href")]
                sender = top_email.sender or ""
                # Extract registrable domain from sender address.
                if "@" in sender:
                    domain_part = sender.split("@", 1)[1].strip().rstrip(">")
                    # Use the last two labels as the registrable domain.
                    parts = domain_part.split(".")
                    sender_domain = ".".join(parts[-2:]) if len(parts) >= 2 else domain_part
            except Exception:
                pass

        ctx = {
            "case_id": case_id,
            "user_id": case.user_id,
            "action_id": action_id,
            "connector": a.connector,
            "email_id": top_email.id if top_email else None,
            "top_email_id": case.top_email_id,
            "subject": top_email.subject if top_email else None,
            "sender_domain": sender_domain,
            "links": links,
            "campaign_key": case.campaign_key,
        }

        connector_result = get_registry().dispatch(a.code, a.connector, ctx)

        # If the connector call failed the action is marked 'failed' so that
        # dependent steps remain blocked (they check for 'approved'/'auto_done').
        if not connector_result.success:
            a.status = "failed"
            a.note = (
                f"{note}\n[CONNECTOR FAILED] {connector_result.detail}".strip()
            )
        else:
            if connector_result.detail:
                a.note = f"{note}\n[CONNECTOR] {connector_result.detail}".strip()

    audit_detail: dict = {"action": a.code, "connector": a.connector, "note": note}
    if connector_result is not None:
        audit_detail["connector_success"] = connector_result.success
        audit_detail["connector_detail"] = connector_result.detail
        if connector_result.data:
            audit_detail["connector_data"] = connector_result.data

    audit(db, actor, role, f"action_{a.status}", case_id, audit_detail)
    db.flush()
    pending = db.scalar(select(func.count(ActionRow.id)).where(ActionRow.case_id == case_id, ActionRow.status == "proposed")) or 0
    if pending == 0 and case.status in ACTIVE:
        case.status, case.resolved_at = "resolved", utcnow()
        audit(db, "traceguard", "system", "case_resolved", case_id, {"reason": "all actions decided"})
    case.updated_at = utcnow()
    return a


def set_status(db: Session, case_id: int, status: str, actor: str, role: str) -> CaseRow:
    if status not in {"open", "investigating", "resolved", "false_positive"}:
        raise WorkflowError("unknown status")
    case = db.get(CaseRow, case_id)
    if case is None:
        raise WorkflowError("case not found", 404)
    old = case.status
    case.status = status
    case.resolved_at = utcnow() if status in {"resolved", "false_positive"} else None
    if status == "investigating" and not case.assignee:
        case.assignee = actor
    case.updated_at = utcnow()
    audit(db, actor, role, "status_changed", case_id, {"from": old, "to": status})
    return case


def set_verdict(db: Session, case_id: int, verdict: str, actor: str, role: str) -> CaseRow:
    if verdict not in {"true_positive", "false_positive"}:
        raise WorkflowError("verdict must be true_positive or false_positive")
    case = db.get(CaseRow, case_id)
    if case is None:
        raise WorkflowError("case not found", 404)
    case.verdict = verdict
    codes = [e["code"] for e in json.loads(case.result_json).get("ledger", []) if e["points"] > 0]
    db.add(FeedbackRow(case_id=case_id, verdict=verdict, codes=",".join(codes), actor=actor))
    if verdict == "false_positive":
        case.status, case.resolved_at = "false_positive", utcnow()
    case.updated_at = utcnow()
    audit(db, actor, role, "verdict", case_id, {"verdict": verdict})
    return case
