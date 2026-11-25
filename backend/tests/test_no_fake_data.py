"""When live inputs are missing the backend must say "unavailable", never invent values."""
import asyncio
import unittest
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from app.main import app
from app.services import cache, market, news, signals, whales


async def _fail(*args, **kwargs):
    raise OSError("network down")


class NoFakeDataTests(unittest.TestCase):
    def setUp(self):
        cache.clear()

    def tearDown(self):
        cache.clear()

    def test_prices_are_empty_when_binance_fails(self):
        with patch.object(market.binance, "tickers", new=_fail):
            self.assertEqual(asyncio.run(market.prices()), {})

    def test_signal_unavailable_when_candles_missing(self):
        with patch.object(signals.binance, "klines", new=_fail), \
             patch.object(signals.binance, "funding_rates", new=_fail), \
             patch.object(signals, "fear_greed", new=_fail):
            with self.assertRaises(signals.SignalUnavailable) as ctx:
                asyncio.run(signals.signal_for("BTCUSDT"))
        self.assertIn("Binance candles", ctx.exception.missing)
        self.assertIn("futures funding rate", ctx.exception.missing)
        self.assertIn("Fear & Greed index", ctx.exception.missing)

    def test_signal_unavailable_without_trained_model(self):
        with patch.object(signals.predictor, "tabular", {}):
            with self.assertRaises(signals.SignalUnavailable) as ctx:
                asyncio.run(signals.signal_for("BTCUSDT"))
        self.assertIn("trained AI model", ctx.exception.missing[0])

    def test_signals_endpoint_returns_503_not_made_up_values(self):
        with patch.object(signals.binance, "klines", new=_fail), \
             patch.object(signals.binance, "funding_rates", new=_fail), \
             patch.object(signals, "fear_greed", new=_fail):
            response = TestClient(app).get("/api/signals")
        self.assertEqual(response.status_code, 503)
        self.assertIn("missing", response.json())

    def test_whales_unavailable_without_key_or_on_error(self):
        with patch.object(whales.settings, "whale_alert_key", ""):
            data = asyncio.run(whales.latest_whales())
        self.assertEqual((data["source"], data["items"]), ("unavailable", []))
        cache.clear()
        with patch.object(whales.settings, "whale_alert_key", "k"), \
             patch.object(whales, "_from_whale_alert", new=_fail):
            data = asyncio.run(whales.latest_whales())
        self.assertEqual((data["source"], data["items"]), ("unavailable", []))

    def test_news_unavailable_when_no_feed(self):
        with patch.object(news, "_from_rss", new=AsyncMock(return_value=[])), \
             patch.object(news.settings, "cryptopanic_key", ""):
            data = asyncio.run(news.latest_news())
        self.assertEqual((data["source"], data["items"]), ("unavailable", []))


if __name__ == "__main__":
    unittest.main()
