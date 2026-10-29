"""Tests for IP reputation signal, threat intel feed, and login scoring integration.

Verifies:
1. Signal appears in the evidence list with source (feed name) and date.
2. Empty feed behavior (does not fire, lookup returns None, no errors).
3. Stale feed behavior (stale detection, does not fire, lookup returns None).
4. Attack-IP signal fires for new accounts with no history.
5. Indicator matching for exact IPs, CIDR blocks, ASNs, and network owners.
6. Refresh schedule and TTL behavior.
7. Safe default weight in settings file.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
import pytest

from app.engine import config as cfgmod
from app.engine.ip_reputation import (
    IPReputationFeed,
    ReputationMatch,
    get_feed,
    reset_feed,
)
from app.engine.login_signals import analyze_logins
from app.engine.types import GlobalContext, LoginEvent


@pytest.fixture(autouse=True)
def clean_feed():
    """Ensure clean singleton state for each test."""
    reset_feed()
    yield
    reset_feed()


# ---------------------------------------------------------------------------
# 1. Evidence attribution: source (feed name) and date
# ---------------------------------------------------------------------------

def test_signal_appears_in_evidence_with_source_and_date():
    """When a login IP matches the feed, L_ATTACK_IP appears with feed name & date."""
    feed = IPReputationFeed(
        feed_name="Campus Threat Intel Feed",
        feed_date="2026-10-25",
        max_age_days=14,
    )
    feed.load_from_dict({
        "feed_name": "Campus Threat Intel Feed",
        "feed_date": "2026-10-25",
        "ips": ["185.220.101.7"],
    })

    # Wire this feed as current
    from app.engine import ip_reputation
    ip_reputation._feed = feed

    now = datetime(2026, 10, 26, 12, 0, tzinfo=timezone.utc)
    ev = LoginEvent(
        user_id="u-alice",
        ts=now - timedelta(minutes=15),
        ip="185.220.101.7",
        country="RU",
        city="Moscow",
        device="windows|chrome",
        success=True,
    )

    cfg = cfgmod.get()
    ctx = GlobalContext()
    res = analyze_logins([ev], cfg, ctx, as_of=now)

    attack_ev = next((e for e in res.ledger if e.code == "L_ATTACK_IP"), None)
    assert attack_ev is not None, "Expected L_ATTACK_IP in evidence ledger"
    assert "Campus Threat Intel Feed" in attack_ev.detail, "Detail must contain feed source name"
    assert "2026-10-25" in attack_ev.detail, "Detail must contain feed date"
    assert attack_ev.points > 0, "Signal must award points"
    assert res.score >= attack_ev.points


# ---------------------------------------------------------------------------
# 2. Empty feed handling
# ---------------------------------------------------------------------------

def test_empty_feed_does_not_fire_signal():
    """An empty feed produces no lookup match and does not fire the signal."""
    feed = IPReputationFeed(
        feed_name="Empty Feed",
        feed_date="2026-10-29",
    )
    assert feed.is_empty() is True

    # Lookup returns None
    assert feed.lookup("185.220.101.7") is None
    assert feed.lookup(asn=65500) is None
    assert feed.lookup(network_owner="BadHost") is None

    from app.engine import ip_reputation
    ip_reputation._feed = feed

    now = datetime(2026, 10, 29, 12, 0, tzinfo=timezone.utc)
    ev = LoginEvent(
        user_id="u-bob",
        ts=now - timedelta(minutes=10),
        ip="185.220.101.7",
        country="US",
        city="Boston",
        device="windows|chrome",
        success=True,
    )

    cfg = cfgmod.get()
    ctx = GlobalContext()
    res = analyze_logins([ev], cfg, ctx, as_of=now)

    # L_ATTACK_IP must NOT be present
    assert not any(e.code == "L_ATTACK_IP" for e in res.ledger)


# ---------------------------------------------------------------------------
# 3. Stale feed handling
# ---------------------------------------------------------------------------

def test_stale_feed_does_not_fire_signal():
    """A stale feed (past max_age_days) returns None on lookup and does not fire."""
    feed = IPReputationFeed(
        feed_name="Old Feed",
        feed_date="2026-09-01",
        max_age_days=7,
    )
    feed.load_from_dict({
        "feed_name": "Old Feed",
        "feed_date": "2026-09-01",
        "ips": ["198.51.100.99"],
    })

    now = datetime(2026, 10, 29, 12, 0, tzinfo=timezone.utc)
    # Feed date 2026-09-01 is ~58 days old, well past 7 days
    assert feed.is_stale(as_of=now) is True

    # Standard lookup must return None for stale feed
    assert feed.lookup("198.51.100.99", as_of=now) is None

    from app.engine import ip_reputation
    ip_reputation._feed = feed

    ev = LoginEvent(
        user_id="u-charlie",
        ts=now - timedelta(minutes=5),
        ip="198.51.100.99",
        country="US",
        city="New York",
        device="mac|safari",
        success=True,
    )

    cfg = cfgmod.get()
    ctx = GlobalContext()
    res = analyze_logins([ev], cfg, ctx, as_of=now)

    assert not any(e.code == "L_ATTACK_IP" for e in res.ledger)


# ---------------------------------------------------------------------------
# 4. User with no history (new account)
# ---------------------------------------------------------------------------

def test_attack_ip_signal_fires_when_user_has_no_history():
    """Attack-IP signal must fire even when baseline has 0 historical logins."""
    feed = IPReputationFeed(
        feed_name="Campus Threat Intel Feed",
        feed_date="2026-10-29",
        max_age_days=7,
    )
    feed.load_from_dict({
        "ips": ["45.154.255.89"],
    })

    from app.engine import ip_reputation
    ip_reputation._feed = feed

    now = datetime(2026, 10, 29, 12, 0, tzinfo=timezone.utc)
    # Only 1 login in history, inside the window (brand new user)
    single_login = LoginEvent(
        user_id="u-brand-new",
        ts=now - timedelta(minutes=20),
        ip="45.154.255.89",
        country="NL",
        city="Amsterdam",
        device="linux|firefox",
        success=True,
    )

    cfg = cfgmod.get()
    ctx = GlobalContext()
    res = analyze_logins([single_login], cfg, ctx, as_of=now)

    assert res.baseline.n_success == 0, "User should have no baseline history"
    attack_ev = next((e for e in res.ledger if e.code == "L_ATTACK_IP"), None)
    assert attack_ev is not None, "Signal must fire for new account with no history"
    assert attack_ev.points == 20, "Must award full points (not halved by thin history)"
    assert res.suspicious is not None
    assert res.suspicious["ip"] == "45.154.255.89"


# ---------------------------------------------------------------------------
# 5. Matching CIDR blocks, ASNs, and network owners
# ---------------------------------------------------------------------------

def test_lookup_cidr_subnet_match():
    """Lookup matches an IP inside a configured CIDR range."""
    feed = IPReputationFeed()
    feed.load_from_dict({
        "feed_name": "Subnet Threat Feed",
        "feed_date": "2026-10-29",
        "cidrs": ["198.51.100.0/24"],
    })

    match = feed.lookup("198.51.100.42")
    assert match is not None
    assert match.category == "cidr_range"
    assert "198.51.100.0/24" in match.matched_value
    assert "Subnet Threat Feed" in match.detail


def test_lookup_asn_match():
    """Lookup matches a flagged Autonomous System Number."""
    feed = IPReputationFeed()
    feed.load_from_dict({
        "feed_name": "ASN Blocklist",
        "feed_date": "2026-10-29",
        "asns": [65500],
    })

    match = feed.lookup("10.0.0.1", asn=65500)
    assert match is not None
    assert match.category == "asn"
    assert match.asn == 65500
    assert "AS65500" in match.matched_value


def test_lookup_network_owner_match():
    """Lookup matches a flagged network owner string."""
    feed = IPReputationFeed()
    feed.load_from_dict({
        "feed_name": "Bulletproof Feed",
        "feed_date": "2026-10-29",
        "network_owners": ["bulletproof hosting"],
    })

    match = feed.lookup("10.0.0.1", network_owner="Bulletproof Hosting LLC")
    assert match is not None
    assert match.category == "network_owner"
    assert "bulletproof hosting" in match.matched_value


# ---------------------------------------------------------------------------
# 6. Scheduled refresh & TTL
# ---------------------------------------------------------------------------

def test_refresh_loads_indicators(tmp_path):
    """Feed refresh loads from JSON file when interval is elapsed or forced."""
    p = tmp_path / "custom_feed.json"
    p.write_text(json.dumps({
        "feed_name": "Local Test Feed",
        "feed_date": "2026-10-28",
        "ips": ["1.2.3.4"],
    }), encoding="utf-8")

    feed = IPReputationFeed(feed_path=p, refresh_hours=12)
    assert feed.is_empty() is True

    # Force refresh loads file
    feed.refresh(force=True)
    assert feed.is_empty() is False
    assert "1.2.3.4" in feed.ips
    assert feed.last_refreshed is not None


# ---------------------------------------------------------------------------
# 7. Safe default weight in settings file
# ---------------------------------------------------------------------------

def test_weight_in_settings_file():
    """Configuration has safe default weight (20 pts) in credential_attack group."""
    cfg = cfgmod.get()
    sig = cfg["login"]["signals"]["attack_ip"]
    assert sig["points"] == 20
    assert sig["group"] == "credential_attack"
    assert cfg["login"]["group_caps"]["credential_attack"] >= sig["points"]
