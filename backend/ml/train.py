"""Train the CryptoSense AI market-state models (XGBoost + LightGBM ensemble).

    python -m ml.train                          # real Binance data, 10 years requested (needs internet)
    python -m ml.train --days 3650 --horizon 24 --threshold 2.5
    python -m ml.train --out ml/models/candidate   # save elsewhere to compare before replacing

Pipeline
1. Data: hourly candles (with taker-buy volume), futures funding rates, Fear & Greed, BTC trend.
   Only hours where funding and Fear & Greed were really observed are used (no filled-in values).
2. Features + label (next `horizon` hours: > +threshold% bullish, < -threshold% bearish, else neutral).
3. Chronological split per coin: 70% train | 15% validation | 15% test, with a `horizon` gap
   between parts so no future label leaks into training.
4. Models: XGBoost and LightGBM (early stopping on validation).
5. Ensemble: probabilities averaged, weighted by each model's validation macro-F1.
6. Report on the untouched test set vs a majority-class baseline; save models + metrics.json.
"""
import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx
import joblib
import lightgbm as lgb
import numpy as np
import pandas as pd
from sklearn.metrics import accuracy_score, classification_report, confusion_matrix, f1_score
from sklearn.utils.class_weight import compute_sample_weight
from xgboost import XGBClassifier

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.config import settings  # noqa: E402
from app.services.binance import funding_frame, to_frame  # noqa: E402
from app.services.features import FEATURES, LABELS, add_features, add_labels, merge_context  # noqa: E402
from app.services.sentiment_index import fng_frame  # noqa: E402

MODEL_DIR = ROOT / "ml" / "models"
NAMES = {"xgb": "XGBoost", "lgbm": "LightGBM", "ensemble": "Ensemble", "ensemble_tuned": "Ensemble (tuned)"}


# ------------------------------------------------------------------ decision tuning
def apply_bias(proba: np.ndarray, bias: list[float]) -> np.ndarray:
    """Multiply each class probability by its bias and renormalise (same code idea as the app)."""
    p = proba * np.asarray(bias, dtype=float)
    return p / p.sum(1, keepdims=True)


def tune_class_bias(y: np.ndarray, proba: np.ndarray) -> list[float]:
    """Grid-search bearish/bullish multipliers (neutral = 1) on validation data.
    Score = average of accuracy and macro-F1, so the model stops over-calling moves (higher
    accuracy) without collapsing into 'always neutral' (macro-F1 would drop)."""
    best, best_score = [1.0, 1.0, 1.0], -1.0
    grid = np.round(np.arange(0.2, 1.51, 0.05), 2)
    for b_bear in grid:
        for b_bull in grid:
            pred = apply_bias(proba, [b_bear, 1.0, b_bull]).argmax(1)
            score = (accuracy_score(y, pred) + f1_score(y, pred, average="macro")) / 2
            if score > best_score:
                best, best_score = [float(b_bear), 1.0, float(b_bull)], score
    return best


def confidence_table(y: np.ndarray, proba: np.ndarray) -> list[dict]:
    pred, conf = proba.argmax(1), proba.max(1)
    rows = []
    for t in (0.0, 0.5, 0.6, 0.7, 0.8):
        m = conf >= t
        rows.append({"min_confidence": t, "coverage": round(float(m.mean()), 4),
                     "accuracy": round(float(accuracy_score(y[m], pred[m])), 4) if m.any() else None})
    return rows


# ------------------------------------------------------------------ data download
def _ms(days_ago: float) -> int:
    return int((time.time() - days_ago * 86400) * 1000)


def download_klines(symbol: str, days: int) -> pd.DataFrame:
    start, rows = _ms(days), []
    with httpx.Client(base_url=settings.binance_base, timeout=20) as c:
        while True:
            r = c.get("/api/v3/klines", params={"symbol": symbol, "interval": "1h", "startTime": start, "limit": 1000})
            r.raise_for_status()
            batch = r.json()
            if not batch:
                break
            rows.extend(batch)
            start = batch[-1][0] + 1
            if len(batch) < 1000:
                break
            time.sleep(0.15)
    return to_frame(rows)


def download_funding(symbol: str, days: int) -> pd.DataFrame | None:
    start, rows = _ms(days + 3), []
    try:
        with httpx.Client(base_url=settings.binance_futures_base, timeout=20) as c:
            while True:
                r = c.get("/fapi/v1/fundingRate", params={"symbol": symbol, "startTime": start, "limit": 1000})
                r.raise_for_status()
                batch = r.json()
                if not batch:
                    break
                rows.extend(batch)
                start = int(batch[-1]["fundingTime"]) + 1
                if len(batch) < 1000:
                    break
                time.sleep(0.15)
        return funding_frame(rows)
    except Exception as e:
        print(f"    (no funding data for {symbol}: {e.__class__.__name__}; using neutral value)")
        return None


