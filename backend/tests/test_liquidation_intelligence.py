"""Liquidation intelligence: parsing, storage, windows, anomalies, context, alerts, explanations."""
import asyncio
import json
import time
import unittest
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import app
from app.models import Alert
from app.services import (explainer, liquidation_alerts, liquidation_anomaly, liquidation_context,
                          liquidation_stats, liquidation_store, liquidations)

NOW_MS = 1_795_500_000_000  # fixed "now" (UTC epoch ms) so tests are deterministic


def raw(symbol="BTCUSDT", side="SELL", z="2", ap="50000", p="49900", t=NOW_MS, status="FILLED", st=1, **extra):
    order = {"s": symbol, "S": side, "o": "LIMIT", "f": "IOC", "q": z, "p": p, "ap": ap, "X": status,
             "l": z, "z": z, "T": t, "st": st, **extra}
    return {"e": "forceOrder", "E": t, "o": order}


def event(symbol="BTCUSDT", side="SELL", usd=100_000.0, t=NOW_MS, n=0):
    e = liquidations.parse_message(raw(symbol, side, z=str(usd / 50000), ap="50000", t=t))[0]
    e["id"] = f"{e['id']}-{n}"
    e["received_at"] = t / 1000
    return e


def memory_db():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)


def reset_stream():
    liquidations._events.clear()
    liquidations._pending.clear()
    liquidations._seen_keys.clear()
    liquidations._seen_set.clear()
    liquidations._gaps.clear()


class ParsingTests(unittest.TestCase):
    def setUp(self):
        reset_stream()

    def test_sell_is_long_and_buy_is_short(self):
        long_ = liquidations.parse_message(raw(side="SELL"))[0]
        short = liquidations.parse_message(raw(side="BUY"))[0]
        self.assertEqual((long_["position"], long_["side"]), ("long", "sell"))
        self.assertEqual((short["position"], short["side"]), ("short", "buy"))

    def test_usd_uses_filled_quantity_times_average_price(self):
        e = liquidations.parse_message(raw(z="0.5", ap="60000", p="59000"))[0]
        self.assertTrue(e["usd_valid"])
        self.assertAlmostEqual(e["usd"], 30000)
        self.assertEqual((e["order_price"], e["avg_price"], e["status"]), (59000, 60000, "FILLED"))

    def test_usd_not_valid_for_coin_margined_or_non_stable_quote(self):
        cm = liquidations.parse_message(raw(symbol="BTCUSD_PERP", st=2))[0]
        self.assertFalse(cm["usd_valid"])
        self.assertEqual(cm["usd"], 0)
        no_fill = liquidations.parse_message(raw(ap="0", p="50000"))[0]
        self.assertFalse(no_fill["usd_valid"])

    def test_combined_and_list_forms(self):
        self.assertEqual(len(liquidations.parse_message({"stream": "!forceOrder@arr", "data": raw()})), 1)
        self.assertEqual(len(liquidations.parse_message([raw(), raw(side="BUY")])), 2)

    def test_invalid_and_missing_data_is_skipped(self):
        bad = [None, "x", {}, {"o": None}, raw(symbol=""), raw(side="HOLD"), raw(ap="0", p="0"),
               raw(z="0", q="0"), raw(t="not-a-time"), raw(ap="abc", p="abc")]
        for message in bad:
            self.assertEqual(liquidations.parse_message(message), [], message)
        self.assertEqual(liquidations.ingest("not json"), 0)

    def test_duplicates_are_dropped(self):
        payload = json.dumps(raw())
        self.assertEqual(liquidations.ingest(payload), 1)
        self.assertEqual(liquidations.ingest(payload), 0)
        self.assertEqual(len(liquidations.take_pending()), 1)


