import time
import unittest
from unittest.mock import AsyncMock, patch

from app.services import watcher


class ExternalAlertTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        watcher._external_alert_ids.clear()
        watcher._external_alert_id_set.clear()

    async def test_only_recent_large_tracked_liquidations_alert_once(self):
        snapshot = {
            "connected": True,
            "items": [
                {
                    "id": "large-live",
                    "symbol": "BTCUSDT",
                    "usd": 1_500_000,
                    "position": "long",
                    "price": 65_000,
                    "received_at": time.time(),
                },
                {
                    "id": "small",
                    "symbol": "BTCUSDT",
                    "usd": 500_000,
                    "position": "short",
                    "price": 65_000,
                    "received_at": time.time(),
                },
                {
                    "id": "old",
                    "symbol": "BTCUSDT",
                    "usd": 2_000_000,
                    "position": "long",
                    "price": 65_000,
                    "received_at": time.time() - 300,
                },
                {
                    "id": "untracked",
                    "symbol": "OTHERUSDT",
                    "usd": 2_000_000,
                    "position": "long",
                    "price": 1,
                    "received_at": time.time(),
                },
            ],
        }
        with (
            patch.object(watcher.liquidations, "snapshot", return_value=snapshot),
            patch.object(watcher.settings, "whale_alert_key", ""),
            patch.object(watcher.settings, "alert_check_seconds", 30),
            patch.object(watcher.settings, "liquidation_alert_usd", 1_000_000),
        ):
            first = await watcher._external_alert_messages()
            self.assertEqual(len(first), 1)
            self.assertIn("BTCUSDT", first[0][1])
            watcher._remember_external_alert(first[0][0])
            self.assertEqual(await watcher._external_alert_messages(), [])

    async def test_demo_whale_items_are_never_sent_as_live_alerts(self):
        with (
            patch.object(watcher.liquidations, "snapshot", return_value={"connected": False, "items": []}),
            patch.object(watcher.settings, "whale_alert_key", "configured"),
            patch.object(watcher, "whales") as whale_service,
        ):
            whale_service.latest_whales = AsyncMock(return_value={
                "source": "demo",
                "items": [{"id": "demo-1", "usd": 10_000_000}],
            })
            self.assertEqual(await watcher._external_alert_messages(), [])


if __name__ == "__main__":
    unittest.main()
