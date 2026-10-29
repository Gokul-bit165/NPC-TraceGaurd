"""The Kaggle training script: schema handling and the held-out-source option, on a tiny fabricated file with the documented columns."""
import json
import os
import subprocess
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]


def _frame(n, source_tag):
    rows = []
    for i in range(n):
        rows.append({"subject": f"Verify your account now {i}", "body": "Your password will expire, click the link to sign in and confirm your password immediately", "label": 1})
        rows.append({"subject": f"Meeting minutes {i}", "body": "Please find the minutes attached. Next week we review the timetable and the library schedule.", "label": 0})
    return pd.DataFrame(rows)


def test_train_script_with_holdout_source(tmp_path):
    d = tmp_path / "corpora"
    d.mkdir()
    _frame(60, "a").to_csv(d / "CorpusA.csv", index=False)
    _frame(60, "b").to_csv(d / "CorpusB.csv", index=False)
    env = {**os.environ, "TRACEGUARD_MODEL_DIR": str(tmp_path / "m")}
    r = subprocess.run([sys.executable, str(ROOT / "scripts" / "train_text_model.py"), "--dir", str(d), "--holdout-file", "CorpusB.csv"],
                       capture_output=True, text=True, env=env)
    assert r.returncode == 0, r.stderr
    meta = json.loads((tmp_path / "m" / "metrics.json").read_text())
    assert "held-out source corpus: CorpusB.csv" in meta["split"] and meta["metrics"]["n"] > 0
