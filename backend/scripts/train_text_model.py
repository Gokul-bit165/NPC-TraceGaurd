"""Train the phishing-text model on the Kaggle phishing-email data set and write models/text_model.joblib + metrics.json.

    kaggle datasets download -d naserabdullahalam/phishing-email-dataset
    python scripts/train_text_model.py --csv phishing_email.csv
    python scripts/train_text_model.py --dir ./phishing-email-dataset --holdout-file Nazario.csv   # cross-corpus test

Accepts any CSV with a text column (`text_combined`, or `subject` + `body`) and a 0/1 `label`.
With --dir, each CSV is a source corpus; --holdout-file keeps one whole corpus out of training so the
reported numbers measure generalisation to a different mail source, which is the honest test.
Without --holdout-file a stratified random split is used, and the report says so: that split tends to look better.
"""
import argparse
import json
import sys
from pathlib import Path

import pandas as pd
from sklearn.model_selection import train_test_split

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.engine.text_model import METRICS_PATH, TextModel  # noqa: E402


def texts_of(df: pd.DataFrame) -> pd.Series:
    if "text_combined" in df.columns:
        return df["text_combined"].fillna("").astype(str)
    return (df.get("subject", "").fillna("").astype(str) + "\n" + df.get("body", "").fillna("").astype(str))


def load(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path, encoding="utf-8", on_bad_lines="skip")
    if "label" not in df.columns:
        sys.exit(f"{path.name}: no 'label' column")
    out = pd.DataFrame({"text": texts_of(df).str.slice(0, 6000), "label": df["label"].astype(int)})
    out["source"] = path.name
    return out[out["text"].str.strip() != ""].drop_duplicates("text")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv")
    ap.add_argument("--dir")
    ap.add_argument("--holdout-file")
    ap.add_argument("--max-rows", type=int, default=0)
    a = ap.parse_args()
    if not (a.csv or a.dir):
        sys.exit("give --csv or --dir")
    paths = [Path(a.csv)] if a.csv else sorted(p for p in Path(a.dir).glob("*.csv") if p.name != "phishing_email.csv")
    df = pd.concat([load(p) for p in paths], ignore_index=True)
    if a.max_rows:
        df = df.sample(min(a.max_rows, len(df)), random_state=1)
    if a.holdout_file:
        test, train = df[df.source == a.holdout_file], df[df.source != a.holdout_file]
        split = f"held-out source corpus: {a.holdout_file}"
        if test.empty:
            sys.exit(f"no rows from {a.holdout_file}")
    else:
        train, test = train_test_split(df, test_size=0.2, stratify=df.label, random_state=1)
        split = "stratified random 80/20 split (optimistic: the same mail sources appear on both sides)"
    m = TextModel().fit(train.text.tolist(), train.label.tolist())
    metrics = m.evaluate(test.text.tolist(), test.label.tolist())
    m.meta = {"source": f"Kaggle phishing-email data set ({', '.join(p.name for p in paths)})", "n_train": int(len(train)), "split": split,
              "metrics": metrics, "label_balance_train": float(train.label.mean()),
              "warning": "Corpora are older mail collections; accuracy on today's AI-written lures, QR codes or token-theft links is not shown by this number."}
    m.save()
    METRICS_PATH.write_text(json.dumps(m.meta, indent=2), encoding="utf-8")
    print(json.dumps(m.meta, indent=2))


if __name__ == "__main__":
    main()
