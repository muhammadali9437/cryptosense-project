import unittest
from unittest.mock import AsyncMock, patch

from app import test_telegram


class TelegramTestCommandTests(unittest.IsolatedAsyncioTestCase):
    async def test_missing_credentials_do_not_send_or_print_values(self):
        with (
            patch.object(test_telegram.settings, "telegram_bot_token", ""),
            patch.object(test_telegram.settings, "telegram_chat_id", ""),
            patch.object(test_telegram, "send_alert", new=AsyncMock()) as send,
            patch("builtins.print") as print_message,
        ):
            result = await test_telegram.run_test()

        self.assertEqual(result, 1)
        send.assert_not_awaited()
        printed = " ".join(str(arg) for call in print_message.call_args_list for arg in call.args)
        self.assertIn("TELEGRAM_BOT_TOKEN", printed)
        self.assertIn("TELEGRAM_CHAT_ID", printed)

    async def test_configured_credentials_send_one_fixed_test_message(self):
        with (
            patch.object(test_telegram.settings, "telegram_bot_token", "hidden-token"),
            patch.object(test_telegram.settings, "telegram_chat_id", "hidden-chat"),
            patch.object(test_telegram, "send_alert", new=AsyncMock(return_value=True)) as send,
            patch("builtins.print") as print_message,
        ):
            result = await test_telegram.run_test()

        self.assertEqual(result, 0)
        send.assert_awaited_once_with(test_telegram.TEST_MESSAGE)
        output = " ".join(str(arg) for call in print_message.call_args_list for arg in call.args)
        self.assertNotIn("hidden-token", output)
        self.assertNotIn("hidden-chat", output)


if __name__ == "__main__":
    unittest.main()
