"""Optional Telegram alert delivery for one operator-configured chat."""
import logging

import httpx

from ..config import settings

log = logging.getLogger("cryptosense.telegram")


async def send_alert(message: str) -> bool:
    if not settings.telegram_bot_token or not settings.telegram_chat_id:
        return False

    url = f"https://api.telegram.org/bot{settings.telegram_bot_token}/sendMessage"
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.post(url, json={
                "chat_id": settings.telegram_chat_id,
                "text": message[:4000],
                "disable_web_page_preview": True,
            })
            response.raise_for_status()
            result = response.json()
            if not result.get("ok"):
                raise RuntimeError("Telegram rejected the message.")
    except (httpx.HTTPError, ValueError, RuntimeError) as exc:
        # Never log the request URL: it contains the bot token.
        log.warning("Telegram alert delivery failed (%s).", exc.__class__.__name__)
        return False
    return True
