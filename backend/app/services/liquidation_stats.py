"""Time-window statistics over stored, observed Binance liquidation events.

Every number is computed from the liquidation_events table (observed forceOrder stream
snapshots). Nothing is extrapolated to exchange-wide totals. Sums use only events whose USD
value is valid (see liquidations.parse_message); other events are counted separately.
"""
import time

from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from ..models import LiquidationEvent as L
from . import liquidations
from .liquidation_store import earliest_event_ms, last_flush_at

WINDOWS = {"5m": 300, "15m": 900, "1h": 3600, "4h": 14_400, "24h": 86_400}
BUCKET_SECONDS = {"5m": 15, "15m": 30, "1h": 120, "4h": 600, "24h": 3600}
MAJORS = ("BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT")
SOURCE = "observed_binance_stream"


def _filters(start_ms: int, end_ms: int, symbol: str | None, group: str | None) -> list:
    conds = [L.event_ms >= start_ms, L.event_ms <= end_ms]
    if symbol:
        conds.append(L.symbol == symbol.upper())
    elif group == "other":
        conds.append(L.symbol.not_in(MAJORS))
    return conds


def _usd(position: str):
    return func.coalesce(func.sum(case((L.position == position, L.usd), else_=0.0)), 0.0)


def _count(position: str):
    return func.coalesce(func.sum(case((L.position == position, 1), else_=0)), 0)


def _event(row: L) -> dict:
    return {
        "id": row.event_key, "symbol": row.symbol, "side": row.side.lower(), "position": row.position,
        "order_type": row.order_type, "status": row.status, "quantity": row.quantity,
        "filled_qty": row.filled_qty, "order_price": row.price, "avg_price": row.avg_price,
        "price": row.avg_price or row.price, "usd": round(row.usd, 2), "usd_valid": row.usd_valid,
        "time": row.event_ms,
    }


def totals(long_usd: float, short_usd: float, long_n: int, short_n: int, invalid_n: int) -> dict:
    total = long_usd + short_usd
    return {
        "long_usd": round(long_usd, 2),
        "short_usd": round(short_usd, 2),
        "total_usd": round(total, 2),
        "long_count": int(long_n),
        "short_count": int(short_n),
        "event_count": int(long_n + short_n),
        "events_without_valid_usd": int(invalid_n),
        "long_short_ratio": round(long_usd / short_usd, 3) if short_usd > 0 else None,
        "long_share_pct": round(long_usd / total * 100, 1) if total > 0 else None,
    }


def coverage(db: Session, start_ms: int, end_ms: int) -> dict:
    """How much of the window was actually observed. Disconnects before this backend started
    are unknown, so a window reaching back before the start is never reported as complete."""
    status = liquidations.stream_status()
    earliest = earliest_event_ms(db)
    started_ms = int(status["backend_started_at"] * 1000)
    down = liquidations.gaps_between(max(start_ms, started_ms) / 1000, end_ms / 1000)
    complete = start_ms >= started_ms and down == 0 and status["connected"]
    observed_from = max(start_ms, earliest) if earliest else None
    if earliest is None:
        note = "No liquidation events stored yet."
    elif complete:
        note = "The stream was connected for the whole window."
    elif start_ms < started_ms:
        note = ("Part of this window is before the current backend started; stored history may have "
                "gaps from earlier restarts or disconnects.")
    else:
        note = f"The stream was disconnected for {down:.0f}s inside this window."
    return {
        "observed_from_ms": observed_from,
        "backend_started_at_ms": started_ms,
        "disconnected_seconds": round(down, 1),
        "window_fully_observed": complete,
        "note": note,
    }


def window_stats(db: Session, window: str = "1h", symbol: str | None = None, group: str | None = None,
                 now_ms: int | None = None) -> dict:
    if window not in WINDOWS:
        raise ValueError(f"window must be one of {', '.join(WINDOWS)}")
    end_ms = now_ms or int(time.time() * 1000)
    start_ms = end_ms - WINDOWS[window] * 1000
    conds = _filters(start_ms, end_ms, symbol, group)

    row = db.execute(select(_usd("long"), _usd("short"), _count("long"), _count("short"),
                            func.coalesce(func.sum(case((L.usd_valid.is_(False), 1), else_=0)), 0))
                     .where(*conds)).one()
    summary = totals(*row)

    by_symbol_rows = db.execute(
        select(L.symbol, _usd("long"), _usd("short"), _count("long"), _count("short"))
        .where(*conds).group_by(L.symbol)
        .order_by((_usd("long") + _usd("short")).desc()).limit(15)
    ).all()
    by_symbol = [{"symbol": r[0], **totals(r[1], r[2], r[3], r[4], 0)} for r in by_symbol_rows]

    largest = [_event(r) for r in db.scalars(
        select(L).where(*conds, L.usd_valid.is_(True)).order_by(L.usd.desc()).limit(10))]
    recent = [_event(r) for r in db.scalars(select(L).where(*conds).order_by(L.event_ms.desc()).limit(30))]

    return {
        "source": SOURCE,
        "window": window,
        "symbol": symbol.upper() if symbol else None,
        "group": group,
        "from_ms": start_ms,
        "to_ms": end_ms,
        "as_of": last_flush_at(),
        "summary": {**summary, "read": liquidations.describe_balance(
            summary["long_usd"], summary["short_usd"], f"the last {window}")},
        "largest": largest,
        "most_affected": by_symbol[0] if by_symbol else None,
        "by_symbol": by_symbol,
        "recent": recent,
        "timeline": timeline(db, window, symbol, group, end_ms),
        "coverage": coverage(db, start_ms, end_ms),
        "stream": liquidations.stream_status(),
    }


def timeline(db: Session, window: str = "1h", symbol: str | None = None, group: str | None = None,
             now_ms: int | None = None) -> list[dict]:
    """Zero-filled long/short USD per bucket, oldest first, aligned to UTC bucket boundaries."""
    end_ms = now_ms or int(time.time() * 1000)
    start_ms = end_ms - WINDOWS[window] * 1000
    size = BUCKET_SECONDS[window] * 1000
    bucket = (L.event_ms // size).label("b")
    rows = db.execute(
        select(bucket, _usd("long"), _usd("short"), func.count())
        .where(*_filters(start_ms, end_ms, symbol, group)).group_by(bucket)
    ).all()
    by_bucket = {int(r[0]): r for r in rows}
    out = []
    for b in range(start_ms // size, end_ms // size + 1):
        r = by_bucket.get(b)
        out.append({
            "t_ms": b * size,
            "long_usd": round(r[1], 2) if r else 0.0,
            "short_usd": round(r[2], 2) if r else 0.0,
            "count": int(r[3]) if r else 0,
        })
    return out


def history(db: Session, symbol: str | None = None, before_ms: int | None = None, limit: int = 100,
            min_usd: float = 0) -> list[dict]:
    """Stored events, newest first, for paging back through history."""
    conds = []
    if symbol:
        conds.append(L.symbol == symbol.upper())
    if before_ms:
        conds.append(L.event_ms < before_ms)
    if min_usd:
        conds.append(L.usd >= min_usd)
    return [_event(r) for r in db.scalars(select(L).where(*conds).order_by(L.event_ms.desc()).limit(limit))]
