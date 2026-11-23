import unittest
from unittest.mock import AsyncMock, Mock, patch

from app.services.telegram import send_alert


class TelegramTests(unittest.IsolatedAsyncioTestCase):
    async def test_delivery_is_skipped_when_credentials_are_missing(self):
        with (
            patch("app.services.telegram.settings.telegram_bot_token", ""),
            patch("app.services.telegram.settings.telegram_chat_id", ""),
        ):
            self.assertFalse(await send_alert("Test alert"))

    async def test_configured_alert_is_sent_to_the_selected_chat(self):
        response = Mock()
        response.json.return_value = {"ok": True}
        client = AsyncMock()
        client.post.return_value = response
        session = AsyncMock()
        session.__aenter__.return_value = client
        with (
            patch("app.services.telegram.settings.telegram_bot_token", "test-token"),
            patch("app.services.telegram.settings.telegram_chat_id", "chat-123"),
            patch("app.services.telegram.httpx.AsyncClient", return_value=session),
        ):
            self.assertTrue(await send_alert("BTC crossed a level"))

        client.post.assert_awaited_once_with(
            "https://api.telegram.org/bottest-token/sendMessage",
            json={
                "chat_id": "chat-123",
                "text": "BTC crossed a level",
                "disable_web_page_preview": True,
            },
        )


if __name__ == "__main__":
    unittest.main()
