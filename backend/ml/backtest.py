"""Backtest CryptoSense AI on real Binance history and save every prediction to CSV.

    python -m ml.backtest                  # last 90 days, all coins
    python -m ml.backtest --days 30        # last 30 days
    python -m ml.backtest --days 60 --symbols BTCUSDT,ETHUSDT

For every hour the trained models (ml/models) make a prediction using ONLY data known at that
hour. 24h later (same horizon/threshold the model was trained with) we check what really
happened. Results:

    ml/backtest_results/predictions.csv  -> one row per coin per hour (prediction vs reality)
    ml/backtest_results/summary.csv      -> accuracy, F1, precision, signal returns per coin

NOTE: Keep --days smaller than the model's test window (about the last 15% of training data,
roughly 12+ months for a 10-year model); otherwise some rows were seen during training and
the result looks better than reality.
"""
import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.metrics import accuracy_score, f1_score, precision_score

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.config import settings  # noqa: E402
from app.services.features import FEATURES, LABELS, add_features, add_labels, merge_context  # noqa: E402
from app.services.predictor import Predictor  # noqa: E402
from ml.train import download_fng, download_funding, download_klines  # noqa: E402

OUT_DIR = ROOT / "ml" / "backtest_results"
WARMUP_DAYS = 10          # extra history so indicators (SMA50, 7-day F&G change) are ready
APP_MIN_CONFIDENCE = 0.55  # same rule as the app: weak bullish/bearish calls are shown as neutral


def ensemble_proba(pred: Predictor, X: pd.DataFrame) -> np.ndarray:
    """Exactly the app's ensemble (weights + tuned class bias), for many rows at once."""
    return pred.combine([(key, model.predict_proba(X)) for key, model in pred.tabular.items()])


def confidence_report(df: pd.DataFrame) -> pd.DataFrame:
    """How accurate the model is when it is more sure (fewer calls, but better ones)."""
    d = df[df["actual_label"] != "pending"]
    rows = []
    for t in (0.0, 0.5, 0.55, 0.6, 0.65, 0.7, 0.8):
        m = d[d["confidence"] >= t]
        rows.append({
            "min_confidence": t,
            "hours": len(m),
            "coverage": round(len(m) / len(d), 4) if len(d) else None,
            "accuracy": round(float((m["model_signal"] == m["actual_label"]).mean()), 4) if len(m) else None,
            "bullish_calls": int((m["model_signal"] == "bullish").sum()),
            "bullish_hit_rate": round(float((m.loc[m["model_signal"] == "bullish", "actual_label"] == "bullish").mean()), 4)
            if (m["model_signal"] == "bullish").any() else None,
            "bearish_calls": int((m["model_signal"] == "bearish").sum()),
            "bearish_hit_rate": round(float((m.loc[m["model_signal"] == "bearish", "actual_label"] == "bearish").mean()), 4)
            if (m["model_signal"] == "bearish").any() else None,
        })
    return pd.DataFrame(rows)


def build_rows(symbol: str, days: int, horizon: int, threshold: float, fng, btc) -> pd.DataFrame:
    df = btc if symbol == "BTCUSDT" else download_klines(symbol, days + WARMUP_DAYS)
    funding = download_funding(symbol, days + WARMUP_DAYS)
    data = add_labels(add_features(merge_context(df, funding, fng, btc)), horizon, threshold)
    start = pd.Timestamp.now(tz="UTC") - pd.Timedelta(days=days)
    data = data[data["time"] >= start].dropna(subset=FEATURES).reset_index(drop=True)
    data["symbol"] = symbol
    return data


def summarize(df: pd.DataFrame, name: str) -> dict:
    d = df[df["actual_label"] != "pending"]
    if d.empty:
        return {"symbol": name, "rows_checked": 0}
    y = d["actual_label"].map({v: k for k, v in LABELS.items()}).to_numpy()
    raw = d["model_signal"].map({v: k for k, v in LABELS.items()}).to_numpy()
    app = d["app_signal"].map({v: k for k, v in LABELS.items()}).to_numpy()
    majority = int(np.bincount(y, minlength=3).argmax())

    def prec(pred, cls):
        return round(float(precision_score(y, pred, labels=[cls], average="macro", zero_division=0)), 4)

    bull = d[d["app_signal"] == "bullish"]
    bear = d[d["app_signal"] == "bearish"]
    traded = d[d["app_signal"] != "neutral"]
    return {
        "symbol": name,
        "rows_checked": len(d),
        "from_utc": d["time_utc"].min(),
        "to_utc": d["time_utc"].max(),
        "model_accuracy": round(float(accuracy_score(y, raw)), 4),
        "model_macro_f1": round(float(f1_score(y, raw, average="macro")), 4),
        "baseline_accuracy(always_most_common)": round(float((y == majority).mean()), 4),
        "baseline_macro_f1": round(float(f1_score(y, np.full_like(y, majority), average="macro")), 4),
        "model_bullish_precision": prec(raw, 2),
        "model_bearish_precision": prec(raw, 0),
        "actual_bullish_share": round(float((y == 2).mean()), 4),
        "actual_bearish_share": round(float((y == 0).mean()), 4),
        "app_accuracy": round(float(accuracy_score(y, app)), 4),
        "app_bullish_signals": len(bull),
        "app_bullish_hit_rate": round(float((bull["actual_label"] == "bullish").mean()), 4) if len(bull) else None,
        "app_bearish_signals": len(bear),
        "app_bearish_hit_rate": round(float((bear["actual_label"] == "bearish").mean()), 4) if len(bear) else None,
        "app_signals_direction_right": round(float((traded["signal_return_pct"] > 0).mean()), 4) if len(traded) else None,
        "avg_return_per_app_signal_pct": round(float(traded["signal_return_pct"].mean()), 4) if len(traded) else None,
        "avg_24h_change_all_hours_pct": round(float(d["actual_change_pct"].mean()), 4),
    }


