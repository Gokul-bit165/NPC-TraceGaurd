"""Install the chosen text model into backend/models. Uses ONLY numbers already measured (results/comparison.json). No training here.

    python ship_model.py            # ships the fold-C TF-IDF model
"""
import json
import shutil
import sys
from datetime import date
from pathlib import Path

import joblib

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))
from app.engine.text_model import ProductionTextModel  # noqa: E402

V2 = ROOT / "dataset" / "processed_v2"
OUT = ROOT / "backend" / "models"
cmp_ = json.loads((V2 / "results" / "comparison.json").read_text(encoding="utf-8"))
rep = json.loads((V2 / "emails_report.json").read_text(encoding="utf-8"))
fold = "C"
e = cmp_[fold]["tfidf"]

# back up what was there (the synthetic bootstrap model and its metrics)
for name, bak in (("text_model.joblib", "text_model_bootstrap_synthetic.joblib"), ("metrics.json", "metrics_bootstrap_synthetic.json")):
    if (OUT / name).exists() and not (OUT / bak).exists():
        shutil.copy2(OUT / name, OUT / bak)

base = joblib.load(V2 / "models" / f"tfidf_fold_{fold}.joblib")
cp = e["calibration_params"]


def row(x):
    return {k: x[k] for k in ("n", "n_pos", "precision", "recall", "false_positive_rate", "f1", "roc_auc", "recall_at_1pct_fpr", "confusion")}


cross = row(e["test_cross"]); indist = row(e["test_in_dist"]); campus = row(e["test_campus"])
folds = rep["folds"][fold]
meta = {
    "source": ("Public mail corpora: Enron, Ling and SpamAssassin legitimate mail; Nigerian_Fraud scam mail as the phishing class; "
               "plus 3,000 generated campus-style messages (synthetic, 20% of training). Cleaned and near-duplicate-filtered (dataset/run_preprocess_v2.py)."),
    "n_train": folds["train"]["rows"],
    "holdout": ("whole sources never seen in training: Nazario (phishing, 1,204 messages) and CEAS_08 (legitimate, 5,000 of 12,229 sampled) — "
                "this is the headline number"),
    "split": "fold C: split by source; near-duplicates (cosine>=0.8) removed across splits; threshold and calibration chosen on validation only",
    "trained_at": date.today().isoformat(),
    "seed": 42,
    "decision_threshold_calibrated": e["threshold_val_fpr_le_1pct"],
    "metrics": {k: cross[k] for k in ("precision", "recall", "false_positive_rate", "roc_auc")},
    "measured": {
        "cross_source_test (Nazario + CEAS_08 ham, unseen sources)": cross,
        "in_distribution_test (same sources as training, near-duplicates removed; optimistic)": indist,
        "campus_style_test (SYNTHETIC, 200 generated messages; measures campus-style handling, not real-world accuracy)": campus,
        "harmless_campus_messages_flagged": e["domain_check"]["ALL harmless campus messages"],
        "advertising_spam_flag_rate (spam is not phishing; informational)": e["spam_flag_rate"],
        "calibration_on_validation": e["calibration_table_val"],
    },
    "candidates_compared": {
        "note": "All candidates scored on the same splits and seed. Numbers are recall at 1% false-positive rate on the cross-source test (fold C unless stated); 'not measured' = not run.",
        "tfidf_logreg (own, SHIPPED)": {"fold_C_recall_at_1pct_fpr": cmp_["C"]["tfidf"]["test_cross"]["recall_at_1pct_fpr"], "fold_C_auc": cmp_["C"]["tfidf"]["test_cross"]["roc_auc"],
                                         "fold_A_recall_at_1pct_fpr": cmp_["A"]["tfidf"]["test_cross"]["recall_at_1pct_fpr"], "fold_B_recall_at_1pct_fpr": cmp_["B"]["tfidf"]["test_cross"]["recall_at_1pct_fpr"],
                                         "harmless_campus_flagged_of_100": cmp_["C"]["tfidf"]["domain_check"]["ALL harmless campus messages"]["flagged"]},
        "distilbert (own, GPU fine-tune; not shipped)": {"fold_C_recall_at_1pct_fpr": cmp_["C"]["distilbert"]["test_cross"]["recall_at_1pct_fpr"], "fold_C_auc": cmp_["C"]["distilbert"]["test_cross"]["roc_auc"],
                                                          "fold_A_recall_at_1pct_fpr": cmp_["A"]["distilbert"]["test_cross"]["recall_at_1pct_fpr"], "fold_B_recall_at_1pct_fpr": cmp_["B"]["distilbert"]["test_cross"]["recall_at_1pct_fpr"],
                                                          "harmless_campus_flagged_of_100": cmp_["C"]["distilbert"]["domain_check"]["ALL harmless campus messages"]["flagged"]},
        "ealvaradob/bert-finetuned-phishing rev fa8fb73a (PUBLIC, Apache-2.0, trained by a third party on data we cannot fully inspect; not shipped)": {
            "fold_C_recall_at_1pct_fpr (CLEAN)": cmp_["C"]["hf"]["test_cross"]["recall_at_1pct_fpr"], "fold_C_auc": cmp_["C"]["hf"]["test_cross"]["roc_auc"],
            "fold_A_recall_at_1pct_fpr (MAY BE INFLATED: SpamAssassin ham 92% in its training texts)": cmp_["A"]["hf"]["test_cross"]["recall_at_1pct_fpr"],
            "fold_B_recall_at_1pct_fpr (MAY BE INFLATED: Nigerian 31%, SpamAssassin 92% in its training texts)": cmp_["B"]["hf"]["test_cross"]["recall_at_1pct_fpr"],
            "advertising_spam_flag_rate": cmp_["C"]["hf"]["spam_flag_rate"],
            "campus_phishing_missed_fold_C_of_100": 100 - round(cmp_["C"]["hf"]["test_campus"]["recall"] * 100)},
        "public model, top 12 layers briefly fine-tuned (own experiment; weights not saved; not shipped)": {"fold_C_recall_at_1pct_fpr": cmp_["C"]["hf_ft"]["test_cross"]["recall_at_1pct_fpr"],
                                                                                                         "fold_C_false_positive_rate_at_val_threshold": cmp_["C"]["hf_ft"]["test_cross"]["false_positive_rate"]},
        "ip_login_model": "not measured (not built; feature pipeline unfinished)",
    },
    "not_measured": ["IP / login risk model", "CPU speed of the transformer candidates", "mobile / non-English / image-only mail", "email headers"],
    "warning": ("Measured on public, older mail collections (Enron, Ling, SpamAssassin, CEAS_08, Nazario, Nigerian_Fraud). The cross-source numbers are the ones to quote; "
                "in-distribution numbers are optimistic. Campus-style results come from 200 GENERATED messages and measure only how the model treats campus-style wording. "
                "Advertising spam is not labelled phishing. Today's AI-written lures, QR codes and token-theft links are not covered by this data. "
                "The public model was compared but is not used. The login/RBA data is artificial."),
}
model = ProductionTextModel(vectorizer=base.vectorizer, clf=base.clf, meta=meta, platt_a=cp["a"], platt_b=cp["b"])
OUT.mkdir(parents=True, exist_ok=True)
model.save(OUT / "text_model.joblib")
(OUT / "metrics.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
print("shipped ->", OUT / "text_model.joblib", "| bytes", (OUT / "text_model.joblib").stat().st_size)
