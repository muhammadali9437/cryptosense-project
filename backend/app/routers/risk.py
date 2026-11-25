"""AI risk score for each coin, risk history, and the risk of the user's portfolio."""
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import settings
from ..database import get_db
from ..models import RiskPrediction, User
from ..schemas import RiskSimulationIn
from ..security import current_user
from ..services import risk as risk_engine
from ..services.copilot import historical_twins
from ..services.signals import all_signals, signal_for
from .portfolio import build_portfolio

router = APIRouter(prefix="/api/risk", tags=["AI risk"])

SAVE_EVERY = timedelta(minutes=30)


def _aware(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


async def _all_risks(db: Session) -> list[dict]:
    risks = [risk_engine.score_from(s) for s in await all_signals()]
    # keep a history (at most one row per coin every 30 minutes) for charts and the report
    now = datetime.now(timezone.utc)
    for r in risks:
        last = db.scalar(select(RiskPrediction).where(RiskPrediction.symbol == r["symbol"])
                         .order_by(RiskPrediction.created_at.desc()).limit(1))
        if last is None or now - _aware(last.created_at) >= SAVE_EVERY:
            db.add(RiskPrediction(symbol=r["symbol"], risk_pct=r["risk_pct"], level=r["level"], model=r["model"]))
    db.commit()
    return risks


@router.get("")
async def all_risks(db: Session = Depends(get_db)):
    """Risk score, level and the reasons behind it, for every tracked coin."""
    return await _all_risks(db)


@router.get("/portfolio")
async def portfolio_risk(user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Value-weighted risk of the logged-in user's portfolio."""
    risks = {r["symbol"]: r for r in await _all_risks(db)}
    pf = await build_portfolio(user, db)
    return risk_engine.portfolio_risk([{"symbol": h.symbol, "value": h.value} for h in pf.holdings], risks)


@router.get("/{symbol}")
async def one_risk(symbol: str, db: Session = Depends(get_db)):
    symbol = symbol.upper()
    if symbol not in settings.symbol_list:
        raise HTTPException(404, f"Not tracked. Use one of {settings.symbol_list}")
    found = next((r for r in await _all_risks(db) if r["symbol"] == symbol), None)
    if found is None:
        raise HTTPException(503, f"Risk for {symbol} is unavailable: its live inputs could not be fetched.")
    return found


@router.get("/{symbol}/copilot")
async def risk_copilot(symbol: str):
    """Model consensus and real, completed historical analogs for a tracked coin."""
    symbol = symbol.upper()
    if symbol not in settings.symbol_list:
        raise HTTPException(404, f"Not tracked. Use one of {settings.symbol_list}")
    signal = await signal_for(symbol)
    votes = signal["votes"]
    counts: dict[str, int] = {}
    for vote in votes.values():
        counts[vote["trend"]] = counts.get(vote["trend"], 0) + 1
    try:
        twins = await historical_twins(symbol)
    except Exception as exc:
        raise HTTPException(503, "Historical market data is unavailable right now.") from exc
    return {
        "symbol": symbol,
        "votes": [
            {"model": model, "trend": vote["trend"], "confidence": vote["confidence"]}
            for model, vote in votes.items()
        ],
        "agreement": max(counts.values(), default=0),
        "model_count": len(votes),
        "disagreement": len(counts) > 1,
        "twins": twins,
        "key_levels": signal.get("key_levels", []),
        "key_levels_source": signal.get("key_levels_source", "unavailable"),
        "key_levels_note": signal.get("key_levels_note", ""),
        "twins_note": "Historical similarity is descriptive, not a forecast or probability.",
    }


@router.post("/{symbol}/simulate")
async def simulate_risk(symbol: str, body: RiskSimulationIn):
    """Recalculate the transparent risk score after changing volatility only."""
    symbol = symbol.upper()
    if symbol not in settings.symbol_list:
        raise HTTPException(404, f"Not tracked. Use one of {settings.symbol_list}")
    signal = await signal_for(symbol)
    current = risk_engine.score_from(signal)
    scenario = {**signal, "indicators": dict(signal["indicators"])}
    scenario["indicators"]["atr_pct"] *= body.volatility_multiplier
    simulated = risk_engine.score_from(scenario)
    return {
        "current_risk_pct": current["risk_pct"],
        "simulated_risk_pct": simulated["risk_pct"],
        "change_pct_points": round(simulated["risk_pct"] - current["risk_pct"], 1),
        "volatility_multiplier": body.volatility_multiplier,
        "note": "What-if estimate: only the volatility input changed; this is not a forecast.",
    }


@router.get("/{symbol}/history")
def risk_history(symbol: str, limit: int = 48, db: Session = Depends(get_db)):
    rows = db.scalars(select(RiskPrediction).where(RiskPrediction.symbol == symbol.upper())
                      .order_by(RiskPrediction.created_at.desc()).limit(min(limit, 500))).all()
    return [{"time": _aware(r.created_at).isoformat(), "risk_pct": r.risk_pct, "level": r.level}
            for r in reversed(rows)]