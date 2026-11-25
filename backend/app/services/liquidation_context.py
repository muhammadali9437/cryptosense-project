"""Puts observed liquidations next to price, volume, open interest, funding and volatility.

The output lists scenarios that are CONSISTENT with the combination of signals, each with the
evidence that supports and contradicts it. It never claims liquidations decide future price.
All market numbers come from Binance USD-M futures public endpoints; any input that can't be
fetched is reported as unavailable instead of being guessed.
"""
import asyncio
import logging

from ..config import settings
from . import binance

log = logging.getLogger("cryptosense.liquidation_context")

# window -> (candle interval, candles per window, open-interest period, OI points per window)
PLAN = {
    "15m": ("1m", 15, "5m", 3),
    "1h": ("5m", 12, "5m", 12),
    "4h": ("15m", 16, "15m", 16),
    "24h": ("1h", 24, "1h", 24),
}
ATR_PERIOD = 14


def dominance(long_usd: float, short_usd: float) -> str:
    total = long_usd + short_usd
    if total <= 0:
        return "none"
    if long_usd > short_usd * 1.5:
        return "long"
    if short_usd > long_usd * 1.5:
        return "short"
    return "balanced"


def market_numbers(candles: list[list], per_window: int) -> dict | None:
    """Price change, range, volume vs the previous window and ATR% from futures candles."""
    rows = [(float(c[1]), float(c[2]), float(c[3]), float(c[4]), float(c[7])) for c in candles]
    if len(rows) < per_window + 1:
        return None
    window = rows[-per_window:]
    prior = rows[-2 * per_window:-per_window] if len(rows) >= 2 * per_window else []
    start_price = window[0][0]
    end_price = window[-1][3]
    trs = []
    for i in range(1, len(rows)):
        high, low, prev_close = rows[i][1], rows[i][2], rows[i - 1][3]
        trs.append(max(high - low, abs(high - prev_close), abs(low - prev_close)))
    atr = sum(trs[-ATR_PERIOD:]) / min(len(trs), ATR_PERIOD)
    volume = sum(r[4] for r in window)
    prior_volume = sum(r[4] for r in prior)
    return {
        "price_start": start_price,
        "price_end": end_price,
        "price_change_pct": round((end_price - start_price) / start_price * 100, 3) if start_price else None,
        "high": max(r[1] for r in window),
        "low": min(r[2] for r in window),
        "quote_volume": round(volume, 2),
        "volume_vs_prior_window": round(volume / prior_volume, 2) if prior_volume else None,
        "atr_pct": round(atr / end_price * 100, 3) if end_price else None,
    }


def oi_numbers(rows: list[dict], points: int) -> dict | None:
    values = [float(r["sumOpenInterestValue"]) for r in rows if r.get("sumOpenInterestValue") not in (None, "")]
    if len(values) < 2:
        return None
    values = values[-(points + 1):]
    first, last = values[0], values[-1]
    return {"oi_usd_start": round(first, 2), "oi_usd_end": round(last, 2),
            "oi_change_pct": round((last - first) / first * 100, 3) if first else None}


def direction(change_pct: float | None, flat_below: float) -> str:
    if change_pct is None:
        return "unknown"
    if abs(change_pct) < flat_below:
        return "flat"
    return "up" if change_pct > 0 else "down"


