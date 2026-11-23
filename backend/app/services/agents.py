"""Specialist analysts orchestrated by CryptoSentinel Risk Copilot.

The specialists use deterministic, inspectable calculations and existing data
providers. Sage is the single user-facing assistant and may synthesize their
reports with the configured LLM.
"""
import asyncio
import logging
import re
from typing import Any

from ..config import settings
from . import binance, risk as risk_engine, whales
from .cache import cached
from .market import NAMES
from .news import latest_news
from .sentiment_index import fear_greed

log = logging.getLogger("cryptosense.agents")

AGENT_ROLES = {
    "Market Intelligence Agent": "Price, volume, live market state and technical signal context.",
    "Derivatives Agent": "Futures funding, open interest and long/short positioning.",
    "On-Chain Agent": "Large wallet transfers and exchange-flow direction.",
    "Sentiment & News Agent": "News sentiment and the Fear & Greed index.",
    "Risk Assessment Agent": "Explainable risk scores, contributing factors and model agreement.",
    "Explanation Agent": "A concise, beginner-friendly synthesis with data limitations.",
}


def _focus_symbols(question: str, context: dict) -> list[str]:
    available = list(context.get("prices", {}))
    query = question.lower()
    mentioned = [
        symbol for symbol in available
        if re.search(rf"\b{re.escape(symbol.replace('USDT', '').lower())}\b", query)
        or re.search(rf"\b{re.escape(NAMES.get(symbol, '').lower())}\b", query)
    ]
    if mentioned:
        return mentioned
    portfolio = context.get("portfolio") or {}
    holdings = [h["symbol"] for h in portfolio.get("holdings", []) if h.get("symbol") in available]
    return list(dict.fromkeys(holdings))[:3] or available[:3] or settings.symbol_list[:3]


def _report(name: str, status: str, summary: str, data: dict | None = None) -> dict:
    return {"name": name, "status": status, "summary": summary, "data": data or {}}


class MarketIntelligenceAgent:
    name = "Market Intelligence Agent"

    @classmethod
    def analyze(cls, question: str, context: dict) -> dict:
        prices = context.get("prices", {})
        signals = context.get("signals", {})
        rows = []
        for symbol in _focus_symbols(question, context):
            ticker = prices.get(symbol)
            signal = signals.get(symbol)
            if ticker is None and signal is None:
                continue
            rows.append({
                "symbol": symbol,
                "price": ticker.get("price") if ticker else None,
                "change_24h_pct": ticker.get("change_pct") if ticker else None,
                "volume_24h_usd": ticker.get("quote_volume") if ticker else None,
                "trend": signal.get("trend") if signal else None,
                "confidence": signal.get("confidence") if signal else None,
                "model": signal.get("model") if signal else None,
                "reasons": signal.get("reasons", []) if signal else [],
                "ticker_live": bool(ticker and ticker.get("live")),
                "signal_live": bool(signal and signal.get("live")),
            })
        if not rows:
            return _report(cls.name, "unavailable", "Market prices and signals are unavailable.")
        lines = []
        for row in rows:
            if row["price"] is None:
                lines.append(f"{row['symbol']}: current price unavailable.")
                continue
            movement = row["change_24h_pct"]
            lines.append(
                f"{row['symbol']}: ${row['price']:,.4f}, 24h change "
                f"{movement:+.2f}%." if movement is not None
                else f"{row['symbol']}: ${row['price']:,.4f}."
            )
            if row["trend"]:
                lines.append(
                    f"Signal: {row['trend']} ({row['confidence'] * 100:.0f}% confidence, {row['model']})."
                )
        status = "available" if all(r["ticker_live"] and r["signal_live"] for r in rows) else "partial"
        if status == "partial":
            lines.append("Some figures use fallback/demo data; check the live flags before relying on them.")
        return _report(cls.name, status, " ".join(lines), {"markets": rows})


