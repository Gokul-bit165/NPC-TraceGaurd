"""TraceGuard API. One FastAPI service: detection engine, case workflow, reports, and the built React app."""
from __future__ import annotations

import copy
import json
from contextlib import asynccontextmanager
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

import yaml
from fastapi import Depends, FastAPI, File, Form, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from . import reports, scenarios as sc, services
from .auth import Actor, assert_owns, require_actor, require_admin, require_staff
from .db import SessionLocal, get_db, init_db
from .engine import config as cfgmod
from .engine import explain, respond
from .engine.baseline import build_baseline
from .engine.counter import get_cross_user_counter
from .engine.email_parse import from_fields, parse_eml
from .engine.pipeline import analyze_case, build_context
from .engine.queue import get_analysis_queue, start_analysis_queue
from .engine.text_model import MODEL_DIR, get_model
from .engine.types import LoginEvent
from .models import ActionRow, AuditRow, CaseRow, EmailRow, LoginRow, NotificationRow, UserRow
from .reports import iso
from .services import WorkflowError, aware

@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    get_model()          # train/load once so the first request is not slow
    with SessionLocal() as db:
        get_cross_user_counter().warmup_from_db(db)
    q = start_analysis_queue()
    try:
        yield
    finally:
        q.stop(drain=True)


app = FastAPI(title="TraceGuard", version="1.0.0", lifespan=lifespan,
              description="Correlates phishing-email evidence with login evidence into one explainable, graded incident.")
app.add_middleware(CORSMiddleware, allow_origins=os.environ.get("TRACEGUARD_CORS", "*").split(","), allow_methods=["*"], allow_headers=["*"])


# ------------------------------------------------------------------ auth
# Auth logic lives in app.auth.  In demo mode (TRACEGUARD_DEMO_AUTH=1, the default)
# the role is read from the X-Role header, matching the old behaviour exactly.
# Set TRACEGUARD_DEMO_AUTH=0 and configure TRACEGUARD_OIDC_* env vars to enable
# real OIDC/JWT validation against a campus SSO.


@app.exception_handler(WorkflowError)
def _wf(_, exc: WorkflowError):
    from fastapi.responses import JSONResponse
    return JSONResponse(status_code=exc.status, content={"detail": str(exc)})


# ------------------------------------------------------------------ serialisers
def user_brief(u: Optional[UserRow], uid: str) -> dict:
    return {"id": uid, "name": u.name if u else uid, "email": u.email if u else "", "dept": u.dept if u else "", "role": u.role if u else ""}


def case_brief(c: CaseRow, u: Optional[UserRow], pending: int = 0) -> dict:
    return {"id": c.id, "user": user_brief(u, c.user_id), "score": c.score, "email_score": c.email_score, "login_score": c.login_score, "band": c.band,
            "status": c.status, "headline": c.headline, "correlated": c.correlated, "low_confidence": c.low_confidence, "campaign_size": c.campaign_size,
            "assignee": c.assignee, "verdict": c.verdict, "scenario": c.scenario_key, "updated_at": iso(c.updated_at), "created_at": iso(c.created_at),
            "pending_approvals": pending}


def action_dict(a: ActionRow) -> dict:
    return {"id": a.id, "order": a.order, "code": a.code, "label": a.label, "detail": a.detail, "reversible": a.reversible, "requires_approval": a.requires_approval,
            "connector": a.connector, "depends_on": a.depends_on, "status": a.status, "decided_by": a.decided_by, "decided_at": iso(a.decided_at), "note": a.note}


# ------------------------------------------------------------------ health
@app.get("/api/health")
def health(db: Session = Depends(get_db)):
    q = get_analysis_queue()
    return {"status": "ok", "time": datetime.now(timezone.utc).isoformat(), "cases": db.scalar(select(func.count(CaseRow.id))),
            "text_model": get_model().meta.get("source", "unknown"), "llm_narrator": explain._llm is not None,
            "queue": q.stats}


@app.get("/api/queue")
def queue_status(a: Actor = Depends(require_staff)):
    return get_analysis_queue().stats


# ------------------------------------------------------------------ dashboard & reports
@app.get("/api/overview")
def overview(days: int = Query(14, ge=1, le=90), db: Session = Depends(get_db), a: Actor = Depends(require_staff)):
    return reports.overview(db, days)


