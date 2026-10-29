"""Parse a raw .eml (or typed fields) into an EmailEvent with authentication results and links."""
from __future__ import annotations

import re
import uuid
from datetime import datetime, timezone
from email import policy
from email.parser import BytesParser
from email.utils import parseaddr, parsedate_to_datetime
from typing import Optional

from . import sanitize
from .domains import address_domain
from .types import EmailEvent, Link

_STATUS = re.compile(r"\b(spf|dkim|dmarc)\s*=\s*([a-z]+)", re.I)
_DKIM_D = re.compile(r"header\.(?:d|i)\s*=\s*@?([A-Za-z0-9.\-]+)", re.I)
_SPF_DOM = re.compile(r"smtp\.mailfrom\s*=\s*(?:[^@\s;]*@)?([A-Za-z0-9.\-]+)", re.I)


def parse_auth_results(values: list[str], received_spf: str = "") -> dict:
    out: dict = {}
    for v in values:
        flat = re.sub(r"\s+", " ", v)
        for k, s in _STATUS.findall(flat):
            out.setdefault(k.lower(), s.lower())
        m = _DKIM_D.search(flat)
        if m:
            out.setdefault("dkim_domain", m.group(1).lower())
        m = _SPF_DOM.search(flat)
        if m:
            out.setdefault("spf_domain", m.group(1).lower())
    if "spf" not in out and received_spf:
        m = re.match(r"\s*([a-zA-Z]+)", received_spf)
        if m:
            out["spf"] = m.group(1).lower()
    return out


def _body_parts(msg) -> tuple[str, str]:
    plain = msg.get_body(preferencelist=("plain",))
    html = msg.get_body(preferencelist=("html",))
    pt = plain.get_content() if plain is not None else ""
    ht = html.get_content() if html is not None else ""
    return pt or "", ht or ""


def parse_eml(raw: bytes | str, user_id: str, received_at: Optional[datetime] = None, email_id: Optional[str] = None) -> EmailEvent:
    data = raw.encode("utf-8", "replace") if isinstance(raw, str) else raw
    msg = BytesParser(policy=policy.default).parsebytes(data)
    sender = parseaddr(str(msg.get("From", "")))[1]
    reply_to = parseaddr(str(msg.get("Reply-To", "")))[1]
    return_path = parseaddr(str(msg.get("Return-Path", "")))[1]
    subject = str(msg.get("Subject", "") or "").strip()
    if received_at is None:
        try:
            received_at = parsedate_to_datetime(str(msg.get("Date")))
        except (TypeError, ValueError):
            received_at = datetime.now(timezone.utc)
    auth = parse_auth_results([str(h) for h in msg.get_all("Authentication-Results", [])], str(msg.get("Received-SPF", "") or ""))
    plain, html = _body_parts(msg)

    links: list[Link] = []
    hidden = ""
    if html:
        visible, hidden, links = sanitize.split_html(html)
        body = visible if visible else sanitize.clean_text(plain)
    else:
        body = sanitize.clean_text(plain)
    seen = {l.href for l in links}
    for u in sanitize.urls_in_text(body):
        if u not in seen:
            links.append(Link(href=u, text=""))
            seen.add(u)
    ev = EmailEvent(
        id=email_id or uuid.uuid4().hex[:12], user_id=user_id, received_at=received_at, sender=sender, subject=subject,
        body_text=body, body_html=html[:20000], reply_to=reply_to, return_path=return_path, auth=auth, links=links,
        has_headers=bool(auth) or bool(msg.get("Received")), hidden_text=hidden,
        raw=data.decode("utf-8", "replace")[:60000])
    return ev


def from_fields(user_id: str, sender: str, subject: str, body: str = "", urls: Optional[list[str]] = None,
                reply_to: str = "", received_at: Optional[datetime] = None, email_id: Optional[str] = None) -> EmailEvent:
    """Analyst typed the details instead of uploading a file: no authentication results exist."""
    links = [Link(href=u, text="") for u in (urls or [])]
    seen = {l.href for l in links}
    for u in sanitize.urls_in_text(body):
        if u not in seen:
            links.append(Link(href=u))
    return EmailEvent(id=email_id or uuid.uuid4().hex[:12], user_id=user_id, received_at=received_at or datetime.now(timezone.utc),
                      sender=sender, subject=subject, body_text=sanitize.clean_text(body), reply_to=reply_to, links=links,
                      has_headers=False)
