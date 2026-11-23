"""UTC market levels calculated from observed Binance candles."""

import pandas as pd


def key_levels(candles: pd.DataFrame, price: float, atr_pct: float) -> list[dict]:
    """Return previous-day, Asia, London, and prior-week highs/lows with ATR distances."""
    if candles.empty or not {"time", "high", "low"}.issubset(candles.columns) or price <= 0 or atr_pct <= 0:
        return []

    frame = candles.copy()
    frame["time"] = pd.to_datetime(frame["time"], utc=True)
    frame = frame.sort_values("time")
    latest = frame["time"].iloc[-1].floor("h")
    current_day = latest.normalize()
    current_week = current_day - pd.Timedelta(days=current_day.weekday())
    atr = price * atr_pct / 100

    periods: list[tuple[str, pd.Timestamp, pd.Timestamp]] = [
        ("Previous day", current_day - pd.Timedelta(days=1), current_day),
        ("Prior week", current_week - pd.Timedelta(days=7), current_week),
    ]

    for label, start_hour, end_hour in (("Asia", 0, 8), ("London", 8, 16)):
        for day_offset in range(7):
            day = current_day - pd.Timedelta(days=day_offset)
            start = day + pd.Timedelta(hours=start_hour)
            end = day + pd.Timedelta(hours=end_hour)
            if end <= latest and (frame["time"] >= start).any() and (frame["time"] < end).any():
                periods.append((f"{label} session", start, end))
                break

    levels = []
    for label, start, end in periods:
        candles_in_period = frame[(frame["time"] >= start) & (frame["time"] < end)]
        if candles_in_period.empty:
            continue
        high = float(candles_in_period["high"].max())
        low = float(candles_in_period["low"].min())
        levels.append({
            "period": label,
            "reference_date": start.date().isoformat(),
            "high": high,
            "low": low,
            "high_distance_atr": round(abs(high - price) / atr, 2),
            "low_distance_atr": round(abs(low - price) / atr, 2),
            "high_side": "above" if high >= price else "below",
            "low_side": "below" if low <= price else "above",
        })
    return levels
