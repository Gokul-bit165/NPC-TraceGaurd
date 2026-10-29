"""Per-user baseline built from successful logins that happened before the judged window."""
from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Iterable, Optional

from .types import LoginEvent


@dataclass
class Baseline:
    n_success: int = 0
    countries: Counter = field(default_factory=Counter)
    cities: Counter = field(default_factory=Counter)
    ips: set = field(default_factory=set)
    devices: Counter = field(default_factory=Counter)
    hours: Counter = field(default_factory=Counter)      # local hour -> count
    last_success: Optional[LoginEvent] = None
    thin: bool = True

    def hour_share(self, local_hour: int) -> float:
        """Share of baseline logins within +/- 1 hour of the given local hour (circular)."""
        if not self.n_success:
            return 0.0
        near = sum(self.hours[(local_hour + d) % 24] for d in (-1, 0, 1))
        return near / self.n_success

    def summary(self) -> dict:
        return {
            "n_success": self.n_success,
            "countries": [c for c, _ in self.countries.most_common(5)],
            "cities": [c for c, _ in self.cities.most_common(5)],
            "devices": [d for d, _ in self.devices.most_common(5)],
            "ip_count": len(self.ips),
            "usual_hours": sorted({h for h, c in self.hours.items() if self.n_success and c / self.n_success >= 0.08}),
            "thin": self.thin,
        }


def local_hour(ts: datetime, offset_minutes: int) -> int:
    return (ts + timedelta(minutes=offset_minutes)).hour


def build_baseline(history: Iterable[LoginEvent], before: datetime, tz_offset_minutes: int, min_history: int) -> Baseline:
    b = Baseline()
    for ev in sorted((e for e in history if e.success and e.ts < before), key=lambda e: e.ts):
        b.n_success += 1
        if ev.country:
            b.countries[ev.country] += 1
        if ev.city:
            b.cities[ev.city.lower()] += 1
        if ev.ip:
            b.ips.add(ev.ip)
        if ev.device:
            b.devices[ev.device] += 1
        b.hours[local_hour(ev.ts, tz_offset_minutes)] += 1
        b.last_success = ev
    b.thin = b.n_success < min_history
    return b


_VERSION = re.compile(r"[\d][\d._]*")


def device_key(os_name: str = "", browser: str = "") -> str:
    """Normalise to 'os|browser' with versions removed, so a Chrome update is not a 'new device'."""
    def fam(s: str) -> str:
        s = _VERSION.sub("", s or "").strip().lower()
        return re.sub(r"\s+", " ", s)
    o, b = fam(os_name), fam(browser)
    return f"{o}|{b}" if (o or b) else ""
