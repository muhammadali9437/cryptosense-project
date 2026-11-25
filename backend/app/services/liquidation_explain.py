"""Builds the facts and the deterministic answers for the liquidation explanation panel.

The rules-based answers are always computed; an LLM may only rephrase them (explainer.py).
"""

QUESTIONS = [
    "Why did liquidation activity suddenly increase?",
    "Are observed long or short liquidations dominating?",
    "Which cryptocurrencies have unusual liquidation activity?",
    "Is price moving alongside the liquidation activity?",
    "Is open interest increasing or decreasing?",
    "What other market signals support or contradict the analysis?",
]


def _usd(v: float | None) -> str:
    if v is None:
        return "n/a"
    if v >= 1e9:
        return f"${v / 1e9:.2f}B"
    if v >= 1e6:
        return f"${v / 1e6:.2f}M"
    if v >= 1e3:
        return f"${v / 1e3:.0f}K"
    return f"${v:,.0f}"


def build_facts(stats: dict, anomalies: dict, context: dict | None) -> dict:
    s = stats["summary"]
    return {
        "data_source": "observed Binance forceOrder stream (max one event per coin per second)",
        "window": stats["window"],
        "symbol_filter": stats.get("symbol") or stats.get("group") or "all",
        "long_usd": s["long_usd"], "short_usd": s["short_usd"], "total_usd": s["total_usd"],
        "long_share_pct": s["long_share_pct"], "event_count": s["event_count"],
        "most_affected": (stats.get("most_affected") or {}).get("symbol"),
        "largest_event": ({k: stats["largest"][0][k] for k in ("symbol", "position", "usd")}
                          if stats.get("largest") else None),
        "window_fully_observed": stats["coverage"]["window_fully_observed"],
        "anomaly_status": anomalies.get("status"),
        "anomalies": [{k: a.get(k) for k in ("type", "symbol", "severity", "current_usd", "baseline_median_usd",
                                             "robust_z", "event_count", "shift_pts")}
                      for a in anomalies.get("anomalies", [])],
        "context": None if not context else {
            "symbol": context["symbol"], "window": context["window"],
            "price_change_pct": (context.get("market") or {}).get("price_change_pct"),
            "price_direction": context["price_direction"],
            "volume_vs_prior_window": (context.get("market") or {}).get("volume_vs_prior_window"),
            "atr_pct": (context.get("market") or {}).get("atr_pct"),
            "oi_change_pct": (context.get("open_interest") or {}).get("oi_change_pct"),
            "open_interest_direction": context["open_interest_direction"],
            "funding_rate": context.get("funding_rate"),
            "scenarios": [{k: sc[k] for k in ("name", "supporting", "contradicting")} for sc in context["scenarios"]],
            "unavailable": context.get("unavailable", []),
        },
    }


def rules_answers(facts: dict) -> list[dict]:
    anomalies = facts["anomalies"]
    ctx = facts["context"]
    answers = []

    if facts["anomaly_status"] == "insufficient_baseline":
        why = "Not enough stored history yet to judge whether activity is unusual."
    elif anomalies:
        kinds = ", ".join(sorted({a["type"].replace("_", " ") for a in anomalies}))
        why = (f"Activity is unusual versus its rolling baseline ({kinds}). The data shows forced closing of "
               "leveraged positions; it does not show the original cause (news, a large order, etc.).")
    else:
        why = "No spike versus the rolling baseline: observed liquidation activity is within its normal range."
    answers.append({"question": QUESTIONS[0], "answer": why})

    share = facts["long_share_pct"]
    if share is None:
        dom = f"No observed liquidations with a USD value in the last {facts['window']}."
    elif share >= 60:
        dom = f"Longs dominate: {share:.0f}% of {_usd(facts['total_usd'])} observed was long liquidations (forced sells)."
    elif share <= 40:
        dom = f"Shorts dominate: {100 - share:.0f}% of {_usd(facts['total_usd'])} observed was short liquidations (forced buys)."
    else:
        dom = f"Roughly balanced: {share:.0f}% longs of {_usd(facts['total_usd'])} observed."
    answers.append({"question": QUESTIONS[1], "answer": dom})

    coins = sorted({a["symbol"] for a in anomalies if a.get("symbol")})
    answers.append({"question": QUESTIONS[2], "answer": (
        "Unusual activity on: " + ", ".join(c.replace("USDT", "") for c in coins) + "."
        if coins else
        f"No single coin is unusual. Most affected by value: {(facts['most_affected'] or 'none').replace('USDT', '')}.")})

    if not ctx or ctx["price_change_pct"] is None:
        price = "Price data is unavailable for this comparison."
    else:
        price = (f"{ctx['symbol'].replace('USDT', '')} moved {ctx['price_change_pct']:+.2f}% over {ctx['window']}, "
                 f"so its direction is '{ctx['price_direction']}' (a move smaller than one average candle range, "
                 f"{ctx['atr_pct']}%, would count as flat).")
    answers.append({"question": QUESTIONS[3], "answer": price})

    if not ctx or ctx["oi_change_pct"] is None:
        oi = "Open-interest data is unavailable."
    else:
        oi = (f"Open interest is {'increasing' if ctx['oi_change_pct'] > 0 else 'decreasing'} "
              f"({ctx['oi_change_pct']:+.2f}% over {ctx['window']}).")
    answers.append({"question": QUESTIONS[4], "answer": oi})

    if not ctx:
        other = "Pick a coin to compare liquidations with price, open interest and funding."
    else:
        parts = []
        for sc in ctx["scenarios"]:
            line = f"{sc['name']}: supported by {', '.join(sc['supporting']) or 'nothing'}"
            if sc["contradicting"]:
                line += f"; contradicted by {', '.join(sc['contradicting'])}"
            parts.append(line + ".")
        if ctx["unavailable"]:
            parts.append("Unavailable inputs: " + ", ".join(ctx["unavailable"]) + ".")
        other = " ".join(parts) + " Liquidations alone don't determine future price direction."
    answers.append({"question": QUESTIONS[5], "answer": other})
    return answers


def rules_text(answers: list[dict]) -> str:
    return "\n".join(f"- {a['answer']}" for a in answers) + (
        "\n(Figures are observed Binance stream events, not exchange-wide totals.)")
