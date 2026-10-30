"""Simulated login telemetry for real mailboxes.

No identity provider is connected, so there are no real sign-in logs. This module generates believable ones for a real mailbox so the
login side of TraceGuard (baseline, anomaly scoring, email-then-login correlation) can be shown on real mail. Every function here is
only called from the explicit "Simulate logins" action; nothing runs in the background.
"""
from __future__ import annotations

import random
from datetime import datetime, timedelta, timezone
from typing import Optional

from .engine.types import LoginEvent

HOME = {"city": "Coimbatore", "country": "IN", "devices": ("windows|chrome", "android|chrome")}
SCENARIOS = {
    "normal": "Normal activity: only the user's usual sign-ins",
    "takeover": "Account takeover: foreign sign-in shortly after the riskiest email",
    "travel": "Impossible travel: two far-apart sign-ins within an hour",
    "stuffing": "Credential stuffing: a burst of failures, then a success from abroad",
}


def _ip(user: str, k: int, prefix: str = "49.37") -> str:
    r = random.Random(f"{user}-ip-{k}")
    return f"{prefix}.{r.randint(1, 250)}.{r.randint(1, 250)}"


def baseline(user_id: str, now: datetime, n: int = 30, days: int = 28) -> list[LoginEvent]:
    """The user's normal pattern: one city, two devices, two IPs, daytime hours (03:00-17:00 UTC is 08:30-22:30 IST)."""
    r = random.Random(f"{user_id}-sim-baseline")
    out = []
    for _ in range(n):
        day = now - timedelta(days=r.randint(2, days))
        ts = day.replace(hour=r.randint(4, 16), minute=r.randint(0, 59), second=r.randint(0, 59), microsecond=0)
        out.append(LoginEvent(user_id=user_id, ts=ts, ip=_ip(user_id, r.randint(0, 1)), country=HOME["country"], city=HOME["city"],
                              device=r.choice(HOME["devices"]), success=True))
    return out


def _home(user_id: str, ts: datetime, k: int = 0) -> LoginEvent:
    return LoginEvent(user_id=user_id, ts=ts, ip=_ip(user_id, k), country=HOME["country"], city=HOME["city"], device=HOME["devices"][0], success=True)


def scenario_events(scenario: str, user_id: str, now: datetime, anchor: Optional[datetime] = None) -> list[LoginEvent]:
    """Events for one scenario. `anchor` is when the user's riskiest real email arrived, so a takeover can follow it."""
    if scenario == "normal":
        return [_home(user_id, now - timedelta(minutes=25))]
    if scenario == "travel":
        return [_home(user_id, now - timedelta(minutes=55)),
                LoginEvent(user_id=user_id, ts=now - timedelta(minutes=12), ip="91.198.174.192", country="DE", city="Frankfurt",
                           device="windows|chrome", success=True)]
    if scenario == "stuffing":
        base = now - timedelta(minutes=30)
        fails = [LoginEvent(user_id=user_id, ts=base + timedelta(seconds=25 * i), ip="185.220.101.47", country="NL", city="Amsterdam",
                            device="linux|curl", success=False) for i in range(12)]
        return fails + [LoginEvent(user_id=user_id, ts=base + timedelta(minutes=8), ip="185.220.101.47", country="NL", city="Amsterdam",
                                   device="linux|curl", success=True)]
    if scenario == "takeover":
        t = min((anchor or now - timedelta(hours=1)) + timedelta(minutes=35), now - timedelta(minutes=2))
        ip = "105.112.141.53"
        fails = [LoginEvent(user_id=user_id, ts=t - timedelta(minutes=2, seconds=20 * i), ip=ip, country="NG", city="Lagos",
                            device="linux|firefox", success=False) for i in range(3)]
        return fails + [LoginEvent(user_id=user_id, ts=t, ip=ip, country="NG", city="Lagos", device="linux|firefox", success=True)]
    raise ValueError(f"unknown scenario {scenario!r}")


def build(scenario: str, user_id: str, now: Optional[datetime] = None, anchor: Optional[datetime] = None, with_baseline: bool = True) -> list[LoginEvent]:
    now = now or datetime.now(timezone.utc)
    events = (baseline(user_id, now) if with_baseline else []) + scenario_events(scenario, user_id, now, anchor)
    return sorted(events, key=lambda e: e.ts)