def scenarios(dom: str, price_dir: str, oi_dir: str, funding: float | None, total_usd: float,
              min_usd: float) -> list[dict]:
    """Rule table: which explanations fit the observed combination. Several may apply."""
    caveat = "Liquidations show which leveraged positions were closed; they don't decide what price does next."
    if total_usd < min_usd or dom == "none":
        return [{"name": "No notable liquidation pressure",
                 "description": "Observed liquidation value in this window is small.",
                 "supporting": [f"observed total below {min_usd:,.0f} USD"], "contradicting": [], "caveat": caveat}]
    out = []
    if dom == "long":
        sup = ["long liquidations (forced sells) dominate"]
        con = []
        (sup if price_dir == "down" else con).append(f"price is {price_dir}")
        if oi_dir == "down":
            out.append({"name": "Long deleveraging",
                        "description": "Leveraged longs are being closed out and open interest is falling, "
                                       "so positions are leaving the market rather than new ones opening.",
                        "supporting": sup + ["open interest falling"], "contradicting": con, "caveat": caveat})
        elif oi_dir == "up":
            out.append({"name": "Longs liquidated while new positions open",
                        "description": "Longs are being liquidated but open interest is rising: new positions "
                                       "(often shorts) are being added during the move.",
                        "supporting": sup + ["open interest rising"], "contradicting": con, "caveat": caveat})
        else:
            out.append({"name": "Long liquidations", "description": "Leveraged longs are being closed out.",
                        "supporting": sup, "contradicting": con + [f"open interest {oi_dir}"], "caveat": caveat})
        if funding is not None and funding > 0.0003:
            out[-1]["supporting"].append("funding was strongly positive (crowded longs)")
    elif dom == "short":
        sup = ["short liquidations (forced buys) dominate"]
        con = []
        (sup if price_dir == "up" else con).append(f"price is {price_dir}")
        if oi_dir == "down":
            out.append({"name": "Short squeeze / short deleveraging",
                        "description": "Leveraged shorts are being closed out and open interest is falling.",
                        "supporting": sup + ["open interest falling"], "contradicting": con, "caveat": caveat})
        elif oi_dir == "up":
            out.append({"name": "Shorts liquidated while new positions open",
                        "description": "Shorts are being liquidated but open interest is rising: new positions "
                                       "(often longs) are being added during the move.",
                        "supporting": sup + ["open interest rising"], "contradicting": con, "caveat": caveat})
        else:
            out.append({"name": "Short liquidations", "description": "Leveraged shorts are being closed out.",
                        "supporting": sup, "contradicting": con + [f"open interest {oi_dir}"], "caveat": caveat})
        if funding is not None and funding < -0.0001:
            out[-1]["supporting"].append("funding was negative (crowded shorts)")
    else:
        out.append({"name": "Two-sided leverage flush",
                    "description": "Longs and shorts are both being liquidated, typical of a choppy, volatile market.",
                    "supporting": ["long and short liquidations are similar in size"],
                    "contradicting": [f"price is {price_dir}"] if price_dir in ("up", "down") else [],
                    "caveat": caveat})
    return out


async def _safe(coro, label: str, missing: list[str]):
    try:
        return await coro
    except Exception as exc:
        log.warning("context input %s unavailable: %s", label, exc.__class__.__name__)
        missing.append(label)
        return None


async def build(symbol: str, window: str, long_usd: float, short_usd: float) -> dict:
    if window not in PLAN:
        raise ValueError(f"window must be one of {', '.join(PLAN)}")
    symbol = symbol.upper()
    interval, per_window, oi_period, oi_points = PLAN[window]
    missing: list[str] = []
    candles, oi_rows, funding_rows = await asyncio.gather(
        _safe(binance.futures_klines(symbol, interval, max(2 * per_window, per_window + ATR_PERIOD + 1)),
              "price_volume", missing),
        _safe(binance.open_interest_hist(symbol, oi_period, oi_points + 1), "open_interest", missing),
        _safe(binance.funding_rates(symbol, 1), "funding", missing),
    )
    market = market_numbers(candles, per_window) if candles else None
    oi = oi_numbers(oi_rows, oi_points) if oi_rows else None
    funding = float(funding_rows[-1]["fundingRate"]) if funding_rows else None
    if candles and market is None:
        missing.append("price_volume")

    flat_below = (market or {}).get("atr_pct") or 0.3
    price_dir = direction((market or {}).get("price_change_pct"), flat_below)
    oi_dir = direction((oi or {}).get("oi_change_pct"), 0.5)
    dom = dominance(long_usd, short_usd)
    return {
        "symbol": symbol,
        "window": window,
        "liquidations": {"long_usd": round(long_usd, 2), "short_usd": round(short_usd, 2), "dominance": dom,
                         "source": "observed_binance_stream"},
        "market": market,
        "open_interest": oi,
        "funding_rate": funding,
        "price_direction": price_dir,
        "open_interest_direction": oi_dir,
        "flat_threshold_pct": round(flat_below, 3),
        "support_resistance": None,  # added by the Support & Resistance engine (phase 2)
        "unavailable": sorted(set(missing)),
        "scenarios": scenarios(dom, price_dir, oi_dir, funding, long_usd + short_usd,
                               settings.liq_spike_min_usd / 5),
        "market_source": "binance_usdm_futures_public_api",
    }
