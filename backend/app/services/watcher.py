"""Background jobs:
- every ALERT_CHECK_SECONDS: check price/risk alerts and P&L limits, write notifications
- every NEWS_INGEST_MINUTES: fetch news (with FinBERT sentiment) and add it to the RAG knowledge base
- every LISTINGS_REFRESH_HOURS: refresh new Binance listings
"""
import asyncio
import logging
import time
from collections import deque
from datetime import datetime, timezone

from sqlalchemy import select

from ..config import settings
from ..database import SessionLocal
from ..models import Alert, Holding, Notification
from . import listings, liquidations, whales
from .market import prices
from .news import latest_news
from .rag import kb
from . import risk as risk_engine
from .signals import all_signals
from .telegram import send_alert as send_telegram_alert

log = logging.getLogger("cryptosense.watcher")
_external_alert_ids: deque[str] = deque(maxlen=5000)
_external_alert_id_set: set[str] = set()


def _remember_external_alert(event_id: str) -> None:
    if len(_external_alert_ids) == _external_alert_ids.maxlen:
        _external_alert_id_set.discard(_external_alert_ids[0])
    _external_alert_ids.append(event_id)
    _external_alert_id_set.add(event_id)


async def _external_alert_messages() -> list[tuple[str, str]]:
    messages = []
    now = time.time()
    liquidation_data = liquidations.snapshot(500)
    if liquidation_data["connected"]:
        for event in liquidation_data["items"]:
            symbol = event["symbol"]
            if (symbol not in settings.symbol_list
                    or event["usd"] < settings.liquidation_alert_usd
                    or now - float(event["received_at"]) > settings.alert_check_seconds * 2
                    or f"liquidation:{event['id']}" in _external_alert_id_set):
                continue
            messages.append((
                f"liquidation:{event['id']}",
                f"Liquidation alert: ${event['usd']:,.0f} {event['position']} liquidation "
                f"on {symbol} at ${event['price']:,.4f}.",
            ))

    if settings.whale_alert_key:
        try:
            whale_data = await whales.latest_whales()
        except Exception as exc:
            log.warning("Whale Alert check failed (%s).", exc.__class__.__name__)
            whale_data = {"source": "unavailable", "items": []}
        if whale_data["source"] == "whale_alert":
            for event in whale_data["items"]:
                try:
                    event_time = datetime.fromisoformat(event["time"].replace("Z", "+00:00")).timestamp()
                except (KeyError, TypeError, ValueError):
                    continue
                event_id = str(event.get("id") or "")
                if (not event_id or event["usd"] < settings.whale_min_usd
                        or now - event_time > settings.alert_check_seconds * 2
                        or f"whale:{event_id}" in _external_alert_id_set):
                    continue
                messages.append((
                    f"whale:{event_id}",
                    f"Whale Alert: {event['amount']:,.4g} {event['coin']} "
                    f"(${event['usd']:,.0f}) moved from {event['from']} to {event['to']}.",
                ))
    return messages


def _describe(a: Alert) -> str:
    base = a.symbol.replace("USDT", "")
    if a.kind == "risk":
        return f"{base} risk reached {a.value:.0f}%"
    return {
        "above": f"{base} rose above ${a.value:,.2f}",
        "below": f"{base} fell below ${a.value:,.2f}",
        "move": f"{base} moved more than {a.value:.0f}% in 24h",
    }[a.kind]


async def check_once() -> int:
    """Evaluate every active alert and limit once. Returns notifications created."""
    tickers = await prices()
    live_prices = any(t.get("live") for t in tickers.values())
    created = 0
    telegram_messages = []
    risk_by_symbol = {}
    if live_prices:
        with SessionLocal() as db:
            has_risk_alerts = db.scalar(
                select(Alert.id).where(Alert.active.is_(True), Alert.kind == "risk").limit(1)
            ) is not None
        if has_risk_alerts:
            try:
                signals = await all_signals()
                risk_by_symbol = {s["symbol"]: risk_engine.score_from(s) for s in signals if s.get("live")}
            except Exception as exc:
                log.warning("risk alert check failed: %s", exc)

        with SessionLocal() as db:
            active_alerts = db.scalars(select(Alert).where(Alert.active.is_(True))).all()
            for a in active_alerts:
                if a.kind == "risk":
                    risk = risk_by_symbol.get(a.symbol)
                    if risk is None or risk["risk_pct"] < a.value:
                        continue
                    a.active = False
                    a.triggered_at = datetime.now(timezone.utc)
                    message = f"Risk alert: {_describe(a)} ({risk['risk_pct']:.0f}%, {risk['level']} risk)."
                    db.add(Notification(user_id=a.user_id, kind="risk", message=message))
                    telegram_messages.append(message)
                    created += 1
                    continue
                t = tickers.get(a.symbol)
                if not t:
                    continue
                hit = (
                    (a.kind == "above" and t["price"] >= a.value)
                    or (a.kind == "below" and t["price"] <= a.value)
                    or (a.kind == "move" and abs(t["change_pct"]) >= a.value)
                )
                if hit:
                    a.active = False
                    a.triggered_at = datetime.now(timezone.utc)
                    message = f"Alert: {_describe(a)}. Now ${t['price']:,.2f}."
                    db.add(Notification(user_id=a.user_id, kind="alert", message=message))
                    telegram_messages.append(message)
                    created += 1

            for h in db.scalars(select(Holding).where(Holding.limit_fired.is_(False))).all():
                t = tickers.get(h.symbol)
                if not t or not h.avg_buy:
                    continue
                pnl = (t["price"] - h.avg_buy) / h.avg_buy * 100
                base = h.symbol.replace("USDT", "")
                msg = None
                if h.stop_loss_pct is not None and pnl <= -h.stop_loss_pct:
                    msg = f"{base} reached your stop-loss ({pnl:+.2f}%). Time to review this position."
                elif h.take_profit_pct is not None and pnl >= h.take_profit_pct:
                    msg = f"{base} reached your take-profit target ({pnl:+.2f}%)."
                if msg:
                    h.limit_fired = True
                    db.add(Notification(user_id=h.user_id, kind="limit", message=msg))
                    telegram_messages.append(msg)
                    created += 1
            db.commit()

    if settings.telegram_bot_token and settings.telegram_chat_id:
        for message in telegram_messages:
            await send_telegram_alert(message)
        for event_id, message in await _external_alert_messages():
            if await send_telegram_alert(message):
                _remember_external_alert(event_id)
                created += 1
    return created


async def alert_loop() -> None:
    while True:
        try:
            await check_once()
        except Exception as e:  # keep the loop alive
            log.warning("alert check failed: %s", e)
        await asyncio.sleep(settings.alert_check_seconds)


async def listings_loop() -> None:
    while True:
        try:
            n = await listings.refresh()
            log.info("listings refreshed, %s new pairs stored", n)
        except Exception as e:
            log.warning("listings refresh failed: %s", e)
        await asyncio.sleep(settings.listings_refresh_hours * 3600)


async def news_loop() -> None:
    """Loads the knowledge base once, then keeps adding fresh news to it."""
    try:
        n = await asyncio.to_thread(kb.build_static)
        log.info("knowledge base ready: %s lesson/guide sections", n)
    except Exception as e:
        log.warning("knowledge base build failed: %s", e)
    while True:
        try:
            items = (await latest_news())["items"]
            await asyncio.to_thread(kb.upsert_news, items)
        except Exception as e:
            log.warning("news ingest failed: %s", e)
        await asyncio.sleep(settings.news_ingest_minutes * 60)
