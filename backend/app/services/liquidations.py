"""Binance USD-M futures liquidation stream (all-market forceOrder).

Data limitation (Binance docs): "For each symbol, only the latest one liquidation order within
1000ms will be pushed as the snapshot." Events here are therefore OBSERVED stream snapshots, a
sample of liquidation activity, never exchange-wide totals.

Flow: websocket -> ingest() / parse_message() validate and normalise -> in-memory 1h window
(fast path for /api/liquidations and Telegram) + a pending buffer that
liquidation_store.store_loop() writes to the liquidation_events table for 4h/24h statistics.
If the stream is unreachable, silent or disconnected the API says so; no demo events are made.
"""
import asyncio
import json
import logging
import time
from collections import deque

import websockets

from ..config import settings

log = logging.getLogger("cryptosense.liquidations")

STREAM_URL = settings.liquidation_stream_url
WINDOW_SECONDS = 3600
MAX_EVENTS = 20000
MAX_PENDING = 100_000
STABLE_QUOTES = ("USDT", "USDC", "FDUSD")
LIMITATION = ("Binance pushes at most one liquidation per symbol per second (the latest one). "
              "Figures are observed stream events, not exchange-wide liquidation totals.")

_events: deque[dict] = deque(maxlen=MAX_EVENTS)
_pending: list[dict] = []
_seen_keys: deque[str] = deque(maxlen=50000)
_seen_set: set[str] = set()
_connected = False
_last_event_at: float | None = None
_last_message_at: float | None = None
_last_error: str | None = None
_started_at = time.time()
_reconnects = 0
_gaps: deque[list] = deque(maxlen=500)   # [disconnected_at, reconnected_at | None]
_stats = {"received": 0, "invalid": 0, "duplicates": 0}


def _num(value) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def parse_message(message) -> list[dict]:
    """Validate and normalise one stream message into zero or more liquidation events.

    Accepts the raw form {"e": "forceOrder", "o": {...}}, the combined-stream form
    {"stream": ..., "data": {...}}, or a list of either. Invalid records are skipped.

    Long liquidation = forced SELL order; short liquidation = forced BUY order. The order side
    says which positions were closed, not where the market is heading.
    USD value = accumulated filled quantity (z) x average price (ap). It is only marked valid for
    USD-M symbols (st=1) quoted in a stablecoin with a positive fill; otherwise usd = 0.
    """
    if isinstance(message, list):
        return [e for m in message for e in parse_message(m)]
    if not isinstance(message, dict):
        return []
    if isinstance(message.get("data"), (dict, list)):
        return parse_message(message["data"])
    order = message.get("o")
    if not isinstance(order, dict):
        return []
    symbol = str(order.get("s") or "").upper()
    side = str(order.get("S") or "").upper()
    if not symbol or side not in ("BUY", "SELL"):
        return []
    quantity = _num(order.get("q"))
    filled = _num(order.get("z")) or _num(order.get("l"))
    order_price = _num(order.get("p"))
    avg_price = _num(order.get("ap"))
    price = avg_price or order_price
    try:
        event_ms = int(order.get("T") or message.get("E"))
    except (TypeError, ValueError):
        return []
    if price <= 0 or (filled <= 0 and quantity <= 0) or event_ms <= 0:
        return []
    symbol_type = str(order.get("st", message.get("st", 1)))
    usd_valid = filled > 0 and avg_price > 0 and symbol_type == "1" and symbol.endswith(STABLE_QUOTES)
    return [{
        "id": f"{symbol}-{event_ms}-{side}-{filled or quantity}-{price}",
        "symbol": symbol,
        "side": side.lower(),
        "position": "long" if side == "SELL" else "short",
        "order_type": str(order.get("o") or ""),
        "status": str(order.get("X") or ""),
        "quantity": quantity,
        "filled_qty": filled,
        "order_price": order_price,
        "avg_price": avg_price,
        "price": price,
        "usd": filled * avg_price if usd_valid else 0.0,
        "usd_valid": usd_valid,
        "time": event_ms,
        "received_at": time.time(),
    }]


def _is_duplicate(key: str) -> bool:
    if key in _seen_set:
        return True
    if len(_seen_keys) == _seen_keys.maxlen:
        _seen_set.discard(_seen_keys[0])
    _seen_keys.append(key)
    _seen_set.add(key)
    return False


def ingest(raw) -> int:
    """Process one raw websocket payload. Returns how many new events were kept."""
    global _last_event_at, _last_message_at
    _last_message_at = time.time()
    _stats["received"] += 1
    try:
        message = json.loads(raw) if isinstance(raw, (str, bytes)) else raw
    except json.JSONDecodeError:
        _stats["invalid"] += 1
        return 0
    events = parse_message(message)
    if not events:
        _stats["invalid"] += 1
        return 0
    kept = 0
    for event in events:
        if _is_duplicate(event["id"]):
            _stats["duplicates"] += 1
            continue
        _events.append(event)
        _pending.append(event)
        if len(_pending) > MAX_PENDING:  # database unreachable for a long time: drop the oldest
            del _pending[: len(_pending) - MAX_PENDING]
        _last_event_at = time.time()
        kept += 1
    _cleanup()
    return kept


def _cleanup() -> None:
    cutoff = time.time() - WINDOW_SECONDS
    while _events and float(_events[0]["received_at"]) < cutoff:
        _events.popleft()


