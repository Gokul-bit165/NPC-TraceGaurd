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
from .engine.counter import get_cross_user_counter
from .engine.email_signals import analyze_email
from .engine.pipeline import analyze_case
from .engine.types import CaseResult, EmailEvent, GlobalContext, Link, LoginEvent
from .models import (ActionRow, AuditRow, CaseRow, EmailRow, FeedbackRow, LoginRow, NotificationRow, UserRow, utcnow)

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
    get_cross_user_counter().record_login(ev.user_id, ev.ts, ev.ip, ev.device, ev.success)
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
    counter = get_cross_user_counter()
    if not counter.is_warmed():
        counter.warmup_from_db(db)
    return counter.build_context_for_user(user_id, window_events, as_of, extra)


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
        if res.band in ("high", "critical"):
            if existing is None or (old_band and old_band not in ("high", "critical")):
                from .engine.notifications import notify_analysts_case
                notify_analysts_case(case, user, headline=narrative.get("headline", ""))
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
    audit(db, actor, role, f"action_{a.status}", case_id, {"action": a.code, "connector": a.connector, "note": note})
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


def undo_action(db: Session, case_id: int, action_id: int, actor: str, role: str, note: str = "") -> ActionRow:
    """Undo an approved action if it is reversible."""
    a = db.get(ActionRow, action_id)
    if a is None or a.case_id != case_id:
        raise WorkflowError("action not found", 404)
    if not a.reversible:
        raise WorkflowError(f"'{a.label}' is not reversible and cannot be undone", 400)
    if a.status not in {"approved", "auto_done"}:
        raise WorkflowError(f"action is {a.status}, only approved actions can be undone", 409)

    # Check if another approved action depends on this action
    dependents = db.scalars(
        select(ActionRow).where(ActionRow.case_id == case_id, ActionRow.depends_on == a.code, ActionRow.status.in_({"approved", "auto_done"}))
    ).all()
    if dependents:
        dep_labels = ", ".join(f"'{d.label}'" for d in dependents)
        raise WorkflowError(f"cannot undo '{a.label}' while {dep_labels} remains approved; undo {dep_labels} first", 409)

    old_status = a.status
    a.status = "proposed"
    a.decided_by = None
    a.decided_at = None
    a.note = f"Undone by {actor}: {note}".strip() if note else f"Undone by {actor}"

    case = db.get(CaseRow, case_id)
    if case and case.status == "resolved":
        case.status = "investigating"
        case.resolved_at = None
        case.updated_at = utcnow()

    audit(db, actor, role, "action_undone", case_id, {"action": a.code, "previous_status": old_status, "note": note})
    return a


def get_campaign_details(db: Session, campaign_key: str) -> dict:
    """Retrieve full campaign details, sample sender/subject/links, and list of affected recipients."""
    if not campaign_key:
        raise WorkflowError("campaign_key required", 400)

    emails = db.scalars(
        select(EmailRow).where(EmailRow.campaign_key == campaign_key).order_by(EmailRow.received_at.asc())
    ).all()
    if not emails:
        raise WorkflowError(f"campaign '{campaign_key}' not found", 404)

    sample = emails[0]
    sender_domain = sample.sender.split("@")[-1].strip("<> ") if "@" in sample.sender else sample.sender

    # Aggregate unique links across campaign emails
    all_links = set()
    for em in emails:
        for l in json.loads(em.links_json or "[]"):
            if isinstance(l, dict) and l.get("href"):
                all_links.add(l["href"])

    # Collect recipient user details
    recipient_ids = list(dict.fromkeys(em.user_id for em in emails))
    users = {u.id: u for u in db.scalars(select(UserRow).where(UserRow.id.in_(recipient_ids))).all()}
    cases = {c.user_id: c for c in db.scalars(select(CaseRow).where(CaseRow.user_id.in_(recipient_ids))).all()}

    recipients = []
    for em in emails:
        uid = em.user_id
        u = users.get(uid)
        c = cases.get(uid)
        recipients.append({
            "user_id": uid,
            "name": u.name if u else uid,
            "email": u.email if u else "",
            "dept": u.dept if u else "",
            "email_id": em.id,
            "received_at": em.received_at.isoformat(),
            "case_id": c.id if c else None,
            "score": c.score if c else em.risk,
            "band": c.band if c else em.risk_band,
            "status": c.status if c else "no_case",
        })

    # Check whether remediation actions were applied
    remediated_count = 0
    can_undo_count = 0
    for r in recipients:
        cid = r["case_id"]
        if cid:
            acts = db.scalars(select(ActionRow).where(ActionRow.case_id == cid)).all()
            if any(a.code in ("block_sender_domain", "remove_from_mailboxes") and a.status == "approved" for a in acts):
                remediated_count += 1
            if any(a.code in ("block_sender_domain", "block_urls") and a.status == "approved" and a.reversible for a in acts):
                can_undo_count += 1

    return {
        "campaign_key": campaign_key,
        "sender": sample.sender,
        "sender_domain": sender_domain,
        "subject": sample.subject,
        "links": sorted(all_links),
        "total_recipients": len(recipient_ids),
        "recipients": recipients,
        "actions": [
            {"code": "block_sender_domain", "label": f"Block sender domain ({sender_domain})", "reversible": True},
            {"code": "block_urls", "label": f"Block {len(all_links)} campaign URLs", "reversible": True},
            {"code": "remove_from_mailboxes", "label": f"Purge message from all recipient mailboxes", "reversible": False},
            {"code": "send_user_alert", "label": "Alert every recipient with verification check", "reversible": True},
        ],
        "remediated": remediated_count > 0,
        "can_undo": can_undo_count > 0,
    }


