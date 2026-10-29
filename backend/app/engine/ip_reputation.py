"""IP reputation and threat intelligence feed module.

Loads known malicious IP addresses, CIDR blocks, ASNs, and network owners
from a local JSON/file feed or an approved public feed URL.

Key properties:
1. Scheduled / TTL-based refresh mechanism with configurable interval.
2. Staleness detection: feeds older than `max_age_days` are marked stale and
   their indicators are skipped during scoring (safe defaults).
3. Attribution: every match carries the feed name and feed date so that
   evidence ledgers record exact provenance.
4. Robust lookups: supports single IPs, CIDR blocks, ASNs, and network owners.
5. Safe behavior for empty feeds and stale feeds (never crashes, returns None).
"""
from __future__ import annotations

import ipaddress
import json
import logging
import os
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional

log = logging.getLogger("traceguard.ip_reputation")

DEFAULT_DATA_DIR = Path(__file__).resolve().parents[2] / "data"
DEFAULT_FEED_PATH = DEFAULT_DATA_DIR / "ip_reputation.json"
DEFAULT_CONFIG_PATH = Path(__file__).resolve().parents[2] / "config" / "ip_reputation.json"


@dataclass
class ReputationMatch:
    """Attribution and match details for an IP/network found on a feed."""
    ip: str
    feed_name: str
    feed_date: str
    category: str = "malicious_ip"  # "malicious_ip", "cidr_range", "asn", "network_owner"
    matched_value: str = ""
    network_owner: Optional[str] = None
    asn: Optional[int] = None
    detail: str = ""