@app.get("/api/reports")
def get_reports(days: int = Query(30, ge=1, le=365), db: Session = Depends(get_db), a: Actor = Depends(require_staff)):
    return reports.reports(db, days)


@app.get("/api/campaigns")
def get_campaigns(db: Session = Depends(get_db), a: Actor = Depends(require_staff)):
    return reports.campaigns(db)


@app.get("/api/campaigns/{campaign_key}")
def get_campaign(campaign_key: str, db: Session = Depends(get_db), a: Actor = Depends(require_staff)):
    return services.get_campaign_details(db, campaign_key)


class CampaignActionBody(BaseModel):
    excluded_user_ids: list[str] = []
    user_ids: Optional[list[str]] = None
    note: str = ""


@app.post("/api/campaigns/{campaign_key}/action")
def approve_campaign_action_endpoint(
    campaign_key: str, body: CampaignActionBody, db: Session = Depends(get_db), a: Actor = Depends(require_staff)
):
    res = services.approve_campaign_action(
        db, campaign_key, actor=a.name, role=a.role,
        excluded_user_ids=body.excluded_user_ids, user_ids=body.user_ids, note=body.note
    )
    db.commit()
    return res


class CampaignUndoBody(BaseModel):
    note: str = ""


@app.post("/api/campaigns/{campaign_key}/undo")
def undo_campaign_action_endpoint(
    campaign_key: str, body: CampaignUndoBody = CampaignUndoBody(), db: Session = Depends(get_db), a: Actor = Depends(require_staff)
):
    res = services.undo_campaign_action(db, campaign_key, actor=a.name, role=a.role, note=body.note)
    db.commit()
    return res


# ------------------------------------------------------------------ analyst notifications
@app.get("/api/notifications/daily-summary")
def preview_daily_summary(date: Optional[str] = None, db: Session = Depends(get_db), a: Actor = Depends(require_staff)):
    from .engine import notifications
    d = datetime.fromisoformat(date) if date else None
    summary_text, meta = notifications.generate_daily_summary(db, d)
    return {"summary": summary_text, "meta": meta}


class DailySummarySendBody(BaseModel):
    date: Optional[str] = None
    channel: str = "both"


@app.post("/api/notifications/daily-summary")
def trigger_daily_summary(body: DailySummarySendBody = DailySummarySendBody(), db: Session = Depends(get_db), a: Actor = Depends(require_staff)):
    from .engine import notifications
    d = datetime.fromisoformat(body.date) if body.date else None
    msgs = notifications.send_daily_summary(db, d, channel=body.channel)
    return {"sent": len(msgs), "messages": [m.to_dict() for m in msgs]}


@app.get("/api/notifications/sent")
def get_sent_notifications(a: Actor = Depends(require_staff)):
    from .engine import notifications
    msgs = notifications.get_notification_sender().sent_messages
    return {"total": len(msgs), "messages": [m.to_dict() for m in msgs]}


@app.get("/api/audit")
def get_audit(case_id: Optional[int] = None, limit: int = Query(100, le=500), db: Session = Depends(get_db), a: Actor = Depends(require_staff)):
    q = select(AuditRow).order_by(AuditRow.ts.desc(), AuditRow.id.desc()).limit(limit)
    if case_id:
        q = q.where(AuditRow.case_id == case_id)
    return [{"id": r.id, "ts": iso(r.ts), "actor": r.actor, "role": r.role, "event": r.event, "case_id": r.case_id, "detail": r.detail} for r in db.scalars(q)]


