"""Aggregate raw scores into the comparison tables. Thresholds and calibration come from the VALIDATION set only.

    python report_models.py --folds C,A,B
Writes processed_v2/results/comparison.json and prints tables. Test sets are read here once; nothing is tuned on them.
"""
import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import tg_common as C  # noqa: E402

MODELS = ["tfidf", "distilbert", "hf", "hf_ft"]
TESTS = ["test_in_dist", "test_cross", "test_campus"]
# folds whose cross-source negatives/positives the public model may have seen (from the overlap table)
HF_STATUS = {"C": "CLEAN (Nazario + CEAS_08: 0% / 0.1% near-duplicates in the public model's training texts)",
             "A": "POSSIBLY SEEN / SEEN: SpamAssassin ham is 92% near-duplicate of its training texts",
             "B": "POSSIBLY SEEN: Nigerian_Fraud 31% near-duplicate, SpamAssassin ham 92%"}
CAMPUS_LEGIT_TOPICS = {"fees": "fee reminder", "exam": "timetable / exam notice", "password": "real password-expiry notice",
                       "helpdesk": "IT notice", "jobs": "event / placement / newsletter-style notice", "parcel": "parcel / library notice"}


def load(fold, model, s):
    p = C.V2 / "results" / f"fold_{fold}" / f"{model}__{s}.csv"
    return pd.read_csv(p) if p.exists() else None


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--folds", default="C,A,B"); a = ap.parse_args()
    camp_meta = pd.read_csv(C.V2 / "emails_test_campus.csv").dropna(subset=["text"]).reset_index(drop=True)
    out = {}
    for fold in a.folds.split(","):
        out[fold] = {"hf_status": HF_STATUS[fold]}
        for m in MODELS:
            v = load(fold, m, "val")
            if v is None:
                continue
            cal = C.Platt().fit(v.score.values, v.label.values)
            pv = cal(v.score.values)
            thr = C.threshold_for_fpr(v.label.values, pv, 0.01)
            e = {"calibration_params": cal.params(), "threshold_val_fpr_le_1pct": round(thr, 5),
                 "val": C.metrics_at(v.label.values, pv, thr), "calibration_table_val": C.calibration_table(v.label.values, pv)}
            for s in TESTS:
                t = load(fold, m, s)
                p = cal(t.score.values)
                e[s] = C.metrics_at(t.label.values, p, thr)
                if s != "test_campus":
                    pass
                wrong = pd.DataFrame({"label": t.label, "p": p})
                wrong["conf_wrong"] = np.where(wrong.label == 1, 1 - wrong.p, wrong.p)
                wrong = wrong[(wrong.label == 1) & (wrong.p < thr) | (wrong.label == 0) & (wrong.p >= thr)].sort_values("conf_wrong", ascending=False).head(10)
                e[s]["worst_10_idx"] = wrong.index.tolist()
                e[s]["worst_10"] = [{"idx": int(i), "label": int(r.label), "p": round(float(r.p), 3)} for i, r in wrong.iterrows()]
            sp = load(fold, m, "spam_eval")
            e["spam_flag_rate"] = round(float((cal(sp.score.values) >= thr).mean()), 4)
            ct = load(fold, m, "test_campus")
            cp = cal(ct.score.values)
            legit = camp_meta.label.values == 0
            dc = {}
            for topic, nm in CAMPUS_LEGIT_TOPICS.items():
                mk = legit & (camp_meta.topic.values == topic)
                dc[nm] = dict(n=int(mk.sum()), flagged=int((cp[mk] >= thr).sum()))
            dc["ALL harmless campus messages"] = dict(n=int(legit.sum()), flagged=int((cp[legit] >= thr).sum()))
            hid = (camp_meta.hidden_instruction.values == 1)
            dc["phishing with hidden AI-reviewer instruction"] = dict(n=int(hid.sum()), caught=int((cp[hid] >= thr).sum()))
            e["domain_check"] = dc
            info_p = C.V2 / "results" / f"fold_{fold}" / f"{m}__info.json"
            e["info"] = json.load(open(info_p)) if info_p.exists() else {}
            out[fold][m] = e
    (C.V2 / "results" / "comparison.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
    # printed summary
    for fold, d in out.items():
        print(f"\n=== FOLD {fold}  (public model status: {d['hf_status']})")
        rows = []
        for m in MODELS:
            if m not in d:
                continue
            e = d[m]
            for s in TESTS:
                x = e[s]
                rows.append([m, s, x["n"], x["precision"], x["recall"], x["false_positive_rate"], x["f1"], x["roc_auc"], x["recall_at_1pct_fpr"], str(x["confusion"])])
        print(pd.DataFrame(rows, columns=["model", "set", "n", "prec", "recall", "FPR", "F1", "AUC", "rec@1%FPR", "tp/fp/tn/fn"]).to_string(index=False))
        print("domain check (harmless campus msgs flagged / spam flag rate):",
              {m: (d[m]["domain_check"]["ALL harmless campus messages"], d[m]["spam_flag_rate"]) for m in MODELS if m in d})


if __name__ == "__main__":
    main()