class DerivativesAgent:
    name = "Derivatives Agent"

    @staticmethod
    async def _one(symbol: str) -> dict:
        async def build() -> dict:
            results = await asyncio.gather(
                binance.funding_rates(symbol, 1),
                binance.open_interest(symbol),
                binance.long_short_ratio(symbol),
                return_exceptions=True,
            )
            rates, open_interest, ratio = results
            for source, result in zip(("funding", "open interest", "positioning"), results):
                if isinstance(result, Exception):
                    log.warning("%s data unavailable for %s: %s",
                                source, symbol, result.__class__.__name__)
            funding_pct = None
            if not isinstance(rates, Exception) and rates:
                funding_pct = float(rates[-1]["fundingRate"]) * 100
            oi = None if isinstance(open_interest, Exception) else float(open_interest)
            positioning = None if isinstance(ratio, Exception) or ratio is None else {
                "long_short_ratio": float(ratio["longShortRatio"]),
                "long_account_pct": float(ratio["longAccount"]) * 100,
                "short_account_pct": float(ratio["shortAccount"]) * 100,
            }
            return {
                "symbol": symbol,
                "funding_rate_pct": funding_pct,
                "open_interest_contracts": oi,
                "positioning": positioning,
            }

        return await cached(f"agent_derivatives:{symbol}", 120, build)

    @classmethod
    async def analyze(cls, question: str, context: dict) -> dict:
        symbols = _focus_symbols(question, context)
        results = await asyncio.gather(*(cls._one(symbol) for symbol in symbols), return_exceptions=True)
        rows = []
        for symbol, result in zip(symbols, results):
            if isinstance(result, Exception):
                log.warning("derivatives data unavailable for %s: %s", symbol, result.__class__.__name__)
                rows.append({"symbol": symbol, "funding_rate_pct": None,
                             "open_interest_contracts": None, "positioning": None})
            else:
                rows.append(result)
        available = sum(
            row["funding_rate_pct"] is not None
            or row["open_interest_contracts"] is not None
            or row["positioning"] is not None
            for row in rows
        )
        if not available:
            return _report(cls.name, "unavailable", "Live Binance Futures data is unavailable.", {"markets": rows})
        summaries = []
        for row in rows:
            parts = []
            if row["funding_rate_pct"] is not None:
                parts.append(f"funding {row['funding_rate_pct']:.4f}%")
            if row["open_interest_contracts"] is not None:
                parts.append(f"open interest {row['open_interest_contracts']:,.2f} contracts")
            if row["positioning"] is not None:
                parts.append(f"long/short ratio {row['positioning']['long_short_ratio']:.2f}")
            summaries.append(f"{row['symbol']}: {', '.join(parts)}." if parts else f"{row['symbol']}: derivatives unavailable.")
        status = "available" if available == len(rows) else "partial"
        return _report(cls.name, status, " ".join(summaries), {"source": "Binance Futures", "markets": rows})


class OnChainAgent:
    name = "On-Chain Agent"

    @staticmethod
    async def analyze(_question: str, _context: dict) -> dict:
        try:
            snapshot = await whales.latest_whales()
        except Exception as exc:
            log.warning("on-chain data unavailable: %s", exc.__class__.__name__)
            return _report(OnChainAgent.name, "unavailable", "Live whale-transfer data is unavailable.")
        if snapshot["source"] != "whale_alert":
            return _report(
                OnChainAgent.name,
                "unavailable",
                "No live on-chain feed is configured; demo transfers were excluded from the analysis.",
                {"source": snapshot["source"], "live_transfer_count": 0},
            )
        items = snapshot["items"]
        summary = whales.summarize(items)
        return _report(
            OnChainAgent.name,
            "available",
            f"{summary['read']} Live transfers in the feed: {len(items)}.",
            {"source": snapshot["source"], "live_transfer_count": len(items),
             "inflow_usd": summary["inflow_usd"], "outflow_usd": summary["outflow_usd"],
             },
        )


class SentimentNewsAgent:
    name = "Sentiment & News Agent"

    @staticmethod
    async def analyze(_question: str, context: dict) -> dict:
        news_result, fear_result = await asyncio.gather(
            latest_news(limit=10),
            _fear_greed(context),
            return_exceptions=True,
        )
        if isinstance(news_result, Exception):
            log.warning("news specialist unavailable: %s", news_result.__class__.__name__)
            news_result = None
        if isinstance(fear_result, Exception):
            log.warning("Fear & Greed unavailable: %s", fear_result.__class__.__name__)
            fear_result = None
        news_items = news_result["items"] if news_result else []
        news_live = bool(news_result and news_result["source"] != "demo")
        counts = {label: sum(item.get("sentiment") == label for item in news_items)
                  for label in ("bullish", "neutral", "bearish")}
        mood = None
        if fear_result:
            mood = {"value": int(fear_result["value"]),
                    "label": fear_result["value_classification"]}
        usable_news = news_items if news_live else []
        parts = []
        if usable_news:
            parts.append(
                f"News sentiment from {news_result['source']}: "
                f"{counts['bullish']} bullish, {counts['neutral']} neutral, {counts['bearish']} bearish headlines."
            )
            parts.append("Recent headlines: " + " | ".join(item["title"] for item in usable_news[:2]))
        else:
            parts.append("No live news headlines are available; demo headlines were excluded.")
        if mood:
            parts.append(f"Fear & Greed is {mood['value']} ({mood['label']}).")
        else:
            parts.append("Fear & Greed data is unavailable.")
        status = "available" if news_live and mood else "partial" if news_live or mood else "unavailable"
        return _report(
            SentimentNewsAgent.name,
            status,
            " ".join(parts),
            {"news_source": news_result["source"] if news_result else "unavailable",
             "news_counts": counts if news_live else None,
             "headlines": [
                 {"title": item["title"], "sentiment": item["sentiment"], "source": item["source"]}
                 for item in usable_news[:5]
             ],
             "fear_greed": mood},
        )


