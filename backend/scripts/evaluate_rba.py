"""Evaluate the login scoring on RBA rows and write models/rba_eval.json (shown on the Evaluation page).

    python scripts/fetch_rba_head.py --out data/rba_head.csv
    python scripts/evaluate_rba.py --src data/rba_head.csv --sample-users 6000
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app import rba  # noqa: E402
from app.engine.text_model import MODEL_DIR  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("--src", required=True, help="rba-dataset.csv, a zip containing it, or the head file from fetch_rba_head.py")
ap.add_argument("--sample-users", type=int, default=6000)
ap.add_argument("--max-rows", type=int, default=None)
a = ap.parse_args()
res = rba.write_eval(a.src, MODEL_DIR / "rba_eval.json", a.max_rows, a.sample_users)
for k in ("behavioural_only", "with_threat_feed_signal"):
    b = res[k]["all_rows"]
    print(k, "| rows", b["rows"], "| ATO rows", b["account_takeover_rows"], "| ATO AUC", b["auc_account_takeover"],
          "| failed-login-rule AUC", b["auc_account_takeover_failed_login_rule"], "| ATO caught at Medium", b["account_takeover_at_medium"]["recall"])
print("account takeovers with no or thin history:", res["behavioural_only"]["account_takeover_rows_with_no_or_thin_history"], "of", res["behavioural_only"]["all_rows"]["account_takeover_rows"])
