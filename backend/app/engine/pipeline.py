"""Case analysis: score the email side and the login side for one user, then correlate them.

S = min(100, max(E, L) + uplift * min(E, L)) when a suspicious login follows a risky email within the
correlation window; otherwise S = max(E, L). The uplift is its own ledger line, so the final number
is always explainable as: the stronger side, plus a visible bonus for the email-then-login pattern.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Iterable, Optional

from . import config as cfgmod
from .email_signals import EmailAnalysis, analyze_email
from .login_signals import analyze_logins
from .scoring import make, rnd
from .text_model import TextModel
from .types import CaseResult, EmailEvent, Evidence, GlobalContext, LoginEvent


def build_context(all_logins: Iterable[LoginEvent], window_hours: int, as_of: datetime) -> GlobalContext:
    """Derive cross-user facts from a login stream: IPs hitting many accounts, shared devices."""
    from collections import defaultdict
    start = as_of - timedelta(hours=window_hours)
    ip_users: dict[str, set] = defaultdict(set)
    dev_users: dict[str, set] = defaultdict(set)
    for e in all_logins:
        if e.ip and start < e.ts <= as_of:
            ip_users[e.ip].add(e.user_id)
        if e.device and e.ip and e.success:
            dev_users[f"{e.device}@{e.ip}"].add(e.user_id)   # a lab PC = many users succeeding from one device on one network
    return GlobalContext(ip_user_counts={k: len(v) for k, v in ip_users.items()},
                         device_user_counts={k: len(v) for k, v in dev_users.items()})


def analyze_case(user_id: str, emails: list[EmailEvent], logins: list[LoginEvent], cfg: Optional[dict] = None,
                 ctx: Optional[GlobalContext] = None, as_of: Optional[datetime] = None, model: Optional[TextModel] = None,
                 disabled_login_signals: Optional[set[str]] = None) -> CaseResult:
    cfg = cfg or cfgmod.get()
    ctx = ctx or GlobalContext()
    stamps = [e.received_at for e in emails] + [l.ts for l in logins]
    as_of = as_of or (max(stamps) if stamps else datetime.now().astimezone())

    # ---------- email side ----------
    e_start = as_of - timedelta(hours=cfg["email"]["window_hours"])
    in_window = [e for e in emails if e_start <= e.received_at <= as_of]
    analyses: list[tuple[EmailEvent, EmailAnalysis]] = [(e, analyze_email(e, cfg, model)) for e in in_window]
    top_em: Optional[EmailEvent] = None
    top_an: Optional[EmailAnalysis] = None
    if analyses:
        top_em, top_an = max(analyses, key=lambda pair: (pair[1].score, pair[0].received_at))
    E = top_an.score if top_an else 0

    # ---------- login side ----------
    la = analyze_logins(logins, cfg, ctx, as_of, disabled_login_signals)
    L = la.score

    # ---------- correlation ----------
    corr = cfg["correlation"]
    correlated = False
    gap_text = ""
    if E >= corr["min_email_score"] and L >= corr["min_login_score"] and top_em is not None and la.first_suspicious_ts is not None:
        gap = la.first_suspicious_ts - top_em.received_at
        if timedelta(0) <= gap <= timedelta(hours=corr["window_hours"]):
            correlated = True
            mins = int(gap.total_seconds() // 60)
            gap_text = f"suspicious login {mins} min after the email" if mins < 120 else f"suspicious login {mins / 60:.1f} h after the email"
    ledger: list[Evidence] = []
    if top_an:
        ledger += top_an.ledger
    ledger += la.ledger
    uplift_pts = 0
    if correlated:
        uplift_pts = rnd(corr["uplift"] * min(E, L))
        ledger.append(Evidence(
            code="X_EMAIL_THEN_LOGIN", side="correlation", label="Risky email followed by a suspicious login",
            detail=f"{gap_text}; adds {corr['uplift']:g} x the weaker side ({min(E, L)})", points=uplift_pts, raw_points=uplift_pts, group="correlation"))
    raw_case = max(E, L) + uplift_pts
    S = min(100, raw_case)
    if raw_case > 100:
        ledger.append(Evidence(code="CASE_CAP", side="cap", label="Case score capped at 100", detail="", points=100 - raw_case,
                               raw_points=0, group="cap"))
    ceiling = corr["email_only_ceiling"]
    if not correlated and E >= L and S > ceiling:
        ledger.append(Evidence(
            code="EMAIL_ONLY_CEILING", side="cap", label="Email alone stops at High",
            detail="A message is a threat, not an incident, until a suspicious login follows it. Critical needs login evidence.",
            points=ceiling - S, raw_points=0, group="cap"))
        S = ceiling
    band = cfgmod.band_of(S, cfg)

    not_eval = list(top_an.not_evaluated) if top_an else []
    if E >= corr["min_email_score"] and L >= corr["min_login_score"] and not correlated:
        not_eval.append("Email and login evidence both exist but the login did not follow the email within the correlation window, so no uplift was applied.")

    # ---------- timeline ----------
    timeline: list[dict] = []
    if top_em is not None:
        timeline.append({"ts": top_em.received_at.isoformat(), "kind": "email", "text": f"Email received: \"{top_em.subject[:80]}\" from {top_em.sender or 'unknown sender'}",
                         "severity": band if E >= cfg["bands"]["medium"][0] else "low"})
    for l in la.window_logins:
        if l.ts.isoformat() in set(la.refs) or not l.success:
            place = ", ".join(x for x in (l.city, l.country) if x) or "unknown location"
            timeline.append({"ts": l.ts.isoformat(), "kind": "login", "text": f"{'Successful' if l.success else 'Failed'} login from {place}" + (f" on {l.device}" if l.device else ""),
                             "severity": "high" if l.ts.isoformat() in set(la.refs) else "low"})
    timeline.sort(key=lambda t: t["ts"])
    if len(timeline) > 14:                       # keep the page readable on credential-stuffing bursts
        timeline = timeline[:6] + [{"ts": timeline[6]["ts"], "kind": "note", "text": f"... {len(timeline) - 12} more events ...", "severity": "low"}] + timeline[-6:]

    base = la.baseline.summary() if la.baseline else {}
    low_conf = bool(la.low_confidence and L > 0)
    reason = ""
    if low_conf:
        reason = (f"Only {base.get('n_success', 0)} earlier successful logins on record, so new-place, new-device and odd-hour points "
                  f"were halved. Treat the login evidence as a prompt to ask the user, not as proof.")

    return CaseResult(
        user_id=user_id, as_of=as_of, email_score=E, login_score=L, score=S, band=band, ledger=ledger,
        low_confidence=low_conf, low_confidence_reason=reason,
        email_ids=[e.id for e in in_window], top_email_id=top_em.id if top_em else None,
        login_refs=la.refs, correlated=correlated,
        text_terms=top_an.terms if top_an else [], text_probability=top_an.probability if top_an else None,
        not_evaluated=not_eval, campaign_key=top_an.campaign_key if (top_an and E >= cfg["bands"]["medium"][0]) else None,
        timeline=timeline, suspicious_login=la.suspicious,
        extras={
            "auth": top_an.auth_summary if top_an else {},
            "flagged_links": top_an.flagged_links if top_an else [],
            "baseline": base,
            "uplift": uplift_pts,
            "formula": (f"S = min(100, max(E, L) + {corr['uplift']:g} x min(E, L)) = min(100, {max(E, L)} + {uplift_pts}) = {S}" if correlated
                        else f"S = max(E, L) = {max(E, L)}" + (f", held at {S} because an email alone stops at High" if S != max(E, L) else " (no email-then-login link, so no uplift)")),
            "top_email": ({"id": top_em.id, "sender": top_em.sender, "subject": top_em.subject, "reply_to": top_em.reply_to,
                           "received_at": top_em.received_at.isoformat(), "links": [{"href": l.href, "text": l.text} for l in top_em.links[:12]],
                           "has_headers": top_em.has_headers, "hidden_text_found": bool(top_em.hidden_text)} if top_em else None),
        })
