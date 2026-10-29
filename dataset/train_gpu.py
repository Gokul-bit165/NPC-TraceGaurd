#!/usr/bin/env python3
r"""
TraceGuard – GPU-accelerated DistilBERT phishing-email trainer
================================================================
Fine-tunes distilbert-base-uncased on the preprocessed email splits
produced by Preprocess.py.  Designed for a 4 GB VRAM GPU (RTX 3050).

Usage:
    conda run -n dl python train_gpu.py

Outputs (in e:\NPC-TraceGaurd\backend\models\):
    text_model.joblib   – wrapper that loads the transformer at inference
    metrics.json        – precision, recall, f1, AUC on both test sets
    distilbert_phish/   – saved HuggingFace model + tokenizer

The saved model is wrapped in a TextModel-compatible interface so the
existing backend code (text_model.py get_model → .predict / .top_terms)
works without changes.
"""
import json
import os
import sys
import gc
from pathlib import Path

import numpy as np
import pandas as pd
import torch
from torch.utils.data import Dataset, DataLoader
from transformers import (
    DistilBertTokenizerFast,
    DistilBertForSequenceClassification,
    get_linear_schedule_with_warmup,
)
from sklearn.metrics import precision_recall_fscore_support, roc_auc_score

# ── Paths ──────────────────────────────────────────────────────────────
DATASET_DIR  = Path(r"e:\NPC-TraceGaurd\dataset\processed")
MODEL_DIR    = Path(r"e:\NPC-TraceGaurd\backend\models")
SAVE_DIR     = MODEL_DIR / "distilbert_phish"
JOBLIB_PATH  = MODEL_DIR / "text_model.joblib"
METRICS_PATH = MODEL_DIR / "metrics.json"

# ── Hyperparameters (tuned for 4 GB VRAM) ──────────────────────────────
MODEL_NAME     = "distilbert-base-uncased"
MAX_LEN        = 256          # tokens (longer emails are truncated)
BATCH_SIZE     = 8            # fits in 4 GB with fp16
GRAD_ACCUM     = 4            # effective batch = 8 * 4 = 32
EPOCHS         = 3
LR             = 2e-5
WARMUP_RATIO   = 0.1
MAX_TRAIN_ROWS = None         # set to e.g. 20000 for a quick test run
USE_FP16       = True         # mixed precision to save VRAM


# ── Dataset ────────────────────────────────────────────────────────────
class EmailDataset(Dataset):
    def __init__(self, texts, labels, tokenizer, max_len):
        self.encodings = tokenizer(
            texts, truncation=True, padding="max_length",
            max_length=max_len, return_tensors="pt",
        )
        self.labels = torch.tensor(labels, dtype=torch.long)

    def __len__(self):
        return len(self.labels)

    def __getitem__(self, idx):
        return {
            "input_ids":      self.encodings["input_ids"][idx],
            "attention_mask": self.encodings["attention_mask"][idx],
            "labels":         self.labels[idx],
        }


# ── Evaluation ─────────────────────────────────────────────────────────
@torch.no_grad()
def evaluate(model, loader, device):
    model.eval()
    all_probs, all_labels = [], []
    for batch in loader:
        input_ids = batch["input_ids"].to(device)
        attention_mask = batch["attention_mask"].to(device)
        logits = model(input_ids=input_ids, attention_mask=attention_mask).logits
        probs = torch.softmax(logits, dim=-1)[:, 1].cpu().numpy()
        all_probs.extend(probs)
        all_labels.extend(batch["labels"].numpy())
    all_probs = np.array(all_probs)
    all_labels = np.array(all_labels)
    preds = (all_probs >= 0.5).astype(int)
    pr, rc, f1, _ = precision_recall_fscore_support(all_labels, preds, average="binary", zero_division=0)
    neg = all_labels == 0
    fpr = float(np.mean(preds[neg])) if neg.any() else 0.0
    auc = float(roc_auc_score(all_labels, all_probs)) if len(set(all_labels)) > 1 else float("nan")
    return {
        "n": len(all_labels),
        "precision": round(float(pr), 4),
        "recall": round(float(rc), 4),
        "f1": round(float(f1), 4),
        "false_positive_rate": round(fpr, 4),
        "roc_auc": round(auc, 4),
    }


