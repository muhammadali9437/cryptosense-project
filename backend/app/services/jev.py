"""Jev by TypeSafe AI: a "System One" decision model.

Jev does not write text. It reads a piece of text (the "state") and answers
typed questions in one fast call:
  - Choice: pick one option      -> choice + probability per option + confidence
  - Score:  place on a scale     -> score (0..n-1) + probabilities + confidence
  - Noul:   yes/no               -> probability of yes

In CryptoSense it judges every news headline: bullish / bearish / neutral,
and how big its market impact is likely to be. If TYPESAFE_API_KEY is empty
or the API fails, the app falls back to FinBERT / VADER automatically.
API: POST https://api.typesafe.ai/v1/systemone  (docs.typesafe.ai)
"""
import asyncio
import logging

import httpx

from ..config import settings

log = logging.getLogger("cryptosense.jev")

IMPACT_LEVELS = [
    "Minor: routine news, unlikely to move prices",
    "Moderate: could move the named coins for a few hours",
    "Major: could move the whole crypto market",
]
IMPACT_LABELS = ["minor", "moderate", "major"]

NEWS_QUESTIONS = {
    "sentiment": {
        "type": "choice",
        "instructions": "How is this crypto news headline likely to affect the price of the coins it mentions?",
        "criteria": {
            "bullish": "Good news that is likely to push prices up",
            "bearish": "Bad news that is likely to push prices down",
            "neutral": "Informational news with no clear price direction",
        },
    },
    "impact": {
        "type": "score",
        "instructions": "How large is the likely market impact of this news?",
        "criteria": IMPACT_LEVELS,
    },
}


def available() -> bool:
    return bool(settings.typesafe_api_key.strip())


async def decide(client: httpx.AsyncClient, state: str, questions: dict) -> dict:
    """One Jev request. Returns the 'answers' object."""
    r = await client.post(
        settings.typesafe_url,
        headers={"Authorization": f"Bearer {settings.typesafe_api_key.strip()}"},
        json={"state": state[:6000], "model": settings.jev_model, "questions": questions},
    )
    r.raise_for_status()
    return r.json()["answers"]


def _news_result(answers: dict) -> dict:
    s = answers["sentiment"]
    probs = s.get("probabilities", {})
    impact = answers.get("impact", {})
    level = int(round(float(impact.get("score", 0))))
    level = max(0, min(level, len(IMPACT_LABELS) - 1))
    return {
        "label": s["choice"],
        "score": round(float(probs.get("bullish", 0)) - float(probs.get("bearish", 0)), 3),
        "confidence": round(float(s.get("confidence", 0)), 3),
        "impact": IMPACT_LABELS[level],
        "impact_score": round(float(impact.get("score", 0)), 2),
        "model": "Jev",
    }


AUTH_ERRORS = {401, 402, 403}
_blocked_reason: str | None = None  # set once TypeSafe rejects the key, so we stop retrying


async def judge_news(texts: list[str]) -> list[dict | None]:
    """Jev verdict for each headline (None where the call failed).
    One test call goes first: if TypeSafe rejects the key (401/402/403, e.g. no credits),
    Jev is switched off until the server restarts and only one clear message is logged."""
    global _blocked_reason
    if not available() or not texts or _blocked_reason:
        return [None] * len(texts)

    async with httpx.AsyncClient(timeout=20) as client:
        try:
            first = _news_result(await decide(client, texts[0], NEWS_QUESTIONS))
        except httpx.HTTPStatusError as e:
            if e.response.status_code in AUTH_ERRORS:
                _blocked_reason = f"HTTP {e.response.status_code}"
                log.warning(
                    "Jev turned off: TypeSafe rejected the API key (%s). Usually this means the account "
                    "has no credits. News will use %s instead. Restart the server after fixing the key.",
                    _blocked_reason, "FinBERT/VADER",
                )
                return [None] * len(texts)
            log.warning("Jev call failed: %s", e)
            first = None
        except Exception as e:
            log.warning("Jev call failed: %s", e)
            first = None

        sem = asyncio.Semaphore(8)

        async def one(text: str):
            async with sem:
                try:
                    return _news_result(await decide(client, text, NEWS_QUESTIONS))
                except Exception as e:
                    log.warning("Jev call failed: %s", e)
                    return None

        rest = await asyncio.gather(*(one(t) for t in texts[1:]))
    results = [first, *rest]
    ok = sum(r is not None for r in results)
    log.info("Jev judged %s/%s headlines", ok, len(texts))
    return results


def status() -> dict:
    """For /api/news/compare and debugging."""
    if not available():
        return {"enabled": False, "reason": "No TYPESAFE_API_KEY in backend/.env"}
    if _blocked_reason:
        return {"enabled": False, "reason": f"TypeSafe rejected the key ({_blocked_reason}); add credits or a new key"}
    return {"enabled": True, "reason": None}
