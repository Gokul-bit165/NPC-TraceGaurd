"""Shared helpers: data loading, head+tail tokenisation, transformer scoring/training, metrics, calibration."""
from __future__ import annotations

import json
import re
import time
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score, roc_curve

V2 = Path(__file__).resolve().parents[1] / "processed_v2"
SEED = 42
MAX_EVAL_NEG = 5000          # cap legit rows in val / test_cross for speed (fixed seed, same rows for every model)


def load_fold(fold: str) -> dict[str, pd.DataFrame]:
    d = V2 / f"fold_{fold}"
    out = {}
    for n in ("train", "val", "test_in_dist", "test_cross"):
        df = pd.read_csv(d / f"emails_{n}.csv").dropna(subset=["text"]).reset_index(drop=True)
        if n in ("val", "test_cross"):
            neg = df[df.label == 0]
            if len(neg) > MAX_EVAL_NEG:
                df = pd.concat([df[df.label == 1], neg.sample(MAX_EVAL_NEG, random_state=SEED)]).sort_index().reset_index(drop=True)
        out[n] = df
    camp = pd.read_csv(V2 / "emails_test_campus.csv").dropna(subset=["text"]).reset_index(drop=True)
    out["test_campus"] = camp
    sp = pd.read_csv(V2 / "emails_spam_eval.csv").dropna(subset=["text"]).reset_index(drop=True)
    out["spam_eval"] = sp
    return out


_RESTORE = [(r"\burltoken\b", "http://link.example/page"), (r"\bemailtoken\b", "user@example.com"), (r"\bphonetoken\b", "555-0100"), (r"\bnametoken\b", "friend")]


def restore_tokens(t: str) -> str:
    """'light' variant for models that were trained on real-looking text: put plausible placeholders back for the mask tokens."""
    for rx, rep in _RESTORE:
        t = re.sub(rx, rep, t)
    return t


# ---------------------------------------------------------------- metrics
def recall_at_fpr(y, p, fpr_max=0.01):
    fpr, tpr, thr = roc_curve(y, p)
    ok = fpr <= fpr_max
    return float(tpr[ok].max()) if ok.any() else 0.0


def threshold_for_fpr(y, p, fpr_max=0.01) -> float:
    """Lowest threshold whose false-positive rate on this (validation) set is <= fpr_max."""
    neg = np.sort(p[y == 0])
    if len(neg) == 0:
        return 0.5
    k = int(np.floor(len(neg) * fpr_max))           # at most k negatives may be at/above the threshold
    cut = neg[-(k + 1)] if k < len(neg) else neg[0]
    return float(np.nextafter(cut, 1.0))             # strictly above the (k+1)-th highest negative


def metrics_at(y, p, thr) -> dict:
    y = np.asarray(y); pred = (np.asarray(p) >= thr).astype(int)
    tp = int(((pred == 1) & (y == 1)).sum()); fp = int(((pred == 1) & (y == 0)).sum())
    tn = int(((pred == 0) & (y == 0)).sum()); fn = int(((pred == 0) & (y == 1)).sum())
    prec = tp / (tp + fp) if tp + fp else 0.0
    rec = tp / (tp + fn) if tp + fn else 0.0
    fpr = fp / (fp + tn) if fp + tn else 0.0
    f1 = 2 * prec * rec / (prec + rec) if prec + rec else 0.0
    two = len(set(y.tolist())) == 2
    return dict(n=int(len(y)), n_pos=int(y.sum()), threshold=round(float(thr), 5), precision=round(prec, 4), recall=round(rec, 4),
                false_positive_rate=round(fpr, 4), f1=round(f1, 4),
                roc_auc=round(float(roc_auc_score(y, p)), 4) if two else None,
                recall_at_1pct_fpr=round(recall_at_fpr(y, p), 4) if two else None,
                confusion=dict(tp=tp, fp=fp, tn=tn, fn=fn))


class Platt:
    """Platt scaling on the validation set: p = sigmoid(a * logit(score) + b)."""
    def __init__(self):
        self.lr = LogisticRegression(C=1e6, max_iter=1000)

    @staticmethod
    def _z(p):
        p = np.clip(np.asarray(p, dtype=float), 1e-6, 1 - 1e-6)
        return np.log(p / (1 - p)).reshape(-1, 1)

    def fit(self, p, y):
        self.lr.fit(self._z(p), y)
        return self

    def __call__(self, p):
        return self.lr.predict_proba(self._z(p))[:, 1]

    def params(self):
        return dict(a=float(self.lr.coef_[0, 0]), b=float(self.lr.intercept_[0]))


def calibration_table(y, p, bins=(0, .05, .2, .4, .6, .8, .95, 1.0001)):
    y = np.asarray(y); p = np.asarray(p); rows = []
    for lo, hi in zip(bins[:-1], bins[1:]):
        m = (p >= lo) & (p < hi)
        if m.sum():
            rows.append(dict(bin=f"{lo:.2f}-{min(hi, 1):.2f}", n=int(m.sum()), mean_predicted=round(float(p[m].mean()), 3), actual_phishing_rate=round(float(y[m].mean()), 3)))
    return rows


