"""Read-side queries for the dashboard, reports page and incident report export."""
from __future__ import annotations

import json
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import case as sql_case, func, select
from sqlalchemy.orm import Session

from .engine import config as cfgmod
from .models import ActionRow, AuditRow, CaseRow, EmailRow, FeedbackRow, LoginRow, UserRow
from .services import aware

BANDS = ["critical", "high", "medium", "low"]


def iso(dt: Optional[datetime]) -> Optional[str]:
    dt = aware(dt)
    return dt.isoformat() if dt else None


def _day(dt) -> str:
    return aware(dt).date().isoformat()


def overview(db: Session, days: int = 14) -> dict:
    cfg = cfgmod.get()
    med = cfg["bands"]["medium"][0]
    last_login = db.scalar(select(func.max(LoginRow.ts)))
    last_mail = db.scalar(select(func.max(EmailRow.received_at)))
    ref = max([aware(x) for x in (last_login, last_mail) if x] or [datetime.now(timezone.utc)])
    since = ref - timedelta(days=days)

    n_emails = db.scalar(select(func.count(EmailRow.id))) or 0
    n_logins = db.scalar(select(func.count(LoginRow.id))) or 0
    flagged_emails = db.scalar(select(func.count(EmailRow.id)).where(EmailRow.risk >= med)) or 0
    flagged_logins = db.scalar(select(func.count(LoginRow.id)).where(LoginRow.risk >= med)) or 0
    band_counts = dict(db.execute(select(CaseRow.band, func.count(CaseRow.id)).where(CaseRow.status.in_(("open", "investigating"))).group_by(CaseRow.band)).all())
    status_counts = dict(db.execute(select(CaseRow.status, func.count(CaseRow.id)).group_by(CaseRow.status)).all())
    n_cases = sum(status_counts.values())
    needs_review = db.scalar(select(func.count(CaseRow.id)).where(CaseRow.band != "low")) or 0
    events = n_emails + n_logins

    # activity by day (flagged emails, flagged logins)
    em_by_day = Counter(_day(r) for (r,) in db.execute(select(EmailRow.received_at).where(EmailRow.received_at >= since, EmailRow.risk >= med)))
    lg_by_day = Counter(_day(r) for (r,) in db.execute(select(LoginRow.ts).where(LoginRow.ts >= since, LoginRow.risk >= med)))
    activity = []
    for i in range(days, -1, -1):
        d = (ref - timedelta(days=i)).date().isoformat()
        activity.append({"day": d[5:], "phishing_emails": em_by_day.get(d, 0), "suspicious_logins": lg_by_day.get(d, 0)})

    # logins by country
    by_country = defaultdict(lambda: {"total": 0, "flagged": 0, "failed": 0})
    for country, success, risk in db.execute(select(LoginRow.country, LoginRow.success, LoginRow.risk).where(LoginRow.ts >= since)):
        k = country or "??"
        by_country[k]["total"] += 1
        by_country[k]["flagged"] += 1 if risk >= med else 0
        by_country[k]["failed"] += 0 if success else 1
    countries = sorted(({"country": k, **v} for k, v in by_country.items()), key=lambda x: (-x["flagged"], -x["total"]))[:10]

    users = {u.id: u for u in db.scalars(select(UserRow)).all()}

    def brief(c: CaseRow) -> dict:
        u = users.get(c.user_id)
        return {"id": c.id, "user_id": c.user_id, "user": u.name if u else c.user_id, "score": c.score, "band": c.band, "status": c.status,
                "headline": c.headline, "updated_at": iso(c.updated_at), "campaign_size": c.campaign_size}

    recent = db.scalars(select(CaseRow).where(CaseRow.band != "low").order_by(CaseRow.updated_at.desc(), CaseRow.id.desc()).limit(8)).all()
    top = db.scalars(select(CaseRow).where(CaseRow.status.in_(("open", "investigating"))).order_by(CaseRow.score.desc(), CaseRow.id).limit(6)).all()
    action_needed = db.scalars(select(CaseRow).where(CaseRow.band.in_(("high", "critical")), CaseRow.status.in_(("open", "investigating")))
                               .order_by(CaseRow.score.desc(), CaseRow.id).limit(8)).all()
    pending = dict(db.execute(select(ActionRow.case_id, func.count(ActionRow.id)).where(ActionRow.status == "proposed", ActionRow.requires_approval.is_(True)).group_by(ActionRow.case_id)).all())
    resolved = db.execute(select(CaseRow.created_at, CaseRow.resolved_at).where(CaseRow.status == "resolved", CaseRow.resolved_at.isnot(None))).all()
    mttr = None
    if resolved:
        mttr = round(sum((aware(b) - aware(a)).total_seconds() for a, b in resolved) / len(resolved) / 3600, 2)
    return {
        "reference_time": ref.isoformat(),
        "kpis": {
            "emails_analyzed": n_emails, "phishing_emails": flagged_emails, "logins_scored": n_logins, "suspicious_logins": flagged_logins,
            "critical_incidents": band_counts.get("critical", 0), "open_cases": status_counts.get("open", 0) + status_counts.get("investigating", 0),
        },
        "triage": {"events_scored": events, "cases_opened": n_cases, "needs_review": needs_review, "auto_closed": status_counts.get("auto_closed", 0),
                   "review_share": round(needs_review / events, 4) if events else 0.0, "mean_hours_to_resolve": mttr},
        "open_by_band": {b: band_counts.get(b, 0) for b in BANDS},
        "activity": activity, "countries": countries,
        "email_mix": {"flagged": flagged_emails, "clean": max(n_emails - flagged_emails, 0)},
        "recent_alerts": [brief(c) for c in recent], "top_users": [brief(c) for c in top],
        "action_needed": [{**brief(c), "pending_approvals": pending.get(c.id, 0)} for c in action_needed],
    }