# ------------------------------------------------------------------ page 2: phishing email investigation
@app.post("/api/emails/analyze")
async def analyze_email_endpoint(
    file: Optional[UploadFile] = File(None), sender: str = Form(""), subject: str = Form(""), body: str = Form(""), urls: str = Form(""),
    reply_to: str = Form(""), recipient: str = Form(""), save: bool = Form(False),
    db: Session = Depends(get_db), a: Actor = Depends(require_staff),
):
    """Analyse an uploaded .eml or typed fields. Dry run unless `save` is true and the recipient is a known user."""
    cfg = cfgmod.get()
    target = services.resolve_user(db, recipient) if recipient else None
    uid = target.id if target else "unattributed"
    now = datetime.now(timezone.utc)
    if file is not None and file.filename:
        raw = await file.read()
        if len(raw) > 5_000_000:
            raise HTTPException(413, "file too large (5 MB limit)")
        try:
            em = parse_eml(raw, uid, None)
        except Exception as exc:
            raise HTTPException(422, f"could not parse the email file: {exc}")
    else:
        if not (sender or subject or body):
            raise HTTPException(422, "upload a .eml file or enter at least a sender, subject or body")
        em = from_fields(uid, sender, subject, body, [u.strip() for u in urls.splitlines() if u.strip()], reply_to, now)
    em.received_at = em.received_at if em.has_headers else now
    res = analyze_case(uid, [em], [], cfg, as_of=em.received_at)
    name = target.name if target else "the recipient"
    nar = explain.narrate(res, name)
    out = {
        "email": {"id": em.id, "sender": em.sender, "subject": em.subject, "reply_to": em.reply_to, "has_headers": em.has_headers,
                  "links": [{"href": l.href, "text": l.text} for l in em.links], "hidden_text_found": bool(em.hidden_text),
                  "preview": em.body_text[:600]},
        "score": res.email_score, "band": cfgmod.band_of(min(res.email_score, cfg["correlation"]["email_only_ceiling"]), cfg),
        "probability": res.text_probability, "terms": res.text_terms, "ledger": [e.to_dict() for e in res.ledger if e.side in ("email", "cap")],
        "flagged_links": res.extras.get("flagged_links", []), "auth": res.extras.get("auth", {}), "not_evaluated": res.not_evaluated,
        "narrative": nar, "campaign_key": res.campaign_key, "saved_case_id": None,
    }
    if save:
        if not target:
            raise HTTPException(422, "to save, name a known recipient (user id, e-mail or name)")
        services.add_email(db, em, cfg)
        services.audit(db, a.name, a.role, "email_ingested", None, {"email": em.id, "recipient": target.id})
        case = services.reanalyze_user(db, target.id, actor=a.name)
        db.commit()
        out["saved_case_id"] = case.id if case else None
    return out


# ------------------------------------------------------------------ page 3: suspicious login investigation
@app.get("/api/logins")
def list_logins(q: str = "", country: str = "", city: str = "", device: str = "", risk: str = "", success: Optional[bool] = None,
                start: Optional[str] = None, end: Optional[str] = None, unusual_only: bool = False,
                limit: int = Query(50, le=200), offset: int = 0, db: Session = Depends(get_db), a: Actor = Depends(require_staff)):
    cfg = cfgmod.get()
    stmt = select(LoginRow, UserRow).join(UserRow, UserRow.id == LoginRow.user_id, isouter=True)
    if q:
        like = f"%{q.lower()}%"
        stmt = stmt.where(or_(func.lower(LoginRow.user_id).like(like), func.lower(UserRow.name).like(like), func.lower(UserRow.email).like(like), LoginRow.ip.like(f"%{q}%")))
    if country:
        stmt = stmt.where(LoginRow.country == country.upper())
    if city:
        stmt = stmt.where(func.lower(LoginRow.city) == city.lower())
    if device:
        stmt = stmt.where(LoginRow.device.like(f"%{device.lower()}%"))
    if risk:
        stmt = stmt.where(LoginRow.risk_band == risk.lower())
    if success is not None:
        stmt = stmt.where(LoginRow.success.is_(success))
    if unusual_only:
        stmt = stmt.where(LoginRow.risk >= cfg["bands"]["medium"][0], LoginRow.success.is_(True))
    if start:
        stmt = stmt.where(LoginRow.ts >= services.aware(datetime.fromisoformat(start)))
    if end:
        stmt = stmt.where(LoginRow.ts <= services.aware(datetime.fromisoformat(end)))
    total = db.scalar(select(func.count()).select_from(stmt.subquery()))
    rows = db.execute(stmt.order_by(LoginRow.ts.desc()).limit(limit).offset(offset)).all()
    return {"total": total, "items": [
        {"id": r.id, "user": user_brief(u, r.user_id), "ts": iso(r.ts), "ip": r.ip, "country": r.country, "city": r.city, "device": r.device,
         "success": r.success, "risk": r.risk, "band": r.risk_band, "flags": [f for f in r.flags.split(",") if f], "attack_ip": r.is_attack_ip}
        for r, u in rows]}