# ---------------------------------------------------------------- transformers
def encode_head_tail(tok, texts, max_len=256, head_frac=0.75):
    """Token ids with the start and the end of long messages kept (middle dropped)."""
    enc = tok(list(texts), add_special_tokens=False, truncation=True, max_length=4096)["input_ids"]
    budget = max_len - 2
    h = int(budget * head_frac)
    out = []
    for ids in enc:
        if len(ids) > budget:
            ids = ids[:h] + ids[-(budget - h):]
        out.append([tok.cls_token_id] + ids + [tok.sep_token_id])
    return out


def _batchify(ids_list, pad_id, device):
    import torch
    L = max(len(x) for x in ids_list)
    ids = torch.full((len(ids_list), L), pad_id, dtype=torch.long)
    att = torch.zeros((len(ids_list), L), dtype=torch.long)
    for i, x in enumerate(ids_list):
        ids[i, :len(x)] = torch.tensor(x); att[i, :len(x)] = 1
    return ids.to(device), att.to(device)


def score_transformer(model, tok, texts, phishing_idx: int, max_len=256, batch=32, device="cuda", fp16=True, head_frac=0.75):
    """Return P(phishing) per text (softmax over the model's own label index)."""
    import torch
    enc = encode_head_tail(tok, texts, max_len, head_frac)
    order = np.argsort([len(x) for x in enc])
    out = np.zeros(len(enc))
    model.eval()
    with torch.no_grad():
        for i in range(0, len(order), batch):
            idx = order[i:i + batch]
            ids, att = _batchify([enc[j] for j in idx], tok.pad_token_id, device)
            with torch.autocast(device_type="cuda", dtype=torch.float16, enabled=(fp16 and device == "cuda")):
                logits = model(input_ids=ids, attention_mask=att).logits.float()
            out[idx] = torch.softmax(logits, -1)[:, phishing_idx].cpu().numpy()
    return out


def train_transformer(model, tok, tr_texts, tr_labels, va_texts, va_labels, *, max_len=256, batch=16, accum=2, lr=3e-5, epochs=3,
                      patience=1, class_weights=(1.0, 1.0), device="cuda", log=print, trainable=None):
    """Plain PyTorch fine-tuning with fp16 autocast, early stopping on validation recall@1%FPR (tie: val loss). Returns best state dict + history."""
    import torch
    from torch.optim import AdamW
    from transformers import get_linear_schedule_with_warmup
    enc = encode_head_tail(tok, tr_texts, max_len)
    y = np.asarray(tr_labels)
    params = [p for p in (trainable if trainable is not None else model.parameters()) if p.requires_grad]
    opt = AdamW(params, lr=lr, weight_decay=0.01)
    steps = epochs * (len(enc) // (batch * accum))
    sch = get_linear_schedule_with_warmup(opt, int(0.06 * steps), steps)
    scaler = torch.amp.GradScaler("cuda")
    lossf = torch.nn.CrossEntropyLoss(weight=torch.tensor(class_weights, dtype=torch.float, device=device))
    rng = np.random.RandomState(SEED)
    hist, best, best_state, bad = [], None, None, 0
    torch.cuda.reset_peak_memory_stats()
    for ep in range(epochs):
        model.train(); t0 = time.time(); perm = rng.permutation(len(enc)); run, n = 0.0, 0
        for bi, i in enumerate(range(0, len(perm) - batch + 1, batch)):
            idx = perm[i:i + batch]
            ids, att = _batchify([enc[j] for j in idx], tok.pad_token_id, device)
            yy = torch.tensor(y[idx], dtype=torch.long, device=device)
            with torch.autocast(device_type="cuda", dtype=torch.float16):
                logits = model(input_ids=ids, attention_mask=att).logits
            loss = lossf(logits.float(), yy) / accum
            scaler.scale(loss).backward()
            run += loss.item() * accum; n += 1
            if (bi + 1) % accum == 0:
                scaler.unscale_(opt); torch.nn.utils.clip_grad_norm_(params, 1.0)
                scaler.step(opt); scaler.update(); opt.zero_grad(set_to_none=True); sch.step()
        pv = score_transformer(model, tok, va_texts, 1, max_len, 32, device)
        yv = np.asarray(va_labels)
        vl = float(-np.mean(yv * np.log(np.clip(pv, 1e-6, 1)) + (1 - yv) * np.log(np.clip(1 - pv, 1e-6, 1))))
        r1 = recall_at_fpr(yv, pv); auc = float(roc_auc_score(yv, pv))
        h = dict(epoch=ep + 1, train_loss=round(run / max(n, 1), 4), val_loss=round(vl, 4), val_auc=round(auc, 4), val_recall_at_1pct_fpr=round(r1, 4),
                 peak_vram_gb=round(torch.cuda.max_memory_allocated() / 1e9, 2), seconds=round(time.time() - t0, 1))
        hist.append(h); log(json.dumps(h))
        key = (r1, -vl)
        if best is None or key > best:
            best, bad = key, 0
            best_state = {k: v.detach().cpu().clone() for k, v in model.state_dict().items()}
        else:
            bad += 1
            if bad > patience:
                log("early stopping"); break
    model.load_state_dict(best_state)
    return hist