def main() -> None:
    p = argparse.ArgumentParser(description="Backtest CryptoSense AI and save results to CSV")
    p.add_argument("--days", type=int, default=90, help="how many recent days to test (default 90)")
    p.add_argument("--symbols", default=None, help="comma list, default = SYMBOLS from .env")
    p.add_argument("--out", default=str(OUT_DIR), help="folder for the CSV files")
    args = p.parse_args()

    pred = Predictor()
    if not pred.ready:
        sys.exit("No trained models in ml/models. Run TRAIN_AI.bat first.")
    horizon = int(pred.metrics.get("horizon_hours", 24))
    threshold = float(pred.metrics.get("threshold_pct", 2.5))
    symbols = [s.strip().upper() for s in args.symbols.split(",")] if args.symbols else settings.symbol_list
    print(f"Backtest: last {args.days} days, horizon {horizon}h, threshold {threshold}%, "
          f"models {pred.models}, trained {pred.metrics.get('trained_at', '?')}")

    print("  downloading Fear & Greed + BTCUSDT ...")
    fng = download_fng()
    btc = download_klines("BTCUSDT", args.days + WARMUP_DAYS)

    frames = []
    for symbol in symbols:
        print(f"  {symbol} ...", end=" ", flush=True)
        try:
            data = build_rows(symbol, args.days, horizon, threshold, fng, btc)
        except Exception as e:
            print(f"skipped ({e.__class__.__name__}: {e})")
            continue
        if data.empty:
            print("no data")
            continue
        proba = ensemble_proba(pred, data[FEATURES])
        cls = proba.argmax(1)
        conf = proba.max(1)
        app_cls = np.where((cls != 1) & (conf < APP_MIN_CONFIDENCE), 1, cls)
        pending = data["label"].isna().to_numpy()

        out = pd.DataFrame({
            "time_utc": data["time"].dt.strftime("%Y-%m-%d %H:%M"),
            "time_pkt": (data["time"] + pd.Timedelta(hours=5)).dt.strftime("%Y-%m-%d %H:%M"),
            "symbol": symbol,
            "price": data["close"].round(6),
            "prob_bearish": proba[:, 0].round(3),
            "prob_neutral": proba[:, 1].round(3),
            "prob_bullish": proba[:, 2].round(3),
            "confidence": conf.round(3),
            "model_signal": [LABELS[c] for c in cls],
            "app_signal": [LABELS[c] for c in app_cls],
            "price_after_24h": (data["close"] * (1 + data["future_ret"] / 100)).round(6),
            "actual_change_pct": data["future_ret"].round(3),
            "actual_label": [("pending" if pd.isna(v) else LABELS[int(v)]) for v in data["label"]],
        })
        out["model_correct"] = np.where(pending, "", np.where(out["model_signal"] == out["actual_label"], "YES", "NO"))
        out["app_correct"] = np.where(pending, "", np.where(out["app_signal"] == out["actual_label"], "YES", "NO"))
        # If you followed the app: bullish = buy (gain = change), bearish = sell/short (gain = -change)
        sign = np.select([out["app_signal"] == "bullish", out["app_signal"] == "bearish"], [1, -1], 0)
        out["signal_return_pct"] = np.where(pending | (sign == 0), np.nan, sign * out["actual_change_pct"]).round(3)
        frames.append(out)
        print(f"{len(out)} hours")

    if not frames:
        sys.exit("No results (check internet / Binance access).")

    allp = pd.concat(frames, ignore_index=True)
    summary = pd.DataFrame([summarize(f, f["symbol"].iloc[0]) for f in frames] + [summarize(allp, "ALL")])

    out_dir = Path(args.out).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    try:
        allp.to_csv(out_dir / "predictions.csv", index=False)
        summary.to_csv(out_dir / "summary.csv", index=False)
        conf_table = confidence_report(allp)
        conf_table.to_csv(out_dir / "confidence.csv", index=False)
    except PermissionError:
        sys.exit(f"Could not write CSV. Close predictions.csv / summary.csv in Excel and run again ({out_dir}).")

    s = summary.iloc[-1]
    print(f"\nALL coins: {s['rows_checked']} checked hours")
    print(f"  model accuracy {s['model_accuracy']}  macro F1 {s['model_macro_f1']}  "
          f"(baseline accuracy {s['baseline_accuracy(always_most_common)']}, F1 {s['baseline_macro_f1']})")
    print(f"  app signals: {s['app_bullish_signals']} bullish (hit {s['app_bullish_hit_rate']}), "
          f"{s['app_bearish_signals']} bearish (hit {s['app_bearish_hit_rate']}), "
          f"avg return per signal {s['avg_return_per_app_signal_pct']}%")
    print("\nAccuracy by confidence (all coins):")
    for r in conf_table.to_dict("records"):
        cov = f"{r['coverage']:.1%}" if r["coverage"] is not None else "-"
        print(f"  conf >= {r['min_confidence']:.2f}: {int(r['hours']):6d} hours ({cov}), accuracy {r['accuracy']}")
    print(f"\nSaved:\n  {out_dir / 'predictions.csv'}\n  {out_dir / 'summary.csv'}\n  {out_dir / 'confidence.csv'}")


if __name__ == "__main__":
    main()