def download_fng() -> pd.DataFrame | None:
    try:
        r = httpx.get(settings.fear_greed_url, params={"limit": 0}, timeout=20)
        r.raise_for_status()
        return fng_frame(r.json()["data"])
    except Exception as e:
        print(f"  (Fear & Greed unavailable: {e.__class__.__name__}; using neutral value)")
        return None


def load_data(args) -> list[pd.DataFrame]:
    """One labelled feature table per coin."""
    tables = []
    print("  downloading Fear & Greed history ...")
    fng = download_fng()
    print("  downloading BTCUSDT (market context) ...")
    btc = download_klines("BTCUSDT", args.days)
    for symbol in settings.symbol_list:
        print(f"  downloading {symbol} ...", end=" ", flush=True)
        df = btc if symbol == "BTCUSDT" else download_klines(symbol, args.days)
        print(f"{len(df)} candles")
        tables.append((symbol, df, download_funding(symbol, args.days), fng, btc))

    out = []
    for symbol, df, funding, fng, btc in tables:
        merged = merge_context(df, funding, fng, btc)
        # Only keep hours where funding and Fear & Greed were really observed (Binance futures
        # funding starts in 2019-2020, Fear & Greed in 2018); filled-in values are never trained on.
        real = pd.Series(True, index=merged.index)
        for col in ("funding_rate", "fng"):
            real &= merged[col].notna() if col in merged else False
        data = add_labels(add_features(merged), args.horizon, args.threshold)
        data = data[real.to_numpy()]
        if data.empty:
            print(f"  {symbol}: no hours with real funding + Fear & Greed data; skipped")
            continue
        print(f"  {symbol}: training data with real inputs starts {pd.Timestamp(data['time'].iloc[0]).date()} "
              f"({(~real).sum()} earlier/missing hours dropped)")
        data = data.dropna(subset=FEATURES + ["label"]).reset_index(drop=True)
        data["label"] = data["label"].astype(int)
        data["symbol"] = symbol
        out.append(data)
    return out


def split_ranges(n: int, gap: int) -> dict[str, tuple[int, int]]:
    """Row ranges for train / val / test inside one coin's table (chronological, with gaps)."""
    a, b = int(n * 0.70), int(n * 0.85)
    return {"train": (0, max(a - gap, 0)), "val": (a, max(b - gap, a)), "test": (b, n)}


# ------------------------------------------------------------------ evaluation
def report(name: str, y: np.ndarray, proba: np.ndarray) -> dict:
    pred = proba.argmax(1)
    acc, f1 = accuracy_score(y, pred), f1_score(y, pred, average="macro")
    conf = proba.max(1)
    sure = conf >= 0.5
    print(f"\n=== {name} ===  accuracy {acc:.3f}   macro F1 {f1:.3f}")
    print(classification_report(y, pred, labels=[0, 1, 2], target_names=[LABELS[i] for i in range(3)],
                                digits=3, zero_division=0))
    cm = confusion_matrix(y, pred, labels=[0, 1, 2])
    print("confusion matrix (rows = actual bearish / neutral / bullish):\n", cm)
    return {
        "accuracy": round(float(acc), 4),
        "macro_f1": round(float(f1), 4),
        "confident_accuracy": round(float(accuracy_score(y[sure], pred[sure])), 4) if sure.any() else None,
        "confident_coverage": round(float(sure.mean()), 4),
        "confusion_matrix": cm.tolist(),
    }


