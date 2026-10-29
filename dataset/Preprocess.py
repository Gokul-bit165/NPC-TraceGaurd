#!/usr/bin/env python3
"""
TraceGuard - data preprocessing
================================
Prepares the three downloaded datasets:

  1. Kaggle phishing emails  -> cleaned, de-duplicated, split train/val/test
                                (+ a cross-source hold-out test set)
  2. RBA login data          -> normalised login table + blind-spot report
  3. FireHOL level1/level2   -> merged public-IP threat list (private ranges removed)

Usage (folders can be anywhere; each may contain sub-folders):
    python preprocess.py --kaggle-dir data/kaggle --rba-dir data/rba \
                         --firehol-dir data/firehol --out processed

Run one part only:
    python preprocess.py --steps emails
    python preprocess.py --steps rba,firehol

Requires: pandas, scikit-learn.  Optional: beautifulsoup4 (better HTML cleaning).
"""
import argparse
import bisect
import hashlib
import ipaddress
import json
import re
import unicodedata
import zipfile
from datetime import date
from pathlib import Path

import pandas as pd

SEED = 42

# ----------------------------------------------------------------------------
# 1. EMAILS
# ----------------------------------------------------------------------------
ZERO_WIDTH = re.compile(r"[\u200b\u200c\u200d\u2060\ufeff\u00ad]")
URL_RE = re.compile(r"(?:https?://|www\.)[^\s<>\"')]+", re.I)
EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
LOOKS_HTML = re.compile(r"<\s*(html|body|div|p|a|span|table|br|font|style|script)\b", re.I)
HIDDEN_STYLE = re.compile(
    r"display\s*:\s*none|visibility\s*:\s*hidden|font-size\s*:\s*0|opacity\s*:\s*0"
    r"|color\s*:\s*(?:#f{3}(?:f{3})?\b|white\b)",
    re.I,
)

try:
    from bs4 import BeautifulSoup, Comment
    import warnings
    from bs4 import MarkupResemblesLocatorWarning
    warnings.filterwarnings("ignore", category=MarkupResemblesLocatorWarning)
    HAVE_BS4 = True
except ImportError:  # fallback to regex stripping
    HAVE_BS4 = False


def visible_text(raw: str):
    """Return (visible_text, hidden_chars, zero_width_count).
    Mirrors the pipeline rule: only visible text is analysed; hidden text is
    counted as evidence, never used as content."""
    raw = "" if raw is None else str(raw)
    zw = len(ZERO_WIDTH.findall(raw))
    raw = ZERO_WIDTH.sub("", raw)
    hidden = 0
    if LOOKS_HTML.search(raw):
        if HAVE_BS4:
            soup = BeautifulSoup(raw, "html.parser")
            for c in soup.find_all(string=lambda s: isinstance(s, Comment)):
                hidden += len(c)
                c.extract()
            for tag in soup(["script", "style", "head", "title"]):
                tag.decompose()
            for tag in soup.find_all(style=HIDDEN_STYLE):
                hidden += len(tag.get_text(" "))
                tag.decompose()
            raw = soup.get_text(" ")
        else:
            raw = re.sub(r"(?is)<(script|style|head)\b.*?</\1>", " ", raw)
            raw = re.sub(r"(?s)<!--.*?-->", " ", raw)
            raw = re.sub(r"<[^>]+>", " ", raw)
    return raw, hidden, zw


