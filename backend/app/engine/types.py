"""Plain data types for the detection engine. No database or web dependencies."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional


def to_utc(value: Any) -> datetime:
    """Accept datetime or ISO string; always return an aware UTC datetime."""
    if isinstance(value, datetime):
        dt = value
    else:
        text = str(value).strip().replace("Z", "+00:00")
        dt = datetime.fromisoformat(text)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


@dataclass
class LoginEvent:
    user_id: str
    ts: datetime
    ip: str = ""
    country: str = ""
    city: str = ""
    asn: Optional[int] = None
    lat: Optional[float] = None
    lon: Optional[float] = None
    device: str = ""          # normalised "os|browser" key, versions ignored
    device_type: str = ""
    success: bool = True
    is_attack_ip: bool = False
    id: Optional[str] = None

    def __post_init__(self) -> None:
        self.ts = to_utc(self.ts)
        self.country = (self.country or "").strip().upper()
        self.city = (self.city or "").strip()
        if self.city in {"-", "?"}:
            self.city = ""


@dataclass
class Link:
    href: str
    text: str = ""


@dataclass
class EmailEvent:
    id: str
    user_id: str                      # recipient
    received_at: datetime
    sender: str = ""                  # full address
    subject: str = ""
    body_text: str = ""
    body_html: str = ""
    reply_to: str = ""
    return_path: str = ""
    # auth: {"spf": "pass|fail|softfail|none|...", "dkim": ..., "dmarc": ..., "dkim_domain": "...", "spf_domain": "..."}
    auth: dict = field(default_factory=dict)
    links: list[Link] = field(default_factory=list)
    has_headers: bool = False         # False when the analyst typed fields instead of uploading .eml
    hidden_text: str = ""             # text a human cannot see (display:none, zero font, comments); never sent to a model
    raw: str = ""                     # original message source (truncated), kept for the evidence panel

    def __post_init__(self) -> None:
        self.received_at = to_utc(self.received_at)


@dataclass
class Evidence:
    """One line of the evidence ledger. The ledger is the source of truth for every score."""
    code: str
    side: str                          # "email" | "login" | "correlation" | "cap"
    label: str
    detail: str
    points: int                        # points actually awarded (after caps)
    raw_points: int                    # points before group cap
    group: str = ""
    ref: Optional[str] = None          # email id, or login timestamp, the evidence refers to

    def to_dict(self) -> dict:
        return {
            "code": self.code, "side": self.side, "label": self.label, "detail": self.detail,
            "points": self.points, "raw_points": self.raw_points, "group": self.group, "ref": self.ref,
        }


@dataclass
class GlobalContext:
    """Cross-user facts the per-user logic needs. Built from the login stream (or DB query)."""
    ip_user_counts: dict[str, int] = field(default_factory=dict)       # ip -> distinct users seen in window
    device_user_counts: dict[str, int] = field(default_factory=dict)   # "device@ip" -> distinct users with a successful login
    campaign_sizes: dict[str, int] = field(default_factory=dict)       # campaign key -> recipients


@dataclass
class CaseResult:
    user_id: str
    as_of: datetime
    email_score: int
    login_score: int
    score: int
    band: str
    ledger: list[Evidence]
    low_confidence: bool
    low_confidence_reason: str
    email_ids: list[str]
    top_email_id: Optional[str]
    login_refs: list[str]
    correlated: bool
    text_terms: list[dict]
    text_probability: Optional[float]
    not_evaluated: list[str]
    campaign_key: Optional[str]
    timeline: list[dict]
    suspicious_login: Optional[dict]
    extras: dict = field(default_factory=dict)   # auth results, flagged links, baseline summary, uplift, formula text

    def ledger_dicts(self) -> list[dict]:
        return [e.to_dict() for e in self.ledger]