class ReconnectTests(unittest.TestCase):
    def setUp(self):
        reset_stream()

    def test_disconnect_then_reconnect_is_tracked(self):
        attempts = {"n": 0}

        class FakeWS:
            def __init__(self):
                self.messages = [json.dumps(raw())]

            async def __aenter__(self):
                return self

            async def __aexit__(self, *exc):
                return False

            async def recv(self):
                if self.messages:
                    return self.messages.pop()
                raise asyncio.CancelledError  # stop the endless loop once data is consumed

        def fake_connect(*args, **kwargs):
            attempts["n"] += 1
            if attempts["n"] == 1:
                raise OSError("network down")
            return FakeWS()

        async def run():
            with patch.object(liquidations.websockets, "connect", side_effect=fake_connect), \
                 patch.object(liquidations.asyncio, "sleep", new=AsyncMock()):
                with self.assertRaises(asyncio.CancelledError):
                    await liquidations.liquidation_loop()

        before = liquidations._reconnects
        asyncio.run(run())
        self.assertEqual(attempts["n"], 2)
        self.assertEqual(liquidations._reconnects, before + 1)
        self.assertIsNotNone(liquidations._gaps[-1][1])
        self.assertEqual(len(liquidations.take_pending()), 1)

    def test_gap_seconds_inside_window(self):
        liquidations._gaps.append([100.0, 160.0])
        liquidations._gaps.append([200.0, None])
        self.assertEqual(liquidations.gaps_between(120, 220), 40 + 20)


class StorageAndWindowTests(unittest.TestCase):
    def setUp(self):
        reset_stream()
        self.Session = memory_db()
        self.db = self.Session()

    def tearDown(self):
        self.db.close()

    def test_store_skips_existing_rows(self):
        e = event()
        self.assertEqual(liquidation_store.store_events(self.db, [e, e]), 1)
        self.assertEqual(liquidation_store.store_events(self.db, [e]), 0)

    def test_window_totals_ratio_and_largest(self):
        events = [
            event("BTCUSDT", "SELL", 300_000, NOW_MS - 60_000, 1),
            event("BTCUSDT", "BUY", 100_000, NOW_MS - 120_000, 2),
            event("ETHUSDT", "SELL", 50_000, NOW_MS - 10 * 60_000, 3),
            event("ETHUSDT", "SELL", 999_000, NOW_MS - 2 * 3_600_000, 4),   # outside 1h
        ]
        liquidation_store.store_events(self.db, events)
        s = liquidation_stats.window_stats(self.db, "1h", now_ms=NOW_MS)
        self.assertEqual(s["summary"]["long_usd"], 350_000)
        self.assertEqual(s["summary"]["short_usd"], 100_000)
        self.assertEqual(s["summary"]["long_short_ratio"], 3.5)
        self.assertEqual(s["summary"]["event_count"], 3)
        self.assertEqual(s["largest"][0]["usd"], 300_000)
        self.assertEqual(s["most_affected"]["symbol"], "BTCUSDT")
        self.assertEqual(s["source"], "observed_binance_stream")
        s5 = liquidation_stats.window_stats(self.db, "5m", now_ms=NOW_MS)
        self.assertEqual(s5["summary"]["total_usd"], 400_000)
        s24 = liquidation_stats.window_stats(self.db, "24h", now_ms=NOW_MS)
        self.assertEqual(s24["summary"]["event_count"], 4)

    def test_symbol_and_other_filters(self):
        liquidation_store.store_events(self.db, [event("BTCUSDT", n=1, t=NOW_MS - 1000),
                                                 event("DOGEUSDT", n=2, t=NOW_MS - 1000)])
        self.assertEqual(liquidation_stats.window_stats(self.db, "1h", "btcusdt", now_ms=NOW_MS)
                         ["summary"]["event_count"], 1)
        other = liquidation_stats.window_stats(self.db, "1h", group="other", now_ms=NOW_MS)
        self.assertEqual([r["symbol"] for r in other["by_symbol"]], ["DOGEUSDT"])

    def test_timeline_is_zero_filled_and_utc_aligned(self):
        liquidation_store.store_events(self.db, [event(usd=1000, t=NOW_MS - 30_000, n=1)])
        points = liquidation_stats.timeline(self.db, "1h", now_ms=NOW_MS)
        self.assertGreaterEqual(len(points), 30)
        self.assertTrue(all(p["t_ms"] % 120_000 == 0 for p in points))
        self.assertEqual(sum(p["long_usd"] for p in points), 1000)
        self.assertEqual(points, sorted(points, key=lambda p: p["t_ms"]))

    def test_history_pages_backwards(self):
        liquidation_store.store_events(self.db, [event(t=NOW_MS - i * 1000, n=i) for i in range(5)])
        first = liquidation_stats.history(self.db, limit=2)
        second = liquidation_stats.history(self.db, before_ms=first[-1]["time"], limit=2)
        self.assertLess(second[0]["time"], first[-1]["time"])

    def test_bad_window_rejected(self):
        with self.assertRaises(ValueError):
            liquidation_stats.window_stats(self.db, "7d")

    def test_prune_removes_old_rows(self):
        liquidation_store.store_events(self.db, [event(t=NOW_MS - 30 * 86_400_000, n=1), event(n=2)])
        self.assertEqual(liquidation_store.prune(self.db, NOW_MS), 1)