@app.get("/api/users/{ident}/logins")
def user_logins(ident: str, limit: int = Query(300, le=1000), db: Session = Depends(get_db), a: Actor = Depends(require_staff)):
    u = services.resolve_user(db, ident)
    if not u:
        raise HTTPException(404, "user not found")
    cfg = cfgmod.get()
    rows = db.scalars(select(LoginRow).where(LoginRow.user_id == u.id).order_by(LoginRow.ts.desc()).limit(limit)).all()
    events = [services.login_from_row(r) for r in reversed(rows)]
    base = build_baseline(events, datetime.now(timezone.utc) + timedelta(days=1), cfg["campus"]["timezone_offset_minutes"], cfg["login"]["min_history_logins"])
    case = db.scalar(select(CaseRow).where(CaseRow.user_id == u.id).order_by(CaseRow.id.desc()))
    return {"user": user_brief(u, u.id), "baseline": base.summary(), "case_id": case.id if case else None,
            "items": [{"id": r.id, "ts": iso(r.ts), "ip": r.ip, "country": r.country, "city": r.city, "device": r.device, "success": r.success,
                       "risk": r.risk, "band": r.risk_band, "flags": [f for f in r.flags.split(",") if f]} for r in rows]}


@app.get("/api/facets")
def facets(db: Session = Depends(get_db), a: Actor = Depends(require_staff)):
    return {"countries": [c for (c,) in db.execute(select(LoginRow.country).distinct().order_by(LoginRow.country)) if c],
            "devices": [d for (d,) in db.execute(select(LoginRow.device).distinct().order_by(LoginRow.device)) if d]}


# ------------------------------------------------------------------ cases (pages 4 and 5)
@app.get("/api/cases")
def list_cases(band: str = "", status: str = "", q: str = "", sort: str = "score", scenario: bool = False,
               limit: int = Query(100, le=500), offset: int = 0, db: Session = Depends(get_db), a: Actor = Depends(require_actor)):
    stmt = select(CaseRow, UserRow).join(UserRow, UserRow.id == CaseRow.user_id, isouter=True)
    # users (role=="user") may only see their own cases
    if not a.is_staff():
        if not a.user_id:
            raise HTTPException(400, "send X-User-Id (or log in) to read your own cases")
        stmt = stmt.where(CaseRow.user_id == a.user_id)
    if band:
        stmt = stmt.where(CaseRow.band.in_(band.split(",")))
    if status == "active":
        stmt = stmt.where(CaseRow.status.in_(services.ACTIVE))
    elif status:
        stmt = stmt.where(CaseRow.status.in_(status.split(",")))
    if q and a.is_staff():   # free-text search only meaningful for staff
        like = f"%{q.lower()}%"
        stmt = stmt.where(or_(func.lower(UserRow.name).like(like), func.lower(UserRow.email).like(like), func.lower(CaseRow.user_id).like(like), func.lower(CaseRow.headline).like(like)))
    total = db.scalar(select(func.count()).select_from(stmt.subquery()))
    order = {"score": (CaseRow.score.desc(), CaseRow.campaign_size.desc()), "recent": (CaseRow.updated_at.desc(),), "campaign": (CaseRow.campaign_size.desc(), CaseRow.score.desc())}.get(sort, (CaseRow.score.desc(),))
    rows = db.execute(stmt.order_by(*order, CaseRow.id).limit(limit).offset(offset)).all()
    pending = dict(db.execute(select(ActionRow.case_id, func.count(ActionRow.id)).where(ActionRow.status == "proposed", ActionRow.requires_approval.is_(True)).group_by(ActionRow.case_id)).all())
    return {"total": total, "items": [case_brief(c, u, pending.get(c.id, 0)) for c, u in rows]}


