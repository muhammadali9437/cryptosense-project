import asyncio
import time
import unittest
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from app.main import app
from app.services import liquidations, quiver, sage


def _event(symbol: str, position: str, usd: float, age: float = 0) -> dict:
    now = time.time()
    return {"id": f"{symbol}-{usd}-{age}", "symbol": symbol, "side": "sell" if position == "long" else "buy",
            "position": position, "quantity": 1, "price": usd, "usd": usd,
            "time": int((now - age) * 1000), "received_at": now - age}


class LiquidationSnapshotTests(unittest.TestCase):
    def setUp(self):
        liquidations._events.clear()

    def tearDown(self):
        liquidations._events.clear()

    def test_totals_cover_whole_window_not_just_limit(self):
        for i in range(5):
            liquidations._events.append(_event("BTCUSDT", "long", 1000, age=600 - i))
        data = liquidations.snapshot(limit=2)
        self.assertEqual(len(data["items"]), 2)
        self.assertEqual(data["summary"]["long_liquidations_usd"], 5000)
        self.assertEqual(data["summary"]["event_count"], 5)

    def test_timeframes_symbols_and_filter(self):
        liquidations._events.append(_event("ETHUSDT", "short", 300, age=1200))
        liquidations._events.append(_event("BTCUSDT", "long", 2000, age=60))
        data = liquidations.snapshot()
        self.assertEqual(data["timeframes"]["5m"]["total_usd"], 2000)
        self.assertEqual(data["timeframes"]["1h"]["total_usd"], 2300)
        self.assertEqual(data["top_symbols"][0]["symbol"], "BTCUSDT")
        self.assertEqual(data["largest"]["usd"], 2000)
        self.assertIn("longs", data["summary"]["read"].lower())
        only_eth = liquidations.snapshot(symbol="ethusdt")
        self.assertEqual(only_eth["summary"]["total_usd"], 300)


class QuiverTests(unittest.TestCase):
    def test_parse_congress_filters_tickers_and_dates(self):
        since = datetime.now(timezone.utc) - timedelta(days=90)
        recent = (datetime.now(timezone.utc) - timedelta(days=3)).strftime("%Y-%m-%dT00:00:00")
        rows = [
            {"Ticker": "COIN", "Representative": "A", "Party": "D", "Transaction": "Purchase",
             "TransactionDate": recent, "ReportDate": recent, "Amount": "1001", "Range": "$1,001 - $15,000"},
            {"Ticker": "AAPL", "Representative": "B", "Party": "R", "Transaction": "Sale",
             "TransactionDate": recent},
            {"Ticker": "MSTR", "Representative": "C", "Party": "R", "Transaction": "Sale (Full)",
             "TransactionDate": "2001-01-01T00:00:00"},
        ]
        out = quiver.parse_congress(rows, {"COIN", "MSTR"}, since)
        self.assertEqual([t["ticker"] for t in out], ["COIN"])
        self.assertEqual(out[0]["side"], "buy")
        self.assertEqual(out[0]["amount_min_usd"], 1001)

    def test_parse_insiders_keeps_open_market_trades(self):
        since = datetime.now(timezone.utc) - timedelta(days=90)
        day = (datetime.now(timezone.utc) - timedelta(days=1)).strftime("%Y-%m-%d")
        rows = [
            {"Ticker": "MARA", "Name": "X", "TransactionCode": "S", "Date": day, "Shares": 100, "PricePerShare": 20},
            {"Ticker": "MARA", "Name": "Y", "TransactionCode": "A", "Date": day, "Shares": 999, "PricePerShare": 1},
        ]
        out = quiver.parse_insiders(rows, since)
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]["usd"], 2000)
        self.assertEqual(out[0]["side"], "sell")

    def test_endpoint_without_key_is_unavailable(self):
        with patch.object(quiver.settings, "quiver_api_key", ""):
            body = TestClient(app).get("/api/quiver").json()
        self.assertEqual(body["source"], "unavailable")
        self.assertEqual(body["status"]["congress"], "no_key")


class SageClaudeTests(unittest.TestCase):
    def test_claude_used_first_when_key_set(self):
        with (
            patch.object(sage.settings, "anthropic_api_key", "test"),
            patch.object(sage.kb, "search", return_value=[]),
            patch.object(sage, "_claude", new=AsyncMock(return_value="Claude says hi")),
            patch.object(sage, "_llm", new=AsyncMock(return_value="groq")) as groq,
        ):
            answer, source, _ = asyncio.run(sage.answer("BTC?", {}))
        self.assertEqual((answer, source), ("Claude says hi", "llm"))
        groq.assert_not_called()

    def test_falls_back_to_groq_then_rules(self):
        with (
            patch.object(sage.settings, "anthropic_api_key", "test"),
            patch.object(sage.settings, "llm_api_key", "test"),
            patch.object(sage.kb, "search", return_value=[]),
            patch.object(sage, "_claude", new=AsyncMock(side_effect=RuntimeError("down"))),
            patch.object(sage, "_llm", new=AsyncMock(return_value="groq answer")),
        ):
            self.assertEqual(asyncio.run(sage.answer("BTC?", {}))[0], "groq answer")
        with (
            patch.object(sage.settings, "anthropic_api_key", "test"),
            patch.object(sage.settings, "llm_api_key", ""),
            patch.object(sage.kb, "search", return_value=[]),
            patch.object(sage, "_claude", new=AsyncMock(side_effect=RuntimeError("down"))),
        ):
            self.assertEqual(asyncio.run(sage.answer("hello", {}))[1], "rules")

    def test_claude_refusal_raises_so_fallback_runs(self):
        fake = SimpleNamespace(stop_reason="refusal", content=[])
        client = SimpleNamespace(beta=SimpleNamespace(messages=SimpleNamespace(create=AsyncMock(return_value=fake))))
        with patch.object(sage, "_claude_api", return_value=client):
            with self.assertRaises(ValueError):
                asyncio.run(sage._claude("q", {}, []))

    def test_claude_request_shape(self):
        fake = SimpleNamespace(stop_reason="end_turn", content=[
            SimpleNamespace(type="thinking", thinking=""), SimpleNamespace(type="text", text=" Answer [1] ")])
        create = AsyncMock(return_value=fake)
        client = SimpleNamespace(beta=SimpleNamespace(messages=SimpleNamespace(create=create)))
        with patch.object(sage, "_claude_api", return_value=client):
            self.assertEqual(asyncio.run(sage._claude("q", {}, [])), "Answer [1]")
        kwargs = create.call_args.kwargs
        self.assertEqual(kwargs["model"], sage.settings.claude_model)
        self.assertEqual(kwargs["system"], sage.SYSTEM_PROMPT)
        self.assertNotIn("temperature", kwargs)


if __name__ == "__main__":
    unittest.main()