class AnomalyTests(unittest.TestCase):
    P = liquidation_anomaly.Params(z=4, min_usd=100_000, burst_events=10, imbalance_pts=35)

    def baseline(self, n=24, level=20_000.0):
        return {"long": [level] * n, "short": [level] * n, "by_symbol": {"BTCUSDT": [level] * n},
                "long_total": level * n, "short_total": level * n}

    def test_spike_detected_only_above_z_and_minimum(self):
        found = liquidation_anomaly.find_anomalies(
            {"long": 900_000, "short": 10_000, "by_symbol": {"BTCUSDT": 910_000}},
            self.baseline(), {}, {"long": 900_000, "short": 10_000}, self.P)
        types = {a["type"] for a in found}
        self.assertIn("long_spike", types)
        self.assertIn("total_spike", types)
        self.assertNotIn("short_spike", types)
        self.assertIn("imbalance_shift", types)
        self.assertTrue(all("not a prediction" in a["message"] for a in found))

    def test_small_amount_on_quiet_baseline_is_not_a_spike(self):
        found = liquidation_anomaly.find_anomalies(
            {"long": 50_000, "short": 0, "by_symbol": {"BTCUSDT": 50_000}},
            self.baseline(level=0.0), {}, {"long": 50_000, "short": 0}, self.P)
        self.assertEqual(found, [])

    def test_normal_activity_is_quiet(self):
        found = liquidation_anomaly.find_anomalies(
            {"long": 25_000, "short": 20_000, "by_symbol": {"BTCUSDT": 45_000}},
            self.baseline(), {}, {"long": 60_000, "short": 60_000}, self.P)
        self.assertEqual(found, [])

    def test_burst(self):
        found = liquidation_anomaly.find_anomalies(
            {"long": 0, "short": 0, "by_symbol": {}}, self.baseline(), {"SOLUSDT": 12},
            {"long": 0, "short": 0}, self.P)
        self.assertEqual(found[0]["type"], "burst")

    def test_db_detection_needs_baseline_then_finds_spike(self):
        Session = memory_db()
        with Session() as db:
            liquidation_store.store_events(db, [event(usd=10_000, t=NOW_MS - 60_000, n=1)])
            self.assertEqual(liquidation_anomaly.detect(db, now_ms=NOW_MS, params=self.P)["status"],
                             "insufficient_baseline")
            history = [event(usd=10_000, t=NOW_MS - (10 + i * 5) * 60_000, n=100 + i) for i in range(30)]
            spike = [event(usd=200_000, t=NOW_MS - (i + 1) * 20_000, n=200 + i) for i in range(6)]
            liquidation_store.store_events(db, history + spike)
            result = liquidation_anomaly.detect(db, now_ms=NOW_MS, params=self.P)
        self.assertEqual(result["status"], "ok")
        self.assertIn("long_spike", {a["type"] for a in result["anomalies"]})


