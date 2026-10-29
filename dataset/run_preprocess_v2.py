#!/usr/bin/env python3
r"""
TraceGuard - email data rebuild (v2).  Writes ONLY to dataset\processed_v2 (the old processed folder is untouched).

    conda activate ai
    python dataset\run_preprocess_v2.py

Label rule (fixed):   1 = phishing or scam meant to steal credentials, money or personal data
                      0 = legitimate mail
    phishing/scam sources : Nazario, Nigerian_Fraud
    legitimate sources    : label-0 rows of CEAS_08, Enron, Ling, SpamAssassin
    advertising spam      : label-1 rows of CEAS_08, Enron, Ling, SpamAssassin  -> NOT positive. Kept only in emails_spam_eval.csv
    phishing_email.csv    : union of the six files above, skipped

Folds (the test source is never in train/val of that fold):
    C  (headline, CLEAN for the public HF model)  train: neg Enron+Ling+SpamAssassin, pos Nigerian | test_cross: Nazario + CEAS_08 ham
    A                                             train: neg CEAS+Enron+Ling,          pos Nigerian | test_cross: Nazario + SpamAssassin ham
    B  (reverse direction)                        train: neg CEAS+Enron+Ling,          pos Nazario  | test_cross: Nigerian + SpamAssassin ham
Near-duplicate clusters (cosine >= 0.8) are split as a unit; clusters that straddle a train source and a held-out source
drop the held-out-side rows. Synthetic rows go to train only (never val/test).
"""
import hashlib
import json
import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.feature_extraction.text import HashingVectorizer
from sklearn.preprocessing import normalize

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE / "scripts_v2"))
sys.path.insert(0, str(HERE.parent / "backend"))
from Preprocess import visible_text  # noqa: E402  (hidden-text stripping, same as production)
from app.engine.text_clean import clean_visible, trim  # noqa: E402
import campus_synth  # noqa: E402

SEED = 42
OUT = HERE / "processed_v2"
SIM = 0.8
SRC_FILES = {"CEAS_08": "CEAS_08.csv", "Enron": "Enron.csv", "Ling": "Ling.csv", "Nazario": "Nazario.csv",
             "Nigerian_Fraud": "Nigerian_Fraud.csv", "SpamAssassin": "SpamAssasin.csv"}
PHISH_SOURCES = {"Nazario", "Nigerian_Fraud"}
NEG_CAP = {"CEAS_08": 6000, "Enron": 6000, "Ling": 10**9, "SpamAssassin": 6000}   # train downsampling of the big class
FOLDS = {
    "C": dict(train_neg=["Enron", "Ling", "SpamAssassin"], train_pos="Nigerian_Fraud", test_pos="Nazario", test_neg="CEAS_08"),
    "A": dict(train_neg=["CEAS_08", "Enron", "Ling"], train_pos="Nigerian_Fraud", test_pos="Nazario", test_neg="SpamAssassin"),
    "B": dict(train_neg=["CEAS_08", "Enron", "Ling"], train_pos="Nazario", test_pos="Nigerian_Fraud", test_neg="SpamAssassin"),
}

# ------------------------------------------------------------------ cleaning (shared with production: backend/app/engine/text_clean.py)
def clean_text(raw: str, counts: dict, src: str):
    vis, hidden, zw = visible_text(raw)
    txt, n_urls, n_phone, n_name = clean_visible(vis, counts, src)
    return txt, hidden, zw, n_urls, n_phone, n_name


def load_sources():
    frames = []
    for src, fn in SRC_FILES.items():
        df = pd.read_csv(HERE / fn, encoding_errors="replace", on_bad_lines="skip", low_memory=False)
        subj = df["subject"].fillna("").astype(str)
        body = df["body"].fillna("").astype(str)
        frames.append(pd.DataFrame({"source": src, "label_orig": pd.to_numeric(df["label"], errors="coerce"),
                                    "raw": subj + " . " + body}))
    return pd.concat(frames, ignore_index=True)


def md5(s):
    return hashlib.md5(s.encode("utf-8", "ignore")).hexdigest()


