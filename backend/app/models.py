"""Database tables."""
from datetime import datetime, timezone

from sqlalchemy import BigInteger, Boolean, DateTime, Float, ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


def now() -> datetime:
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(80))
    email: Mapped[str] = mapped_column(String(160), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)

    holdings: Mapped[list["Holding"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    alerts: Mapped[list["Alert"]] = relationship(back_populates="user", cascade="all, delete-orphan")


class Holding(Base):
    """A coin the user owns, with optional stop-loss / take-profit (in %)."""
    __tablename__ = "holdings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    symbol: Mapped[str] = mapped_column(String(20))
    amount: Mapped[float] = mapped_column(Float)
    avg_buy: Mapped[float] = mapped_column(Float)
    stop_loss_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    take_profit_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    limit_fired: Mapped[bool] = mapped_column(Boolean, default=False)

    user: Mapped[User] = relationship(back_populates="holdings")


class Alert(Base):
    """User alert.

    One-shot kinds: above | below | move (24h % move) | risk.
    Recurring liquidation kinds (re-arm after LIQ_ALERT_COOLDOWN_MINUTES):
    liq_large (single event >= value USD), liq_spike / liq_long / liq_short (robust z >= value),
    liq_imbal (long-share shift >= value percentage points).
    """
    __tablename__ = "alerts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    symbol: Mapped[str] = mapped_column(String(20))
    kind: Mapped[str] = mapped_column(String(10))
    value: Mapped[float] = mapped_column(Float)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    triggered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)

    user: Mapped[User] = relationship(back_populates="alerts")


class Notification(Base):
    """Message created when an alert or a P&L limit fires."""
    __tablename__ = "notifications"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    message: Mapped[str] = mapped_column(String(300))
    kind: Mapped[str] = mapped_column(String(20), default="alert")
    seen: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Listing(Base):
    """Cache of Binance USDT pairs and the date each one was first listed."""
    __tablename__ = "listings"

    symbol: Mapped[str] = mapped_column(String(20), primary_key=True)
    base: Mapped[str] = mapped_column(String(20))
    listed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    first_price: Mapped[float] = mapped_column(Float, default=0)
    last_price: Mapped[float] = mapped_column(Float, default=0)
    volume_24h: Mapped[float] = mapped_column(Float, default=0)
    volatility: Mapped[float] = mapped_column(Float, default=0)
    risk: Mapped[int] = mapped_column(Integer, default=1)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class RiskPrediction(Base):
    """History of the AI risk score (one row per coin every ~30 minutes)."""
    __tablename__ = "risk_predictions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    symbol: Mapped[str] = mapped_column(String(20), index=True)
    risk_pct: Mapped[float] = mapped_column(Float)
    level: Mapped[str] = mapped_column(String(10))
    model: Mapped[str] = mapped_column(String(80), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, index=True)

class LiquidationEvent(Base):
    """One observed Binance futures liquidation (forceOrder stream snapshot).

    The stream sends at most one event per symbol per second, so these rows are a sample of
    liquidation activity, not a complete record. Times are UTC epoch milliseconds.
    """
    __tablename__ = "liquidation_events"
    __table_args__ = (
        Index("ix_liq_symbol_time", "symbol", "event_ms"),
        Index("ix_liq_bucket", "bucket_5m"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    event_key: Mapped[str] = mapped_column(String(120), unique=True)
    symbol: Mapped[str] = mapped_column(String(30))
    side: Mapped[str] = mapped_column(String(4))          # BUY | SELL (the forced order's side)
    position: Mapped[str] = mapped_column(String(5))      # long (forced SELL) | short (forced BUY)
    order_type: Mapped[str] = mapped_column(String(12), default="")
    status: Mapped[str] = mapped_column(String(20), default="")
    quantity: Mapped[float] = mapped_column(Float)        # original quantity (q)
    filled_qty: Mapped[float] = mapped_column(Float)      # accumulated filled quantity (z)
    price: Mapped[float] = mapped_column(Float)           # order (bankruptcy) price (p)
    avg_price: Mapped[float] = mapped_column(Float)       # average fill price (ap)
    usd: Mapped[float] = mapped_column(Float, default=0)
    usd_valid: Mapped[bool] = mapped_column(Boolean, default=False)
    event_ms: Mapped[int] = mapped_column(BigInteger, index=True)
    bucket_5m: Mapped[int] = mapped_column(BigInteger)    # event_ms // 300000, for fast aggregation
    received_ms: Mapped[int] = mapped_column(BigInteger)
