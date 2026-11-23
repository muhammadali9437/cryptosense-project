"""Paper-trading rules. Pretend money, real live prices, realistic 0.1 % fee (like Binance spot).

buy : spend `usd`; fee = 0.1 % of it; coins = (usd - fee) / price; cost basis includes the fee.
sell: sell a percentage of the position; proceeds = coins * price - 0.1 % fee;
      realised profit = proceeds - average cost * coins.
"""
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from ..paper_models import PaperAccount, PaperPosition, PaperTrade

FEE_RATE = 0.001
START_CASH = 10_000.0
MIN_TRADE_USD = 1.0


class TradeError(Exception):
    """A rule was broken (not enough cash, nothing to sell, ...). The message is shown to the user."""


def account_for(db: Session, user_id: int) -> PaperAccount:
    acct = db.scalar(select(PaperAccount).where(PaperAccount.user_id == user_id))
    if acct is None:
        acct = PaperAccount(user_id=user_id, cash_usd=START_CASH, starting_cash=START_CASH)
        db.add(acct)
        db.commit()
        db.refresh(acct)
    return acct


def positions_of(db: Session, acct: PaperAccount) -> list[PaperPosition]:
    return list(db.scalars(select(PaperPosition).where(PaperPosition.account_id == acct.id)
                           .order_by(PaperPosition.symbol)).all())


def _position(db: Session, acct: PaperAccount, symbol: str) -> PaperPosition | None:
    return db.scalar(select(PaperPosition).where(PaperPosition.account_id == acct.id,
                                                 PaperPosition.symbol == symbol))


def buy(db: Session, acct: PaperAccount, symbol: str, usd: float, price: float, risk: dict | None) -> PaperTrade:
    if usd < MIN_TRADE_USD:
        raise TradeError("The smallest order is 1 dollar.")
    if usd > acct.cash_usd + 1e-9:
        raise TradeError(f"Not enough cash. You have ${acct.cash_usd:,.2f}.")
    fee = usd * FEE_RATE
    amount = (usd - fee) / price

    pos = _position(db, acct, symbol)
    if pos is None:
        db.add(PaperPosition(account_id=acct.id, symbol=symbol, amount=amount, avg_price=usd / amount))
    else:
        total = pos.amount + amount
        pos.avg_price = (pos.amount * pos.avg_price + usd) / total
        pos.amount = total
    acct.cash_usd -= usd

    trade = PaperTrade(account_id=acct.id, symbol=symbol, side="buy", amount=amount, price=price, usd=usd,
                       fee_usd=fee, risk_pct=(risk or {}).get("risk_pct"),
                       risk_level=(risk or {}).get("level"), trend=(risk or {}).get("trend"))
    db.add(trade)
    db.commit()
    db.refresh(trade)
    return trade


def sell(db: Session, acct: PaperAccount, symbol: str, percent: float, price: float, risk: dict | None) -> PaperTrade:
    pos = _position(db, acct, symbol)
    if pos is None or pos.amount <= 0:
        raise TradeError(f"You don't hold any {symbol.replace('USDT', '')} to sell.")
    amount = pos.amount if percent >= 99.999 else pos.amount * percent / 100
    gross = amount * price
    fee = gross * FEE_RATE
    proceeds = gross - fee
    realized = proceeds - pos.avg_price * amount

    pos.amount -= amount
    if pos.amount < 1e-12:
        db.delete(pos)
    acct.cash_usd += proceeds

    trade = PaperTrade(account_id=acct.id, symbol=symbol, side="sell", amount=amount, price=price, usd=gross,
                       fee_usd=fee, realized_pnl=realized, risk_pct=(risk or {}).get("risk_pct"),
                       risk_level=(risk or {}).get("level"), trend=(risk or {}).get("trend"))
    db.add(trade)
    db.commit()
    db.refresh(trade)
    return trade


def reset(db: Session, acct: PaperAccount) -> None:
    db.execute(delete(PaperTrade).where(PaperTrade.account_id == acct.id))
    db.execute(delete(PaperPosition).where(PaperPosition.account_id == acct.id))
    acct.cash_usd = acct.starting_cash
    db.commit()


def stats(db: Session, acct: PaperAccount) -> dict:
    sells = list(db.scalars(select(PaperTrade).where(PaperTrade.account_id == acct.id,
                                                     PaperTrade.side == "sell")).all())
    count = len(list(db.scalars(select(PaperTrade.id).where(PaperTrade.account_id == acct.id)).all()))
    wins = sum(1 for t in sells if (t.realized_pnl or 0) > 0)
    return {"trades_count": count, "win_rate": round(wins / len(sells) * 100, 1) if sells else None}