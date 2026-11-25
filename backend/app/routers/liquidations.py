"""Liquidation intelligence: statistics, timeline, anomalies, market context and explanations.

All figures come from OBSERVED Binance forceOrder stream events (see services/liquidations.py).
The original 1h snapshot endpoint GET /api/liquidations (routers/discover.py) is unchanged.
"""
import asyncio

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from ..database import get_db
from ..services import explainer, liquidation_anomaly, liquidation_context, liquidation_explain
from ..services import liquidation_stats, liquidations

router = APIRouter(prefix="/api/liquidations", tags=["Liquidation Intelligence"])

WINDOW = Query("1h", pattern="^(5m|15m|1h|4h|24h)$")
SYMBOL = Query(None, pattern="^[A-Za-z0-9]{2,30}$")
GROUP = Query(None, pattern="^(other)$")


@router.get("/status")
def stream_status():
    """Connection health, counters, reconnects and the Binance data limitation."""
    return liquidations.stream_status()


@router.get("/stats")
async def stats(window: str = WINDOW, symbol: str | None = SYMBOL, group: str | None = GROUP,
                db: Session = Depends(get_db)):
    """Totals, long/short split and ratio, largest events, most affected coin, by-coin table,
    recent events, timeline and how much of the window was actually observed."""
    return await asyncio.to_thread(liquidation_stats.window_stats, db, window, symbol, group)


@router.get("/timeline")
async def timeline(window: str = WINDOW, symbol: str | None = SYMBOL, group: str | None = GROUP,
                   db: Session = Depends(get_db)):
    points = await asyncio.to_thread(liquidation_stats.timeline, db, window, symbol, group)
    return {"source": liquidation_stats.SOURCE, "window": window,
            "bucket_seconds": liquidation_stats.BUCKET_SECONDS[window], "points": points}


@router.get("/history")
async def history(symbol: str | None = SYMBOL, before_ms: int | None = Query(None, gt=0),
                  limit: int = Query(100, ge=1, le=500), min_usd: float = Query(0, ge=0),
                  db: Session = Depends(get_db)):
    items = await asyncio.to_thread(liquidation_stats.history, db, symbol, before_ms, limit, min_usd)
    return {"source": liquidation_stats.SOURCE, "items": items,
            "next_before_ms": items[-1]["time"] if len(items) == limit else None}


@router.get("/anomalies")
async def anomalies(symbol: str | None = SYMBOL, db: Session = Depends(get_db)):
    return await asyncio.to_thread(liquidation_anomaly.detect, db, symbol)


async def _context(symbol: str, window: str, db: Session) -> dict:
    if window == "5m":
        window = "15m"  # the shortest window with enough candles for context
    data = await asyncio.to_thread(liquidation_stats.window_stats, db, window, symbol, None)
    return await liquidation_context.build(symbol, window, data["summary"]["long_usd"], data["summary"]["short_usd"])


@router.get("/context/{symbol}")
async def context(symbol: str, window: str = WINDOW, db: Session = Depends(get_db)):
    """Liquidations next to price, volume, open interest, funding and ATR, with possible scenarios."""
    if not symbol.isalnum() or len(symbol) > 30:
        raise HTTPException(422, "Invalid symbol.")
    return await _context(symbol, window, db)


@router.get("/explain")
async def explain(window: str = WINDOW, symbol: str | None = SYMBOL, db: Session = Depends(get_db)):
    """Answers the six panel questions from verified data. An LLM may phrase the answer only if every
    number it writes matches the data; otherwise the rules-based answer is returned."""
    stats_data = await asyncio.to_thread(liquidation_stats.window_stats, db, window, symbol, None)
    anomaly_data = await asyncio.to_thread(liquidation_anomaly.detect, db, symbol)
    focus = symbol or (stats_data.get("most_affected") or {}).get("symbol")
    ctx = await _context(focus, window, db) if focus else None
    facts = liquidation_explain.build_facts(stats_data, anomaly_data, ctx)
    answers = liquidation_explain.rules_answers(facts)
    result = await explainer.explain(facts, liquidation_explain.QUESTIONS, liquidation_explain.rules_text(answers))
    return {**result, "answers": answers, "facts": facts, "context": ctx}
