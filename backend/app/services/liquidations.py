"""Binance public futures liquidation stream.

Liquidation history is not retained by this stream. Events received after the
backend starts are kept in memory for a rolling window. If the stream is
unreachable or disconnected, the API reports an unavailable status and never
falls back to fabricated demo liquidation events.
"""
import asyncio
import json
import logging
import time
from collections import deque

import websockets

log = logging.getLogger("cryptosense.liquidations")

STREAM_URL = "wss://fstream.binance.com/ws/!forceOrder@arr"
WINDOW_SECONDS = 3600
MAX_EVENTS = 5000

_events: deque[dict] = deque(maxlen=MAX_EVENTS)
_connected = False
_last_event_at: float | None = None
_last_error: str | None = None


def _cleanup() -> None:
    cutoff = time.time() - WINDOW_SECONDS
    while _events and float(_events[0]["received_at"]) < cutoff:
        _events.popleft()


async def liquidation_loop() -> None:
    global _connected, _last_error
    while True:
        try:
            async with websockets.connect(
                STREAM_URL,
                ping_interval=20,
                ping_timeout=10,
                open_timeout=12,
                close_timeout=5,
            ) as ws:
                _connected = True
                _last_error = None
                async for raw in ws:
                    try:
                        message = json.loads(raw)
                        order = message.get("o")
                        if not order:
                            continue
                        symbol = str(order.get("s") or "").upper()
                        if not symbol:
                            continue
                        quantity = float(order.get("z") or 0)
                        price = float(order.get("ap") or order.get("p") or 0)
                        usd = quantity * price
                        event_time = int(order.get("T") or message.get("E") or time.time() * 1000)
                        side = str(order.get("S") or "").upper()
                        global _last_event_at
                        _last_event_at = time.time()
                        _events.append({
                            "id": f"{symbol}-{event_time}-{quantity}-{price}",
                            "symbol": symbol,
                            "side": "sell" if side == "SELL" else "buy",
                            "position": "long" if side == "SELL" else "short",
                            "quantity": quantity,
                            "price": price,
                            "usd": usd,
                            "time": event_time,
                            "received_at": time.time(),
                        })
                        _cleanup()
                    except (KeyError, TypeError, ValueError, json.JSONDecodeError):
                        continue
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            _connected = False
            _last_error = f"{exc.__class__.__name__}: {exc}"
            log.warning("liquidation stream disconnected: %s", _last_error)
            await asyncio.sleep(5)


def snapshot(limit: int = 100) -> dict:
    _cleanup()
    items = list(reversed(list(_events)))[:limit]
    sell_usd = sum(i["usd"] for i in items if i["position"] == "long")
    buy_usd = sum(i["usd"] for i in items if i["position"] == "short")
    return {
        "source": "binance" if _connected else "unavailable",
        "connected": _connected,
        "window_seconds": WINDOW_SECONDS,
        "last_event_at": _last_event_at,
        "error": _last_error,
        "items": items,
        "summary": {
            "long_liquidations_usd": round(sell_usd, 2),
            "short_liquidations_usd": round(buy_usd, 2),
            "event_count": len(items),
        },
    }
