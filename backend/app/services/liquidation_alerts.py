"""User liquidation alerts (kinds liq_large, liq_spike, liq_long, liq_short, liq_imbal).

Unlike price alerts these are recurring: after firing, an alert stays active but stays quiet for
LIQ_ALERT_COOLDOWN_MINUTES, so one burst of activity produces one notification, not dozens.
"""
import time
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import settings
from ..models import Alert, LiquidationEvent as L
from . import liquidation_anomaly

KINDS = ("liq_large", "liq_spike", "liq_long", "liq_short", "liq_imbal")


def _aware(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def cooling_down(alert: Alert, now: datetime) -> bool:
    last = _aware(alert.triggered_at)
    return last is not None and now - last < timedelta(minutes=settings.liq_alert_cooldown_minutes)


def _usd(v: float) -> str:
    return f"${v / 1e6:.2f}M" if v >= 1e6 else f"${v:,.0f}"


def message_for(alert: Alert, metrics: dict) -> str | None:
    """Pure check: the notification text if `alert` should fire for `metrics`, else None."""
    base = alert.symbol.replace("USDT", "")
    min_usd = settings.liq_spike_min_usd
    if alert.kind == "liq_large":
        event = metrics.get("largest_new")
        if event and event["usd"] >= alert.value:
            return (f"Liquidation alert: observed {_usd(event['usd'])} {base} {event['position']} liquidation "
                    f"at ${event['price']:,.4f} (threshold {_usd(alert.value)}).")
        return None
    s = metrics.get("scores")
    if not s:
        return None
    if alert.kind == "liq_spike" and s["total_z"] >= alert.value and s["total_usd"] >= min_usd:
        return (f"Unusual {base} liquidation activity: {_usd(s['total_usd'])} observed in 5 min "
                f"(robust z {s['total_z']:.1f}, your threshold {alert.value:g}). Context, not a price prediction.")
    if alert.kind == "liq_long" and s["long_z"] >= alert.value and s["long_usd"] >= min_usd:
        return (f"{base} long-liquidation spike: {_usd(s['long_usd'])} of forced sells in 5 min "
                f"(robust z {s['long_z']:.1f}). Context, not a price prediction.")
    if alert.kind == "liq_short" and s["short_z"] >= alert.value and s["short_usd"] >= min_usd:
        return (f"{base} short-liquidation spike: {_usd(s['short_usd'])} of forced buys in 5 min "
                f"(robust z {s['short_z']:.1f}). Context, not a price prediction.")
    shift = s.get("long_share_shift_pts")
    if (alert.kind == "liq_imbal" and shift is not None and abs(shift) >= alert.value
            and s["recent_15m_usd"] >= min_usd):
        side = "longs" if shift > 0 else "shorts"
        return (f"{base} liquidation imbalance changed: long share moved {shift:+.0f} points in 15 min "
                f"toward {side} being liquidated.")
    return None


def metrics_for(db: Session, symbol: str, since_ms: int, now_ms: int) -> dict:
    largest = db.scalars(
        select(L).where(L.symbol == symbol, L.usd_valid.is_(True), L.event_ms > since_ms, L.event_ms <= now_ms)
        .order_by(L.usd.desc()).limit(1)
    ).first()
    inputs = liquidation_anomaly.load_inputs(db, symbol, now_ms)
    return {
        "largest_new": ({"usd": largest.usd, "position": largest.position,
                         "price": largest.avg_price or largest.price} if largest else None),
        "scores": liquidation_anomaly.scores(inputs, settings.liq_spike_min_usd) if inputs else None,
    }


def evaluate(db: Session, alerts: list[Alert], now: datetime | None = None) -> list[tuple[Alert, str]]:
    """Returns (alert, message) pairs that fire now, marking triggered_at for the cooldown."""
    now = now or datetime.now(timezone.utc)
    now_ms = int(now.timestamp() * 1000)
    window_ms = settings.alert_check_seconds * 2 * 1000
    cache: dict[tuple[str, int], dict] = {}
    fired = []
    for alert in alerts:
        if alert.kind not in KINDS or cooling_down(alert, now):
            continue
        last = _aware(alert.triggered_at)
        since = max(now_ms - window_ms, int(last.timestamp() * 1000) if last else 0)
        key = (alert.symbol, since)
        if key not in cache:
            cache[key] = metrics_for(db, alert.symbol, since, now_ms)
        message = message_for(alert, cache[key])
        if message:
            alert.triggered_at = now
            fired.append((alert, message))
    return fired


def now_ms() -> int:
    return int(time.time() * 1000)
