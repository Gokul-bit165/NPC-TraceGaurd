"""Streaming scorer for large login files: one pass in time order, per-user rolling history.

Used by the seed script, the RBA loader and the throughput benchmark. It scores each login on its own
(window = that login) against that user's previous logins, with the same signals and weights as cases.
Memory per user is capped, so a 33M-row file can be processed shard by shard (shard on user_id).
"""
from __future__ import annotations

import copy
from collections import defaultdict, deque
from datetime import timedelta
from typing import Iterable, Iterator, Optional

from . import config as cfgmod
from .login_signals import analyze_logins
from .types import GlobalContext, LoginEvent

HISTORY_CAP = 300


def score_stream(events: Iterable[LoginEvent], cfg: Optional[dict] = None, disabled: Optional[set[str]] = None,
                 history_cap: int = HISTORY_CAP) -> Iterator[tuple[LoginEvent, int, str, list[str], bool]]:
    cfg = copy.deepcopy(cfg or cfgmod.get())
    cfg["login"]["window_hours"] = 0.5             # 30 min: long enough to see a failed burst before a success
    win_ip = timedelta(hours=24)
    by_user: dict[str, deque] = defaultdict(lambda: deque(maxlen=history_cap))
    ip_recent: dict[str, deque] = defaultdict(deque)
    pair_users: dict[str, set] = defaultdict(set)
    for ev in sorted(events, key=lambda e: e.ts):
        hist = by_user[ev.user_id]
        if ev.ip:
            q = ip_recent[ev.ip]
            q.append((ev.ts, ev.user_id))
            while q and ev.ts - q[0][0] > win_ip:
                q.popleft()
            n_ip = len({u for _, u in q})
        else:
            n_ip = 0
        if ev.device and ev.ip and ev.success:
            pair_users[f"{ev.device}@{ev.ip}"].add(ev.user_id)
        ctx = GlobalContext(ip_user_counts={ev.ip: n_ip} if ev.ip else {},
                            device_user_counts={f"{ev.device}@{ev.ip}": len(pair_users.get(f"{ev.device}@{ev.ip}", ()))} if ev.device and ev.ip else {})
        hist.append(ev)
        res = analyze_logins(list(hist), cfg, ctx, ev.ts, disabled)
        flags = [e.code for e in res.ledger if e.points > 0]
        yield ev, res.score, cfgmod.band_of(res.score, cfg), flags, bool(res.low_confidence)
