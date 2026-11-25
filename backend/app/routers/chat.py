"""CryptoSentinel Risk Copilot chat and its six specialist analysts."""
import asyncio

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import User
from ..schemas import ChatIn, ChatOut
from ..security import optional_user
from ..services.agents import AGENT_ROLES, run_specialists
from ..services import sage
from ..services import risk as risk_engine
from ..services.market import prices
from ..services.news import latest_news
from ..services.rag import kb
from ..services.sentiment_index import fear_greed
from ..services.signals import SignalUnavailable, all_signals
from .portfolio import build_portfolio

router = APIRouter(prefix="/api/chat", tags=["CryptoSentinel Risk Copilot"])


@router.post("", response_model=ChatOut)
async def chat(body: ChatIn, user: User | None = Depends(optional_user), db: Session = Depends(get_db)):
    try:
        fng = (await fear_greed(1))[0]
    except Exception:
        fng = None
    try:
        signals = await all_signals()
    except SignalUnavailable:
        signals = []  # Sage still answers; the specialists report signals as unavailable
    context = {
        "prices": await prices(),
        "signals": {s["symbol"]: s for s in signals},
        "risks": {s["symbol"]: risk_engine.score_from(s) for s in signals},
        "fear_greed": fng,
        "portfolio": (await build_portfolio(user, db)).model_dump() if user else None,
    }
    reports = await run_specialists(body.question, context)
    context["specialists"] = reports
    context["copilot_summary"] = reports[-1]["summary"]
    answer, source, sources = await sage.answer(body.question, context)
    return ChatOut(answer=answer, source=source, sources=sources, agents=reports)


@router.get("/agents")
async def specialist_agents():
    """Names and responsibilities of the six specialists coordinated by the copilot."""
    return [{"name": name, "responsibility": role} for name, role in AGENT_ROLES.items()]


@router.get("/knowledge")
async def knowledge_status():
    """Which search engine the RAG uses and how many documents it holds."""
    return await asyncio.to_thread(kb.status)


@router.post("/knowledge/rebuild")
async def rebuild_knowledge():
    """Re-load lessons, latest news and signals into the knowledge base."""
    n = await asyncio.to_thread(kb.build_static)
    news = (await latest_news())["items"]
    await asyncio.to_thread(kb.upsert_news, news)
    try:
        await asyncio.to_thread(kb.upsert_signals, await all_signals())
    except SignalUnavailable:
        pass
    return {**(await asyncio.to_thread(kb.status)), "static_docs": n, "news_docs": len(news)}
