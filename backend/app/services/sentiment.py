"""News sentiment: VADER + a crypto word list (headline polarity, -1..1).

Jev (services/jev.py) can judge headlines instead when TYPESAFE_API_KEY is set.
"""
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

CRYPTO_LEXICON = {
    "surge": 2.5, "surges": 2.5, "rally": 2.3, "rallies": 2.3, "soar": 2.6, "soars": 2.6,
    "bullish": 2.5, "inflows": 1.8, "adoption": 1.6, "approval": 2.0, "approves": 2.0,
    "record": 1.5, "breakout": 2.0, "upgrade": 1.5, "partnership": 1.5,
    "plunge": -2.8, "plunges": -2.8, "crash": -3.0, "crashes": -3.0, "dump": -2.4,
    "bearish": -2.5, "outflows": -1.8, "hack": -3.0, "hacked": -3.0, "exploit": -2.8,
    "ban": -2.5, "bans": -2.5, "lawsuit": -2.2, "sues": -2.2, "fraud": -3.0,
    "liquidations": -2.0, "sell-off": -2.4, "selloff": -2.4, "slump": -2.3,
}

_vader = SentimentIntensityAnalyzer()
_vader.lexicon.update(CRYPTO_LEXICON)


def _label(score: float) -> str:
    return "bullish" if score > 0.15 else "bearish" if score < -0.15 else "neutral"


def analyze(texts: list[str]) -> list[dict]:
    """Returns one {label, score (-1..1), model} per text."""
    if not texts:
        return []
    res = []
    for t in texts:
        score = _vader.polarity_scores(t)["compound"]
        res.append({"label": _label(score), "score": round(score, 3), "model": "VADER"})
    return res


def engine() -> str:
    return "VADER"
