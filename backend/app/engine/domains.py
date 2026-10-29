"""Domain helpers: registrable domain, edit distance, lookalike detection."""
from __future__ import annotations

import re
from typing import Optional
from urllib.parse import urlparse

MULTI_SUFFIX = {
    "co.uk", "ac.uk", "org.uk", "gov.uk", "co.in", "ac.in", "edu.in", "gov.in", "org.in", "net.in", "res.in",
    "com.au", "edu.au", "gov.au", "org.au", "com.br", "co.jp", "ac.jp", "co.za", "ac.za", "com.cn", "edu.cn",
    "com.ng", "edu.ng", "co.nz", "com.sg", "edu.sg", "com.pk", "edu.pk",
}
_IPV4 = re.compile(r"^\d{1,3}(\.\d{1,3}){3}$")
_GLYPH = str.maketrans({"0": "o", "1": "l", "3": "e", "4": "a", "5": "s", "7": "t", "$": "s", "@": "a"})


def host_of(url: str) -> str:
    """Host of a URL, lower-cased, without port or userinfo. Empty string if there is none."""
    u = url.strip()
    if not re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*://", u):
        u = "http://" + u
    try:
        return (urlparse(u).hostname or "").lower().rstrip(".")
    except ValueError:
        return ""


def has_userinfo(url: str) -> bool:
    u = url.strip()
    if not re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*://", u):
        u = "http://" + u
    try:
        p = urlparse(u)
        return bool(p.username)
    except ValueError:
        return False


def is_ip_host(host: str) -> bool:
    return bool(_IPV4.match(host)) or (host.startswith("[") and host.endswith("]")) or ":" in host


def registrable(host: str) -> str:
    host = (host or "").lower().strip(".")
    if not host or is_ip_host(host):
        return host
    parts = host.split(".")
    if len(parts) <= 2:
        return host
    if ".".join(parts[-2:]) in MULTI_SUFFIX:
        return ".".join(parts[-3:])
    return ".".join(parts[-2:])


def tld_of(host: str) -> str:
    return host.rsplit(".", 1)[-1] if "." in host else ""


def address_domain(addr: str) -> str:
    m = re.search(r"@([A-Za-z0-9.-]+)", addr or "")
    return m.group(1).lower().rstrip(".") if m else ""


def levenshtein(a: str, b: str) -> int:
    if a == b:
        return 0
    if not a or not b:
        return max(len(a), len(b))
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


def lookalike(domain: str, cfg: dict) -> Optional[str]:
    """Return a human-readable reason if `domain` imitates a protected brand/campus domain, else None."""
    host = (domain or "").lower().strip(".")
    if not host or is_ip_host(host):
        return None
    reg = registrable(host)
    trusted = set(cfg["campus"]["trusted_domains"]) | set(cfg["campus"]["protected_domains"])
    if reg in trusted:
        return None
    if any(lbl.startswith("xn--") for lbl in host.split(".")):
        return f"{host} uses punycode (internationalised characters that can imitate a real name)"
    label = reg.split(".")[0]
    norm = label.translate(_GLYPH)
    tokens = [t for t in re.split(r"[-_]", norm) if t]
    for brand in cfg["campus"]["protected_brands"]:
        if norm == brand:
            return f"{reg} uses the name '{brand}' but is not a trusted {brand} domain"
        if len(brand) >= 5 and 1 <= levenshtein(norm, brand) <= 2:
            return f"{reg} is one or two characters away from '{brand}'"
        if brand in tokens or (len(brand) >= 6 and brand in norm):
            return f"{reg} embeds the name '{brand}' on an untrusted domain"
    return None
