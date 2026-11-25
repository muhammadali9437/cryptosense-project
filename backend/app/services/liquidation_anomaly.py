"""Liquidation spike detection against a rolling statistical baseline.

Method (transparent and configurable in .env):
- Activity is bucketed into 5-minute UTC buckets of observed liquidation USD.
- Baseline = the previous LIQ_BASELINE_HOURS of buckets (empty buckets count as 0), starting no
  earlier than the first stored event.
- Score = robust z = (current - median) / scale, where scale = 1.4826 x MAD (median absolute
  deviation), floored at LIQ_SPIKE_MIN_USD / 4 so a near-silent baseline can't turn a small
  amount into a huge z.
- A spike needs BOTH z >= LIQ_SPIKE_Z and current >= LIQ_SPIKE_MIN_USD.
- Burst = at least LIQ_BURST_EVENTS events for one coin within 60 seconds.
- Imbalance shift = long share of the last 15 min vs the baseline's long share, in percentage
  points, flagged at >= LIQ_IMBALANCE_SHIFT_PTS (only with >= LIQ_SPIKE_MIN_USD of activity).

An anomaly says activity is unusual for this stream. It does not say a crash or reversal is
happening, and liquidations alone do not determine price direction.
"""
import statistics
import time
from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..config import settings
from ..models import LiquidationEvent as L
from .liquidation_store import earliest_event_ms

BUCKET_MS = 300_000
MIN_BASELINE_BUCKETS = 12  # at least one hour of history
CAVEAT = "Unusual liquidation activity is context, not a prediction of where price goes next."


@dataclass(frozen=True)
class Params:
    z: float = 4.0
    min_usd: float = 250_000
    burst_events: int = 15
    imbalance_pts: float = 35

    @classmethod
    def from_settings(cls) -> "Params":
        return cls(settings.liq_spike_z, settings.liq_spike_min_usd,
                   settings.liq_burst_events, settings.liq_imbalance_shift_pts)


def robust_z(current: float, history: list[float], min_usd: float) -> tuple[float, float, float]:
    """Returns (z, median, scale)."""
    median = statistics.median(history) if history else 0.0
    mad = statistics.median([abs(x - median) for x in history]) if history else 0.0
    scale = max(1.4826 * mad, min_usd / 4, 1.0)
    return (current - median) / scale, median, scale


def _usd(v: float) -> str:
    if v >= 1e9:
        return f"${v / 1e9:.2f}B"
    if v >= 1e6:
        return f"${v / 1e6:.2f}M"
    if v >= 1e3:
        return f"${v / 1e3:.0f}K"
    return f"${v:,.0f}"


def _severity(z: float, threshold: float) -> str:
    return "high" if z >= threshold * 2 else "elevated"


def spike(kind: str, label: str, current: float, history: list[float], p: Params,
          symbol: str | None = None) -> dict | None:
    z, median, scale = robust_z(current, history, p.min_usd)
    if z < p.z or current < p.min_usd:
        return None
    where = symbol.replace("USDT", "") + " " if symbol else ""
    return {
        "type": kind, "symbol": symbol, "severity": _severity(z, p.z), "window": "5m",
        "current_usd": round(current, 2), "baseline_median_usd": round(median, 2),
        "baseline_scale_usd": round(scale, 2), "robust_z": round(z, 2),
        "message": (f"Observed {where}{label} in the last 5 minutes: {_usd(current)}, versus a typical "
                    f"5-minute level of {_usd(median)} (robust z {z:.1f}). {CAVEAT}"),
    }


