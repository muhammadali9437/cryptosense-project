"""Send one safe test message using the local Telegram settings."""
import asyncio

from .config import settings
from .services.telegram import send_alert

TEST_MESSAGE = "CryptoSense test: Telegram alerts are connected."


async def run_test() -> int:
    missing = [
        name for name, value in (
            ("TELEGRAM_BOT_TOKEN", settings.telegram_bot_token),
            ("TELEGRAM_CHAT_ID", settings.telegram_chat_id),
        )
        if not value
    ]
    if missing:
        print("Telegram is not configured. Set " + " and ".join(missing) + " in backend\\.env.")
        return 1

    if not await send_alert(TEST_MESSAGE):
        print("Telegram test failed. Check the bot token, chat ID, and backend log warning.")
        return 1

    print("Telegram test message sent successfully.")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(run_test()))