async def _fear_greed(context: dict) -> dict | None:
    if context.get("fear_greed"):
        return context["fear_greed"]
    values = await fear_greed(1)
    return values[0] if values else None


class RiskAssessmentAgent:
    name = "Risk Assessment Agent"

    @classmethod
    def analyze(cls, question: str, context: dict) -> dict:
        signals = context.get("signals", {})
        rows = []
        for symbol in _focus_symbols(question, context):
            signal = signals.get(symbol)
            if signal is None:
                continue
            score = risk_engine.score_from(signal)
            votes = signal.get("votes") or {}
            trends = {vote["trend"] for vote in votes.values()}
            top = max(score["factors"], key=lambda factor: factor["points"] / factor["max"])
            rows.append({
                "symbol": symbol,
                "risk_pct": score["risk_pct"],
                "level": score["level"],
                "horizon": score["horizon"],
                "model": signal.get("model", "unknown"),
                "top_factor": {"name": top["name"], "points": top["points"], "note": top["note"]},
                "model_votes": votes,
                "model_disagreement": len(trends) > 1,
                "live": bool(signal.get("live")),
            })
        if not rows:
            return _report(cls.name, "unavailable", "A risk score cannot be calculated without market signals.")
        summaries = [
            f"{row['symbol']} risk is {row['risk_pct']:.0f}% ({row['level']}); "
            f"largest contributor: {row['top_factor']['name']}."
            for row in rows
        ]
        for row in rows:
            votes = row["model_votes"]
            if votes:
                trends = {vote["trend"] for vote in votes.values()}
                consensus = "disagree" if len(trends) > 1 else "agree"
                summaries.append(
                    f"Available models {consensus} for {row['symbol']} "
                    f"({max(sum(v['trend'] == trend for v in votes.values()) for trend in trends)}/{len(votes)} share the leading view)."
                )
            else:
                summaries.append(f"{row['symbol']} uses {row['model']}; individual model votes are unavailable.")
        if any(not row["live"] for row in rows):
            summaries.append("At least one score uses fallback/demo candles.")
        status = "available" if all(row["live"] for row in rows) else "partial"
        return _report(cls.name, status, " ".join(summaries), {"markets": rows})


class ExplanationAgent:
    name = "Explanation Agent"

    @classmethod
    def analyze(cls, reports: list[dict]) -> dict:
        market = next((r for r in reports if r["name"] == MarketIntelligenceAgent.name), None)
        risk = next((r for r in reports if r["name"] == RiskAssessmentAgent.name), None)
        derivatives = next((r for r in reports if r["name"] == DerivativesAgent.name), None)
        onchain = next((r for r in reports if r["name"] == OnChainAgent.name), None)
        sentiment = next((r for r in reports if r["name"] == SentimentNewsAgent.name), None)
        parts = []
        if market and market["status"] != "unavailable":
            parts.append(market["summary"])
        if risk and risk["status"] != "unavailable":
            parts.append(risk["summary"])
        if derivatives and derivatives["status"] != "unavailable":
            parts.append(derivatives["summary"])
        if sentiment and sentiment["status"] != "unavailable":
            parts.append(sentiment["summary"])
        if onchain and onchain["status"] == "available":
            parts.append(onchain["summary"])
        unavailable = [r["name"] for r in reports if r["status"] == "unavailable"]
        if unavailable:
            parts.append("Unavailable live data: " + ", ".join(unavailable) + ".")
        parts.append("These are market observations, not a buy/sell recommendation or a price prediction.")
        status = "available" if any(r["status"] != "unavailable" for r in reports) else "unavailable"
        return _report(cls.name, status, " ".join(parts))


async def run_specialists(question: str, context: dict) -> list[dict[str, Any]]:
    """Run all six specialists and return their structured reports in stable order."""
    market = MarketIntelligenceAgent.analyze(question, context)
    risk = RiskAssessmentAgent.analyze(question, context)
    specialist_results = await asyncio.gather(
        DerivativesAgent.analyze(question, context),
        OnChainAgent.analyze(question, context),
        SentimentNewsAgent.analyze(question, context),
        return_exceptions=True,
    )
    async_reports = []
    async_agents = (DerivativesAgent.name, OnChainAgent.name, SentimentNewsAgent.name)
    for name, result in zip(async_agents, specialist_results):
        if isinstance(result, Exception):
            log.warning("%s failed: %s", name, result.__class__.__name__)
            async_reports.append(_report(name, "unavailable", f"{name} could not retrieve its data."))
        else:
            async_reports.append(result)
    reports = [market, async_reports[0], async_reports[1], async_reports[2], risk]
    reports.append(ExplanationAgent.analyze(reports))
    return reports
