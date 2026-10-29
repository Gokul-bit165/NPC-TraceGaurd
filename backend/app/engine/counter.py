"""Shared streaming counter / cache for cross-user signals (IP concurrency and device sharing).

Replaces per-case database queries:
1. Number of accounts an IP touched in the last 24 hours.
2. Number of distinct users sharing a device@IP with successful logins.

Can be updated as logins stream in and shared across multiple workers
(threads or processes via BaseManager) with zero per-case SQL queries.
"""
from __future__ import annotations

import threading
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Iterable, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from .types import GlobalContext, LoginEvent


def aware(dt: Optional[datetime]) -> Optional[datetime]:
    if dt is None:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


class CrossUserCounter:
    """Thread-safe streaming counter and cache for cross-user IP and device counts."""

    def __init__(self, retention_hours: int = 48) -> None:
        self.retention_hours = retention_hours
        self._lock = threading.RLock()
        # ip -> list of (ts, user_id)
        self._ip_logins: dict[str, list[tuple[datetime, str]]] = defaultdict(list)
        # device@ip -> set of user_ids
        self._device_users: dict[str, set[str]] = defaultdict(set)
        self._warmed: bool = False

    def clear(self) -> None:
        with self._lock:
            self._ip_logins.clear()
            self._device_users.clear()
            self._warmed = False

    def is_warmed(self) -> bool:
        with self._lock:
            return self._warmed

    def set_warmed(self, warmed: bool = True) -> None:
        with self._lock:
            self._warmed = warmed

    def record_login(self, user_id: str, ts: datetime, ip: str = "", device: str = "", success: bool = True) -> None:
        """Stream an incoming login event into the counter."""
        ts = aware(ts)
        with self._lock:
            if ip:
                self._ip_logins[ip].append((ts, user_id))
            if device and ip and success:
                self._device_users[f"{device}@{ip}"].add(user_id)

    def record_logins(self, events: Iterable[LoginEvent]) -> None:
        with self._lock:
            for ev in events:
                self.record_login(ev.user_id, ev.ts, ev.ip, ev.device, ev.success)

    def warmup_from_db(self, db: Session, since: Optional[datetime] = None) -> int:
        """Pre-populate the counter from stored logins (run on startup or first access)."""
        from ..models import LoginRow
        with self._lock:
            stmt = select(LoginRow.user_id, LoginRow.ts, LoginRow.ip, LoginRow.device, LoginRow.success)
            if since is not None:
                stmt = stmt.where(LoginRow.ts >= aware(since))
            stmt = stmt.order_by(LoginRow.ts.asc())
            rows = db.execute(stmt).all()
            for r in rows:
                ts = aware(r.ts)
                if r.ip:
                    self._ip_logins[r.ip].append((ts, r.user_id))
                if r.device and r.ip and r.success:
                    self._device_users[f"{r.device}@{r.ip}"].add(r.user_id)
            self._warmed = True
            return len(rows)

    def get_ip_user_count(self, ip: str, as_of: datetime, window_hours: int = 24, extra_user: Optional[str] = None) -> int:
        """Return the number of distinct accounts touched by `ip` in (as_of - window, as_of]."""
        if not ip:
            return 0
        as_of = aware(as_of)
        start = as_of - timedelta(hours=window_hours)
        with self._lock:
            records = self._ip_logins.get(ip, [])
            users = {uid for ts, uid in records if start < ts <= as_of}
            if extra_user:
                users.add(extra_user)
            return len(users)

    def get_device_user_count(self, device: str, ip: str, extra_user: Optional[str] = None) -> int:
        """Return the number of distinct accounts succeeding on `device@ip`."""
        if not device or not ip:
            return 0
        key = f"{device}@{ip}"
        with self._lock:
            users = set(self._device_users.get(key, set()))
            if extra_user:
                users.add(extra_user)
            return len(users)

    def build_context_for_user(
        self,
        user_id: str,
        window_events: list[LoginEvent],
        as_of: datetime,
        extra: Optional[list[LoginEvent]] = None,
        window_hours: int = 24,
    ) -> GlobalContext:
        """Build a GlobalContext instance directly from the cache without DB queries."""
        as_of = aware(as_of)
        start = as_of - timedelta(hours=window_hours)
        ips = {e.ip for e in window_events if e.ip and start < aware(e.ts) <= as_of}
        pairs = {(e.device, e.ip) for e in window_events if e.device and e.ip and e.success and start < aware(e.ts) <= as_of}
        unsaved = {(e.ip, e.device, e.success) for e in (extra or [])}

        ctx = GlobalContext()
        with self._lock:
            for ip in ips:
                records = self._ip_logins.get(ip, [])
                users = {uid for ts, uid in records if start < ts <= as_of}
                if any(u[0] == ip for u in unsaved):
                    users.add(user_id)
                ctx.ip_user_counts[ip] = len(users)

            for dev, ip in pairs:
                users = set(self._device_users.get(f"{dev}@{ip}", set()))
                if (ip, dev, True) in unsaved:
                    users.add(user_id)
                ctx.device_user_counts[f"{dev}@{ip}"] = len(users)

        return ctx


_GLOBAL_COUNTER: Optional[CrossUserCounter] = None
_GLOBAL_COUNTER_LOCK = threading.Lock()


def get_cross_user_counter() -> CrossUserCounter:
    """Get or create the global cross-user streaming counter instance."""
    global _GLOBAL_COUNTER
    if _GLOBAL_COUNTER is None:
        with _GLOBAL_COUNTER_LOCK:
            if _GLOBAL_COUNTER is None:
                _GLOBAL_COUNTER = CrossUserCounter()
    return _GLOBAL_COUNTER


def reset_cross_user_counter() -> CrossUserCounter:
    """Reset the global counter state."""
    c = get_cross_user_counter()
    c.clear()
    return c