def _mark_disconnected(error: str) -> None:
    global _connected, _last_error
    if not _gaps or _gaps[-1][1] is not None:
        _gaps.append([time.time(), None])
    _connected = False
    _last_error = error


def _mark_connected() -> None:
    global _connected, _last_error, _reconnects
    if _gaps and _gaps[-1][1] is None:
        _gaps[-1][1] = time.time()
        _reconnects += 1
    _connected = True
    _last_error = None


async def liquidation_loop() -> None:
    """Keep the websocket open; reconnect on errors or when no message arrives for
    LIQUIDATION_SILENCE_SECONDS (a connection that is open but silent is treated as broken)."""
    global _last_message_at
    while True:
        try:
            async with websockets.connect(
                STREAM_URL, ping_interval=20, ping_timeout=10, open_timeout=12, close_timeout=5,
            ) as ws:
                _mark_connected()
                _last_message_at = time.time()
                while True:
                    try:
                        raw = await asyncio.wait_for(ws.recv(), timeout=settings.liquidation_silence_seconds)
                    except asyncio.TimeoutError:
                        raise ConnectionError(
                            f"no messages for {settings.liquidation_silence_seconds}s") from None
                    ingest(raw)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            _mark_disconnected(f"{exc.__class__.__name__}: {exc}")
            log.warning("liquidation stream disconnected: %s", _last_error)
            await asyncio.sleep(5)


def take_pending() -> list[dict]:
    """Hand the not-yet-stored events to the store (and clear the buffer)."""
    batch = list(_pending)
    _pending.clear()
    return batch


def gaps_between(start: float, end: float) -> float:
    """Seconds the stream was disconnected inside [start, end]. Only known since backend start."""
    total = 0.0
    for down, up in _gaps:
        lo, hi = max(down, start), min(up if up is not None else end, end)
        if hi > lo:
            total += hi - lo
    return total


def stream_status() -> dict:
    now = time.time()
    return {
        "source": "binance_forceorder_stream",
        "connected": _connected,
        "url": STREAM_URL,
        "last_message_at": _last_message_at,
        "last_event_at": _last_event_at,
        "seconds_since_last_message": round(now - _last_message_at, 1) if _last_message_at else None,
        "error": _last_error,
        "backend_started_at": _started_at,
        "reconnects": _reconnects,
        "disconnected_seconds_since_start": round(gaps_between(_started_at, now), 1),
        "counters": dict(_stats),
        "limitation": LIMITATION,
    }


# ------------------------------------------------------- 1h in-memory snapshot (existing API)
TIMEFRAMES = {"5m": 300, "15m": 900, "1h": 3600}


def _totals(events: list[dict]) -> dict:
    long_usd = sum(e["usd"] for e in events if e["position"] == "long")
    short_usd = sum(e["usd"] for e in events if e["position"] == "short")
    return {
        "long_liquidations_usd": round(long_usd, 2),
        "short_liquidations_usd": round(short_usd, 2),
        "total_usd": round(long_usd + short_usd, 2),
        "event_count": len(events),
    }


def describe_balance(long_usd: float, short_usd: float, window: str = "the last hour") -> str:
    """Neutral description of which side is being liquidated. Never predicts direction."""
    total = long_usd + short_usd
    if total == 0:
        return f"No observed Binance futures liquidations in {window}."
    if long_usd > short_usd * 1.5:
        return (f"Observed liquidations in {window} are mostly longs (forced sells): leveraged buyers "
                "were closed out, which usually happens while price is falling.")
    if short_usd > long_usd * 1.5:
        return (f"Observed liquidations in {window} are mostly shorts (forced buys): leveraged sellers "
                "were closed out, which usually happens while price is rising.")
    return f"Observed long and short liquidations in {window} are roughly balanced."


def snapshot(limit: int = 100, symbol: str | None = None) -> dict:
    """Recent events (newest first) plus totals over the full rolling 1h window.

    Totals cover every retained event in the window, not just the returned `items`.
    """
    _cleanup()
    events = list(reversed(list(_events)))
    if symbol:
        symbol = symbol.upper()
        events = [e for e in events if e["symbol"] == symbol]
    now = time.time()
    summary = _totals(events)

    by_symbol: dict[str, list[dict]] = {}
    for e in events:
        by_symbol.setdefault(e["symbol"], []).append(e)
    top_symbols = sorted(
        ({"symbol": sym, **_totals(evts)} for sym, evts in by_symbol.items()),
        key=lambda row: row["total_usd"], reverse=True,
    )[:10]
    largest = max(events, key=lambda e: e["usd"], default=None)

    return {
        "source": "binance" if _connected else "unavailable",
        "connected": _connected,
        "window_seconds": WINDOW_SECONDS,
        "last_event_at": _last_event_at,
        "error": _last_error,
        "symbol": symbol,
        "limitation": LIMITATION,
        "items": events[:limit],
        "summary": {
            **summary,
            "read": describe_balance(summary["long_liquidations_usd"], summary["short_liquidations_usd"]),
        },
        "timeframes": {
            name: _totals([e for e in events if float(e["received_at"]) >= now - seconds])
            for name, seconds in TIMEFRAMES.items()
        },
        "top_symbols": top_symbols,
        "largest": largest,
    }
