"""Loader tests on 400 real rows from the RBA data set (CC BY 4.0, Wiefling et al.)."""
from pathlib import Path

from app import rba
from app.engine.bulk import score_stream

FIX = Path(__file__).parent / "fixtures" / "rba_head_400.csv"


def test_loads_real_rows_and_maps_columns():
    pairs = rba.load(FIX)
    assert len(pairs) == 400
    ev, ato = pairs[0]
    assert ev.user_id.lstrip("-").isdigit() and ev.ts.tzinfo is not None
    assert ev.device and "|" in ev.device and not any(ch.isdigit() for ch in ev.device)     # versions stripped
    assert ato is False
    assert all(e.city != "-" for e, _ in pairs)


def test_sample_users_keeps_complete_histories(tmp_path):
    import csv
    with open(FIX, newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    victim = rows[5]["User ID"]
    rows[5]["Is Account Takeover"] = "True"                     # mark one account as a takeover victim
    p = tmp_path / "x.csv"
    with open(p, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    pairs = rba.load(p, sample_users=3)                          # aggressive sampling must still keep the victim, with every row
    assert victim in {e.user_id for e, _ in pairs}
    assert sum(1 for e, _ in pairs if e.user_id == victim) == sum(1 for r in rows if r["User ID"] == victim)
    assert sum(1 for _, ato in pairs if ato) == 1


def test_scoring_stream_and_evaluation_run_on_real_rows():
    pairs = rba.load(FIX)
    out = list(score_stream([e for e, _ in pairs]))
    assert len(out) == 400 and all(0 <= s <= 100 for _, s, _, _, _ in out)
    ev = rba.evaluate(pairs)
    assert ev["all_rows"]["rows"] == 400 and ev["attack_ip_signal"] is False
    assert "L_ATTACK_IP" not in ev["signals_fired"]            # the label cannot leak into the score
    with_feed = rba.evaluate(pairs, disable_attack_ip=False)
    assert with_feed["attack_ip_signal"] is True


def test_empty_history_does_not_fire_new_country():
    from datetime import datetime, timezone
    from app.engine.types import LoginEvent
    evs = [LoginEvent("only-once", datetime(2026, 1, 1, tzinfo=timezone.utc), "9.9.9.9", "BR", "Recife", device="android|chrome")]
    (_, score, _, flags, thin), = list(score_stream(evs))
    assert score == 0 and thin and "L_NEW_COUNTRY" not in flags
