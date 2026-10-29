"""Login evidence: compare logins in the judged window with the user's own history."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Iterable, Optional

from . import geo
from .baseline import Baseline, build_baseline, local_hour
from .scoring import apply_group_caps, make, rnd, side_total
from .types import Evidence, GlobalContext, LoginEvent

BASELINE_RELATIVE = {"new_country", "new_city", "new_ip", "new_device", "odd_hour"}


@dataclass
class LoginAnalysis:
    score: int = 0
    ledger: list[Evidence] = field(default_factory=list)
    refs: list[str] = field(default_factory=list)          # ISO timestamps of logins the evidence refers to
    suspicious: Optional[dict] = None                       # the login the case is about
    baseline: Optional[Baseline] = None
    window_logins: list[LoginEvent] = field(default_factory=list)
    low_confidence: bool = False
    first_suspicious_ts: Optional[datetime] = None


def _loc(ev: LoginEvent) -> str:
    return ", ".join(x for x in (ev.city, ev.country) if x) or "unknown location"


def _coords(ev: LoginEvent):
    if ev.lat is not None and ev.lon is not None:
        return ev.lat, ev.lon
    return geo.resolve(ev.city, ev.country)


def _sig(cfg: dict, name: str) -> dict:
    return cfg["login"]["signals"][name]


def _per_login_signals(ev: LoginEvent, prev_success: Optional[LoginEvent], base: Baseline, cfg: dict,
                       ctx: GlobalContext, disabled: set[str]) -> list[Evidence]:
    lc = cfg["login"]
    tz = cfg["campus"]["timezone_offset_minutes"]
    thin = base.thin
    factor = lc["thin_history_factor"] if thin else 1.0
    ref = ev.ts.isoformat()
    out: list[Evidence] = []

    def add(name: str, label: str, detail: str, scale: float = 1.0) -> None:
        if name in disabled:
            return
        if name in BASELINE_RELATIVE and base.n_success == 0:
            return                       # nothing is "new" relative to an empty history; the case is flagged low-confidence instead
        s = _sig(cfg, name)
        pts = s["points"] * scale * (factor if name in BASELINE_RELATIVE else 1.0)
        out.append(make("L_" + name.upper(), "login", label, detail, pts, s["group"], ref))

    new_country = bool(ev.country) and ev.country not in base.countries
    known = ", ".join(c for c, _ in base.countries.most_common(3)) or "none on record"
    if new_country:
        add("new_country", "Login from a new country", f"{_loc(ev)}; this user's earlier logins were from {known}")
    elif ev.city and base.cities and ev.city.lower() not in base.cities:
        add("new_city", "Login from a new city", f"{_loc(ev)}; usual cities: {', '.join(c.title() for c in list(base.cities)[:3])}")

    if ev.ip and ev.ip not in base.ips and 0 < len(base.ips) <= 3 and not new_country:
        add("new_ip", "New IP for a user with a stable network", f"{ev.ip}; {len(base.ips)} IP(s) seen before")

    if ev.device and ev.device not in base.devices and base.n_success:
        pair_users = ctx.device_user_counts.get(f"{ev.device}@{ev.ip}", 0)
        if pair_users >= lc["shared_device_users"]:
            add("new_device", "New device on a shared machine (damped)",
                f"{ev.device} from {ev.ip} has {pair_users} different users signing in successfully, so it is likely a lab PC", lc["shared_device_damping"])
        else:
            usual = ", ".join(d for d, _ in base.devices.most_common(2)) or "none on record"
            add("new_device", "Device not seen before for this user", f"{ev.device}; usual: {usual}")

    if base.n_success >= lc["min_history_logins"]:
        lh = local_hour(ev.ts, tz)
        share = base.hour_share(lh)
        if share < lc["usual_hour_min_share"]:
            add("odd_hour", "Outside the user's usual login hours", f"{lh:02d}:00 local; {share:.0%} of past logins fall within an hour of this")

    if prev_success is not None and "impossible_travel" not in disabled:
        a, b = _coords(prev_success), _coords(ev)
        if a and b:
            km = geo.haversine_km(a[0], a[1], b[0], b[1])
            hours = max((ev.ts - prev_success.ts).total_seconds() / 3600.0, 1e-6)
            speed = km / hours
            if km >= lc["min_travel_km"] and speed > lc["travel_speed_kmh"]:
                add("impossible_travel", "Impossible travel",
                    f"{_loc(prev_success)} to {_loc(ev)}: {km:,.0f} km in {hours * 60:.0f} min (about {speed:,.0f} km/h)")
    return out


def analyze_logins(history: Iterable[LoginEvent], cfg: dict, ctx: GlobalContext, as_of: datetime,
                   disabled: Optional[set[str]] = None) -> LoginAnalysis:
    """Judge logins in (as_of - window, as_of] against everything the user did before that window."""
    disabled = disabled or set()
    lc = cfg["login"]
    tz = cfg["campus"]["timezone_offset_minutes"]
    events = sorted(history, key=lambda e: e.ts)
    start = as_of - timedelta(hours=lc["window_hours"])
    window = [e for e in events if start < e.ts <= as_of]
    res = LoginAnalysis(window_logins=window)
    base = build_baseline(events, start, tz, lc["min_history_logins"])
    res.baseline = base
    res.low_confidence = base.thin
    if not window:
        return res

    successes = [e for e in window if e.success]
    failures = [e for e in window if not e.success]

    # ---- per-login evidence: keep the single worst successful login as the case's focus ----
    best_items: list[Evidence] = []
    best_login: Optional[LoginEvent] = None
    best_total = -1
    prev = base.last_success
    for ev in successes:
        items = _per_login_signals(ev, prev, base, cfg, ctx, disabled)
        total = sum(i.raw_points for i in items)
        if total > best_total:
            best_total, best_items, best_login = total, items, ev
        prev = ev

    items: list[Evidence] = list(best_items)
    refs: set[str] = {best_login.ts.isoformat()} if (best_login and best_items) else set()

    # ---- account-level credential-attack evidence over the whole window ----
    def add(name: str, label: str, detail: str, ref: Optional[str] = None) -> None:
        if name in disabled:
            return
        s = _sig(cfg, name)
        items.append(make("L_" + name.upper(), "login", label, detail, s["points"], s["group"], ref))
        if ref:
            refs.add(ref)

    # failed burst: >= N failures within M minutes
    n, m = lc["burst_failures"], timedelta(minutes=lc["burst_minutes"])
    fts = [f.ts for f in failures]
    for i in range(len(fts)):
        j = i
        while j < len(fts) and fts[j] - fts[i] <= m:
            j += 1
        if j - i >= n:
            add("failed_burst", "Burst of failed logins",
                f"{j - i} failed logins within {lc['burst_minutes']} minutes from {failures[i].ip or 'unknown IP'}", fts[i].isoformat())
            break

    # success after failures on the same account
    k, after = lc["success_after_failures"], timedelta(minutes=lc["success_after_minutes"])
    for s in successes:
        prior = [f for f in failures if s.ts - after <= f.ts < s.ts]
        if len(prior) >= k:
            add("success_after_failures", "Successful login right after repeated failures",
                f"{len(prior)} failures in the {lc['success_after_minutes']} minutes before a success from {s.ip or 'unknown IP'}", s.ts.isoformat())
            if not best_items:
                best_login = s          # no location/context anomaly: the post-failure success is the focus
            break

    # an IP that is hitting many accounts at once
    for ev in window:
        n_users = ctx.ip_user_counts.get(ev.ip, 0) if ev.ip else 0
        if n_users >= lc["multi_account_users"]:
            add("multi_account_ip", "One IP targeting many accounts", f"{ev.ip} attempted {n_users} different accounts in the window", ev.ts.isoformat())
            break

    # known attack IP from the threat feed (RBA dataset flag or your own reputation feed)
    for ev in window:
        if ev.is_attack_ip:
            add("attack_ip", "IP is on the attack-IP list", f"{ev.ip or 'unknown IP'} is flagged by the threat feed", ev.ts.isoformat())
            break

    items = apply_group_caps(items, lc["group_caps"])
    res.score, res.ledger = side_total(items, "login")
    res.refs = sorted(refs)
    if res.score > 0:
        focus = best_login
        if focus is None and failures:
            focus = failures[-1]                # failures only: show the last failed attempt
        if focus is not None:
            res.suspicious = {
                "ts": focus.ts.isoformat(), "ip": focus.ip, "city": focus.city, "country": focus.country,
                "device": focus.device, "success": focus.success,
            }
        times = [datetime.fromisoformat(r) for r in refs]
        res.first_suspicious_ts = min(times) if times else None
    return res