def approve_campaign_action(
    db: Session,
    campaign_key: str,
    actor: str,
    role: str,
    excluded_user_ids: Optional[list[str]] = None,
    user_ids: Optional[list[str]] = None,
    note: str = "",
) -> dict:
    """Approve unified campaign action: block sender & links, purge messages, and alert every recipient.

    Allows removing users from the list before approval, and records exactly one audit entry per user.
    """
    details = get_campaign_details(db, campaign_key)
    excluded = set(excluded_user_ids or [])
    all_recipients = details["recipients"]

    # Filter to included users
    if user_ids is not None:
        target_recipients = [r for r in all_recipients if r["user_id"] in user_ids and r["user_id"] not in excluded]
    else:
        target_recipients = [r for r in all_recipients if r["user_id"] not in excluded]

    if not target_recipients:
        raise WorkflowError("no recipients selected for campaign action", 400)

    sender_domain = details["sender_domain"]
    sample_subject = details["subject"]
    sample_sender = details["sender"]
    links = details["links"]

    processed_users = []
    actions_created_or_updated = 0

    for r in target_recipients:
        uid = r["user_id"]
        cid = r["case_id"]
        case = db.get(CaseRow, cid) if cid else None

        # If user has no case, open one for the campaign incident
        if case is None:
            case = CaseRow(
                user_id=uid,
                as_of=utcnow(),
                score=r.get("score") or 75,
                email_score=r.get("score") or 75,
                login_score=0,
                band=r.get("band") or "high",
                status="investigating",
                campaign_key=campaign_key,
                campaign_size=details["total_recipients"],
                headline=f"Phishing campaign: {sample_subject}",
                assignee=actor,
            )
            db.add(case)
            db.flush()

        # Build/update the 4 unified campaign actions on the user's case
        action_specs = [
            ("block_sender_domain", f"Block sender domain ({sender_domain})", f"Sender domain {sender_domain} blocked across campus mail and DNS.", True, "dns.block_domain"),
            ("block_urls", "Block the link URLs", f"Blocked {len(links)} flagged campaign URLs at web filter.", True, "dns.block_url"),
            ("remove_from_mailboxes", f"Remove message from mailbox ({r.get('email') or uid})", f"Purged phishing message '{sample_subject}' from mailbox.", False, "mail.purge"),
            ("send_user_alert", "Send user verification alert", "Phishing notification alert dispatched to user.", True, "notify.user"),
        ]

        existing_actions = {a.code: a for a in db.scalars(select(ActionRow).where(ActionRow.case_id == case.id)).all()}

        for order, (code, label, detail, reversible, connector) in enumerate(action_specs, start=1):
            act = existing_actions.get(code)
            if act is None:
                act = ActionRow(
                    case_id=case.id,
                    order=order,
                    code=code,
                    label=label,
                    detail=detail,
                    reversible=reversible,
                    requires_approval=True,
                    connector=connector,
                    status="approved",
                    decided_by=actor,
                    decided_at=utcnow(),
                    note=f"Campaign action approved for {campaign_key}: {note}".strip(),
                )
                db.add(act)
                actions_created_or_updated += 1
            else:
                act.status = "approved"
                act.decided_by = actor
                act.decided_at = utcnow()
                act.note = f"Campaign action approved for {campaign_key}: {note}".strip()
                actions_created_or_updated += 1

        # Alert the recipient: create NotificationRow for user
        db.add(NotificationRow(
            user_id=uid,
            case_id=case.id,
            title="Security Alert: Phishing message removed",
            body=(
                f"A phishing message with subject '{sample_subject}' sent from '{sample_sender}' was delivered to your mailbox. "
                "The message has been purged from your inbox and related sender addresses and links have been blocked. "
                "If you did not click links or reply to the email, no further action is required."
            ),
            ts=utcnow(),
        ))

        # Record ONE audit entry per user
        audit(
            db,
            actor=actor,
            role=role,
            event="campaign_action_approved",
            case_id=case.id,
            detail={
                "campaign_key": campaign_key,
                "user_id": uid,
                "actions": ["block_sender_domain", "block_urls", "remove_from_mailboxes", "send_user_alert"],
                "note": note,
            },
        )
        case.status = "investigating"
        case.assignee = case.assignee or actor
        case.updated_at = utcnow()
        processed_users.append(uid)

    db.flush()
    return {
        "campaign_key": campaign_key,
        "status": "approved",
        "affected_users": processed_users,
        "affected_count": len(processed_users),
        "excluded_count": len(excluded),
        "actions_updated": actions_created_or_updated,
        "audit_entries_recorded": len(processed_users),
    }


