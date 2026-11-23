import unittest
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from app.main import app


class RiskCopilotTests(unittest.TestCase):
    def test_endpoint_includes_observed_level_data(self):
        signal = {
            "votes": {},
            "key_levels": [{
                "period": "Prior week",
                "reference_date": "2024-01-08",
                "high": 48000,
                "low": 42000,
                "high_distance_atr": 1.2,
                "low_distance_atr": 0.8,
                "high_side": "above",
                "low_side": "below",
            }],
            "key_levels_source": "binance",
            "key_levels_note": "Observed UTC levels.",
        }
        with (
            patch("app.routers.risk.signal_for", new=AsyncMock(return_value=signal)),
            patch("app.routers.risk.historical_twins", new=AsyncMock(return_value=[])),
        ):
            response = TestClient(app).get("/api/risk/BTCUSDT/copilot")

        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertEqual(body["key_levels"], signal["key_levels"])
        self.assertEqual(body["key_levels_source"], "binance")


if __name__ == "__main__":
    unittest.main()