def find_anomalies(current: dict, baseline: dict, bursts: dict[str, int], recent_15m: dict,
                   p: Params) -> list[dict]:
    """Pure detection step.

    current:    {"long": usd, "short": usd, "by_symbol": {sym: usd}}      last 5 minutes
    baseline:   {"long": [usd per bucket], "short": [...], "by_symbol": {sym: [...]},
                 "long_total": usd, "short_total": usd}
    bursts:     {sym: events in the last 60s}
    recent_15m: {"long": usd, "short": usd}
    """
    found = []
    total_hist = [a + b for a, b in zip(baseline["long"], baseline["short"])]
    for kind, label, cur, hist in (
        ("total_spike", "liquidations", current["long"] + current["short"], total_hist),
        ("long_spike", "long liquidations (forced sells)", current["long"], baseline["long"]),
        ("short_spike", "short liquidations (forced buys)", current["short"], baseline["short"]),
    ):
        hit = spike(kind, label, cur, hist, p)
        if hit:
            found.append(hit)
    n = len(total_hist)
    for sym, cur in current["by_symbol"].items():
        hist = baseline["by_symbol"].get(sym, [])
        hist = hist + [0.0] * (n - len(hist))
        hit = spike("symbol_spike", "liquidations", cur, hist, p, symbol=sym)
        if hit:
            found.append(hit)
    for sym, count in bursts.items():
        if count >= p.burst_events:
            found.append({
                "type": "burst", "symbol": sym, "severity": _severity(count, p.burst_events), "window": "60s",
                "event_count": count,
                "message": (f"{count} observed {sym.replace('USDT', '')} liquidation events within 60 seconds "
                            f"(Binance sends at most one per second per coin, so this is near-continuous). {CAVEAT}"),
            })
    base_total = baseline["long_total"] + baseline["short_total"]
    recent_total = recent_15m["long"] + recent_15m["short"]
    if base_total > 0 and recent_total >= p.min_usd:
        base_share = baseline["long_total"] / base_total * 100
        now_share = recent_15m["long"] / recent_total * 100
        shift = now_share - base_share
        if abs(shift) >= p.imbalance_pts:
            side = "longs" if shift > 0 else "shorts"
            found.append({
                "type": "imbalance_shift", "symbol": None,
                "severity": "high" if abs(shift) >= min(p.imbalance_pts * 1.5, 100) else "elevated",
                "window": "15m", "long_share_pct": round(now_share, 1),
                "baseline_long_share_pct": round(base_share, 1), "shift_pts": round(shift, 1),
                "message": (f"In the last 15 minutes {now_share:.0f}% of observed liquidation value was longs, "
                            f"versus {base_share:.0f}% over the baseline period: a shift toward {side} being "
                            f"liquidated. {CAVEAT}"),
            })
    order = {"high": 0, "elevated": 1}
    return sorted(found, key=lambda a: (order[a["severity"]], -a.get("robust_z", a.get("event_count", 0))))


def _sum_by(db: Session, start_ms: int, end_ms: int, symbol: str | None = None) -> dict:
    conds = [L.event_ms >= start_ms, L.event_ms <= end_ms, L.usd_valid.is_(True)]
    if symbol:
        conds.append(L.symbol == symbol)
    out = {"long": 0.0, "short": 0.0, "by_symbol": {}}
    for sym, pos, usd in db.execute(select(L.symbol, L.position, func.sum(L.usd)).where(*conds)
                                    .group_by(L.symbol, L.position)):
        out[pos] += usd
        out["by_symbol"][sym] = out["by_symbol"].get(sym, 0.0) + usd
    return out


