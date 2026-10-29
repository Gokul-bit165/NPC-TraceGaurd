"""Single-process throughput measurements. Writes models/benchmark.json (shown on the Evaluation page).

    python scripts/benchmark.py --src data/rba_head.csv --rows 300000

Numbers are for one Python process on whatever machine runs this. Scaling out is by sharding on user_id,
so multiply by workers for a rough capacity estimate and measure it before promising anything.
"""
import argparse
import json
import os
import platform
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app import rba, scenarios as sc  # noqa: E402
from app.engine import config as cfgmod  # noqa: E402
from app.engine.bulk import score_stream  # noqa: E402
from app.engine.email_signals import analyze_email  # noqa: E402
from app.engine.pipeline import analyze_case, build_context  # noqa: E402
from app.engine.text_model import MODEL_DIR, get_model  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("--src")
ap.add_argument("--rows", type=int, default=300000)
a = ap.parse_args()
cfg = cfgmod.get()
out = {"machine": {"cpus": os.cpu_count(), "python": platform.python_version(), "platform": platform.platform()}, "when": datetime.now(timezone.utc).isoformat()}

if a.src:
    t = time.perf_counter()
    pairs = rba.load(a.src, max_rows=a.rows)
    t_parse = time.perf_counter() - t
    events = [e for e, _ in pairs]
    t = time.perf_counter()
    n = sum(1 for _ in score_stream(events, cfg))
    t_score = time.perf_counter() - t
    out["login_scoring"] = {"rows": n, "source": "real RBA rows (first rows of the data set)", "parse_seconds": round(t_parse, 2), "score_seconds": round(t_score, 2),
                            "rows_per_second": round(n / t_score), "note": "score_stream: per-login scoring against a rolling per-user history (cap 300)"}

scen = sc.build_all(datetime(2026, 1, 15, 15, tzinfo=timezone.utc))
A = sc.anchor_time(datetime(2026, 1, 15, 15, tzinfo=timezone.utc))
mails = [e for s in scen for e in s.emails]
model = get_model()
reps = 200
t = time.perf_counter()
for _ in range(reps):
    for m in mails:
        analyze_email(m, cfg, model)
dt = time.perf_counter() - t
out["email_analysis"] = {"emails": reps * len(mails), "seconds": round(dt, 2), "emails_per_second": round(reps * len(mails) / dt),
                         "note": "full signal set including the text model, on 5 scripted mails"}
ctx = build_context(sc.all_logins(scen), cfg["login"]["window_hours"], A)
reps = 100
t = time.perf_counter()
for _ in range(reps):
    for s in scen:
        analyze_case(s.person.id, s.emails, s.logins, cfg, ctx, as_of=A)
dt = time.perf_counter() - t
out["case_analysis"] = {"cases": reps * len(scen), "seconds": round(dt, 2), "cases_per_second": round(reps * len(scen) / dt),
                        "note": "email + login + correlation for one user, histories of about 40 logins"}
MODEL_DIR.mkdir(parents=True, exist_ok=True)
(MODEL_DIR / "benchmark.json").write_text(json.dumps(out, indent=2), encoding="utf-8")
print(json.dumps(out, indent=2))