# ── Training loop ──────────────────────────────────────────────────────
def train():
    # --- Device ---
    if not torch.cuda.is_available():
        print("WARNING: CUDA not available. Training will be VERY slow on CPU.")
        print("Install PyTorch with CUDA:  pip install torch --index-url https://download.pytorch.org/whl/cu128")
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"Device: {device}")
    if device.type == "cuda":
        print(f"GPU: {torch.cuda.get_device_name(0)}")
        print(f"VRAM: {torch.cuda.get_device_properties(0).total_mem / 1024**3:.1f} GB")

    # --- Load data ---
    print("\nLoading preprocessed data ...")
    train_df = pd.read_csv(DATASET_DIR / "emails_train.csv")
    val_df   = pd.read_csv(DATASET_DIR / "emails_val.csv")
    test_df  = pd.read_csv(DATASET_DIR / "emails_test_in_distribution.csv")
    cross_df = pd.read_csv(DATASET_DIR / "emails_test_cross_source.csv")

    if MAX_TRAIN_ROWS and len(train_df) > MAX_TRAIN_ROWS:
        train_df = train_df.sample(MAX_TRAIN_ROWS, random_state=42)
        print(f"  Sampled training set to {MAX_TRAIN_ROWS} rows")

    print(f"  Train: {len(train_df)},  Val: {len(val_df)},  "
          f"Test: {len(test_df)},  Cross-source: {len(cross_df)}")

    # --- Tokenizer ---
    print(f"\nLoading tokenizer: {MODEL_NAME} ...")
    tokenizer = DistilBertTokenizerFast.from_pretrained(MODEL_NAME)

    # --- Datasets ---
    print("Tokenizing ...")
    train_ds = EmailDataset(train_df["text"].fillna("").tolist(), train_df["label"].tolist(), tokenizer, MAX_LEN)
    val_ds   = EmailDataset(val_df["text"].fillna("").tolist(), val_df["label"].tolist(), tokenizer, MAX_LEN)
    test_ds  = EmailDataset(test_df["text"].fillna("").tolist(), test_df["label"].tolist(), tokenizer, MAX_LEN)
    cross_ds = EmailDataset(cross_df["text"].fillna("").tolist(), cross_df["label"].tolist(), tokenizer, MAX_LEN)

    train_loader = DataLoader(train_ds, batch_size=BATCH_SIZE, shuffle=True,  pin_memory=True, num_workers=0)
    val_loader   = DataLoader(val_ds,   batch_size=BATCH_SIZE * 2, shuffle=False, pin_memory=True, num_workers=0)
    test_loader  = DataLoader(test_ds,  batch_size=BATCH_SIZE * 2, shuffle=False, pin_memory=True, num_workers=0)
    cross_loader = DataLoader(cross_ds, batch_size=BATCH_SIZE * 2, shuffle=False, pin_memory=True, num_workers=0)

    # --- Model ---
    print(f"Loading model: {MODEL_NAME} ...")
    model = DistilBertForSequenceClassification.from_pretrained(MODEL_NAME, num_labels=2)
    model.to(device)

    # --- Optimizer & scheduler ---
    optimizer = torch.optim.AdamW(model.parameters(), lr=LR, weight_decay=0.01)
    total_steps = (len(train_loader) // GRAD_ACCUM) * EPOCHS
    scheduler = get_linear_schedule_with_warmup(
        optimizer, num_warmup_steps=int(total_steps * WARMUP_RATIO), num_training_steps=total_steps
    )
    scaler = torch.amp.GradScaler("cuda", enabled=(USE_FP16 and device.type == "cuda"))

    # --- Training ---
    print(f"\n{'='*60}")
    print(f"Training: {EPOCHS} epochs, batch={BATCH_SIZE}, grad_accum={GRAD_ACCUM}, "
          f"effective_batch={BATCH_SIZE * GRAD_ACCUM}")
    print(f"FP16: {USE_FP16 and device.type == 'cuda'},  Total steps: {total_steps}")
    print(f"{'='*60}\n")

    best_f1, best_epoch = 0.0, 0
    for epoch in range(EPOCHS):
        model.train()
        total_loss, n_batches = 0.0, 0
        optimizer.zero_grad()

        for step, batch in enumerate(train_loader):
            input_ids = batch["input_ids"].to(device)
            attention_mask = batch["attention_mask"].to(device)
            labels = batch["labels"].to(device)

            with torch.amp.autocast("cuda", enabled=(USE_FP16 and device.type == "cuda")):
                outputs = model(input_ids=input_ids, attention_mask=attention_mask, labels=labels)
                loss = outputs.loss / GRAD_ACCUM

            scaler.scale(loss).backward()
            total_loss += loss.item() * GRAD_ACCUM
            n_batches += 1

            if (step + 1) % GRAD_ACCUM == 0:
                scaler.unscale_(optimizer)
                torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
                scaler.step(optimizer)
                scaler.update()
                optimizer.zero_grad()
                scheduler.step()

            if (step + 1) % 500 == 0:
                avg = total_loss / n_batches
                vram = torch.cuda.memory_allocated() / 1024**3 if device.type == "cuda" else 0
                print(f"  Epoch {epoch+1}/{EPOCHS}  Step {step+1}/{len(train_loader)}  "
                      f"Loss: {avg:.4f}  VRAM: {vram:.2f} GB")

        # End of epoch: validate
        avg_loss = total_loss / max(n_batches, 1)
        val_metrics = evaluate(model, val_loader, device)
        print(f"  Epoch {epoch+1}/{EPOCHS} done — Loss: {avg_loss:.4f}  "
              f"Val F1: {val_metrics['f1']:.4f}  Val AUC: {val_metrics['roc_auc']:.4f}")

        if val_metrics["f1"] > best_f1:
            best_f1 = val_metrics["f1"]
            best_epoch = epoch + 1
            # Save best checkpoint
            SAVE_DIR.mkdir(parents=True, exist_ok=True)
            model.save_pretrained(SAVE_DIR)
            tokenizer.save_pretrained(SAVE_DIR)
            print(f"    -> New best! Saved to {SAVE_DIR}")

    # --- Reload best & evaluate on test sets ---
    print(f"\nBest epoch: {best_epoch} (val F1 = {best_f1:.4f})")
    print("Reloading best checkpoint for final evaluation ...")
    model = DistilBertForSequenceClassification.from_pretrained(SAVE_DIR, num_labels=2).to(device)

    test_metrics  = evaluate(model, test_loader, device)
    cross_metrics = evaluate(model, cross_loader, device)

    print(f"\n{'='*60}")
    print("FINAL RESULTS")
    print(f"{'='*60}")
    print(f"In-distribution test:  {json.dumps(test_metrics, indent=2)}")
    print(f"Cross-source test:     {json.dumps(cross_metrics, indent=2)}")

    # --- Save joblib wrapper for backend compatibility ---
    save_wrapper(SAVE_DIR, test_metrics, cross_metrics)

    # --- Save metrics.json ---
    meta = {
        "model": "distilbert-base-uncased (fine-tuned)",
        "source": "Kaggle phishing-email dataset (CEAS_08, Enron, Ling, Nazario, Nigerian_Fraud)",
        "n_train": len(train_df),
        "holdout_source": "SpamAssasin",
        "best_epoch": best_epoch,
        "hyperparameters": {
            "max_len": MAX_LEN, "batch_size": BATCH_SIZE, "grad_accum": GRAD_ACCUM,
            "lr": LR, "epochs": EPOCHS, "fp16": USE_FP16,
        },
        "test_in_distribution": test_metrics,
        "test_cross_source": cross_metrics,
        "notes": [
            "Cross-source test (SpamAssasin) is the most credible number.",
            "Production must apply the same visible_text + normalise cleaning before scoring.",
        ],
    }
    METRICS_PATH.write_text(json.dumps(meta, indent=2), encoding="utf-8")
    print(f"\nMetrics saved to {METRICS_PATH}")
    print(f"Model saved to {SAVE_DIR}")
    print("Done!")


# ── Backend-compatible wrapper ─────────────────────────────────────────
def save_wrapper(model_dir, test_metrics, cross_metrics):
    """Save a joblib wrapper that mimics TextModel's predict/predict_many/top_terms API."""
    import joblib

    class TransformerTextModel:
        """Drop-in replacement for TextModel that uses the fine-tuned DistilBERT."""

        def __init__(self, model_dir):
            self.model_dir = str(model_dir)
            self._model = None
            self._tokenizer = None
            self._device = None
            self.meta = {}

        def _load(self):
            if self._model is None:
                self._device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
                self._tokenizer = DistilBertTokenizerFast.from_pretrained(self.model_dir)
                self._model = DistilBertForSequenceClassification.from_pretrained(
                    self.model_dir, num_labels=2
                ).to(self._device).eval()

        def predict(self, text: str) -> float:
            return float(self.predict_many([text])[0])

        def predict_many(self, texts: list) -> np.ndarray:
            self._load()
            enc = self._tokenizer(
                texts, truncation=True, padding=True,
                max_length=256, return_tensors="pt",
            )
            with torch.no_grad():
                logits = self._model(
                    input_ids=enc["input_ids"].to(self._device),
                    attention_mask=enc["attention_mask"].to(self._device),
                ).logits
            return torch.softmax(logits, dim=-1)[:, 1].cpu().numpy()

        def top_terms(self, text: str, k: int = 5) -> list:
            """Return top-k tokens that contribute most to the phishing score."""
            self._load()
            tokens = self._tokenizer.tokenize(text)[:255]
            if not tokens:
                return []
            # Score with and without each token to get attributions
            base_score = self.predict(text)
            results = []
            for i, token in enumerate(tokens):
                # Remove token i and re-score
                ablated = tokens[:i] + tokens[i+1:]
                ablated_text = self._tokenizer.convert_tokens_to_string(ablated)
                ablated_score = self.predict(ablated_text)
                contribution = base_score - ablated_score
                if contribution > 0:
                    results.append({"term": token.replace("##", ""), "weight": round(contribution, 3)})
            results.sort(key=lambda x: x["weight"], reverse=True)
            return results[:k]

        def evaluate(self, texts: list, labels: list) -> dict:
            p = self.predict_many(texts)
            preds = (p >= 0.5).astype(int)
            pr, rc, f1, _ = precision_recall_fscore_support(labels, preds, average="binary", zero_division=0)
            neg = [i for i, y in enumerate(labels) if y == 0]
            fpr = float(np.mean(preds[neg])) if neg else 0.0
            auc = float(roc_auc_score(labels, p)) if len(set(labels)) > 1 else float("nan")
            return {
                "n": len(labels), "precision": round(float(pr), 4),
                "recall": round(float(rc), 4), "f1": round(float(f1), 4),
                "false_positive_rate": round(fpr, 4), "roc_auc": round(auc, 4),
            }

        def save(self, path=None):
            path = Path(path or JOBLIB_PATH)
            path.parent.mkdir(parents=True, exist_ok=True)
            # Don't serialize the loaded model/tokenizer, just the path
            self._model = None
            self._tokenizer = None
            self._device = None
            joblib.dump(self, path)

        @staticmethod
        def load(path=None):
            return joblib.load(path or JOBLIB_PATH)

    wrapper = TransformerTextModel(str(model_dir))
    wrapper.meta = {
        "model": "distilbert-base-uncased (fine-tuned)",
        "test_in_distribution": test_metrics,
        "test_cross_source": cross_metrics,
    }
    wrapper.save(JOBLIB_PATH)
    print(f"Backend-compatible wrapper saved to {JOBLIB_PATH}")


if __name__ == "__main__":
    train()

