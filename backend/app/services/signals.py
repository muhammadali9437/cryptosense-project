"""Builds each coin's AI signal from live data: candles + funding + Fear & Greed + BTC trend.

Every model input must be real. If Binance candles, futures funding or the Fear & Greed index
can't be fetched, or no trained model exists, the signal is reported as unavailable
(SignalUnavailable) instead of being computed from made-up values.
"""
import asyncio
import logging
from datetime import datetime, timezone

from ..config import settings
from . import binance
from .cache import cached
from .features import FEATURES, add_features, explain, merge_context
from .levels import key_levels
from .predictor import predictor
from .sentiment_index import fear_greed, fng_frame

log = logging.getLogger("cryptosense.signals")


class SignalUnavailable(Exception):
    """Raised when a signal can't be computed from real inputs. `missing` names what's missing."""

    def __init__(self, symbol: str, missing: list[str]):
        self.symbol = symbol
        self.missing = missing
        super().__init__(f"{symbol}: unavailable inputs: {', '.join(missing)}")


async def _candles(symbol: str):
    async def build():
        return binance.to_frame(await binance.klines(symbol, "1h", 250))
    try:
        return await cached(f"candles:{symbol}", 60, build)
    except Exception as exc:
        log.warning("candles unavailable for %s: %s", symbol, exc.__class__.__name__)
        return None


async def _funding(symbol: str):
    try:
        frame = binance.funding_frame(await binance.funding_rates(symbol, 30))
        return frame if len(frame) else None
    except Exception:
        return None


async def _fng():
    try:
        frame = fng_frame(await fear_greed(30))
        return frame if len(frame) else None
    except Exception:
        return None


async def signal_for(symbol: str) -> dict:
    if not predictor.ready:
        raise SignalUnavailable(symbol, ["trained AI model (run TRAIN_AI.bat)"])
    df, btc, funding, fng = await asyncio.gather(_candles(symbol), _candles("BTCUSDT"), _funding(symbol), _fng())
    missing = [name for name, value in (("Binance candles", df), ("BTC candles", btc),
                                        ("futures funding rate", funding), ("Fear & Greed index", fng))
               if value is None]
    if missing:
        raise SignalUnavailable(symbol, missing)
    merged = merge_context(df, funding, fng, btc)
    feats = add_features(merged).dropna(subset=FEATURES).reset_index(drop=True)
    if feats.empty:
        raise SignalUnavailable(symbol, ["enough candle history"])
    row = feats.iloc[-1]
    pred = predictor.predict(feats)
    horizon = predictor.metrics.get("horizon_hours", 24)

    return {
        "symbol": symbol,
        "trend": pred["trend"],
        "model": pred["model"],
        "confidence": pred["confidence"],
        "horizon": f"Next {horizon} hours",
        "reasons": explain(row, pred["trend"]),
        "votes": pred["votes"],
        "probabilities": pred["probabilities"],
        "price": round(float(row["close"]), 8),
        "key_levels": key_levels(df, float(row["close"]), float(row["atr_pct"])),
        "key_levels_source": "binance",
        "key_levels_note": "Observed Binance candle levels in UTC. They add context; they are not a prediction.",
        "indicators": {k: round(float(row[k]), 4) for k in FEATURES},
        "live": True,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


async def all_signals() -> list[dict]:
    """Signals for every tracked coin that has real inputs right now (others are left out and logged).
    Raises SignalUnavailable when no coin can be computed."""
    async def build():
        out, failures = [], []
        for s in settings.symbol_list:
            try:
                out.append(await signal_for(s))
            except SignalUnavailable as exc:
                failures.append(exc)
                log.warning("%s", exc)
        if not out:
            missing = sorted({m for f in failures for m in f.missing})
            raise SignalUnavailable("all coins", missing)
        try:  # keep the chatbot's knowledge base up to date
            from .rag import kb
            await asyncio.to_thread(kb.upsert_signals, out)
        except Exception:
            pass
        return out
    return await cached("signals", 300, build)