@app.get("/api/cases/{case_id}")
def get_case(case_id: int, db: Session = Depends(get_db), a: Actor = Depends(require_actor)):
    c = db.get(CaseRow, case_id)
    if not c:
        raise HTTPException(404, "case not found")
    # users may only fetch their own case
    assert_owns(a, c.user_id)
    u = db.get(UserRow, c.user_id)
    res = json.loads(c.result_json or "{}")
    acts = db.scalars(select(ActionRow).where(ActionRow.case_id == c.id).order_by(ActionRow.order)).all()
    audits = db.scalars(select(AuditRow).where(AuditRow.case_id == c.id).order_by(AuditRow.ts, AuditRow.id)).all()
    email = None
    if c.top_email_id:
        er = db.get(EmailRow, c.top_email_id)
        if er:
            email = {"id": er.id, "sender": er.sender, "subject": er.subject, "reply_to": er.reply_to, "received_at": iso(er.received_at), "auth": json.loads(er.auth_json),
                     "links": json.loads(er.links_json), "preview": er.body_text[:800], "hidden_text_found": bool(er.hidden_text), "has_headers": er.has_headers,
                     "probability": er.probability, "raw": er.raw[:6000]}
    recent_logins = []
    refs = set(res.get("login_refs", []))
    for r in db.scalars(select(LoginRow).where(LoginRow.user_id == c.user_id, LoginRow.ts <= aware(c.as_of)).order_by(LoginRow.ts.desc()).limit(12)):
        recent_logins.append({"ts": iso(r.ts), "ip": r.ip, "country": r.country, "city": r.city, "device": r.device, "success": r.success, "risk": r.risk,
                              "flagged": iso(r.ts) in refs or any(iso(r.ts).startswith(x[:19]) for x in refs)})
    cfg = cfgmod.get()
    ctx_res = None
    return {
        "case": case_brief(c, u), "user": user_brief(u, c.user_id), "ledger": res.get("ledger", []), "timeline": res.get("timeline", []),
        "extras": res.get("extras", {}), "text_terms": res.get("text_terms", []), "text_probability": res.get("text_probability"),
        "not_evaluated": res.get("not_evaluated", []), "low_confidence_reason": res.get("low_confidence_reason", ""),
        "suspicious_login": res.get("suspicious_login"), "narrative": json.loads(c.narrative_json or "{}"),
        "actions": [action_dict(x) for x in acts], "audit": [{"ts": iso(x.ts), "actor": x.actor, "role": x.role, "event": x.event, "detail": x.detail} for x in audits],
        "email": email, "recent_logins": recent_logins, "formula": res.get("extras", {}).get("formula", ""),
        "user_alert": respond.user_alert(_stub(c, res), u.name if u else c.user_id, email["subject"] if email else None),
        "bands": cfg["bands"],
    }


def _stub(c: CaseRow, res: dict):
    """Minimal CaseResult-like object for drafting the user alert from stored evidence."""
    from .engine.types import CaseResult
    return CaseResult(user_id=c.user_id, as_of=aware(c.as_of), email_score=c.email_score, login_score=c.login_score, score=c.score, band=c.band, ledger=[],
                      low_confidence=c.low_confidence, low_confidence_reason="", email_ids=[], top_email_id=c.top_email_id, login_refs=[], correlated=c.correlated,
                      text_terms=[], text_probability=None, not_evaluated=[], campaign_key=c.campaign_key, timeline=[], suspicious_login=res.get("suspicious_login"))


class Decision(BaseModel):
    decision: str = Field(pattern="^(approve|reject)$")
    note: str = ""


@app.post("/api/cases/{case_id}/actions/{action_id}")
def decide(case_id: int, action_id: int, body: Decision, db: Session = Depends(get_db), a: Actor = Depends(require_staff)):
    act = services.decide_action(db, case_id, action_id, body.decision, a.name, a.role, body.note)
    db.commit()
    return action_dict(act)


class ActionUndoBody(BaseModel):
    note: str = ""


@app.post("/api/cases/{case_id}/actions/{action_id}/undo")
def undo_action_endpoint(
    case_id: int, action_id: int, body: ActionUndoBody = ActionUndoBody(), db: Session = Depends(get_db), a: Actor = Depends(require_staff)
):
    act = services.undo_action(db, case_id, action_id, actor=a.name, role=a.role, note=body.note)
    db.commit()
    return action_dict(act)


class StatusBody(BaseModel):
    status: str


@app.post("/api/cases/{case_id}/status")
def change_status(case_id: int, body: StatusBody, db: Session = Depends(get_db), a: Actor = Depends(require_staff)):
    c = services.set_status(db, case_id, body.status, a.name, a.role)
    db.commit()
    return case_brief(c, db.get(UserRow, c.user_id))


class VerdictBody(BaseModel):
    verdict: str