def campaigns(db: Session) -> list[dict]:
    cfg = cfgmod.get()
    med = cfg["bands"]["medium"][0]
    out = []
    for key, n_users, first, last, risk in db.execute(
        select(EmailRow.campaign_key, func.count(func.distinct(EmailRow.user_id)), func.min(EmailRow.received_at), func.max(EmailRow.received_at), func.max(EmailRow.risk))
        .where(EmailRow.risk >= med, EmailRow.campaign_key != "").group_by(EmailRow.campaign_key).order_by(func.max(EmailRow.risk).desc())):
        sample = db.scalars(select(EmailRow).where(EmailRow.campaign_key == key).limit(1)).first()
        open_cases = db.scalar(select(func.count(CaseRow.id)).where(CaseRow.campaign_key == key, CaseRow.status.in_(("open", "investigating")))) or 0
        out.append({"key": key, "recipients": n_users, "first_seen": iso(first), "last_seen": iso(last), "max_email_score": risk,
                    "sender": sample.sender if sample else "", "subject": sample.subject if sample else "", "open_cases": open_cases})
    return sorted(out, key=lambda x: (-x["recipients"], -x["max_email_score"]))


def signal_frequency(db: Session) -> list[dict]:
    """How often each reason code contributed points across cases, and how often it appears in false positives."""
    freq, fp = Counter(), Counter()
    labels = {}
    verdict = {c.id: c.verdict for c in db.scalars(select(CaseRow)).all()}
    for cid, rj in db.execute(select(CaseRow.id, CaseRow.result_json)):
        for e in json.loads(rj or "{}").get("ledger", []):
            if e["points"] > 0 and e["side"] in ("email", "login", "correlation"):
                freq[e["code"]] += 1
                labels[e["code"]] = e["label"]
                if verdict.get(cid) == "false_positive":
                    fp[e["code"]] += 1
    return [{"code": c, "label": labels[c], "cases": n, "false_positive_cases": fp.get(c, 0)} for c, n in freq.most_common(14)]