def undo_campaign_action(db: Session, campaign_key: str, actor: str, role: str, note: str = "") -> dict:
    """Undo the campaign action where actions are reversible.

    Reversible actions (block_sender_domain, block_urls, send_user_alert) are undone.
    Irreversible actions (remove_from_mailboxes) are retained with explanatory note.
    Records exactly one audit entry per recipient user.
    """
    details = get_campaign_details(db, campaign_key)
    recipients = details["recipients"]
    reversed_users = []

    for r in recipients:
        uid = r["user_id"]
        cid = r["case_id"]
        case = db.get(CaseRow, cid) if cid else None
        if not case:
            continue

        actions = db.scalars(select(ActionRow).where(ActionRow.case_id == case.id)).all()
        reversed_codes = []
        retained_codes = []

        for a in actions:
            if a.code in ("block_sender_domain", "block_urls", "send_user_alert"):
                if a.reversible and a.status == "approved":
                    a.status = "proposed"
                    a.decided_by = None
                    a.decided_at = None
                    a.note = f"Reversed by campaign undo ({actor}): {note}".strip()
                    reversed_codes.append(a.code)
            elif a.code == "remove_from_mailboxes":
                # Message purge is irreversible: retain as approved
                retained_codes.append(a.code)

        if reversed_codes or retained_codes:
            # Record exactly ONE audit entry per user
            audit(
                db,
                actor=actor,
                role=role,
                event="campaign_action_undone",
                case_id=case.id,
                detail={
                    "campaign_key": campaign_key,
                    "user_id": uid,
                    "reversed_actions": reversed_codes,
                    "retained_irreversible_actions": retained_codes,
                    "note": note,
                },
            )
            case.status = "investigating"
            case.resolved_at = None
            case.updated_at = utcnow()
            reversed_users.append(uid)

    db.flush()
    return {
        "campaign_key": campaign_key,
        "status": "undone",
        "affected_users": reversed_users,
        "affected_count": len(reversed_users),
        "reversed_actions": ["block_sender_domain", "block_urls", "send_user_alert"],
        "retained_irreversible_actions": ["remove_from_mailboxes"],
        "audit_entries_recorded": len(reversed_users),
    }