class ContextTests(unittest.TestCase):
    def candles(self, closes):
        return [[0, c, c * 1.002, c * 0.998, c, 0, 0, 1000.0] for c in closes]

    def test_market_numbers_and_direction(self):
        m = liquidation_context.market_numbers(self.candles([100] * 12 + [100 + i for i in range(12)]), 12)
        self.assertGreater(m["price_change_pct"], 0)
        self.assertEqual(liquidation_context.direction(m["price_change_pct"], m["atr_pct"]), "up")
        self.assertIsNone(liquidation_context.market_numbers(self.candles([1, 2]), 12))

    def test_scenarios_never_predict_and_list_evidence(self):
        out = liquidation_context.scenarios("long", "down", "down", 0.001, 5e6, 1e5)
        self.assertEqual(out[0]["name"], "Long deleveraging")
        self.assertIn("price is down", out[0]["supporting"])
        self.assertIn("don't decide", out[0]["caveat"])
        mixed = liquidation_context.scenarios("long", "up", "flat", None, 5e6, 1e5)
        self.assertIn("price is up", mixed[0]["contradicting"])
        self.assertEqual(liquidation_context.scenarios("none", "up", "up", None, 0, 1e5)[0]["name"],
                         "No notable liquidation pressure")

    def test_unavailable_inputs_reported_not_guessed(self):
        async def fail(*a, **k):
            raise RuntimeError("down")
        with patch.object(liquidation_context.binance, "futures_klines", new=fail), \
             patch.object(liquidation_context.binance, "open_interest_hist", new=fail), \
             patch.object(liquidation_context.binance, "funding_rates", new=fail):
            ctx = asyncio.run(liquidation_context.build("BTCUSDT", "1h", 1e6, 0))
        self.assertEqual(ctx["unavailable"], ["funding", "open_interest", "price_volume"])
        self.assertIsNone(ctx["market"])
        self.assertEqual(ctx["price_direction"], "unknown")


class AlertTests(unittest.TestCase):
    def alert(self, kind, value, triggered=None):
        return Alert(id=1, user_id=1, symbol="BTCUSDT", kind=kind, value=value, active=True, triggered_at=triggered)

    def test_messages(self):
        scores = {"total_usd": 2e6, "long_usd": 2e6, "short_usd": 0, "total_z": 9, "long_z": 9, "short_z": -1,
                  "recent_15m_usd": 2e6, "long_share_shift_pts": 50}
        m = {"largest_new": {"usd": 1.5e6, "position": "long", "price": 50000}, "scores": scores}
        self.assertIn("1.50M", liquidation_alerts.message_for(self.alert("liq_large", 1e6), m))
        self.assertIsNone(liquidation_alerts.message_for(self.alert("liq_large", 2e6), m))
        self.assertIsNotNone(liquidation_alerts.message_for(self.alert("liq_spike", 4), m))
        self.assertIsNotNone(liquidation_alerts.message_for(self.alert("liq_long", 4), m))
        self.assertIsNone(liquidation_alerts.message_for(self.alert("liq_short", 4), m))
        self.assertIsNotNone(liquidation_alerts.message_for(self.alert("liq_imbal", 30), m))
        self.assertIsNone(liquidation_alerts.message_for(self.alert("liq_spike", 4), {"scores": None}))

    def test_cooldown_prevents_duplicates(self):
        now = datetime.now(timezone.utc)
        self.assertTrue(liquidation_alerts.cooling_down(self.alert("liq_large", 1, now - timedelta(minutes=1)), now))
        self.assertFalse(liquidation_alerts.cooling_down(self.alert("liq_large", 1, now - timedelta(days=1)), now))
        naive = (now - timedelta(minutes=1)).replace(tzinfo=None)  # SQLite returns naive datetimes
        self.assertTrue(liquidation_alerts.cooling_down(self.alert("liq_large", 1, naive), now))

    def test_evaluate_fires_once_then_cools_down(self):
        Session = memory_db()
        now = datetime.fromtimestamp(NOW_MS / 1000, timezone.utc)
        with Session() as db:
            liquidation_store.store_events(db, [event(usd=2e6, t=NOW_MS - 5000, n=1)])
            a = self.alert("liq_large", 1e6)
            self.assertEqual(len(liquidation_alerts.evaluate(db, [a], now)), 1)
            self.assertEqual(liquidation_alerts.evaluate(db, [a], now + timedelta(seconds=30)), [])

    def test_alert_schema_validation(self):
        from app.schemas import AlertIn
        AlertIn(symbol="BTCUSDT", kind="liq_large", value=5000)
        with self.assertRaises(ValueError):
            AlertIn(symbol="BTCUSDT", kind="liq_large", value=10)
        with self.assertRaises(ValueError):
            AlertIn(symbol="BTCUSDT", kind="liq_spike", value=80)