def load_inputs(db: Session, symbol: str | None, now_ms: int) -> dict | None:
    """Current 5m / last 15m sums, the zero-filled 5m baseline series and 60s burst counts.
    Returns None when there are fewer than MIN_BASELINE_BUCKETS baseline buckets."""
    current = _sum_by(db, now_ms - BUCKET_MS, now_ms, symbol)
    recent = _sum_by(db, now_ms - 3 * BUCKET_MS, now_ms, symbol)
    first_bucket = (now_ms - settings.liq_baseline_hours * 3_600_000) // BUCKET_MS
    earliest = earliest_event_ms(db)
    if earliest:
        first_bucket = max(first_bucket, earliest // BUCKET_MS)
    last_bucket = (now_ms - BUCKET_MS) // BUCKET_MS - 1   # only buckets that end before "current"
    buckets = list(range(first_bucket, last_bucket + 1))
    if len(buckets) < MIN_BASELINE_BUCKETS:
        return None
    conds = [L.bucket_5m >= first_bucket, L.bucket_5m <= last_bucket, L.usd_valid.is_(True)]
    if symbol:
        conds.append(L.symbol == symbol)
    index = {b: i for i, b in enumerate(buckets)}
    base = {"long": [0.0] * len(buckets), "short": [0.0] * len(buckets), "by_symbol": {},
            "long_total": 0.0, "short_total": 0.0}
    for b, sym, pos, usd in db.execute(select(L.bucket_5m, L.symbol, L.position, func.sum(L.usd))
                                       .where(*conds).group_by(L.bucket_5m, L.symbol, L.position)):
        i = index[int(b)]
        base[pos][i] += usd
        base[f"{pos}_total"] += usd
        base["by_symbol"].setdefault(sym, [0.0] * len(buckets))[i] += usd
    burst_conds = [L.event_ms >= now_ms - 60_000, L.event_ms <= now_ms]
    if symbol:
        burst_conds.append(L.symbol == symbol)
    bursts = dict(db.execute(select(L.symbol, func.count()).where(*burst_conds).group_by(L.symbol)).all())
    return {"current": current, "recent": recent, "baseline": base, "bursts": bursts, "buckets": len(buckets)}


def scores(inputs: dict, min_usd: float) -> dict:
    """Raw robust z-scores and the imbalance shift for one symbol (used by user alerts)."""
    cur, base, recent = inputs["current"], inputs["baseline"], inputs["recent"]
    total_hist = [a + b for a, b in zip(base["long"], base["short"])]
    base_total = base["long_total"] + base["short_total"]
    recent_total = recent["long"] + recent["short"]
    shift = None
    if base_total > 0 and recent_total > 0:
        shift = recent["long"] / recent_total * 100 - base["long_total"] / base_total * 100
    return {
        "total_usd": cur["long"] + cur["short"], "long_usd": cur["long"], "short_usd": cur["short"],
        "total_z": robust_z(cur["long"] + cur["short"], total_hist, min_usd)[0],
        "long_z": robust_z(cur["long"], base["long"], min_usd)[0],
        "short_z": robust_z(cur["short"], base["short"], min_usd)[0],
        "recent_15m_usd": recent_total, "long_share_shift_pts": shift,
    }


def detect(db: Session, symbol: str | None = None, now_ms: int | None = None,
           params: Params | None = None) -> dict:
    """Load the inputs from the database and run find_anomalies()."""
    p = params or Params.from_settings()
    now_ms = now_ms or int(time.time() * 1000)
    symbol = symbol.upper() if symbol else None
    inputs = load_inputs(db, symbol, now_ms)
    if inputs is None:
        return {"status": "insufficient_baseline", "anomalies": [], "symbol": symbol, "params": p.__dict__,
                "note": (f"Needs at least {MIN_BASELINE_BUCKETS} five-minute buckets "
                         f"({MIN_BASELINE_BUCKETS * 5} minutes) of stored history before spikes can be judged.")}
    current = inputs["current"]
    anomalies = find_anomalies(current, inputs["baseline"], inputs["bursts"], inputs["recent"], p)
    return {"status": "ok", "anomalies": anomalies, "baseline_buckets": inputs["buckets"],
            "baseline_hours": round(inputs["buckets"] * 5 / 60, 1), "symbol": symbol, "params": p.__dict__,
            "current_5m": {"long_usd": round(current["long"], 2), "short_usd": round(current["short"], 2)},
            "method": "robust z-score of 5-minute observed liquidation USD vs a rolling baseline (median/MAD)"}