def clusters(texts, thr=SIM, chunk=2500):
    hv = HashingVectorizer(n_features=2**19, ngram_range=(1, 2), alternate_sign=False, norm=None)
    X = normalize(hv.transform([t[:2000] for t in texts])).tocsr()
    XT = X.T.tocsr()
    parent = np.arange(X.shape[0])

    def find(a):
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a
    for i in range(0, X.shape[0], chunk):
        S = (X[i:i + chunk] @ XT).tocoo()
        m = (S.data >= thr) & ((S.row + i) < S.col)
        for r, c in zip(S.row[m] + i, S.col[m]):
            ra, rb = find(r), find(c)
            if ra != rb:
                parent[rb] = ra
        print(f"  clustering {min(i + chunk, X.shape[0])}/{X.shape[0]}", flush=True)
    return np.array([find(i) for i in range(len(parent))])


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    rep = {"seed": SEED, "similarity_threshold": SIM, "label_rule": __doc__.split("Label rule (fixed):")[1].split("Folds")[0].strip()}
    raw = load_sources()
    rep["loaded_rows"] = raw["source"].value_counts().to_dict()
    raw = raw[raw["label_orig"].isin([0, 1])].copy()
    raw["label_orig"] = raw["label_orig"].astype(int)

    # role: phishing / ham / spam
    def role(r):
        if r.source in PHISH_SOURCES:
            return "phish"
        return "ham" if r.label_orig == 0 else "spam"
    raw["role"] = [role(r) for r in raw.itertuples()]
    rep["rows_by_source_role_before"] = {s: g["role"].value_counts().to_dict() for s, g in raw.groupby("source")}

    counts: dict = {}
    res = [clean_text(t, counts, s) for t, s in zip(raw["raw"], raw["source"])]
    raw["text"] = [trim(r[0]) for r in res]
    raw["had_hidden_text"] = [int(r[1] > 0 or r[2] > 0) for r in res]
    raw["url_count"] = [r[3] for r in res]
    raw["phones_masked"] = [r[4] for r in res]
    raw["names_masked"] = [r[5] for r in res]
    rep["markers_removed_rows_by_source"] = counts
    rep["pii"] = {"phone_numbers_masked": int(raw.phones_masked.sum()), "rows_with_greeting_name_masked": int(raw.names_masked.sum()),
                  "email_addresses": "replaced by 'emailtoken' (Preprocess.normalise)",
                  "limit": "no named-entity recognition: names in signatures/body are NOT masked, only names after Dear/Hi/Hello"}
    n0 = len(raw)
    raw = raw[raw["text"].str.len() >= 30]
    rep["dropped_too_short"] = n0 - len(raw)
    n0 = len(raw)
    raw["k"] = raw["text"].map(lambda s: md5(re.sub(r"[^a-z]+", " ", s)))
    conflict = raw.groupby("k")["role"].transform("nunique") > 1
    rep["dropped_conflicting_roles"] = int(conflict.sum())
    raw = raw[~conflict].drop_duplicates("k")
    rep["dropped_exact_dups"] = n0 - len(raw) - rep["dropped_conflicting_roles"]
    raw = raw.reset_index(drop=True)

    # spam kept aside
    spam = raw[raw.role == "spam"]
    pool = raw[raw.role != "spam"].copy().reset_index(drop=True)
    pool["label"] = (pool.role == "phish").astype(int)

    print("clustering pool", len(pool), flush=True)
    pool["cluster"] = clusters(pool["text"].tolist())
    csrc = pool.groupby("cluster")["source"].nunique()
    mixed = set(csrc[csrc > 1].index)
    HELD = {"Nazario", "Nigerian_Fraud", "SpamAssassin", "CEAS_08"}   # sources that serve as a held-out test source in some fold
    # In a mixed cluster keep every source's rows only if the cluster would not leak across any fold:
    # simple, conservative rule: drop all rows of a mixed cluster that belong to Nazario / Nigerian / SpamAssassin / CEAS_08
    # when the cluster also contains a different source.
    drop = pool["cluster"].isin(mixed) & pool["source"].isin(HELD)
    rep["near_duplicate_clusters_mixed_sources"] = len(mixed)
    rep["dropped_cross_source_near_dups"] = pool[drop].groupby(["source", "label"]).size().rename(lambda x: str(x)).to_dict() if drop.any() else {}
    rep["dropped_cross_source_near_dups"] = {f"{s}/{l}": int(n) for (s, l), n in pool[drop].groupby(["source", "label"]).size().items()}
    pool = pool[~drop].copy()
    # near-duplicates inside one source: keep one row per cluster (they inflate val/test and weight training)
    n0 = len(pool)
    pool = pool.drop_duplicates("cluster").copy()
    rep["dropped_within_source_near_dups"] = n0 - len(pool)

    # group split of the training-side rows: same function for every fold
    rng = np.random.RandomState(SEED)
    pool["u"] = rng.rand(len(pool))
    pool["part"] = np.where(pool.u < 0.8, "train", np.where(pool.u < 0.9, "val", "test_in_dist"))
    pool.drop(columns=["u"]).to_csv(OUT / "emails_pool_clean.csv", index=False)
    rep["pool_rows_by_source_label"] = {f"{s}/{l}": int(n) for (s, l), n in pool.groupby(["source", "label"]).size().items()}

    # synthetic
    syn_train = pd.DataFrame(campus_synth.make("train", 1500, SEED + 1))
    syn_eval = pd.DataFrame(campus_synth.make("eval", 100, SEED + 2))
    for d in (syn_train, syn_eval):
        res = [clean_text(t, {}, "synthetic") for t in d["text_raw"]]
        d["text"] = [r[0] for r in res]
        d["had_hidden_text"] = 0
        d["url_count"] = [r[3] for r in res]
        d["phones_masked"] = 0
        d["names_masked"] = 0
    syn_train["part"] = "train"
    syn_train.to_csv(OUT / "synthetic_train.csv", index=False)
    syn_eval.to_csv(OUT / "emails_test_campus.csv", index=False)
    # the synthetic train/eval banks must not share any text
    overlap = set(syn_train.text) & set(syn_eval.text)
    rep["synthetic"] = {"train_rows": len(syn_train), "eval_rows": len(syn_eval), "exact_text_overlap_train_vs_eval": len(overlap),
                        "note": "emails_test_campus.csv is SYNTHETIC: it measures campus-style handling, not real-world accuracy."}

    keep = ["source", "label", "text", "url_count", "had_hidden_text"]
    rep["folds"] = {}
    for f, cfg in FOLDS.items():
        d = OUT / f"fold_{f}"
        d.mkdir(exist_ok=True)
        trn_src = cfg["train_neg"] + [cfg["train_pos"]]
        inpool = pool[pool.source.isin(trn_src)]
        tr, va, ti = (inpool[inpool.part == p] for p in ("train", "val", "test_in_dist"))
        # downsample the big class in train only (never copy minority rows)
        parts = [tr[tr.label == 1]]
        for s in cfg["train_neg"]:
            g = tr[(tr.source == s) & (tr.label == 0)]
            parts.append(g.sample(min(len(g), NEG_CAP[s]), random_state=SEED))
        tr = pd.concat(parts)
        tr_real = len(tr)
        tr = pd.concat([tr[keep], syn_train[keep]]).sample(frac=1, random_state=SEED)
        tc = pool[(pool.source == cfg["test_pos"]) | ((pool.source == cfg["test_neg"]) & (pool.label == 0))]
        for name, part in [("train", tr), ("val", va[keep]), ("test_in_dist", ti[keep]), ("test_cross", tc[keep])]:
            part.to_csv(d / f"emails_{name}.csv", index=False)
        sets = {"train": tr, "val": va, "test_in_dist": ti, "test_cross": tc}
        rep["folds"][f] = {"config": cfg,
                           **{n: {"rows": int(len(p)), "phishing": int(p.label.sum()), "legit": int((p.label == 0).sum()),
                                  "by_source": {str(k): int(v) for k, v in p.groupby("source").size().items()}} for n, p in sets.items()},
                           "synthetic_share_of_train": round(len(syn_train) / len(tr), 3)}
        assert not (set(tc.source) & set(tr.source)), "test source leaked into train"
        assert not (set(tc.source) & set(va.source))
    # spam evaluation (separate, informational: how often is plain advertising spam flagged?)
    sp = pd.concat([spam[spam.source == "SpamAssassin"], spam[spam.source == "CEAS_08"].sample(1500, random_state=SEED)])
    sp = sp.assign(label=0, note="advertising spam, label 0 here means 'not phishing'; report flag rate only")
    sp[["source", "label", "text", "note"]].to_csv(OUT / "emails_spam_eval.csv", index=False)
    rep["spam_eval_rows"] = int(len(sp))

    (OUT / "emails_report.json").write_text(json.dumps(rep, indent=2, default=str), encoding="utf-8")
    lines = ["TraceGuard data report (v2)", f"seed={SEED}  near-duplicate threshold={SIM}", "", "LABEL RULE", rep["label_rule"], ""]
    for k in ("loaded_rows", "rows_by_source_role_before", "dropped_too_short", "dropped_conflicting_roles", "dropped_exact_dups",
              "dropped_cross_source_near_dups", "dropped_within_source_near_dups", "pool_rows_by_source_label", "pii", "synthetic", "spam_eval_rows"):
        lines += [f"{k}: {json.dumps(rep[k])}"]
    lines += ["markers_removed_rows_by_source: " + json.dumps(counts)]
    for f, v in rep["folds"].items():
        lines += ["", f"FOLD {f}: {v['config']}"] + [f"  {n}: {v[n]['rows']} rows ({v[n]['phishing']} phishing / {v[n]['legit']} legit) {v[n]['by_source']}" for n in ("train", "val", "test_in_dist", "test_cross")]
        lines += [f"  synthetic share of train: {v['synthetic_share_of_train']}"]
    (OUT / "emails_report.txt").write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
