"""TF-IDF + logistic regression phishing-text classifier with per-term attributions.

Chosen over a transformer for this build because (a) every prediction decomposes into term
contributions an analyst can read, (b) it trains in seconds, scores thousands of emails per second
on one CPU core, and (c) it has no GPU or model-download dependency. A fine-tuned transformer is a
roadmap item behind the same `predict` / `top_terms` interface.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import joblib
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import precision_recall_fscore_support, roc_auc_score

MODEL_DIR = Path(os.environ.get("TRACEGUARD_MODEL_DIR", Path(__file__).resolve().parents[2] / "models"))
MODEL_PATH = MODEL_DIR / "text_model.joblib"
METRICS_PATH = MODEL_DIR / "metrics.json"


@dataclass
class TextModel:
    vectorizer: TfidfVectorizer = field(default_factory=lambda: TfidfVectorizer(
        lowercase=True, ngram_range=(1, 2), min_df=2, max_features=60000, sublinear_tf=True, strip_accents="unicode"))
    clf: LogisticRegression = field(default_factory=lambda: LogisticRegression(C=2.0, max_iter=1000, class_weight="balanced"))
    meta: dict = field(default_factory=dict)

    def fit(self, texts: list[str], labels: list[int]) -> "TextModel":
        X = self.vectorizer.fit_transform(texts)
        self.clf.fit(X, labels)
        return self

    def predict(self, text: str) -> float:
        return float(self.clf.predict_proba(self.vectorizer.transform([text]))[0, 1])

    def predict_many(self, texts: list[str]) -> np.ndarray:
        return self.clf.predict_proba(self.vectorizer.transform(texts))[:, 1]

    def top_terms(self, text: str, k: int = 5) -> list[dict]:
        """Terms in this email that pushed the score towards phishing, with their contribution (log-odds)."""
        X = self.vectorizer.transform([text])
        idx = X.nonzero()[1]
        if idx.size == 0:
            return []
        names = self.vectorizer.get_feature_names_out()
        contrib = X[0, idx].toarray().ravel() * self.clf.coef_[0][idx]
        order = np.argsort(-contrib)[:k]
        return [{"term": str(names[idx[i]]), "weight": round(float(contrib[i]), 3)} for i in order if contrib[i] > 0]

    def evaluate(self, texts: list[str], labels: list[int]) -> dict:
        p = self.predict_many(texts)
        pred = (p >= 0.5).astype(int)
        pr, rc, f1, _ = precision_recall_fscore_support(labels, pred, average="binary", zero_division=0)
        neg = [i for i, y in enumerate(labels) if y == 0]
        fpr = float(np.mean(pred[neg])) if neg else 0.0
        auc = float(roc_auc_score(labels, p)) if len(set(labels)) > 1 else float("nan")
        return {"n": len(labels), "precision": round(float(pr), 4), "recall": round(float(rc), 4), "f1": round(float(f1), 4),
                "false_positive_rate": round(fpr, 4), "roc_auc": round(auc, 4)}

    def save(self, path: Path = MODEL_PATH) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        joblib.dump(self, path)

    @staticmethod
    def load(path: Path = MODEL_PATH) -> "TextModel":
        return joblib.load(path)


def bootstrap(save: bool = True) -> TextModel:
    """Train on the synthetic template corpus. Metrics are written with an explicit 'synthetic' label."""
    from . import synth_text
    tx, ty, vx, vy = synth_text.build()
    m = TextModel().fit(tx, ty)
    metrics = m.evaluate(vx, vy)
    m.meta = {
        "source": "synthetic template corpus (team-written, NOT real mail)",
        "n_train": len(tx), "holdout": "unseen template families",
        "metrics": metrics,
        "warning": "These numbers measure how well the pipeline separates template text. They are not evidence of real-world accuracy. "
                   "Retrain with scripts/train_text_model.py on the Kaggle dataset.",
    }
    if save:
        m.save()
        METRICS_PATH.write_text(json.dumps(m.meta, indent=2), encoding="utf-8")
    return m


_cached: Optional[TextModel] = None


def get_model() -> TextModel:
    global _cached
    if _cached is None:
        try:
            _cached = TextModel.load()
        except Exception:
            _cached = bootstrap(save=True)
    return _cached


def reset_cache() -> None:
    global _cached
    _cached = None