@app.post("/api/cases/{case_id}/verdict")
def verdict(case_id: int, body: VerdictBody, db: Session = Depends(get_db), a: Actor = Depends(require_staff)):
    c = services.set_verdict(db, case_id, body.verdict, a.name, a.role)
    db.commit()
    return case_brief(c, db.get(UserRow, c.user_id))


@app.post("/api/cases/{case_id}/reanalyze")
def reanalyze(case_id: int, db: Session = Depends(get_db), a: Actor = Depends(require_staff)):
    c = db.get(CaseRow, case_id)
    if not c:
        raise HTTPException(404, "case not found")
    services.reanalyze_user(db, c.user_id, actor=a.name, as_of=aware(c.as_of))
    db.commit()
    return get_case(case_id, db, a)


@app.get("/api/cases/{case_id}/report", response_class=PlainTextResponse)
def case_report(case_id: int, db: Session = Depends(get_db), a: Actor = Depends(require_staff)):
    c = db.get(CaseRow, case_id)
    if not c:
        raise HTTPException(404, "case not found")
    acts = db.scalars(select(ActionRow).where(ActionRow.case_id == c.id).order_by(ActionRow.order)).all()
    aud = db.scalars(select(AuditRow).where(AuditRow.case_id == c.id).order_by(AuditRow.ts, AuditRow.id)).all()
    return PlainTextResponse(reports.case_markdown(c, db.get(UserRow, c.user_id), acts, aud), media_type="text/markdown",
                             headers={"Content-Disposition": f'attachment; filename="traceguard-case-{c.id}.md"'})


# ------------------------------------------------------------------ student / staff view
@app.get("/api/me/alerts")
def my_alerts(db: Session = Depends(get_db), a: Actor = Depends(require_actor)):
    if not a.user_id:
        raise HTTPException(400, "send X-User-Id to read your own alerts")
    rows = db.scalars(select(NotificationRow).where(NotificationRow.user_id == a.user_id).order_by(NotificationRow.ts.desc()).limit(30)).all()
    u = db.get(UserRow, a.user_id)
    return {"user": user_brief(u, a.user_id), "items": [{"id": n.id, "ts": iso(n.ts), "title": n.title, "body": n.body, "case_id": n.case_id, "acknowledged": n.acknowledged} for n in rows]}


class Ack(BaseModel):
    answer: str = Field(pattern="^(it_was_me|not_me)$")


@app.post("/api/me/alerts/{nid}/ack")
def ack_alert(nid: int, body: Ack, db: Session = Depends(get_db), a: Actor = Depends(require_actor)):
    n = db.get(NotificationRow, nid)
    if not n or n.user_id != a.user_id:
        raise HTTPException(404, "alert not found")
    n.acknowledged = body.answer
    if n.case_id:
        services.audit(db, a.name, "user", "user_" + body.answer, n.case_id, {"alert": nid})
        if body.answer == "not_me":
            c = db.get(CaseRow, n.case_id)
            if c and c.status == "open":
                c.status = "investigating"
            c.updated_at = datetime.now(timezone.utc)
    db.commit()
    return {"ok": True, "acknowledged": n.acknowledged}


# ------------------------------------------------------------------ ingest API for connectors (SIEM, mail gateway, IdP)
class LoginIn(BaseModel):
    user_id: str
    ts: str
    ip: str = ""
    country: str = ""
    city: str = ""
    device: str = ""
    success: bool = True
    is_attack_ip: bool = False


@app.post("/api/ingest/logins")
def ingest_logins(batch: list[LoginIn], sync: bool = Query(False), db: Session = Depends(get_db), a: Actor = Depends(require_admin)):
    if len(batch) > 5000:
        raise HTTPException(413, "batch limit is 5000 events")
    events = [LoginEvent(user_id=item.user_id, ts=item.ts, ip=item.ip, country=item.country, city=item.city,
                         device=item.device.lower(), success=item.success, is_attack_ip=item.is_attack_ip)
              for item in batch]
    q = get_analysis_queue()
    if not q.is_running():
        q.start()
    job = q.enqueue(events)
    if sync or os.environ.get("TRACEGUARD_SYNC_INGEST", "").lower() in ("1", "true"):
        job.done.wait(timeout=30.0)
        return {"stored": len(events), "cases": job.result_cases}
    return {"stored": len(events), "queued": True, "cases": []}


class EmailIn(BaseModel):
    recipient: str
    raw_eml: str


