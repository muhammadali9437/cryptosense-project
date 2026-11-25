"""Quiver Quantitative: "smart money" trades in crypto-linked US stocks.

Quiver has no crypto wallet data. It does track US Congress members' stock trades and
SEC Form 4 insider trades, which we filter to companies and ETFs whose price follows
crypto (COIN, MSTR, miners, spot-bitcoin ETFs...). Set QUIVER_API_KEY to enable it.
Without a key, or if Quiver fails, the API reports "unavailable"; no demo data is shown.
Insider trades need a Quiver Trader plan or higher (Hobbyist plans get HTTP 403).
"""
import asyncio
import logging
from datetime import datetime, timedelta, timezone

import httpx

from ..config import settings
from .cache import cached

log = logging.getLogger("cryptosense.quiver")

LOOKBACK_DAYS = 90
CACHE_SECONDS = 15 * 60

# Form 4 transaction codes that reflect the insider's own decision to trade.
INSIDER_CODES = {"P": "Open-market purchase", "S": "Open-market sale"}


def _get_headers() -> dict:
    return {"Authorization": f"Bearer {settings.quiver_api_key}", "Accept": "application/json"}


def _parse_date(value) -> datetime | None:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        try:
            dt = datetime.strptime(str(value)[:10], "%Y-%m-%d")
        except ValueError:
            return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _num(value) -> float:
    try:
        return float(str(value).replace("$", "").replace(",", ""))
    except (TypeError, ValueError):
        return 0.0


def _status_of(exc: Exception) -> str:
    if isinstance(exc, httpx.HTTPStatusError):
        code = exc.response.status_code
        if code in (401, 403):
            return "plan_required" if code == 403 else "bad_key"
        return f"http_{code}"
    return "unreachable"


def parse_congress(rows: list[dict], tickers: set[str], since: datetime) -> list[dict]:
    out = []
    for r in rows:
        ticker = str(r.get("Ticker") or "").upper()
        when = _parse_date(r.get("TransactionDate")) or _parse_date(r.get("ReportDate"))
        if ticker not in tickers or not when or when < since:
            continue
        transaction = str(r.get("Transaction") or "")
        out.append({
            "ticker": ticker,
            "who": r.get("Representative") or "Unknown",
            "party": r.get("Party") or "",
            "chamber": r.get("House") or "",
            "side": "buy" if transaction.lower().startswith("purchase") else "sell",
            "range": r.get("Range") or "",
            "amount_min_usd": _num(r.get("Amount")),
            "traded_at": when.isoformat(),
            "reported_at": (_parse_date(r.get("ReportDate")) or when).isoformat(),
        })
    out.sort(key=lambda t: t["traded_at"], reverse=True)
    return out


def parse_insiders(rows: list[dict], since: datetime) -> list[dict]:
    out = []
    for r in rows:
        code = str(r.get("TransactionCode") or "").upper()
        when = _parse_date(r.get("Date"))
        if code not in INSIDER_CODES or not when or when < since:
            continue
        shares, price = _num(r.get("Shares")), _num(r.get("PricePerShare"))
        out.append({
            "ticker": str(r.get("Ticker") or "").upper(),
            "who": r.get("Name") or "Unknown",
            "title": r.get("officerTitle") or ("Director" if r.get("isDirector") else ""),
            "side": "buy" if code == "P" else "sell",
            "kind": INSIDER_CODES[code],
            "shares": shares,
            "price": price,
            "usd": round(shares * price, 2),
            "traded_at": when.isoformat(),
        })
    out.sort(key=lambda t: t["traded_at"], reverse=True)
    return out


def summarize(congress: list[dict], insiders: list[dict], tickers: list[str]) -> dict:
    per_ticker = {t: {"ticker": t, "congress_buys": 0, "congress_sells": 0,
                      "insider_buy_usd": 0.0, "insider_sell_usd": 0.0} for t in tickers}
    for t in congress:
        row = per_ticker.get(t["ticker"])
        if row:
            row["congress_buys" if t["side"] == "buy" else "congress_sells"] += 1
    for t in insiders:
        row = per_ticker.get(t["ticker"])
        if row:
            row["insider_buy_usd" if t["side"] == "buy" else "insider_sell_usd"] += t["usd"]
    buys = sum(r["congress_buys"] for r in per_ticker.values())
    sells = sum(r["congress_sells"] for r in per_ticker.values())
    if buys + sells == 0:
        read = f"No Congress trades in crypto-linked stocks in the last {LOOKBACK_DAYS} days."
    elif buys > sells * 1.5:
        read = "Members of Congress have mostly been buying crypto-linked stocks recently."
    elif sells > buys * 1.5:
        read = "Members of Congress have mostly been selling crypto-linked stocks recently."
    else:
        read = "Congress trades in crypto-linked stocks are mixed between buys and sells."
    read += (" Disclosures can arrive up to 45 days after the trade, so treat this as slow-moving "
             "context, not a trading signal.")
    active = [r for r in per_ticker.values()
              if r["congress_buys"] or r["congress_sells"] or r["insider_buy_usd"] or r["insider_sell_usd"]]
    return {"congress_buys": buys, "congress_sells": sells, "read": read, "tickers": active}


async def _fetch(client: httpx.AsyncClient, path: str, params: dict | None = None) -> list[dict]:
    r = await client.get(f"{settings.quiver_base.rstrip('/')}{path}", params=params, headers=_get_headers())
    r.raise_for_status()
    data = r.json()
    return data if isinstance(data, list) else []


async def _build() -> dict:
    tickers = settings.quiver_ticker_list
    since = datetime.now(timezone.utc) - timedelta(days=LOOKBACK_DAYS)
    status = {"congress": "ok", "insiders": "ok"}
    congress: list[dict] = []
    insiders: list[dict] = []
    async with httpx.AsyncClient(timeout=20) as client:
        try:
            congress = parse_congress(await _fetch(client, "/live/congresstrading"), set(tickers), since)
        except Exception as exc:
            status["congress"] = _status_of(exc)
            log.warning("Quiver congress feed failed: %s", status["congress"])

        results = await asyncio.gather(
            *(_fetch(client, "/live/insiders", {"ticker": t, "page_size": 50}) for t in tickers),
            return_exceptions=True,
        )
        errors = [r for r in results if isinstance(r, Exception)]
        for r in results:
            if not isinstance(r, Exception):
                insiders.extend(parse_insiders(r, since))
        if errors and len(errors) == len(results):
            status["insiders"] = _status_of(errors[0])
            log.warning("Quiver insider feed failed: %s", status["insiders"])
    insiders.sort(key=lambda t: t["traded_at"], reverse=True)

    live = status["congress"] == "ok" or status["insiders"] == "ok"
    return {
        "source": "quiver" if live else "unavailable",
        "status": status,
        "tickers": tickers,
        "lookback_days": LOOKBACK_DAYS,
        "summary": summarize(congress, insiders, tickers),
        "congress": congress[:50],
        "insiders": insiders[:50],
    }


async def smart_money() -> dict:
    if not settings.quiver_api_key:
        return {
            "source": "unavailable",
            "status": {"congress": "no_key", "insiders": "no_key"},
            "tickers": settings.quiver_ticker_list,
            "lookback_days": LOOKBACK_DAYS,
            "summary": None,
            "congress": [],
            "insiders": [],
            "note": "Set QUIVER_API_KEY in backend/.env to see Congress and insider trades in crypto-linked stocks.",
        }
    return await cached("quiver", CACHE_SECONDS, _build)
