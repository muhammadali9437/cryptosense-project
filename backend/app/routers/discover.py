"""News, whale transfers and new listings."""
from fastapi import APIRouter, Query

from ..services import jev
from ..services.listings import recent_listings
from ..services.news import latest_news
from ..services.whales import latest_whales
from ..services.liquidations import snapshot

router = APIRouter(prefix="/api", tags=["Discover"])


@router.get("/news")
async def news(sentiment: str | None = Query(None, pattern="^(bullish|bearish|neutral)$"), limit: int = 30):
    data = await latest_news()
    items = [i for i in data["items"] if sentiment is None or i["sentiment"] == sentiment]
    engine = items[0]["sentiment_model"] if items else None
    return {"source": data["source"], "sentiment_engine": engine, "items": items[:limit]}


@router.get("/news/compare")
async def news_compare():
    """Jev vs the baseline model (FinBERT or VADER) on the current headlines. For the report."""
    items = (await latest_news())["items"]
    judged = [i for i in items if i.get("sentiment_model") == "Jev"]
    if not judged:
        return {"jev_active": False, **jev.status()}
    agree = sum(i["sentiment"] == i["baseline_sentiment"] for i in judged)
    count = lambda key, rows: {lab: sum(r[key] == lab for r in rows) for lab in ("bullish", "bearish", "neutral")}  # noqa: E731
    return {
        "jev_active": True,
        "headlines": len(judged),
        "baseline_model": judged[0]["baseline_model"],
        "agreement_pct": round(agree / len(judged) * 100, 1),
        "jev_labels": count("sentiment", judged),
        "baseline_labels": count("baseline_sentiment", judged),
        "impact": {lab: sum(i.get("impact") == lab for i in judged) for lab in ("minor", "moderate", "major")},
        "disagreements": [
            {"title": i["title"], "jev": i["sentiment"], "baseline": i["baseline_sentiment"],
             "jev_confidence": i.get("confidence")}
            for i in judged if i["sentiment"] != i["baseline_sentiment"]
        ][:15],
    }


@router.get("/whales")
async def whales():
    return await latest_whales()


@router.get("/liquidations")
def liquidations(limit: int = Query(100, ge=1, le=500)):
    return snapshot(limit)


@router.get("/listings")
def listings():
    items = recent_listings()
    return {
        "source": "binance",
        "items": items,
        "note": None if items else "Still scanning Binance for new listings. Try again in a minute.",
    }
