"""Loader and evaluator for the RBA login data set (Wiefling et al., CC BY 4.0).

The data set is >33 million synthesised login attempts. Its authors warn that feature values are plausible
but artificial, so this module is for testing the pipeline and ranking behaviour, not for claiming detection
rates against real attackers.

Source: https://zenodo.org/records/6782156  (also released at https://github.com/das-group/rba-dataset)
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
import zipfile
from collections import Counter
from pathlib import Path
from typing import Iterator, Optional

from .engine.baseline import device_key
from .engine.bulk import score_stream
from .engine.types import LoginEvent

CSV_NAME = "rba-dataset.csv"


def _open_text(path: str | Path):
    p = Path(path)
    if p.suffix == ".zip":
        zf = zipfile.ZipFile(p)
        name = next((n for n in zf.namelist() if n.endswith(".csv")), CSV_NAME)
        return io.TextIOWrapper(zf.open(name), encoding="utf-8", newline="")
    return open(p, newline="", encoding="utf-8")


def iter_rows(path: str | Path, max_rows: Optional[int] = None) -> Iterator[dict]:
    with _open_text(path) as fh:
        for i, row in enumerate(csv.DictReader(fh)):
            if max_rows is not None and i >= max_rows:
                return
            yield row


def _flag(v: str) -> bool:
    return str(v).strip().lower() in {"true", "1", "yes"}


def to_event(row: dict) -> Optional[tuple[LoginEvent, bool]]:
    try:
        city = row.get("City", "")
        if city in {"-", ""}:
            city = ""
        ev = LoginEvent(
            user_id=str(row["User ID"]), ts=row["Login Timestamp"].replace(" ", "T") + "+00:00", ip=row.get("IP Address", ""),
            country=row.get("Country", ""), city=city, asn=int(row["ASN"]) if str(row.get("ASN", "")).isdigit() else None,
            device=device_key(row.get("OS Name and Version", ""), row.get("Browser Name and Version", "")),
            device_type=row.get("Device Type", ""), success=_flag(row.get("Login Successful", "")), is_attack_ip=_flag(row.get("Is Attack IP", "")))
    except (KeyError, ValueError):
        return None
    return ev, _flag(row.get("Is Account Takeover", ""))


def load(path: str | Path, max_rows: Optional[int] = None, sample_users: Optional[int] = None, seed: int = 1) -> list[tuple[LoginEvent, bool]]:
    """Read rows. With `sample_users`, keep every account that has an account-takeover or attack-IP row,
    plus a deterministic hash-based sample of other accounts, so histories stay complete (two passes)."""
    if not sample_users:
        return [x for x in (to_event(r) for r in iter_rows(path, max_rows)) if x]
    keep: set[str] = set()
    seen: set[str] = set()
    for r in iter_rows(path, max_rows):
        uid = str(r.get("User ID"))
        seen.add(uid)
        if _flag(r.get("Is Account Takeover", "")):
            keep.add(uid)
    for uid in sorted(seen, key=lambda u: hashlib.sha1(f"{seed}-{u}".encode()).hexdigest())[:sample_users]:
        keep.add(uid)
    return [x for x in (to_event(r) for r in iter_rows(path, max_rows) if str(r.get("User ID")) in keep) if x]


def evaluate(pairs: list[tuple[LoginEvent, bool]], cfg: Optional[dict] = None, disable_travel: bool = False, disable_attack_ip: bool = True) -> dict:
    """Score every login with the attack-IP signal switched off, then ask: do the behavioural signals alone rank
    attack-IP logins (and account takeovers, if present) above ordinary ones? Reported for all rows and for rows
    where the user already has an established history (5 or more earlier successful logins)."""
    from sklearn.metrics import roc_auc_score
    from .engine import config as cfgmod
    cfg = cfg or cfgmod.get()
    disabled = ({"attack_ip"} if disable_attack_ip else set()) | ({"impossible_travel"} if disable_travel else set())
    ato_by_key = {(e.user_id, e.ts, e.ip): ato for e, ato in pairs}
    fail_by_key = {(e.user_id, e.ts, e.ip): (0 if e.success else 1) for e, _ in pairs}
    rows = []                                    # (attack_ip, ato, failed, risk, thin)
    fired = Counter()
    for ev, score, band, flags, thin in score_stream([e for e, _ in pairs], cfg, disabled):
        k = (ev.user_id, ev.ts, ev.ip)
        rows.append((1 if ev.is_attack_ip else 0, 1 if ato_by_key.get(k) else 0, fail_by_key.get(k, 0), score, thin))
        fired.update(flags)
    med, high = cfg["bands"]["medium"][0], cfg["bands"]["high"][0]

    def auc(y, x):
        return round(float(roc_auc_score(y, x)), 4) if 0 < sum(y) < len(y) else None

    def at(subset, label_idx, threshold):
        flagged = [r[3] >= threshold for r in subset]
        y = [r[label_idx] for r in subset]
        tp = sum(1 for f, v in zip(flagged, y) if f and v)
        fp = sum(1 for f, v in zip(flagged, y) if f and not v)
        pos = sum(y)
        return {"threshold": threshold, "flagged_share": round(sum(flagged) / len(subset), 4) if subset else 0,
                "precision": round(tp / (tp + fp), 4) if (tp + fp) else None, "recall": round(tp / pos, 4) if pos else None}

    def block(subset):
        return {
            "rows": len(subset), "attack_ip_rows": sum(r[0] for r in subset), "account_takeover_rows": sum(r[1] for r in subset),
            "auc_attack_ip": auc([r[0] for r in subset], [r[3] for r in subset]),
            "auc_account_takeover": auc([r[1] for r in subset], [r[3] for r in subset]),
            "auc_attack_ip_failed_login_rule": auc([r[0] for r in subset], [r[2] for r in subset]),
            "auc_account_takeover_failed_login_rule": auc([r[1] for r in subset], [r[2] for r in subset]),
            "attack_ip_at_medium": at(subset, 0, med), "attack_ip_at_high": at(subset, 0, high),
            "account_takeover_at_medium": at(subset, 1, med), "account_takeover_at_high": at(subset, 1, high),
        }
    established = [r for r in rows if not r[4]]
    return {
        "source": "RBA data set (artificial values; see README)", "users": len({e.user_id for e, _ in pairs}),
        "label_note": ("Behavioural signals only: TraceGuard's attack-IP signal is switched off so the score cannot read the label." if disable_attack_ip
                       else "Attack-IP signal ON (a threat feed). The Is Attack IP label is then partly circular; read only the account-takeover numbers."),
        "attack_ip_signal": not disable_attack_ip, "impossible_travel_disabled": disable_travel,
        "account_takeover_rows_with_no_or_thin_history": sum(1 for r in rows if r[1] and r[4]),
        "all_rows": block(rows), "established_history_rows": block(established),
        "signals_fired": dict(fired.most_common()),
    }


def write_eval(path_in: str | Path, path_out: Path, max_rows: Optional[int] = None, sample_users: Optional[int] = None) -> dict:
    pairs = load(path_in, max_rows, sample_users)
    stamps = sorted(e.ts for e, _ in pairs)
    result = {
        "behavioural_only": evaluate(pairs, disable_attack_ip=True),
        "with_threat_feed_signal": evaluate(pairs, disable_attack_ip=False),
        "input": {"file": Path(path_in).name, "max_rows": max_rows, "sample_users": sample_users, "rows_scored": len(pairs),
                  "from": stamps[0].isoformat() if stamps else None, "to": stamps[-1].isoformat() if stamps else None,
                  "sampling": "every account with an account-takeover row, plus a deterministic hash sample of other accounts, all of their rows kept"},
    }
    path_out.parent.mkdir(parents=True, exist_ok=True)
    path_out.write_text(json.dumps(result, indent=2), encoding="utf-8")
    return result