# ------------------------------------------------------------------ main
def main() -> None:
    p = argparse.ArgumentParser(description="Train CryptoSense AI models")
    p.add_argument("--days", type=int, default=3650, help="days of hourly history per coin (default 10 years; Binance data starts 2017, futures funding 2019-2020)")
    p.add_argument("--horizon", type=int, default=24, help="hours ahead the label looks")
    p.add_argument("--threshold", type=float, default=1.5, help="%% move that counts as bullish/bearish")
    p.add_argument("--out", default=None,
                   help="folder to save models in (default ml/models; use another folder to compare first)")
    args = p.parse_args()
    global MODEL_DIR
    if args.out:
        MODEL_DIR = Path(args.out).resolve()

    print(f"Building dataset (live Binance data, {args.days} days, "
          f"horizon {args.horizon}h, threshold {args.threshold}%)")
    tables = load_data(args)
    gap = args.horizon
    ranges = [split_ranges(len(t), gap) for t in tables]

    def part(name: str) -> pd.DataFrame:
        return pd.concat([t.iloc[r[name][0]:r[name][1]] for t, r in zip(tables, ranges)])

    # Validation and test rows are identical for every model, so their probabilities can be averaged
    tr, va, te = part("train"), part("val"), part("test")
    X_tr, y_tr = tr[FEATURES], tr["label"].to_numpy()
    X_va, y_va = va[FEATURES], va["label"].to_numpy()
    X_te, y_te = te[FEATURES], te["label"].to_numpy()
    balance = {LABELS[k]: int(v) for k, v in zip(*np.unique(y_tr, return_counts=True))}
    print(f"rows: train {len(X_tr)}, validation {len(X_va)}, test {len(X_te)}; train classes {balance}")

    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    for old in ("rf.joblib", "svm.joblib", "gru.pt"):
        (MODEL_DIR / old).unlink(missing_ok=True)

    val_proba, test_proba, results = {}, {}, {}

    print("\nTraining XGBoost ...")
    xgb = XGBClassifier(n_estimators=800, max_depth=4, learning_rate=0.03, subsample=0.8, colsample_bytree=0.8,
                        min_child_weight=5, objective="multi:softprob", num_class=3, eval_metric="mlogloss",
                        early_stopping_rounds=50, n_jobs=-1, random_state=42)
    xgb.fit(X_tr, y_tr, sample_weight=compute_sample_weight("balanced", y_tr), eval_set=[(X_va, y_va)], verbose=False)
    val_proba["xgb"], test_proba["xgb"] = xgb.predict_proba(X_va), xgb.predict_proba(X_te)
    joblib.dump(xgb, MODEL_DIR / "xgb.joblib")

    print("Training LightGBM ...")
    lgbm = lgb.LGBMClassifier(n_estimators=1000, learning_rate=0.03, num_leaves=31, min_child_samples=50,
                              subsample=0.8, subsample_freq=1, colsample_bytree=0.8, class_weight="balanced",
                              random_state=42, verbose=-1)
    lgbm.fit(X_tr, y_tr, eval_set=[(X_va, y_va)], callbacks=[lgb.early_stopping(50, verbose=False)])
    val_proba["lgbm"], test_proba["lgbm"] = lgbm.predict_proba(X_va), lgbm.predict_proba(X_te)
    joblib.dump(lgbm, MODEL_DIR / "lgbm.joblib")

    # Ensemble weights = validation macro-F1 of each model
    weights = {k: round(float(f1_score(y_va, v.argmax(1), average="macro")), 4) for k, v in val_proba.items()}
    wsum = sum(weights.values())
    val_proba["ensemble"] = sum(weights[k] * val_proba[k] for k in weights) / wsum
    test_proba["ensemble"] = sum(weights[k] * test_proba[k] for k in weights) / wsum

    # Decision tuning (on VALIDATION only, test stays untouched): scale the bearish/bullish
    # probabilities so the ensemble balances accuracy and macro-F1 instead of over-calling moves.
    class_bias = tune_class_bias(y_va, val_proba["ensemble"])
    print(f"\nTuned class bias (from validation): {class_bias}")
    test_proba["ensemble_tuned"] = apply_bias(test_proba["ensemble"], class_bias)

    for key in test_proba:
        results[key] = report(NAMES[key], y_te, test_proba[key])
    results["confidence_table_test"] = confidence_table(y_te, test_proba["ensemble_tuned"])
    print("\nTuned ensemble on test, by confidence (higher confidence = fewer but better calls):")
    for row in results["confidence_table_test"]:
        print(f"  conf >= {row['min_confidence']:.2f}: coverage {row['coverage']:.1%}, accuracy {row['accuracy']}")

    majority = int(np.bincount(y_tr, minlength=3).argmax())
    base_pred = np.full_like(y_te, majority)
    results["baseline_majority"] = {
        "accuracy": round(float(accuracy_score(y_te, base_pred)), 4),
        "macro_f1": round(float(f1_score(y_te, base_pred, average="macro")), 4),
    }
    print(f"\nBaseline (always '{LABELS[majority]}'): accuracy {results['baseline_majority']['accuracy']:.3f}, "
          f"macro F1 {results['baseline_majority']['macro_f1']:.3f}")

    importance = pd.Series(xgb.feature_importances_, index=FEATURES).sort_values(ascending=False)
    metrics = {
        "trained_at": datetime.now(timezone.utc).isoformat(),
        "data": "binance",
        "data_start": {t["symbol"].iloc[0]: str(pd.Timestamp(t["time"].iloc[0]).date()) for t in tables},
        "symbols": settings.symbol_list,
        "days": args.days, "interval": "1h",
        "horizon_hours": args.horizon, "threshold_pct": args.threshold,
        "features": FEATURES,
        "split": "chronological 70/15/15 per coin with gaps",
        "rows": {"train": int(len(X_tr)), "validation": int(len(X_va)), "test": int(len(X_te))},
        "class_balance_train": balance,
        "ensemble_weights": weights,
        "class_bias": class_bias,
        "results": results,
        "feature_importance_xgb": {k: round(float(v), 4) for k, v in importance.items()},
    }
    (MODEL_DIR / "metrics.json").write_text(json.dumps(metrics, indent=2))

    print("\nSummary (test set, macro F1):")
    for k, r in results.items():
        if not isinstance(r, dict):
            continue
        print(f"  {NAMES.get(k, 'Baseline'):10s} {r['macro_f1']:.3f}   accuracy {r['accuracy']:.3f}")
    print(f"Saved to {MODEL_DIR}")


if __name__ == "__main__":
    main()