class ExplainerTests(unittest.TestCase):
    FACTS = {"long_usd": 1_234_567.0, "long_share_pct": 72.4, "oi_change_pct": -1.83}

    def test_grounded_numbers_pass_including_rounding_and_suffixes(self):
        text = "Longs made up 72% ($1.2M) and open interest fell 1.83% over 15 minutes."
        self.assertEqual(explainer.ungrounded_numbers(text, self.FACTS), [])

    def test_invented_numbers_are_caught(self):
        self.assertEqual(explainer.ungrounded_numbers("BTC could reach $95,000 soon.", self.FACTS), [95000])
        self.assertTrue(explainer.ungrounded_numbers("There is a 64% chance of a bounce.", self.FACTS))

    def test_llm_answer_with_invented_numbers_falls_back_to_rules(self):
        with patch.object(explainer.sage, "complete", new=AsyncMock(return_value=("Price will hit $99,999", "claude"))):
            out = asyncio.run(explainer.explain(self.FACTS, ["q"], "rules text"))
        self.assertEqual((out["text"], out["source"]), ("rules text", "rules"))
        self.assertEqual(out["rejected_numbers"], [99999])
        with patch.object(explainer.sage, "complete", new=AsyncMock(return_value=("Longs were 72%.", "claude"))):
            out = asyncio.run(explainer.explain(self.FACTS, ["q"], "rules text"))
        self.assertEqual(out["source"], "claude")
        with patch.object(explainer.sage, "complete", new=AsyncMock(return_value=None)):
            self.assertEqual(asyncio.run(explainer.explain(self.FACTS, ["q"], "r"))["source"], "rules")


class EndpointTests(unittest.TestCase):
    def setUp(self):
        reset_stream()
        self.Session = memory_db()

        def override():
            db = self.Session()
            try:
                yield db
            finally:
                db.close()
        app.dependency_overrides[get_db] = override
        with self.Session() as db:
            now = int(time.time() * 1000)
            liquidation_store.store_events(db, [event("BTCUSDT", "SELL", 500_000, now - 30_000, 1),
                                                event("ETHUSDT", "BUY", 100_000, now - 60_000, 2)])
        self.client = TestClient(app)

    def tearDown(self):
        app.dependency_overrides.clear()

    def test_stats_timeline_history_status(self):
        stats = self.client.get("/api/liquidations/stats", params={"window": "15m"}).json()
        self.assertEqual(stats["summary"]["total_usd"], 600_000)
        self.assertIn("limitation", stats["stream"])
        self.assertEqual(self.client.get("/api/liquidations/stats", params={"window": "2h"}).status_code, 422)
        tl = self.client.get("/api/liquidations/timeline", params={"window": "5m"}).json()
        self.assertEqual(tl["bucket_seconds"], 15)
        self.assertEqual(len(self.client.get("/api/liquidations/history").json()["items"]), 2)
        self.assertIn("connected", self.client.get("/api/liquidations/status").json())
        self.assertEqual(self.client.get("/api/liquidations/anomalies").json()["status"], "insufficient_baseline")

    def test_explain_uses_rules_without_llm(self):
        fake_ctx = {"symbol": "BTCUSDT", "window": "1h", "market": None, "open_interest": None,
                    "funding_rate": None, "price_direction": "unknown", "open_interest_direction": "unknown",
                    "scenarios": [], "unavailable": ["price_volume"]}
        with patch.object(liquidation_context, "build", new=AsyncMock(return_value=fake_ctx)), \
             patch.object(explainer.sage, "complete", new=AsyncMock(return_value=None)):
            body = self.client.get("/api/liquidations/explain", params={"window": "1h"}).json()
        self.assertEqual(body["source"], "rules")
        self.assertEqual(len(body["answers"]), 6)
        self.assertIn("Longs dominate", body["answers"][1]["answer"])


if __name__ == "__main__":
    unittest.main()
