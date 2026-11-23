"""Paper wallet: practice trading with 10,000 pretend dollars at real live prices."""
import asyncio
from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import settings
from ..database import get_db
from ..models import User
from ..paper_models import PaperTrade
from ..security import current_user
from ..services import paper as engine
from ..services import risk as risk_engine
from ..services.market import prices
from ..services.signals import all_signals

router = APIRouter(prefix="/api/paper", tags=["Paper wallet"])


class TradeIn(BaseModel):
    symbol: str = Field(min_length=5, max_length=20)
    side: Literal["buy", "sell"]
    usd: float | None = Field(default=None, gt=0, le=1e9, description="Dollars to spend (buy)")
    percent: float | None = Field(default=None, gt=0, le=100, description="Share of the position to sell (sell)")


def _aware(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _trade_json(t: PaperTrade) -> dict:
    return {"id": t.id, "symbol": t.symbol, "side": t.side, "amount": t.amount, "price": t.price, "usd": t.usd,
            "fee_usd": t.fee_usd, "realized_pnl": t.realized_pnl, "risk_pct": t.risk_pct,
            "risk_level": t.risk_level, "trend": t.trend, "time": _aware(t.created_at).isoformat()}


async def _risk_of(symbol: str) -> dict | None:
    """AI risk of a coin right now. Waits at most 4 s so an order is never blocked by slow data."""
    try:
        signals = await asyncio.wait_for(asyncio.shield(all_signals()), timeout=4)
        s = next(x for x in signals if x["symbol"] == symbol)
        r = risk_engine.score_from(s)
        return {"risk_pct": r["risk_pct"], "level": r["level"], "trend": s["trend"]}
    except Exception:
        return None


async def _summary(db: Session, user: User) -> dict:
    acct = engine.account_for(db, user.id)
    live = await prices()
    rows, invested = [], 0.0
    for p in engine.positions_of(db, acct):
        price = live.get(p.symbol, {}).get("price") or p.avg_price
        value, cost = p.amount * price, p.amount * p.avg_price
        invested += value
        rows.append({"symbol": p.symbol, "amount": p.amount, "avg_price": p.avg_price, "price": price,
                     "value": value, "pnl": value - cost, "pnl_pct": (price / p.avg_price - 1) * 100})
    equity = acct.cash_usd + invested
    pnl = equity - acct.starting_cash
    return {"cash": acct.cash_usd, "starting_cash": acct.starting_cash, "positions_value": invested,
            "equity": equity, "pnl": pnl, "pnl_pct": pnl / acct.starting_cash * 100,
            "prices_live": any(t.get("live") for t in live.values()), "positions": rows,
            **engine.stats(db, acct)}


@router.get("")
async def my_account(user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Cash, open positions with live profit/loss, and simple statistics."""
    return await _summary(db, user)


@router.post("/trade")
async def place_trade(body: TradeIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    symbol = body.symbol.upper()
    if symbol not in settings.symbol_list:
        raise HTTPException(404, f"Not tracked. Use one of {settings.symbol_list}")
    live = (await prices()).get(symbol)
    if not live or not live.get("live"):
        raise HTTPException(503, "Live prices are not available right now, so practice trading is paused.")
    price = float(live["price"])
    acct = engine.account_for(db, user.id)
    risk = await _risk_of(symbol)

    try:
        if body.side == "buy":
            if body.usd is None:
                raise engine.TradeError("Enter how many dollars you want to spend.")
            trade = engine.buy(db, acct, symbol, body.usd, price, risk)
        else:
            if body.percent is None:
                raise engine.TradeError("Choose how much of your coins to sell.")
            trade = engine.sell(db, acct, symbol, body.percent, price, risk)
    except engine.TradeError as e:
        raise HTTPException(400, str(e))

    summary = await _summary(db, user)
    base = symbol.replace("USDT", "")
    warnings = []
    if body.side == "buy" and risk and risk["level"] == "high":
        warnings.append(f"You bought {base} while its AI risk score was {risk['risk_pct']:.0f}% (high). "
                        "Many traders use smaller amounts when risk is this high.")
    if body.side == "buy" and summary["equity"] > 0:
        share = next((p["value"] for p in summary["positions"] if p["symbol"] == symbol), 0) / summary["equity"] * 100
        if share > 50:
            warnings.append(f"{base} is now {share:.0f}% of your account. Spreading across coins lowers the damage "
                            "of one bad week.")
    return {"trade": _trade_json(trade), "account": summary, "warning": " ".join(warnings) or None}


@router.get("/trades")
def trade_history(limit: int = 50, user: User = Depends(current_user), db: Session = Depends(get_db)):
    acct = engine.account_for(db, user.id)
    rows = db.scalars(select(PaperTrade).where(PaperTrade.account_id == acct.id)
                      .order_by(PaperTrade.created_at.desc(), PaperTrade.id.desc()).limit(min(limit, 500))).all()
    return [_trade_json(t) for t in rows]


@router.post("/reset")
async def reset_account(user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Delete all practice trades and start again with the starting cash."""
    engine.reset(db, engine.account_for(db, user.id))
    return await _summary(db, user)