@app.post("/api/ingest/email")
def ingest_email(body: EmailIn, db: Session = Depends(get_db), a: Actor = Depends(require_admin)):
    u = services.resolve_user(db, body.recipient)
    if not u:
        raise HTTPException(404, "recipient is not a known user")
    em = parse_eml(body.raw_eml, u.id)
    row, an = services.add_email(db, em)
    c = services.reanalyze_user(db, u.id, actor="ingest")
    db.commit()
    return {"email_id": row.id, "score": an.score, "case_id": c.id if c else None, "band": c.band if c else None}


# ------------------------------------------------------------------ scoring configuration
def _scenario_table(cfg: dict) -> list[dict]:
    now = datetime(2026, 1, 15, 15, 0, tzinfo=timezone.utc)      # fixed clock: results are reproducible
    scen = sc.build_all(now)
    A = sc.anchor_time(now)
    ctx = build_context(sc.all_logins(scen), cfg["login"]["window_hours"], A)
    out = []
    for s in scen:
        r = analyze_case(s.person.id, s.emails, s.logins, cfg, ctx, as_of=A)
        out.append({"key": s.key, "title": s.title, "blurb": s.blurb, "expected": s.expected_band, "actual": r.band, "ok": r.band == s.expected_band,
                    "score": r.score, "email_score": r.email_score, "login_score": r.login_score, "correlated": r.correlated})
    return out


@app.get("/api/config")
def get_config(a: Actor = Depends(require_staff)):
    return cfgmod.get()


class ConfigBody(BaseModel):
    overrides: dict = {}
    force: bool = False


def _merge(base: dict, patch: dict) -> dict:
    out = copy.deepcopy(base)
    for k, v in patch.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _merge(out[k], v)
        else:
            out[k] = v
    return out


@app.post("/api/config/simulate")
def simulate_config(body: ConfigBody, a: Actor = Depends(require_staff)):
    try:
        cfg = cfgmod.validate(_merge(cfgmod.get(), body.overrides))
    except Exception as exc:
        raise HTTPException(422, f"invalid configuration: {exc}")
    table = _scenario_table(cfg)
    return {"scenarios": table, "all_ok": all(r["ok"] for r in table)}


@app.put("/api/config")
def save_config(body: ConfigBody, db: Session = Depends(get_db), a: Actor = Depends(require_admin)):
    try:
        cfg = cfgmod.validate(_merge(cfgmod.get(), body.overrides))
    except Exception as exc:
        raise HTTPException(422, f"invalid configuration: {exc}")
    table = _scenario_table(cfg)
    if not all(r["ok"] for r in table) and not body.force:
        raise HTTPException(409, {"message": "These weights move scenarios out of their expected band. Review them or save with force.", "scenarios": table})
    path = Path(os.environ.get("TRACEGUARD_WEIGHTS", cfgmod.DEFAULT_PATH))
    path.write_text(yaml.safe_dump(cfg, sort_keys=False), encoding="utf-8")
    cfgmod.reload()
    services.audit(db, a.name, a.role, "config_changed", None, {"overrides": body.overrides, "forced": body.force})
    db.commit()
    return {"saved": True, "scenarios": table}


# ------------------------------------------------------------------ evaluation page
@app.get("/api/evaluation")
def evaluation(a: Actor = Depends(require_staff)):
    def read(name):
        p = MODEL_DIR / name
        return json.loads(p.read_text()) if p.exists() else None
    return {"scenarios": _scenario_table(cfgmod.get()), "text_model": get_model().meta, "rba": read("rba_eval.json"), "benchmark": read("benchmark.json"),
            "notes": ["Scenario results are a regression suite written by the team, not a measure of real-world accuracy.",
                      "The RBA data set is synthesised by its authors and says so; use it to test plumbing and ranking, not to claim detection rates.",
                      "The bundled text model is trained on template text unless you retrain on the Kaggle data set."]}


# ------------------------------------------------------------------ static front end
DIST = Path(__file__).resolve().parents[2] / "frontend" / "dist"
if DIST.exists():
    app.mount("/assets", StaticFiles(directory=DIST / "assets"), name="assets")

    @app.get("/{path:path}")
    def spa(path: str):
        if path.startswith("api/"):
            raise HTTPException(404)
        f = DIST / path
        return FileResponse(f if path and f.is_file() else DIST / "index.html")