class IPReputationFeed:
    """In-memory reputation feed with file/URL loading and TTL refresh."""

    def __init__(
        self,
        feed_name: str = "Campus Threat Intelligence Feed",
        feed_date: Optional[str] = None,
        feed_path: Optional[str | Path] = None,
        feed_url: Optional[str] = None,
        max_age_days: int = 7,
        refresh_hours: int = 24,
    ) -> None:
        self.feed_name = feed_name
        self.feed_date = feed_date or datetime.now(timezone.utc).strftime("%Y-%m-%d")
        self.feed_path: Optional[Path] = Path(feed_path) if feed_path else DEFAULT_FEED_PATH
        self.feed_url: Optional[str] = feed_url
        self.max_age_days = max_age_days
        self.refresh_hours = refresh_hours
        self.last_refreshed: Optional[datetime] = None

        self.ips: set[str] = set()
        self.cidrs: list[ipaddress.IPv4Network | ipaddress.IPv6Network] = []
        self.asns: set[int] = set()
        self.network_owners: set[str] = set()

    def is_empty(self) -> bool:
        """Return True if no indicators are loaded."""
        return not (self.ips or self.cidrs or self.asns or self.network_owners)

    def is_stale(self, as_of: Optional[datetime] = None) -> bool:
        """Return True if the feed date or last refresh is older than max_age_days."""
        ref_time = as_of or datetime.now(timezone.utc)
        if ref_time.tzinfo is None:
            ref_time = ref_time.replace(tzinfo=timezone.utc)

        # 1. Check feed_date if present
        if self.feed_date:
            try:
                # Try ISO or YYYY-MM-DD
                d_str = self.feed_date.strip().replace("Z", "+00:00")
                if len(d_str) == 10:
                    feed_dt = datetime.strptime(d_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
                else:
                    feed_dt = datetime.fromisoformat(d_str)
                    if feed_dt.tzinfo is None:
                        feed_dt = feed_dt.replace(tzinfo=timezone.utc)
                if (ref_time - feed_dt) > timedelta(days=self.max_age_days):
                    return True
            except Exception:
                pass

        # 2. Check last_refreshed timestamp
        if self.last_refreshed:
            lr = self.last_refreshed
            if lr.tzinfo is None:
                lr = lr.replace(tzinfo=timezone.utc)
            if (ref_time - lr) > timedelta(days=self.max_age_days):
                return True

        return False

    def load_from_dict(self, data: dict[str, Any]) -> None:
        """Populate threat indicators from a parsed dictionary."""
        self.feed_name = str(data.get("feed_name") or self.feed_name)
        self.feed_date = str(data.get("feed_date") or self.feed_date)

        # IPs
        self.ips = {str(ip).strip() for ip in data.get("ips", []) if str(ip).strip()}

        # CIDRs
        self.cidrs = []
        for c in data.get("cidrs", []):
            try:
                self.cidrs.append(ipaddress.ip_network(str(c).strip(), strict=False))
            except ValueError as exc:
                log.warning("Invalid CIDR %r in feed: %s", c, exc)

        # ASNs
        self.asns = set()
        for a in data.get("asns", []):
            try:
                self.asns.add(int(str(a).replace("AS", "").strip()))
            except (ValueError, TypeError):
                pass

        # Network owners (normalized to lowercase)
        self.network_owners = {
            str(o).strip().lower() for o in data.get("network_owners", []) if str(o).strip()
        }
        self.last_refreshed = datetime.now(timezone.utc)

    def load_from_file(self, path: Optional[str | Path] = None) -> bool:
        """Load indicators from a local JSON file. Return True if successful."""
        target = Path(path) if path else self.feed_path
        if not target or not target.exists():
            if DEFAULT_CONFIG_PATH.exists():
                target = DEFAULT_CONFIG_PATH
            else:
                log.info("Threat feed file not found at %s", target)
                return False
        try:
            with open(target, "r", encoding="utf-8") as fh:
                data = json.load(fh)
            self.load_from_dict(data)
            log.info(
                "Loaded IP reputation feed %r from %s (%d IPs, %d CIDRs, %d ASNs)",
                self.feed_name, target, len(self.ips), len(self.cidrs), len(self.asns)
            )
            return True
        except Exception as exc:
            log.warning("Failed to load feed file from %s: %s", target, exc)
            return False

    def load_from_url(self, url: Optional[str] = None) -> bool:
        """Fetch indicators from an approved public feed URL. Return True if successful."""
        target_url = url or self.feed_url
        if not target_url:
            return False
        try:
            req = urllib.request.Request(
                target_url,
                headers={"User-Agent": "TraceGuard-ThreatFeed/1.0", "Accept": "application/json"}
            )
            with urllib.request.urlopen(req, timeout=5) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            self.load_from_dict(data)
            log.info("Fetched feed %r from %s", self.feed_name, target_url)
            return True
        except Exception as exc:
            log.warning("Could not fetch threat feed from %s: %s", target_url, exc)
            return False

    def refresh(self, force: bool = False, as_of: Optional[datetime] = None) -> bool:
        """Refresh feed if interval has elapsed or if forced.
        
        Attempts URL fetch first if configured, then falls back to local file.
        """
        now = as_of or datetime.now(timezone.utc)
        if not force and self.last_refreshed:
            lr = self.last_refreshed
            if lr.tzinfo is None:
                lr = lr.replace(tzinfo=timezone.utc)
            if (now - lr) < timedelta(hours=self.refresh_hours):
                return True

        # Try URL first if configured
        if self.feed_url and self.load_from_url(self.feed_url):
            return True

        # Fallback to local file
        if self.feed_path and self.load_from_file(self.feed_path):
            return True

        return False

    def lookup(
        self,
        ip: Optional[str] = None,
        asn: Optional[int | str] = None,
        network_owner: Optional[str] = None,
        as_of: Optional[datetime] = None,
        allow_stale: bool = False,
    ) -> Optional[ReputationMatch]:
        """Look up an IP, ASN, or network owner.

        Returns None if:
        - feed is empty
        - feed is stale (unless allow_stale=True)
        - indicator does not match

        Returns ReputationMatch on hit, including feed_name and feed_date.
        """
        if self.is_empty():
            return None

        if not allow_stale and self.is_stale(as_of):
            log.debug("Feed %r (%s) is stale; skipping lookup", self.feed_name, self.feed_date)
            return None

        clean_ip = (ip or "").strip()

        # 1. Exact IP match
        if clean_ip and clean_ip in self.ips:
            return ReputationMatch(
                ip=clean_ip,
                feed_name=self.feed_name,
                feed_date=self.feed_date,
                category="malicious_ip",
                matched_value=clean_ip,
                detail=f"{clean_ip} is flagged on threat feed: {self.feed_name} ({self.feed_date})",
            )

        # 2. CIDR match
        if clean_ip and self.cidrs:
            try:
                ip_obj = ipaddress.ip_address(clean_ip)
                for net in self.cidrs:
                    if ip_obj in net:
                        return ReputationMatch(
                            ip=clean_ip,
                            feed_name=self.feed_name,
                            feed_date=self.feed_date,
                            category="cidr_range",
                            matched_value=str(net),
                            detail=f"{clean_ip} belongs to malicious subnet {net} in {self.feed_name} ({self.feed_date})",
                        )
            except ValueError:
                pass

        # 3. ASN match
        if asn is not None:
            try:
                asn_int = int(str(asn).replace("AS", "").strip())
                if asn_int in self.asns:
                    return ReputationMatch(
                        ip=clean_ip,
                        feed_name=self.feed_name,
                        feed_date=self.feed_date,
                        category="asn",
                        asn=asn_int,
                        matched_value=f"AS{asn_int}",
                        detail=f"{clean_ip or 'Login'} originates from malicious AS{asn_int} in {self.feed_name} ({self.feed_date})",
                    )
            except (ValueError, TypeError):
                pass

        # 4. Network owner match
        if network_owner:
            owner_lower = network_owner.strip().lower()
            for bad_owner in self.network_owners:
                if bad_owner in owner_lower:
                    return ReputationMatch(
                        ip=clean_ip,
                        feed_name=self.feed_name,
                        feed_date=self.feed_date,
                        category="network_owner",
                        network_owner=network_owner,
                        matched_value=bad_owner,
                        detail=f"{clean_ip or 'Login'} network owner '{network_owner}' matches flagged provider in {self.feed_name} ({self.feed_date})",
                    )

        return None


# Module singleton
_feed: Optional[IPReputationFeed] = None


def get_feed(cfg: Optional[dict[str, Any]] = None) -> IPReputationFeed:
    """Return process-wide IPReputationFeed, initialised from configuration or defaults."""
    global _feed
    if _feed is None:
        rep_cfg = {}
        if cfg and "login" in cfg and "ip_reputation" in cfg["login"]:
            rep_cfg = cfg["login"]["ip_reputation"]

        feed_name = rep_cfg.get("feed_name") or os.environ.get(
            "TRACEGUARD_IP_FEED_NAME", "Campus Threat Intelligence Feed"
        )
        feed_date = rep_cfg.get("feed_date") or os.environ.get("TRACEGUARD_IP_FEED_DATE")
        feed_path = rep_cfg.get("feed_path") or os.environ.get("TRACEGUARD_IP_FEED_PATH")
        feed_url = rep_cfg.get("feed_url") or os.environ.get("TRACEGUARD_IP_FEED_URL")
        max_age_days = int(rep_cfg.get("max_age_days", 7))
        refresh_hours = int(rep_cfg.get("refresh_hours", 24))

        feed = IPReputationFeed(
            feed_name=feed_name,
            feed_date=feed_date,
            feed_path=feed_path,
            feed_url=feed_url,
            max_age_days=max_age_days,
            refresh_hours=refresh_hours,
        )
        # Attempt to load local file or URL
        feed.refresh(force=True)
        _feed = feed
    return _feed


def reset_feed() -> None:
    """Reset singleton instance (used in tests)."""
    global _feed
    _feed = None
