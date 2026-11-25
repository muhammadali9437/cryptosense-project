"""CryptoSense AI backend. Start with:  uvicorn app.main:app --reload
Interactive API docs: http://127.0.0.1:8000/docs
"""
import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware

from .config import settings
from .database import Base, engine
from .routers import alerts, auth, chat, discover, liquidations, market, paper, portfolio, risk, signals
from .services import binance
from .services.predictor import predictor
from .services.signals import SignalUnavailable
from .services.watcher import alert_loop, listings_loop, news_loop
from .services.liquidations import liquidation_loop
from .services.liquidation_store import store_loop

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logging.getLogger("httpx").setLevel(logging.WARNING)


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(engine)
    tasks = [asyncio.create_task(t()) for t in (
        alert_loop,
        news_loop,
        listings_loop,
        liquidation_loop,
        store_loop,
    )]
    logging.getLogger("cryptosense").info(
        "Models loaded: %s", predictor.models or "none: AI signals unavailable until TRAIN_AI.bat is run"
    )
    yield
    for t in tasks:
        t.cancel()
    await binance.close()


app = FastAPI(
    title=settings.app_name,
    version="2.2.0",
    description=(
        "Real-time crypto analytics: live data, XGBoost + LightGBM market signals, portfolio, alerts, "
        "VADER news sentiment, whales, liquidations, new listings and the six-specialist CryptoSentinel Risk Copilot."
    ),
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_list,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.exception_handler(SignalUnavailable)
async def signal_unavailable(_: Request, exc: SignalUnavailable):
    """Signals/risk can't be computed from real data right now: say so instead of guessing."""
    return JSONResponse(status_code=503, content={
        "detail": f"AI signal unavailable for {exc.symbol}: missing {', '.join(exc.missing)}.",
        "missing": exc.missing,
    })


for r in (auth, market, signals, risk, portfolio, paper, alerts, discover, liquidations, chat):
    app.include_router(r.router)


@app.get("/", tags=["Health"])
def root():
    return {"app": settings.app_name, "status": "ok", "docs": "/docs", "models": predictor.models}