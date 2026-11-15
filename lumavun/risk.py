"""Pure order-sizing and validation helpers, separated from broker side effects."""
from __future__ import annotations
from dataclasses import dataclass
from decimal import Decimal, ROUND_FLOOR
import math

class TradeRejected(ValueError):
    """A proposed order is unsafe or violates configured limits."""

@dataclass(frozen=True)
class OrderIntent:
    symbol: str
    side: str
    sl: float
    tp: float

def ensure_direction(side: str, entry: float, sl: float, tp: float) -> None:
    if side not in ("BUY", "SELL"):
        raise TradeRejected("Only BUY or SELL can become an order")
    if not all(math.isfinite(v) and v > 0 for v in (entry, sl, tp)):
        raise TradeRejected("Entry/SL/TP must be finite positive prices")
    if side == "BUY" and not (sl < entry < tp):
        raise TradeRejected("BUY must have SL < entry < TP")
    if side == "SELL" and not (tp < entry < sl):
        raise TradeRejected("SELL must have TP < entry < SL")
    if abs(tp - entry) < abs(entry - sl) * 1.5:
        raise TradeRejected("Reward/risk below 1.5:1")

def normalize_volume(raw: float, minimum: float, maximum: float, step: float) -> float:
    if not all(math.isfinite(v) for v in (raw, minimum, maximum, step)):
        raise TradeRejected("Nonfinite lot sizing input")
    if minimum <= 0 or maximum < minimum or step <= 0:
        raise TradeRejected("Invalid broker lot limits")
    # Broker volume grid is anchored at volume_min, not necessarily zero.
    if raw < minimum:
        raise TradeRejected("Minimum broker lot exceeds risk budget")
    capped = min(raw, maximum)
    count = ((Decimal(str(capped)) - Decimal(str(minimum))) / Decimal(str(step))).to_integral_value(rounding=ROUND_FLOOR)
    volume = Decimal(str(minimum)) + count * Decimal(str(step))
    return float(volume)

def calculate_lot(equity: float, risk_pct: float, loss_one_lot: float,
                  volume_min: float, volume_max: float, volume_step: float,
                  cap: float) -> float:
    if not all(math.isfinite(x) for x in (equity, risk_pct, loss_one_lot, cap)):
        raise TradeRejected("Invalid account risk calculation")
    if equity <= 0 or risk_pct <= 0 or risk_pct > 2 or loss_one_lot <= 0 or cap <= 0:
        raise TradeRejected("Invalid equity, risk percent, or SL loss")
    raw = equity * (risk_pct / 100.0) / loss_one_lot
    return normalize_volume(raw, volume_min, min(volume_max, cap), volume_step)
