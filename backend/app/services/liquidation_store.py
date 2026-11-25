"""Persists observed liquidation events so 4h/24h statistics and baselines survive restarts.

store_loop() runs in the background: every FLUSH_SECONDS it writes the stream's pending buffer
to the liquidation_events table (skipping duplicates by event_key) and once an hour deletes rows
older than LIQUIDATION_RETENTION_DAYS.
"""
import asyncio
import logging
import time

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session, sessionmaker

from ..config import settings
from ..database import SessionLocal
from ..models import LiquidationEvent
from . import liquidations

log = logging.getLogger("cryptosense.liquidation_store")

FLUSH_SECONDS = 3
PRUNE_SECONDS = 3600
_last_flush_at: float | None = None
_stored_total = 0


def to_row(event: dict) -> LiquidationEvent:
    return LiquidationEvent(
        event_key=event["id"][:120],
        symbol=event["symbol"],
        side=event["side"].upper(),
        position=event["position"],
        order_type=event.get("order_type", ""),
        status=event.get("status", ""),
        quantity=event.get("quantity", 0.0),
        filled_qty=event.get("filled_qty", 0.0),
        price=event.get("order_price", event["price"]),
        avg_price=event.get("avg_price", event["price"]),
        usd=event["usd"],
        usd_valid=bool(event.get("usd_valid", event["usd"] > 0)),
        event_ms=int(event["time"]),
        bucket_5m=int(event["time"]) // 300_000,
        received_ms=int(float(event["received_at"]) * 1000),
    )


def store_events(db: Session, events: list[dict]) -> int:
    """Insert events not already stored. Returns the number inserted."""
    if not events:
        return 0
    unique = {e["id"][:120]: e for e in events}
    existing = set(db.scalars(
        select(LiquidationEvent.event_key).where(LiquidationEvent.event_key.in_(list(unique)))
    ))
    rows = [to_row(e) for key, e in unique.items() if key not in existing]
    db.add_all(rows)
    db.commit()
    return len(rows)


def prune(db: Session, now_ms: int | None = None) -> int:
    now_ms = now_ms or int(time.time() * 1000)
    cutoff = now_ms - settings.liquidation_retention_days * 86_400_000
    result = db.execute(delete(LiquidationEvent).where(LiquidationEvent.event_ms < cutoff))
    db.commit()
    return result.rowcount or 0


def earliest_event_ms(db: Session) -> int | None:
    return db.scalar(select(func.min(LiquidationEvent.event_ms)))


def last_flush_at() -> float | None:
    return _last_flush_at


def _flush(factory: sessionmaker, batch: list[dict]) -> int:
    with factory() as db:
        return store_events(db, batch)


async def store_loop(factory: sessionmaker = SessionLocal) -> None:
    global _last_flush_at, _stored_total
    last_prune = 0.0
    while True:
        batch = liquidations.take_pending()
        try:
            if batch:
                _stored_total += await asyncio.to_thread(_flush, factory, batch)
            _last_flush_at = time.time()
            if time.time() - last_prune > PRUNE_SECONDS:
                with factory() as db:
                    removed = await asyncio.to_thread(prune, db)
                if removed:
                    log.info("pruned %s old liquidation events", removed)
                last_prune = time.time()
        except Exception as exc:
            # Keep the events for the next attempt rather than silently dropping them.
            liquidations._pending[:0] = batch[-20000:]
            log.warning("liquidation store failed: %s", exc)
        await asyncio.sleep(FLUSH_SECONDS)
