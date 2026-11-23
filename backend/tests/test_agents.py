import unittest
from unittest.mock import AsyncMock, patch

from app.services.agents import (
    AGENT_ROLES,
    DerivativesAgent,
    ExplanationAgent,
    MarketIntelligenceAgent,
    OnChainAgent,
    RiskAssessmentAgent,
    SentimentNewsAgent,
    run_specialists,
)


def _signal(symbol: str = "BTCUSDT", live: bool = True) -> dict:
    return {
        "symbol": symbol,
        "trend": "bearish",
        "confidence": 0.72,
        "model": "Ensemble",
        "horizon": "Next 24 hours",
        "reasons": ["Price is below its moving averages."],
        "votes": {
            "XGBoost": {"trend": "bearish", "confidence": 0.72},
            "LightGBM": {"trend": "bullish", "confidence": 0.61},
        },
        "probabilities": {"bearish": 0.5, "neutral": 0.2, "bullish": 0.3},
        "indicators": {
            "atr_pct": 1.1,
            "sma50_dist": -2.0,
            "rsi_14": 68.0,
            "funding_rate": 0.06,
            "fng": 78.0,
            "btc_sma50_dist": -1.5,
        },
        "live": live,
    }


def _context(live: bool = True) -> dict:
    return {
        "prices": {
            "BTCUSDT": {
                "price": 65000.0,
                "change_pct": -2.5,
                "quote_volume": 1_000_000.0,
                "live": live,
            },
        },
        "signals": {"BTCUSDT": _signal(live=live)},
    }


class SpecialistAgentTests(unittest.TestCase):
    def test_market_agent_marks_fallback_data_as_partial(self):
        report = MarketIntelligenceAgent.analyze("BTC", _context(live=False))
        self.assertEqual(report["status"], "partial")
        self.assertIn("fallback/demo", report["summary"])

    def test_risk_agent_reports_disagreement_and_explanation_factor(self):
        report = RiskAssessmentAgent.analyze("BTC risk", _context())
        market = report["data"]["markets"][0]
        self.assertTrue(market["model_disagreement"])
        self.assertTrue(market["top_factor"]["name"])
        self.assertIn("models disagree", report["summary"])

    def test_demo_whale_events_are_not_reported_as_live(self):
        async def run():
            with patch("app.services.agents.whales.latest_whales", new=AsyncMock(
                return_value={"source": "demo", "items": [{"usd": 10_000_000}]}
            )):
                return await OnChainAgent.analyze("BTC whale activity", _context())

        report = self._run_async(run())
        self.assertEqual(report["status"], "unavailable")
        self.assertEqual(report["data"]["live_transfer_count"], 0)
        self.assertIn("excluded", report["summary"])

    def test_demo_news_is_not_used_as_live_sentiment(self):
        async def run():
            with (
                patch("app.services.agents.latest_news", new=AsyncMock(return_value={
                    "source": "demo",
                    "items": [{"title": "Sample", "sentiment": "bullish", "source": "Demo"}],
                })),
                patch("app.services.agents._fear_greed", new=AsyncMock(return_value=None)),
            ):
                return await SentimentNewsAgent.analyze("market sentiment", _context())

        report = self._run_async(run())
        self.assertEqual(report["status"], "unavailable")
        self.assertEqual(report["data"]["headlines"], [])
        self.assertIn("demo headlines were excluded", report["summary"])

    def test_derivatives_agent_normalizes_live_binance_fields(self):
        async def run():
            with (
                patch("app.services.agents.binance.funding_rates", new=AsyncMock(
                    return_value=[{"fundingRate": "0.0001"}]
                )),
                patch("app.services.agents.binance.open_interest", new=AsyncMock(
                    return_value=123.0
                )),
                patch("app.services.agents.binance.long_short_ratio", new=AsyncMock(
                    return_value={
                        "longShortRatio": "1.2",
                        "longAccount": "0.55",
                        "shortAccount": "0.45",
                    }
                )),
            ):
                return await DerivativesAgent.analyze("BTC", _context())

        report = self._run_async(run())
        market = report["data"]["markets"][0]
        self.assertEqual(report["status"], "available")
        self.assertAlmostEqual(market["funding_rate_pct"], 0.01)
        self.assertEqual(market["open_interest_contracts"], 123.0)
        self.assertEqual(market["positioning"]["long_short_ratio"], 1.2)

    def _run_async(self, awaitable):
        import asyncio

        return asyncio.run(awaitable)


class OrchestratorTests(unittest.IsolatedAsyncioTestCase):
    async def test_orchestrator_returns_six_ordered_specialist_reports(self):
        def result(name):
            return {"name": name, "status": "available", "summary": name, "data": {}}

        with (
            patch.object(DerivativesAgent, "analyze", new=AsyncMock(
                return_value=result(DerivativesAgent.name)
            )),
            patch.object(OnChainAgent, "analyze", new=AsyncMock(
                return_value=result(OnChainAgent.name)
            )),
            patch.object(SentimentNewsAgent, "analyze", new=AsyncMock(
                return_value=result(SentimentNewsAgent.name)
            )),
        ):
            reports = await run_specialists("BTC", _context())

        self.assertEqual(len(reports), 6)
        self.assertEqual([report["name"] for report in reports], list(AGENT_ROLES))
        self.assertEqual(reports[-1]["name"], ExplanationAgent.name)