def normalise(text: str):
    """Visible text -> model text. URLs / addresses become tokens (counts kept)."""
    text = unicodedata.normalize("NFKC", html_unescape(text))
    n_urls = len(URL_RE.findall(text))
    text = URL_RE.sub(" urltoken ", text)
    text = EMAIL_RE.sub(" emailtoken ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text, n_urls


def html_unescape(s: str) -> str:
    import html
    return html.unescape(s)


def find_text_and_label(df: pd.DataFrame):
    cols = {c.lower().strip(): c for c in df.columns}
    label = cols.get("label") or cols.get("class") or cols.get("target")
    if "subject" in cols and "body" in cols:
        text = df[cols["subject"]].fillna("").astype(str) + " . " + df[cols["body"]].fillna("").astype(str)
    elif "text_combined" in cols:
        text = df[cols["text_combined"]].fillna("").astype(str)
    elif "text" in cols:
        text = df[cols["text"]].fillna("").astype(str)
    elif "body" in cols:
        text = df[cols["body"]].fillna("").astype(str)
    else:
        return None, None
    return text, label


def load_kaggle(folder: Path, include_combined: bool):
    frames, report = [], []
    files = sorted(folder.rglob("*.csv"))
    if not files:
        raise SystemExit(f"No CSV files found under {folder}")
    for f in files:
        try:
            df = pd.read_csv(f, encoding_errors="replace", on_bad_lines="skip", low_memory=False)
        except Exception as e:  # noqa
            report.append(f"SKIPPED {f.name}: {e}")
            continue
        text, label = find_text_and_label(df)
        is_combined = "text_combined" in [c.lower() for c in df.columns]
        if text is None or label is None:
            report.append(f"SKIPPED {f.name}: no usable text/label columns {list(df.columns)}")
            continue
        if is_combined and not include_combined and len(files) > 1:
            report.append(f"SKIPPED {f.name}: aggregate of the other files (use --include-combined to keep)")
            continue
        out = pd.DataFrame({
            "source": f.stem,
            "raw_text": text.values,
            "label": pd.to_numeric(df[label], errors="coerce").values,
        })
        report.append(f"LOADED  {f.name}: {len(out)} rows, columns={list(df.columns)}")
        frames.append(out)
    if not frames:
        raise SystemExit("\n".join(report) + "\nNothing usable loaded.")
    return pd.concat(frames, ignore_index=True), report


def md5(s: str) -> str:
    return hashlib.md5(s.encode("utf-8", "ignore")).hexdigest()


def preprocess_emails(kaggle_dir: Path, out: Path, holdout: str, include_combined: bool, min_chars: int):
    from sklearn.model_selection import train_test_split

    df, report = load_kaggle(kaggle_dir, include_combined)
    stats = {"loaded_rows": int(len(df))}

    df = df[df["label"].isin([0, 1])].copy()
    df["label"] = df["label"].astype(int)
    stats["after_valid_label"] = int(len(df))

    vis = df["raw_text"].map(visible_text)
    df["visible"] = vis.map(lambda t: t[0])
    df["hidden_chars"] = vis.map(lambda t: t[1])
    df["zero_width"] = vis.map(lambda t: t[2])
    norm = df["visible"].map(normalise)
    df["text"] = norm.map(lambda t: t[0])
    df["url_count"] = norm.map(lambda t: t[1])
    df = df.drop(columns=["raw_text", "visible"])

    df = df[df["text"].str.len() >= min_chars]
    stats["after_min_length"] = int(len(df))

    # exact duplicates, then near duplicates (letters only), then conflicting labels
    df["k_exact"] = df["text"].str.lower().map(md5)
    df["k_near"] = df["text"].str.lower().map(lambda s: md5(re.sub(r"[^a-z]+", " ", s).strip()))
    conflict = df.groupby("k_near")["label"].transform("nunique") > 1
    stats["dropped_conflicting_labels"] = int(conflict.sum())
    df = df[~conflict]
    df = df.drop_duplicates("k_exact").drop_duplicates("k_near")
    stats["after_dedup"] = int(len(df))

    # split: cross-source hold-out + stratified random split of the rest
    is_hold = df["source"].str.lower().str.contains(holdout.lower(), regex=False) if holdout else pd.Series(False, index=df.index)
    hold, rest = df[is_hold].copy(), df[~is_hold].copy()
    train, tmp = train_test_split(rest, test_size=0.2, stratify=rest["label"], random_state=SEED)
    val, test = train_test_split(tmp, test_size=0.5, stratify=tmp["label"], random_state=SEED)
    if len(hold):  # no leakage from train into hold-out
        hold = hold[~hold["k_near"].isin(set(train["k_near"]) | set(val["k_near"]) | set(test["k_near"]))]

    out.mkdir(parents=True, exist_ok=True)
    keep = ["source", "label", "text", "url_count", "hidden_chars", "zero_width"]
    for name, part in [("train", train), ("val", val), ("test_in_distribution", test), ("test_cross_source", hold)]:
        part[keep].to_csv(out / f"emails_{name}.csv", index=False)
        stats[f"{name}_rows"] = int(len(part))
        stats[f"{name}_phishing_share"] = round(float(part["label"].mean()), 3) if len(part) else None
    stats["rows_by_source_and_label"] = {
        s: {int(k): int(v) for k, v in g["label"].value_counts().items()} for s, g in df.groupby("source")
    }
    stats["holdout_source"] = holdout or None
    stats["notes"] = [
        "label 1 = phishing/spam as labelled by the dataset authors; some sources are spam or fraud, not only phishing.",
        "Text model results must be reported as TEXT-MODEL results on public data, not whole-system accuracy.",
        "Production must apply the same cleaning (visible_text + normalise) before scoring.",
    ]
    (out / "emails_report.json").write_text(json.dumps({"files": report, "stats": stats}, indent=2))
    print("\n".join(report))
    print(json.dumps(stats, indent=2))
    if holdout and not len(hold):
        print(f"WARNING: hold-out source '{holdout}' matched nothing; cross-source test is empty.")


# ----------------------------------------------------------------------------
# 2. FIREHOL
# ----------------------------------------------------------------------------
NON_PUBLIC = [ipaddress.ip_network(n) for n in (
    "0.0.0.0/8", "10.0.0.0/8", "100.64.0.0/10", "127.0.0.0/8", "169.254.0.0/16",
    "172.16.0.0/12", "192.0.0.0/24", "192.0.2.0/24", "192.168.0.0/16", "198.18.0.0/15",
    "198.51.100.0/24", "203.0.113.0/24", "224.0.0.0/4", "240.0.0.0/4")]


def preprocess_firehol(folder: Path, out: Path):
    files = sorted(list(folder.rglob("*.netset")) + list(folder.rglob("*.ipset")))
    if not files:
        raise SystemExit(f"No .netset/.ipset files found under {folder}")
    nets, per_file, dropped = [], {}, 0
    for f in files:
        kept = 0
        for line in f.read_text(errors="ignore").splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            try:
                net = ipaddress.ip_network(line, strict=False)
            except ValueError:
                continue
            if net.version != 4:
                continue
            if any(net.overlaps(x) for x in NON_PUBLIC):
                dropped += 1
                continue
            nets.append(net)
            kept += 1
        per_file[f.name] = kept
    merged = list(ipaddress.collapse_addresses(sorted(nets)))
    out.mkdir(parents=True, exist_ok=True)
    pd.DataFrame({
        "start": [int(n.network_address) for n in merged],
        "end": [int(n.broadcast_address) for n in merged],
        "cidr": [str(n) for n in merged],
    }).to_csv(out / "threat_ranges.csv", index=False)
    addresses = sum(n.num_addresses for n in merged)
    meta = {
        "downloaded_on": date.today().isoformat(),
        "source_files": per_file,
        "private_or_reserved_ranges_dropped": dropped,
        "merged_ranges": len(merged),
        "total_addresses": addresses,
        "note": "Refresh regularly and re-run. Check each list's licence before redistributing.",
    }
    (out / "threat_ranges_meta.json").write_text(json.dumps(meta, indent=2))
    print(json.dumps(meta, indent=2))


class ThreatList:
    """Fast lookup used by the login scorer:  ThreatList('processed').contains('1.2.3.4')"""

    def __init__(self, folder):
        d = pd.read_csv(Path(folder) / "threat_ranges.csv")
        self.starts, self.ends = d["start"].tolist(), d["end"].tolist()

    def contains(self, ip: str) -> bool:
        try:
            v = int(ipaddress.ip_address(ip))
        except ValueError:
            return False
        i = bisect.bisect_right(self.starts, v) - 1
        return i >= 0 and v <= self.ends[i]


# ----------------------------------------------------------------------------
# 3. RBA LOGINS
# ----------------------------------------------------------------------------
def snake(c: str) -> str:
    return re.sub(r"[^0-9a-z]+", "_", c.lower()).strip("_")


def parse_ts(s: pd.Series) -> pd.Series:
    """Accept text dates OR integer epochs (s / ms / us / ns, detected by size)."""
    num = pd.to_numeric(s, errors="coerce")
    if num.notna().mean() > 0.9:
        m = num.dropna().abs().median()
        unit = "ns" if m > 1e17 else "us" if m > 1e14 else "ms" if m > 1e11 else "s"
        return pd.to_datetime(num, unit=unit, errors="coerce")
    return pd.to_datetime(s, errors="coerce")


def strip_version(s) -> str:
    return re.sub(r"[\d.]+$", "", str(s)).strip() or "unknown"


def read_rba(folder: Path, max_rows):
    csvs = sorted(folder.rglob("*.csv"))
    zips = sorted(folder.rglob("*.zip"))
    if csvs:
        src, opener = csvs[0], lambda: open(csvs[0], "rb")
    elif zips:
        z = zipfile.ZipFile(zips[0])
        name = next(n for n in z.namelist() if n.lower().endswith(".csv"))
        src, opener = zips[0], lambda: z.open(name)
    else:
        raise SystemExit(f"No CSV or ZIP found under {folder}")
    print(f"Reading RBA from {src}")
    parts, n = [], 0
    with opener() as fh:
        for chunk in pd.read_csv(fh, chunksize=500_000, low_memory=False):
            chunk.columns = [snake(c) for c in chunk.columns]
            parts.append(chunk)
            n += len(chunk)
            if max_rows and n >= max_rows:
                break
    df = pd.concat(parts, ignore_index=True)
    return df.head(max_rows) if max_rows else df


def preprocess_rba(folder: Path, out: Path, max_rows, threat_dir: Path):
    df = read_rba(folder, max_rows)
    if len(df) > 5_000_000:
        print("WARNING: very large table; consider --rba-max-rows to work on a sample.")
    df = df.rename(columns={c: "rtt_ms" for c in df.columns if c.startswith("round_trip_time")})
    rename = {
        "login_timestamp": "timestamp", "user_id": "user_id", "ip_address": "ip",
        "round_trip_time_ms": "rtt_ms", "browser_name_and_version": "browser",
        "os_name_and_version": "os", "login_successful": "success",
        "is_attack_ip": "attack_ip", "is_account_takeover": "takeover",
    }
    df = df.rename(columns={k: v for k, v in rename.items() if k in df.columns})
    df["timestamp"] = parse_ts(df["timestamp"])
    df = df.dropna(subset=["timestamp", "user_id", "ip"])
    for c in ("success", "attack_ip", "takeover"):
        if c in df.columns:
            df[c] = df[c].astype(str).str.lower().isin(["true", "1", "yes"])
    df["device"] = df["os"].map(strip_version) + " | " + df["browser"].map(strip_version)
    df["hour"] = df["timestamp"].dt.hour
    df = df.sort_values(["user_id", "timestamp"]).reset_index(drop=True)
    df["prior_logins"] = df.groupby("user_id").cumcount()

    out.mkdir(parents=True, exist_ok=True)
    keep = [c for c in ["timestamp", "user_id", "ip", "country", "region", "city", "asn", "device",
                        "hour", "success", "attack_ip", "takeover", "prior_logins", "rtt_ms"] if c in df.columns]
    df[keep].to_csv(out / "rba_logins.csv.gz", index=False)

    rep = {"rows": int(len(df)), "users": int(df["user_id"].nunique()),
           "date_range": [str(df["timestamp"].min()), str(df["timestamp"].max())]}
    if "takeover" in df.columns:
        tk = df[df["takeover"]]
        rep["account_takeovers"] = int(len(tk))
        rep["takeovers_with_<5_prior_logins"] = int((tk["prior_logins"] < 5).sum())
        rep["note"] = "Takeovers on accounts with little history are invisible to behaviour-only scoring."
    tl_file = threat_dir / "threat_ranges.csv"
    if tl_file.exists() and "attack_ip" in df.columns:
        tl = ThreatList(threat_dir)
        ips = df.drop_duplicates("ip")[["ip", "attack_ip"]]
        if len(ips) > 200_000:
            ips = ips.sample(200_000, random_state=SEED)
        ips = ips.assign(listed=ips["ip"].map(tl.contains))
        rep["threat_list_match_rate_attack_ips"] = round(float(ips[ips["attack_ip"]]["listed"].mean()), 4)
        rep["threat_list_match_rate_other_ips"] = round(float(ips[~ips["attack_ip"]]["listed"].mean()), 4)
    (out / "rba_report.json").write_text(json.dumps(rep, indent=2, default=str))
    print(json.dumps(rep, indent=2, default=str))


# ----------------------------------------------------------------------------
def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--kaggle-dir", type=Path, default=Path("data/kaggle"))
    p.add_argument("--rba-dir", type=Path, default=Path("data/rba"))
    p.add_argument("--firehol-dir", type=Path, default=Path("data/firehol"))
    p.add_argument("--out", type=Path, default=Path("processed"))
    p.add_argument("--steps", default="firehol,emails,rba", help="comma list of: emails, rba, firehol")
    p.add_argument("--holdout-source", default="SpamAssasin",
                   help="filename (or part of it) of the source kept ONLY for the cross-source test; '' to disable")
    p.add_argument("--include-combined", action="store_true", help="also load the aggregate phishing_email.csv")
    p.add_argument("--min-chars", type=int, default=20)
    p.add_argument("--rba-max-rows", type=int, default=None)
    a = p.parse_args()
    steps = [s.strip() for s in a.steps.split(",")]

    if "firehol" in steps:
        print("\n=== FireHOL threat lists ===")
        preprocess_firehol(a.firehol_dir, a.out)
    if "emails" in steps:
        print("\n=== Kaggle phishing emails ===")
        preprocess_emails(a.kaggle_dir, a.out, a.holdout_source, a.include_combined, a.min_chars)
    if "rba" in steps:
        print("\n=== RBA logins ===")
        preprocess_rba(a.rba_dir, a.out, a.rba_max_rows, a.out)
    print(f"\nDone. Outputs are in {a.out.resolve()}")


if __name__ == "__main__":
    main()