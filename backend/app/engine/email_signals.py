"""Email evidence: authentication, impersonation, links, wording, injection attempts, text model."""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from typing import Optional

from . import sanitize
from .domains import (address_domain, has_userinfo, host_of, is_ip_host, lookalike, registrable, tld_of)
from .scoring import apply_group_caps, make, rnd, side_total
from .text_model import TextModel, get_model
from .types import EmailEvent, Evidence

_DOMAIN_TEXT = re.compile(r"(?:https?://)?((?:[a-z0-9-]+\.)+[a-z]{2,})(?:/\S*)?", re.I)


@dataclass
class EmailAnalysis:
    email_id: str
    score: int = 0
    ledger: list[Evidence] = field(default_factory=list)
    probability: Optional[float] = None
    terms: list[dict] = field(default_factory=list)
    not_evaluated: list[str] = field(default_factory=list)
    campaign_key: str = ""
    flagged_links: list[dict] = field(default_factory=list)
    auth_summary: dict = field(default_factory=dict)


def campaign_key(sender: str, subject: str) -> str:
    dom = registrable(address_domain(sender))
    subj = re.sub(r"[^a-z ]+", " ", (subject or "").lower())
    subj = re.sub(r"\b(re|fwd|fw)\b", " ", subj)
    subj = re.sub(r"\s+", " ", subj).strip()
    return hashlib.sha1(f"{dom}|{subj}".encode()).hexdigest()[:10]


def _sig(cfg: dict, name: str) -> dict:
    return cfg["email"]["signals"][name]


def _auth_issue(em: EmailEvent) -> Optional[str]:
    a = em.auth or {}
    from_reg = registrable(address_domain(em.sender))
    bad = [f"{k.upper()} {a[k]}" for k in ("dmarc", "spf", "dkim") if a.get(k) in {"fail", "softfail", "permerror", "temperror"}]
    if bad:
        return ", ".join(bad)
    d = a.get("dkim_domain")
    s = a.get("spf_domain")
    if a.get("dkim") == "pass" and d and registrable(d) != from_reg and not (a.get("spf") == "pass" and s and registrable(s) == from_reg):
        return f"DKIM passes only for {registrable(d)}, not for the visible sender {from_reg}"
    if a.get("spf") == "pass" and s and registrable(s) != from_reg and a.get("dkim") != "pass":
        return f"SPF passes only for {registrable(s)}, not for the visible sender {from_reg}"
    return None


def analyze_email(em: EmailEvent, cfg: dict, model: Optional[TextModel] = None) -> EmailAnalysis:
    ec = cfg["email"]
    model = model or get_model()
    res = EmailAnalysis(email_id=em.id, campaign_key=campaign_key(em.sender, em.subject))
    items: list[Evidence] = []
    ref = em.id
    from_dom = address_domain(em.sender)
    from_reg = registrable(from_dom)

    def add(name: str, label: str, detail: str, scale: float = 1.0) -> None:
        s = _sig(cfg, name)
        items.append(make("E_" + name.upper(), "email", label, detail, s["points"] * scale, s["group"], ref))

    # --- authentication ---
    if em.has_headers and em.auth:
        res.auth_summary = {k: em.auth.get(k) for k in ("spf", "dkim", "dmarc") if em.auth.get(k)}
        issue = _auth_issue(em)
        if issue:
            add("auth_failure", "Sender authentication failed", issue)
    else:
        res.not_evaluated.append("SPF, DKIM and DMARC were not checked: no Authentication-Results header (typed fields or stripped headers). Upload the .eml to check them.")

    # --- Reply-To ---
    if em.reply_to:
        rt_reg = registrable(address_domain(em.reply_to))
        if rt_reg and from_reg and rt_reg != from_reg:
            add("reply_to_mismatch", "Reply-To points to a different domain", f"From {from_reg}, Reply-To {rt_reg}")

    # --- lookalike (sender first, then link hosts) ---
    reason = lookalike(from_dom, cfg)
    link_reason = None
    for l in em.links:
        h = host_of(l.href)
        r = lookalike(h, cfg)
        if r and not link_reason:
            link_reason = r
            res.flagged_links.append({"href": l.href, "text": l.text, "reason": r})
    if reason or link_reason:
        add("lookalike_domain", "Look-alike of a trusted name", "Sender: " + reason if reason else "Link: " + link_reason)

    # --- links ---
    mismatch, risky = [], []
    for l in em.links:
        h = host_of(l.href)
        if not h:
            continue
        reg = registrable(h)
        trusted = reg in set(cfg["campus"]["trusted_domains"]) | set(cfg["campus"]["protected_domains"])
        m = _DOMAIN_TEXT.search(l.text or "")
        if m:
            shown = registrable(m.group(1).lower())
            if shown and shown != reg:
                mismatch.append(f"text shows {shown} but the link goes to {reg}")
                res.flagged_links.append({"href": l.href, "text": l.text, "reason": mismatch[-1]})
        why = []
        if is_ip_host(h):
            why.append("raw IP address as host")
        if reg in ec["shorteners"]:
            why.append("URL shortener hides the destination")
        if tld_of(h) in ec["risky_tlds"]:
            why.append(f"high-abuse TLD .{tld_of(h)}")
        if any(x.startswith("xn--") for x in h.split(".")):
            why.append("punycode host")
        if has_userinfo(l.href):
            why.append("user@host trick in the URL")
        if why and not trusted:
            risky.append(f"{h}: {', '.join(why)}")
            res.flagged_links.append({"href": l.href, "text": l.text, "reason": risky[-1]})
    if mismatch:
        add("link_mismatch", "Link text names a different site than its target", "; ".join(mismatch[:2]))
    if risky:
        add("risky_link", "Risky link features", "; ".join(risky[:2]))
    elif len(em.links) >= ec["many_links_threshold"]:
        add("risky_link", "Unusually many links", f"{len(em.links)} links in one message", 0.3)

    # --- wording (visible text only) ---
    visible = f"{em.subject}\n{em.body_text}"
    urg = sanitize.find_terms(visible, ec["urgency_terms"])
    if urg:
        add("urgency_language", "Urgency language", "found: " + ", ".join(urg[:3]))
    cred = sanitize.find_terms(visible, ec["credential_terms"])
    if cred:
        add("credential_request", "Asks for sign-in or credentials", "found: " + ", ".join(cred[:3]))

    # --- prompt injection aimed at an AI reviewer ---
    hit_vis = sanitize.find_terms(visible, ec["injection_terms"])
    hit_hid = sanitize.find_terms(em.hidden_text, ec["injection_terms"])
    if hit_vis or hit_hid:
        where = "hidden text" if hit_hid else "visible text"
        add("prompt_injection", "Message tries to instruct an AI reviewer", f"{where} contains: {', '.join((hit_hid or hit_vis)[:2])}")

    # --- trained text model, on visible text only ---
    p = model.predict(visible[:6000])
    res.probability = round(p, 4)
    res.terms = model.top_terms(visible[:6000], 5)
    add("text_model", "Text model: wording resembles phishing", f"probability {p:.0%}; top terms: {', '.join(t['term'] for t in res.terms[:3]) or 'none'}", p)

    items = [i for i in items if i.raw_points > 0]
    items = apply_group_caps(items, ec["group_caps"])
    res.score, res.ledger = side_total(items, "email")
    return res
