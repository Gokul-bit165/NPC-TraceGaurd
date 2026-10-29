"""Train / score the candidate models on one fold and write raw scores (no thresholds, no test-set tuning here).

    python run_models.py --fold C --models tfidf,distilbert,hf,hf_ft

Outputs  dataset/processed_v2/results/fold_X/<model>__<set>.csv  (columns: label, score)  and  <model>__info.json
Sets: val, test_in_dist, test_cross, test_campus, spam_eval
"""
import argparse
import json
import sys
import time
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import torch

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(ROOT / "backend"))
import tg_common as C  # noqa: E402
from app.engine.text_model import TextModel  # noqa: E402

DEV = "cuda" if torch.cuda.is_available() else "cpu"
HF_DIR = ROOT / "models" / "phishing-bert"
SETS = ["val", "test_in_dist", "test_cross", "test_campus", "spam_eval"]


def save(res_dir, model, name, df, score):
    pd.DataFrame({"label": df["label"].values, "score": score}).to_csv(res_dir / f"{model}__{name}.csv", index=False)


def run_tfidf(fold, data, res_dir):
    t0 = time.time()
    m = TextModel().fit(data["train"].text.tolist(), data["train"].label.tolist())
    train_s = time.time() - t0
    (C.V2 / "models").mkdir(exist_ok=True)
    joblib.dump(m, C.V2 / "models" / f"tfidf_fold_{fold}.joblib")
    info = dict(kind="tfidf+logreg (own)", train_seconds=round(train_s, 1), n_train=len(data["train"]))
    for s in SETS:
        t0 = time.time(); sc = m.predict_many(data[s].text.tolist()); dt = time.time() - t0
        save(res_dir, "tfidf", s, data[s], sc)
        info[f"cpu_ms_per_msg_{s}"] = round(1000 * dt / len(data[s]), 3)
    json.dump(info, open(res_dir / "tfidf__info.json", "w"), indent=2)


def run_distilbert(fold, data, res_dir, args):
    from transformers import AutoModelForSequenceClassification, AutoTokenizer
    name = args.small_model
    tok = AutoTokenizer.from_pretrained(name)
    model = AutoModelForSequenceClassification.from_pretrained(name, num_labels=2, id2label={0: "benign", 1: "phishing"},
                                                                label2id={"benign": 0, "phishing": 1}).to(DEV)
    tr, va = data["train"], data["val"]
    pos = tr.label.mean()
    cw = (1.0, float((1 - pos) / pos) ** 0.5)       # softened class weight
    t0 = time.time()
    hist = C.train_transformer(model, tok, tr.text.tolist(), tr.label.tolist(), va.text.tolist(), va.label.tolist(),
                               max_len=256, batch=args.batch, accum=32 // args.batch, lr=3e-5, epochs=args.epochs, patience=1,
                               class_weights=cw, device=DEV, log=lambda s: print("   ", s, flush=True))
    train_s = time.time() - t0
    out = C.V2 / "models" / f"{name.split('/')[-1]}_fold_{fold}"
    out.mkdir(parents=True, exist_ok=True)
    model.save_pretrained(out); tok.save_pretrained(out)
    info = dict(kind=f"{name} fine-tuned (own)", history=hist, train_seconds=round(train_s, 1), class_weights=cw,
                peak_vram_gb=max(h["peak_vram_gb"] for h in hist), params_m=round(sum(p.numel() for p in model.parameters()) / 1e6, 1),
                size_mb=round(sum(f.stat().st_size for f in out.glob("*.safetensors")) / 1e6, 1))
    for s in SETS:
        torch.cuda.synchronize(); t0 = time.time()
        sc = C.score_transformer(model, tok, data[s].text.tolist(), 1, 256, 32, DEV)
        torch.cuda.synchronize(); dt = time.time() - t0
        save(res_dir, "distilbert", s, data[s], sc)
        info[f"gpu_ms_per_msg_{s}"] = round(1000 * dt / len(data[s]), 3)
    # CPU speed on 64 messages, batch 1
    model.to("cpu").float()
    sample = data["test_campus"].text.tolist()[:40]
    t0 = time.time()
    for t in sample:
        C.score_transformer(model, tok, [t], 1, 256, 1, "cpu", fp16=False)
    info["cpu_ms_per_msg_single"] = round(1000 * (time.time() - t0) / len(sample), 1)
    json.dump(info, open(res_dir / "distilbert__info.json", "w"), indent=2)
    del model; torch.cuda.empty_cache()


def load_hf():
    from transformers import AutoModelForSequenceClassification, AutoTokenizer
    if not (HF_DIR / "config.json").exists():
        sys.exit(f"public model folder missing: {HF_DIR}")
    tok = AutoTokenizer.from_pretrained(HF_DIR, local_files_only=True)
    model = AutoModelForSequenceClassification.from_pretrained(HF_DIR, local_files_only=True, torch_dtype=torch.float16 if DEV == "cuda" else torch.float32).to(DEV)
    idx = int(model.config.label2id["phishing"])
    return tok, model, idx


