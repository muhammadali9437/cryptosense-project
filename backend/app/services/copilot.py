"""Historical market analogs for the risk copilot."""
import numpy as np
import pandas as pd

from . import binance
from .cache import cached
from .features import add_features

_TWIN_FEATURES = ("ret_24", "rsi_14", "atr_pct", "sma50_dist", "bb_width", "vol_ratio")
_HORIZON_HOURS = 24


def find_historical_twins(candles: pd.DataFrame, limit: int = 3) -> list[dict]:
    """Find similar completed hourly states and report their following 24h returns."""
    features = add_features(candles).replace([np.inf, -np.inf], np.nan)
    if len(features) <= 50 + _HORIZON_HOURS:
        return []

    values = features[list(_TWIN_FEATURES)].to_numpy(dtype=float)
    target = values[-1]
    scale = np.nanstd(values, axis=0)
    scale[~np.isfinite(scale) | (scale == 0)] = 1.0
    valid_end = len(features) - _HORIZON_HOURS
    candidates = values[50:valid_end]
    returns = (features["close"].shift(-_HORIZON_HOURS) / features["close"] - 1) * 100
    candidate_returns = returns.iloc[50:valid_end].to_numpy(dtype=float)
    candidate_times = features["time"].iloc[50:valid_end]
    valid = np.isfinite(candidates).all(axis=1) & np.isfinite(candidate_returns)
    if not valid.any():
        return []

    distances = np.sqrt(np.mean(((candidates[valid] - target) / scale) ** 2, axis=1))
    indices = np.flatnonzero(valid)
    nearest = np.argsort(distances)[:limit]
    matches = []
    for rank in nearest:
        index = indices[rank]
        result_pct = float(candidate_returns[index])
        matches.append({
            "time": candidate_times.iloc[index].isoformat(),
            "similarity_pct": round(100 / (1 + float(distances[rank])), 1),
            "future_return_pct": round(result_pct, 2),
        })
    return matches


async def historical_twins(symbol: str) -> list[dict]:
    async def build() -> list[dict]:
        rows = await binance.klines(symbol, "1h", 1000)
        return find_historical_twins(binance.to_frame(rows))

    return await cached(f"historical_twins:{symbol}", 300, build)
