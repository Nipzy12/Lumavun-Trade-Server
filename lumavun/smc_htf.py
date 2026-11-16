"""Confirmed H4 structure and unmitigated Order Block / Fair Value Gap context.

Pine v6 reference: f_htfContext(), including confirmed pivots, close-based
structure breaks, OB preference and 3-candle displacement gaps. This is an
independent Python translation, not TradingView's own Pine runtime.
"""
from __future__ import annotations
from bisect import bisect_right
from dataclasses import asdict, dataclass
from math import isfinite


@dataclass(frozen=True)
class POI:
    kind: str
    side: int  # +1 bullish, -1 bearish
    bottom: float
    top: float
    confirmed_at: int  # HTF open timestamp; usable after HTF close


@dataclass(frozen=True)
class H4Context:
    bias: int
    poi: POI | None
    poi_touched_recently: bool
    invalid_reason: str | None

    def to_dict(self) -> dict:
        return asdict(self)


def _atr(bars: list[dict], idx: int, period: int = 14) -> float:
    if idx < period:
        return 0.0
    result = 0.0
    for k in range(idx - period + 1, idx + 1):
        previous = bars[k - 1]["close"]
        b = bars[k]
        result += max(b["high"] - b["low"],
                      abs(b["high"] - previous),
                      abs(b["low"] - previous))
    return result / period


def _pivot(bars: list[dict], end: int, swing: int, high: bool):
    origin = end - swing
    if origin - swing < 0:
        return None
    field = "high" if high else "low"
    value = bars[origin][field]
    left = [b[field] for b in bars[origin - swing:origin]]
    right = [b[field] for b in bars[origin + 1:end + 1]]
    # Strict on older bars, non-strict on later bars to disambiguate equal highs/lows.
    if high and all(value > x for x in left) and all(value >= x for x in right):
        return value
    if not high and all(value < x for x in left) and all(value <= x for x in right):
        return value
    return None


def _historical_state(bars: list[dict], poi_type: str, swing: int,
                      ob_lookback: int, min_fvg_atr: float,
                      displacement_atr: float) -> tuple[int, POI | None]:
    high_level = low_level = None
    high_broken = low_broken = False
    trend = 0
    ob = fvg = None
    for i in range(max(2 * swing, 15), len(bars)):
        b = bars[i]
        prev = bars[i - 1]
        atr = _atr(bars, i)
        ph = _pivot(bars, i, swing, True)
        pl = _pivot(bars, i, swing, False)
        if ph is not None:
            high_level, high_broken = ph, False
        if pl is not None:
            low_level, low_broken = pl, False
        up = (high_level is not None and not high_broken and
              b["close"] > high_level and prev["close"] <= high_level)
        dn = (low_level is not None and not low_broken and
              b["close"] < low_level and prev["close"] >= low_level)
        if up or dn:
            trend = 1 if up else -1
            if up:
                high_broken = True
            else:
                low_broken = True
            ob = None
            for old in reversed(bars[max(0, i - ob_lookback):i]):
                opposing = (old["close"] < old["open"] if up
                            else old["close"] > old["open"])
                if opposing:
                    ob = POI("OB", trend, old["low"], old["high"], b["time"])
                    break
        # HTF invalidation is strictly based on confirmed candle CLOSE.
        if ob is not None:
            if ((ob.side == 1 and b["close"] < ob.bottom) or
                (ob.side == -1 and b["close"] > ob.top)):
                ob = None
        if fvg is not None:
            if ((fvg.side == 1 and b["close"] < fvg.bottom) or
                (fvg.side == -1 and b["close"] > fvg.top)):
                fvg = None
        middle = bars[i - 1]
        prev_atr = _atr(bars, i - 1)
        mid_body = abs(middle["close"] - middle["open"])
        if atr > 0 and prev_atr > 0 and mid_body >= displacement_atr * prev_atr:
            if (trend == 1 and middle["close"] > middle["open"] and
                b["low"] > bars[i - 2]["high"] and
                b["low"] - bars[i - 2]["high"] >= min_fvg_atr * atr):
                fvg = POI("FVG", 1, bars[i - 2]["high"], b["low"], b["time"])
            if (trend == -1 and middle["close"] < middle["open"] and
                b["high"] < bars[i - 2]["low"] and
                bars[i - 2]["low"] - b["high"] >= min_fvg_atr * atr):
                fvg = POI("FVG", -1, b["high"], bars[i - 2]["low"], b["time"])
    if poi_type == "OB only":
        selected = ob
    elif poi_type == "FVG only":
        selected = fvg
    elif poi_type == "OB or FVG":
        selected = ob if ob and ob.side == trend else fvg
    else:
        raise ValueError("Unsupported H4 POI type")
    if selected is not None and selected.side != trend:
        selected = None
    return trend, selected


def context(htf: list[dict], ltf: list[dict], at_time: int,
            poi_type: str = "OB or FVG", memory: int = 12,
            invalid_buffer_atr: float = 0.03, consume_depth: float = 0.95,
            cache: dict | None = None) -> H4Context:
    """Never uses H4 candle whose 4-hour close is later than at_time."""
    if len(htf) < 35 or len(ltf) < 15:
        return H4Context(0, None, False, "INSUFFICIENT_HISTORY")
    times = [int(b["time"]) for b in htf]
    length = bisect_right(times, int(at_time) - 14400)
    if length < 35:
        return H4Context(0, None, False, "H4_NOT_CLOSED")
    key = (length, poi_type)
    if cache is not None and key in cache:
        trend, poi = cache[key]
    else:
        # Full context, up to 320 H4 candles (~53 days), enough to find pivots
        # but not a guarantee of structure continuity over longer histories.
        begin = max(0, length - 320)
        trend, poi = _historical_state(htf[begin:length], poi_type, 3, 12, .12, 1.0)
        if cache is not None:
            cache[key] = trend, poi
    if poi is None:
        return H4Context(trend, None, False, "NO_ACTIVE_POI")
    # Check all available LTF bars since this POI was confirmed. Unknown prior
    # history cannot establish freshness, so fail closed when truncated.
    confirmed_time = poi.confirmed_at + 14400
    eligible = [b for b in ltf if confirmed_time <= b["time"] <= at_time]
    if not eligible:
        return H4Context(trend, None, False, "POI_NOT_OBSERVABLE")
    if ltf[0]["time"] > confirmed_time:
        return H4Context(trend, None, False, "POI_FRESHNESS_HISTORY_MISSING")
    recent_hit = False
    for idx, b in enumerate(eligible):
        price_atr = _atr(ltf, max(14, len(ltf) - len(eligible) + idx))
        buf = invalid_buffer_atr * price_atr
        broken = (b["close"] < poi.bottom - buf if poi.side == 1
                  else b["close"] > poi.top + buf)
        overlaps = b["low"] <= poi.top and b["high"] >= poi.bottom
        depth = ((poi.top - b["low"]) if poi.side == 1
                 else (b["high"] - poi.bottom)) / (poi.top - poi.bottom)
        if broken or (overlaps and depth >= consume_depth):
            return H4Context(trend, None, False, "CLOSE_BROKEN_OR_CONSUMED")
        if overlaps and idx >= len(eligible) - memory:
            recent_hit = True
    return H4Context(trend, poi, recent_hit, None)
