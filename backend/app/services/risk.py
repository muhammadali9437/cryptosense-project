"""AI risk score: how risky does a coin look over the next 24 hours? (0-100 %)

The score is built from seven transparent factors. Their maximum points add up to 100,
so a reader can see exactly WHY a coin got its number:

    volatility 30 | trend 15 | AI model view 15 | RSI stretch 10 | funding 10 | mood 10 | Bitcoin 10

Levels: below 35 = low, 35 to 59 = moderate, 60 or more = high.
"""

LOW_BELOW = 35
HIGH_FROM = 60


def _clamp01(x: float) -> float:
    return max(0.0, min(1.0, x))


def level_of(pct: float) -> str:
    return "low" if pct < LOW_BELOW else "high" if pct >= HIGH_FROM else "moderate"


def _bearish_probability(signal: dict) -> float:
    """The ensemble's (uncalibrated) bearish-class probability. Signals only exist when a
    trained model produced them, so there is no made-up fallback value."""
    return float(signal["probabilities"]["bearish"])


def score_from(signal: dict) -> dict:
    ind = signal["indicators"]
    atr, sma50 = float(ind["atr_pct"]), float(ind["sma50_dist"])
    rsi, funding = float(ind["rsi_14"]), float(ind["funding_rate"])
    fng, btc = float(ind["fng"]), float(ind["btc_sma50_dist"])
    p_bear = _bearish_probability(signal)

    factors: list[dict] = []

    def add(name: str, max_pts: float, x: float, note: str) -> None:
        factors.append({"name": name, "points": round(_clamp01(x) * max_pts, 1), "max": max_pts, "note": note})

    add("Price swings", 30, atr / 1.5,
        f"Typical move is {atr:.2f}% per hour. "
        + ("Very jumpy." if atr > 1.0 else "Moderately active." if atr > 0.5 else "Fairly calm."))

    add("Trend", 15, (-sma50 / 5) if sma50 < 0 else 0,
        f"Price is {abs(sma50):.1f}% below its 50-hour average, so sellers are ahead."
        if sma50 < 0 else f"Price is {sma50:.1f}% above its 50-hour average, so the trend is holding.")

    add("AI model view", 15, p_bear,
        f"The AI ensemble's bearish score is {p_bear * 100:.0f}% for the next 24 hours "
        "(a raw model score, not a calibrated probability).")

    dev = abs(rsi - 50)
    add("Momentum stretch", 10, (dev - 20) / 30,
        f"RSI is {rsi:.0f}: "
        + ("the rise is stretched, so a pullback is common." if rsi >= 70
           else "the fall is stretched, so sellers may be tiring but the drop is fast." if rsi <= 30
           else "a normal reading, neither side is exhausted."))

    add("Crowded trades", 10, abs(funding) / 0.1,
        f"Futures funding is {funding:.3f}%. "
        + ("Many traders lean the same way, which often ends in a shake-out." if abs(funding) > 0.05
           else "Traders are not heavily one-sided."))

    mood = "extreme greed" if fng >= 75 else "extreme fear" if fng <= 25 else "a balanced mood"
    add("Market mood", 10, (abs(fng - 50) - 25) / 25,
        f"Fear & Greed is {fng:.0f} ({mood}). Extremes in either direction raise the risk of sharp reversals.")

    add("Bitcoin trend", 10, (-btc / 3) if btc < 0 else 0,
        "Bitcoin is trending down, which usually drags other coins." if btc < -1
        else "Bitcoin is steady or rising, which supports the market.")

    total = round(sum(f["points"] for f in factors), 1)
    level = level_of(total)
    base = signal["symbol"].replace("USDT", "")
    top = max(factors, key=lambda f: f["points"] / f["max"])
    advice = {
        "low": "Conditions look calm, but a stop-loss is still a good habit.",
        "moderate": "Many traders use smaller positions and a stop-loss when risk is in this range.",
        "high": "Many traders wait or use a very small position when risk is this high.",
    }[level]
    return {
        "symbol": signal["symbol"],
        "risk_pct": total,
        "level": level,
        "horizon": signal.get("horizon", "Next 24 hours"),
        "model": signal.get("model", ""),
        "summary": f"{base} risk is {level} at {total:.0f}%. Biggest driver: {top['name'].lower()}. {advice}",
        "factors": factors,
        "live": bool(signal.get("live", False)),
        "generated_at": signal.get("generated_at"),
    }


def portfolio_risk(holdings: list[dict], risks: dict[str, dict]) -> dict:
    """Value-weighted risk of a user's portfolio. holdings: [{symbol, value}]."""
    rated = [(h, risks[h["symbol"]]) for h in holdings if h["symbol"] in risks and h["value"] > 0]
    total_value = sum(h["value"] for h in holdings)
    rated_value = sum(h["value"] for h, _ in rated)
    if not rated or total_value <= 0:
        return {"risk_pct": 0.0, "level": "low", "rated_share_pct": 0.0, "high_risk_share_pct": 0.0,
                "biggest_holding": None, "biggest_share_pct": 0.0,
                "tips": ["Add coins to your portfolio to see its risk."]}
    weighted = sum(h["value"] * r["risk_pct"] for h, r in rated) / rated_value
    high_value = sum(h["value"] for h, r in rated if r["level"] == "high")
    biggest = max(holdings, key=lambda h: h["value"])
    share = biggest["value"] / total_value * 100
    tips = []
    if share > 50:
        tips.append(f"{biggest['symbol'].replace('USDT', '')} is {share:.0f}% of your portfolio. "
                    "Spreading across more coins reduces the damage of one bad week.")
    if high_value / rated_value > 0.3:
        tips.append(f"{high_value / rated_value * 100:.0f}% of your money is in high-risk coins right now.")
    if rated_value < total_value:
        tips.append("Some of your coins are not tracked by the AI, so their risk is not included.")
    if not tips:
        tips.append("Your portfolio risk looks balanced. Keep your stop-losses in place.")
    return {
        "risk_pct": round(weighted, 1),
        "level": level_of(weighted),
        "rated_share_pct": round(rated_value / total_value * 100, 1),
        "high_risk_share_pct": round(high_value / rated_value * 100, 1),
        "biggest_holding": biggest["symbol"],
        "biggest_share_pct": round(share, 1),
        "tips": tips,
    }