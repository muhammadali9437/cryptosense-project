"""Live prices for the tracked coins (cached a few seconds).

If Binance can't be reached the result is empty: no made-up prices are returned.
"""
import logging

from ..config import settings
from . import binance
from .cache import cached

NAMES = {
    "BTCUSDT": "Bitcoin", "ETHUSDT": "Ethereum", "BNBUSDT": "BNB",
    "SOLUSDT": "Solana", "XRPUSDT": "XRP", "ADAUSDT": "Cardano",
}


async def prices() -> dict[str, dict]:
    """{symbol: ticker} for every tracked coin. Adds live=True/False."""
    async def build():
        try:
            rows = await binance.tickers(settings.symbol_list)
            return {r["symbol"]: {**binance.simple_ticker(r), "live": True} for r in rows}
        except Exception as exc:
            logging.getLogger("cryptosense.market").warning("Binance prices unavailable: %s", exc.__class__.__name__)
            return {}
    return await cached("prices", 5, build)


async def price_of(symbol: str) -> float | None:
    p = (await prices()).get(symbol)
    if p:
        return p["price"]
    try:
        rows = await binance.tickers([symbol])
        return float(rows[0]["lastPrice"])
    except Exception:
        return None