def run_hf(fold, data, res_dir, tag="hf"):
    tok, model, idx = load_hf()
    info = dict(kind="ealvaradob/bert-finetuned-phishing, used as downloaded (no training)", phishing_label_index=idx,
                params_m=round(sum(p.numel() for p in model.parameters()) / 1e6, 1))
    # decide on the validation set: shared normalised text vs placeholders restored ("light raw")
    va = data["val"]
    cand = {}
    for variant, fn in (("normalised", lambda t: t), ("restored_placeholders", C.restore_tokens)):
        sc = C.score_transformer(model, tok, [fn(t) for t in va.text], idx, 512, 16, DEV, head_frac=0.75)
        cand[variant] = dict(auc=float(C.roc_auc_score(va.label, sc)), r1=C.recall_at_fpr(va.label.values, sc))
    best = max(cand, key=lambda k: (cand[k]["r1"], cand[k]["auc"]))
    fn = (lambda t: t) if best == "normalised" else C.restore_tokens
    info["input_variant_on_validation"] = cand; info["input_variant_chosen"] = best
    torch.cuda.reset_peak_memory_stats()
    for s in SETS:
        torch.cuda.synchronize(); t0 = time.time()
        sc = C.score_transformer(model, tok, [fn(t) for t in data[s].text], idx, 512, 16, DEV, head_frac=0.75)
        torch.cuda.synchronize(); dt = time.time() - t0
        save(res_dir, tag, s, data[s], sc)
        info[f"gpu_ms_per_msg_{s}"] = round(1000 * dt / len(data[s]), 3)
    info["peak_vram_gb"] = round(torch.cuda.max_memory_allocated() / 1e9, 2)
    json.dump(info, open(res_dir / f"{tag}__info.json", "w"), indent=2)
    del model; torch.cuda.empty_cache()


def run_hf_ft(fold, data, res_dir, args):
    """C2: brief partial fine-tune of the public model on OUR training split. Only the top half of the encoder + classifier is trained so that it
    fits in 6 GB (full AdamW on 335M parameters needs ~6 GB for weights+grads+optimizer alone)."""
    from transformers import AutoModelForSequenceClassification, AutoTokenizer
    tok = AutoTokenizer.from_pretrained(HF_DIR, local_files_only=True)
    model = AutoModelForSequenceClassification.from_pretrained(HF_DIR, local_files_only=True).to(DEV)   # fp32 master weights
    idx = int(model.config.label2id["phishing"]); assert idx == 1
    for p in model.bert.embeddings.parameters(): p.requires_grad = False
    for l in model.bert.encoder.layer[:12]:
        for p in l.parameters(): p.requires_grad = False
    model.gradient_checkpointing_enable()
    trainable = [p for p in model.parameters() if p.requires_grad]
    tr, va = data["train"], data["val"]
    if len(tr) > args.ft_max_rows:        # keep the brief fine-tune brief: stratified sample, same for every run
        tr = pd.concat([g.sample(min(len(g), int(args.ft_max_rows * len(g) / len(tr)) + 1), random_state=C.SEED) for _, g in tr.groupby("label")])
    pos = tr.label.mean(); cw = (1.0, float((1 - pos) / pos) ** 0.5)
    t0 = time.time()
    try:
        hist = C.train_transformer(model, tok, [C.restore_tokens(t) for t in tr.text], tr.label.tolist(), [C.restore_tokens(t) for t in va.text], va.label.tolist(),
                                   max_len=256, batch=4, accum=8, lr=1.5e-5, epochs=args.ft_epochs, patience=1, class_weights=cw, device=DEV,
                                   log=lambda s: print("   ", s, flush=True), trainable=trainable)
    except torch.cuda.OutOfMemoryError:
        json.dump(dict(status="SKIPPED: out of GPU memory"), open(res_dir / "hf_ft__info.json", "w")); print("hf_ft: OOM, skipped"); return
    info = dict(kind="public model, top 12 of 24 layers fine-tuned briefly on our training split", history=hist, train_seconds=round(time.time() - t0, 1),
                trained_rows=len(tr), peak_vram_gb=max(h["peak_vram_gb"] for h in hist), params_m=round(sum(p.numel() for p in model.parameters()) / 1e6, 1))
    model.half()
    for s in SETS:
        sc = C.score_transformer(model, tok, [C.restore_tokens(t) for t in data[s].text], idx, 512, 16, DEV)
        save(res_dir, "hf_ft", s, data[s], sc)
    json.dump(info, open(res_dir / "hf_ft__info.json", "w"), indent=2)
    del model; torch.cuda.empty_cache()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--fold", required=True)
    ap.add_argument("--models", default="tfidf,distilbert,hf")
    ap.add_argument("--small-model", default="distilbert-base-uncased")
    ap.add_argument("--batch", type=int, default=16)
    ap.add_argument("--epochs", type=int, default=3)
    ap.add_argument("--ft-epochs", type=int, default=1)
    ap.add_argument("--ft-max-rows", type=int, default=6000)
    a = ap.parse_args()
    data = C.load_fold(a.fold)
    res = C.V2 / "results" / f"fold_{a.fold}"
    res.mkdir(parents=True, exist_ok=True)
    print({k: len(v) for k, v in data.items()}, "device", DEV, flush=True)
    for m in a.models.split(","):
        t0 = time.time(); print(f"== {m}", flush=True)
        {"tfidf": lambda: run_tfidf(a.fold, data, res), "distilbert": lambda: run_distilbert(a.fold, data, res, a),
         "hf": lambda: run_hf(a.fold, data, res), "hf_ft": lambda: run_hf_ft(a.fold, data, res, a)}[m]()
        print(f"== {m} done in {time.time() - t0:.0f}s", flush=True)