def reports(db: Session, days: int = 30) -> dict:
    ref = max([aware(x) for x in (db.scalar(select(func.max(CaseRow.updated_at))),) if x] or [datetime.now(timezone.utc)])
    since = ref - timedelta(days=days)
    users = {u.id: u for u in db.scalars(select(UserRow)).all()}
    by_band_day: dict[str, dict[str, int]] = defaultdict(lambda: {b: 0 for b in BANDS})
    for created, band in db.execute(select(CaseRow.created_at, CaseRow.band).where(CaseRow.created_at >= since)):
        by_band_day[_day(created)][band] += 1
    trend = [{"day": d[5:], **v} for d, v in sorted(by_band_day.items())]
    risky = []
    for uid, mx, n in db.execute(select(CaseRow.user_id, func.max(CaseRow.score), func.count(CaseRow.id)).group_by(CaseRow.user_id).order_by(func.max(CaseRow.score).desc()).limit(15)):
        u = users.get(uid)
        risky.append({"user_id": uid, "user": u.name if u else uid, "dept": u.dept if u else "", "max_score": mx, "cases": n})
    dept = defaultdict(lambda: {"cases": 0, "high_or_critical": 0})
    for uid, band in db.execute(select(CaseRow.user_id, CaseRow.band)):
        d = users[uid].dept if uid in users else "Unknown"
        dept[d]["cases"] += 1
        dept[d]["high_or_critical"] += 1 if band in ("high", "critical") else 0
    verdicts = dict(db.execute(select(FeedbackRow.verdict, func.count(FeedbackRow.id)).group_by(FeedbackRow.verdict)).all())
    history = db.scalars(select(AuditRow).order_by(AuditRow.ts.desc(), AuditRow.id.desc()).limit(40)).all()
    return {
        "trend": trend, "risky_users": risky,
        "departments": sorted(({"dept": k, **v} for k, v in dept.items()), key=lambda x: -x["high_or_critical"]),
        "signals": signal_frequency(db), "verdicts": {"true_positive": verdicts.get("true_positive", 0), "false_positive": verdicts.get("false_positive", 0)},
        "history": [{"ts": iso(a.ts), "actor": a.actor, "role": a.role, "event": a.event, "case_id": a.case_id, "detail": a.detail} for a in history],
        "overview": overview(db)["triage"],
    }


def case_markdown(case: CaseRow, user: Optional[UserRow], actions: list[ActionRow], audit_rows: list[AuditRow]) -> str:
    res = json.loads(case.result_json or "{}")
    nar = json.loads(case.narrative_json or "{}")
    name = user.name if user else case.user_id
    L = [f"# Incident report: case #{case.id}", "",
         f"- **User:** {name} ({user.email if user else case.user_id})",
         f"- **Band / score:** {case.band.title()} / {case.score}  (email {case.email_score}, login {case.login_score})",
         f"- **Status:** {case.status.replace('_', ' ')}" + (f", assigned to {case.assignee}" if case.assignee else ""),
         f"- **Opened:** {iso(case.created_at)}   **Evidence as of:** {iso(case.as_of)}",
         f"- **Formula:** {res.get('extras', {}).get('formula', '')}", "",
         "## What happened", "", nar.get("summary", ""), ""]
    if case.low_confidence:
        L += [f"> Low confidence: {res.get('low_confidence_reason', '')}", ""]
    L += ["## Evidence ledger", "", "| Code | Evidence | Points |", "|---|---|---|"]
    for e in res.get("ledger", []):
        capped = f" (capped from {e['raw_points']})" if e["side"] in ("email", "login") and e["points"] != e["raw_points"] else ""
        L.append(f"| {e['code']} | {e['label']}: {e['detail']} | {e['points']:+d}{capped} |")
    L += ["", "## Timeline", ""] + [f"- {t['ts'][:16].replace('T', ' ')} UTC: {t['text']}" for t in res.get("timeline", [])]
    if res.get("not_evaluated"):
        L += ["", "## Not checked", ""] + [f"- {x}" for x in res["not_evaluated"]]
    L += ["", "## Response", "", "| # | Action | Status | Decided by |", "|---|---|---|---|"]
    for a in actions:
        L.append(f"| {a.order} | {a.label} | {a.status.replace('_', ' ')} | {a.decided_by or ''} |")
    L += ["", "## Audit trail", ""] + [f"- {iso(a.ts)[:19].replace('T', ' ')} {a.actor} ({a.role}): {a.event} {a.detail}" for a in audit_rows]
    L += ["", "_Generated by TraceGuard. Scores come from the evidence ledger above; the narrative only restates it._"]
    return "\n".join(L)
