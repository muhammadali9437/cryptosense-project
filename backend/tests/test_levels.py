import unittest

import pandas as pd

from app.services.levels import key_levels


class KeyLevelTests(unittest.TestCase):
    def test_returns_observed_utc_levels_and_atr_distances(self):
        times = pd.date_range("2024-01-07", "2024-01-15 18:00", freq="h", tz="UTC")
        candles = pd.DataFrame({
            "time": times,
            "high": [100.0 + i for i in range(len(times))],
            "low": [90.0 + i for i in range(len(times))],
        })

        levels = key_levels(candles, price=300.0, atr_pct=1.0)
        by_period = {level["period"]: level for level in levels}

        self.assertEqual(set(by_period), {
            "Previous day", "Prior week", "Asia session", "London session",
        })
        self.assertEqual(by_period["Previous day"]["reference_date"], "2024-01-14")
        self.assertEqual(by_period["Prior week"]["reference_date"], "2024-01-08")
        self.assertEqual(by_period["Asia session"]["reference_date"], "2024-01-15")
        self.assertEqual(by_period["London session"]["reference_date"], "2024-01-15")
        self.assertEqual(by_period["Asia session"]["high"], 100 + times.get_loc("2024-01-15 07:00"))
        self.assertEqual(by_period["London session"]["high"], 100 + times.get_loc("2024-01-15 15:00"))
        self.assertAlmostEqual(
            by_period["Asia session"]["high_distance_atr"],
            round(abs(by_period["Asia session"]["high"] - 300) / 3, 2),
        )

    def test_empty_or_invalid_market_snapshot_has_no_levels(self):
        empty = pd.DataFrame(columns=["time", "high", "low"])
        self.assertEqual(key_levels(empty, price=100, atr_pct=1), [])
        self.assertEqual(key_levels(pd.DataFrame({"time": ["2024-01-01"]}), 100, 1), [])
        self.assertEqual(key_levels(pd.DataFrame({"time": ["2024-01-01"]}), 0, 1), [])


if __name__ == "__main__":
    unittest.main()
