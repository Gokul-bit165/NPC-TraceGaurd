"""Past-only login features for the IP-reputation and login-anomaly models (RBA data).

One chronological pass; every feature of row i uses rows strictly before i (same timestamp ties are broken by file order).
Excluded as inputs on purpose: User ID, exact IP string, Is Attack IP, Is Account Takeover (kept only as labels).

    python login_features.py --src ../backend/data/rba_head.csv --out ../dataset/processed_v2/login/features.parquet|csv.gz
"""
import argparse
import bisect
import ipaddress
import re
from collections import Counter, defaultdict, deque
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
H1, H24 = 3600.0, 86400.0


def load_ranges(path):
    nets = []
    for l in open(path, errors="ignore"):
        l = l.strip()
        if l and not l.startswith("#"):
            try:
                n = ipaddress.ip_network(l, strict=False)
                if n.version == 4:
                    nets.append(n)
            except ValueError:
                pass
    m = list(ipaddress.collapse_addresses(sorted(nets)))
    return [int(n.network_address) for n in m], [int(n.broadcast_address) for n in m]


def hit(ranges, ipint):
    s, e = ranges
    i = bisect.bisect_right(s, ipint) - 1
    return int(i >= 0 and ipint <= e[i])


def family(s):
    return re.sub(r"[\d.]+$", "", str(s)).strip() or "unknown"


def build(src, dataset_dir):
    cols = ["Login Timestamp", "User ID", "Round-Trip Time [ms]", "IP Address", "Country", "ASN", "Browser Name and Version", "OS Name and Version",
            "Device Type", "Login Successful", "Is Attack IP", "Is Account Takeover"]
    d = pd.read_csv(src, usecols=cols)
    d.columns = ["ts", "user", "rtt", "ip", "country", "asn", "browser", "os", "device_type", "success", "attack_ip", "takeover"]
    d["t"] = pd.to_datetime(d.ts).astype("int64") / 1e9
    d = d.sort_values("t", kind="stable").reset_index(drop=True)
    d["browser_family"] = d.browser.map(family)
    d["os_family"] = d.os.map(family)
    d["dev"] = d.os_family + "|" + d.browser_family
    d["hour"] = ((d.t % 86400) // 3600).astype(int)
    r1 = load_ranges(dataset_dir / "firehol_level1.netset"); r2 = load_ranges(dataset_dir / "firehol_level2.netset")
    ipint = d.ip.map(lambda x: int(ipaddress.ip_address(x)) if re.match(r"^\d+\.\d+\.\d+\.\d+$", str(x)) else -1)
    d["threat_l1"] = [hit(r1, v) if v >= 0 else 0 for v in ipint]
    d["threat_l2"] = [hit(r2, v) if v >= 0 else 0 for v in ipint]

    n = len(d)
    f = {k: np.zeros(n, dtype=np.float32) for k in
         ["ip_rows_1h", "ip_rows_24h", "ip_users_1h", "ip_users_24h", "ip_fail_rate_24h", "ip_fail_rate_all", "ip_countries", "ip_devices",
          "ip_age_h", "ip_prior_rows", "new_country", "new_asn", "new_device", "hour_diff", "fails_before", "since_last_h", "hist_len", "user_ips_seen_24h"]}
    ipw = defaultdict(deque)           # ip -> deque[(t, user, failed)]
    ipu24 = defaultdict(Counter); ipu1 = defaultdict(Counter); ipf24 = Counter()
    ipfirst, ipall, ipallfail = {}, Counter(), Counter()
    ipc, ipd = defaultdict(set), defaultdict(set)
    ucount = Counter(); ucountry = defaultdict(set); uasn = defaultdict(set); udev = defaultdict(set)
    ulast = {}; ufail = Counter(); usin = defaultdict(float); ucos = defaultdict(float); uw = defaultdict(deque)
    T, U, IP, CO, AS, DV, SU, HR = (d[c].values for c in ["t", "user", "ip", "country", "asn", "dev", "success", "hour"])
    for i in range(n):
        t, u, ip = T[i], U[i], IP[i]
        q = ipw[ip]
        while q and q[0][0] < t - H24:                     # expire > 24 h
            _, uu, ff = q.popleft(); ipu24[ip][uu] -= 1
            if ipu24[ip][uu] <= 0: del ipu24[ip][uu]
            ipf24[ip] -= ff
        # 1 h window is a suffix of the 24 h deque
        c1 = Counter(); r1n = 0
        for tt, uu, _ in reversed(q):
            if tt < t - H1: break
            c1[uu] += 1; r1n += 1
        f["ip_rows_1h"][i] = r1n; f["ip_users_1h"][i] = len(c1)
        f["ip_rows_24h"][i] = len(q); f["ip_users_24h"][i] = len(ipu24[ip])
        f["ip_fail_rate_24h"][i] = ipf24[ip] / len(q) if q else 0
        a = ipall[ip]
        f["ip_prior_rows"][i] = a; f["ip_fail_rate_all"][i] = ipallfail[ip] / a if a else 0
        f["ip_countries"][i] = len(ipc[ip]); f["ip_devices"][i] = len(ipd[ip])
        f["ip_age_h"][i] = (t - ipfirst[ip]) / 3600 if ip in ipfirst else 0
        # ---- user history (past only)
        h = ucount[u]
        f["hist_len"][i] = h
        if h:
            f["new_country"][i] = float(CO[i] not in ucountry[u]); f["new_asn"][i] = float(AS[i] not in uasn[u]); f["new_device"][i] = float(DV[i] not in udev[u])
            ang = 2 * np.pi * HR[i] / 24; m = np.arctan2(usin[u], ucos[u]); dd = abs((ang - m + np.pi) % (2 * np.pi) - np.pi) * 24 / (2 * np.pi)
            f["hour_diff"][i] = dd
            f["since_last_h"][i] = (t - ulast[u]) / 3600
        else:
            f["since_last_h"][i] = -1
        f["fails_before"][i] = ufail[u]
        w = uw[u]
        while w and w[0][0] < t - H24: w.popleft()
        f["user_ips_seen_24h"][i] = len({x[1] for x in w})
        # ---- update state AFTER computing features
        failed = 0 if SU[i] else 1
        q.append((t, u, failed)); ipu24[ip][u] += 1; ipf24[ip] += failed
        ipfirst.setdefault(ip, t); ipall[ip] += 1; ipallfail[ip] += failed; ipc[ip].add(CO[i]); ipd[ip].add(DV[i])
        ucount[u] += 1; ucountry[u].add(CO[i]); uasn[u].add(AS[i]); udev[u].add(DV[i]); ulast[u] = t
        ufail[u] = 0 if SU[i] else ufail[u] + 1
        if SU[i]:
            ang = 2 * np.pi * HR[i] / 24; usin[u] += np.sin(ang); ucos[u] += np.cos(ang)
        w.append((t, ip))
        if i % 300000 == 0: print("  features", i, "/", n, flush=True)
    out = pd.concat([d.drop(columns=["ts", "browser", "os", "dev"]), pd.DataFrame(f)], axis=1)
    out["success"] = out.success.astype(bool); out["attack_ip"] = out.attack_ip.astype(bool); out["takeover"] = out.takeover.astype(bool)
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", default=str(HERE.parents[1] / "backend" / "data" / "rba_head.csv"))
    ap.add_argument("--out", default=str(HERE.parent / "processed_v2" / "login" / "features.csv.gz"))
    a = ap.parse_args()
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    df = build(a.src, HERE.parent)
    df.to_csv(a.out, index=False)
    print(df.shape, "->", a.out)
