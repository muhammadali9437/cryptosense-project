"""Loads the trained models and combines them into one signal.

Ensemble = weighted soft voting: each model's class probabilities are averaged, weighted
by that model's macro-F1 on the validation set (better models get a bigger say).
Without trained models there is no prediction: callers report the signal as unavailable.
"""
import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

from .features import FEATURES, LABELS

MODEL_DIR = Path(__file__).resolve().parents[2] / "ml" / "models"
MODEL_NAMES = {"xgb": "XGBoost", "lgbm": "LightGBM"}


class Predictor:
    def __init__(self, model_dir: Path = MODEL_DIR):
        self.model_dir = model_dir
        self.tabular: dict = {}
        self.metrics: dict = {}
        self.weights: dict = {}
        self.reload()

    def reload(self) -> None:
        self.tabular = {}
        for key in MODEL_NAMES:
            p = self.model_dir / f"{key}.joblib"
            if p.exists():
                self.tabular[key] = joblib.load(p)
        mp = self.model_dir / "metrics.json"
        self.metrics = json.loads(mp.read_text()) if mp.exists() else {}
        self.weights = self.metrics.get("ensemble_weights", {})
        # Decision tuning learnt on validation data in ml/train.py (older models: no change)
        self.class_bias = np.asarray(self.metrics.get("class_bias", [1.0, 1.0, 1.0]), dtype=float)

    def combine(self, probs: list[tuple[str, np.ndarray]]) -> np.ndarray:
        """Weighted soft vote of model probabilities (1 or many rows), then the tuned class bias."""
        total, wsum = 0.0, 0.0
        for key, p in probs:
            w = float(self.weights.get(key, 1.0))
            total = total + w * p
            wsum += w
        avg = (total / wsum) * self.class_bias
        return avg / avg.sum(-1, keepdims=True)

    @property
    def models(self) -> list[str]:
        return list(self.tabular)

    @property
    def ready(self) -> bool:
        return bool(self.models)

    def predict(self, feats: pd.DataFrame) -> dict:
        """feats = feature rows in time order (the last row is 'now')."""
        if not self.ready:
            raise RuntimeError("No trained models in ml/models. Run TRAIN_AI.bat.")

        probs: dict[str, np.ndarray] = {}
        last = feats.iloc[[-1]][FEATURES]
        for key, model in self.tabular.items():
            probs[key] = model.predict_proba(last)[0]

        avg = self.combine(list(probs.items()))
        cls = int(np.argmax(avg))
        trend = LABELS[cls]
        confidence = round(float(avg[cls]), 3)

        # Do not issue a directional trade signal merely because it is the
        # largest of three probabilities. Low-confidence directions become
        # neutral; the UI should keep capital idle instead of forcing a call.
        if trend != "neutral" and confidence < 0.55:
            trend = "neutral"
            cls = 1

        votes = {k: {"trend": LABELS[int(np.argmax(p))], "confidence": round(float(p.max()), 3)} for k, p in probs.items()}
        agreeing = [k for k, v in votes.items() if v["trend"] == trend] or list(votes)
        best = max(agreeing, key=lambda k: votes[k]["confidence"])
        return {
            "trend": trend,
            "confidence": round(float(avg[cls]), 3),
            "model": f"Ensemble (led by {MODEL_NAMES[best]})",
            "votes": {MODEL_NAMES[k]: v for k, v in votes.items()},
            "probabilities": {LABELS[i]: round(float(x), 3) for i, x in enumerate(avg)},
        }


predictor = Predictor()