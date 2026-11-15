"""Read-only, broker-backed portfolio analytics and target-profit progress.

Never invent sample balances or P&L. History is sourced from deal executions
(not submitted orders). Dates/target periods are computed in UTC.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import math
from typing import Any

PERIODS = ("day", "week", "month")
TRADE_TYPES = (0, 1)
CLOSE_ENTRIES = (1, 2, 3)

class HistoryUnavailable(RuntimeError):
    pass

def _number(value: Any, default: float = 0.0) -> float:
    try:
        val = float(value)
        return val if math.isfinite(val) else default
    except (ValueError, TypeError):
        return default

def _time(value: Any) -> int:
    if value is None:
        raise ValueError("Missing deal timestamp")
    if isinstance(value, (int, float)):
        number = int(value)
        return number // 1000 if number > 100000000000 else number
    if isinstance(value, str):
        if value.isdigit():
            return _time(int(value))
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return int(dt.timestamp())
    raise ValueError("Invalid deal timestamp")

def _is_trade_type(value: Any) -> bool:
    if isinstance(value, int) and not isinstance(value, bool):
        return value in TRADE_TYPES
    if isinstance(value, str):
        return value.upper() in ("BUY", "SELL", "DEAL_TYPE_BUY", "DEAL_TYPE_SELL", "0", "1")
    return False

def _is_exit(value: Any) -> bool:
    if isinstance(value, int):
        return value in CLOSE_ENTRIES
    if isinstance(value, str):
        return value.upper() in ("OUT", "INOUT", "OUT_BY", "DEAL_ENTRY_OUT",
                                 "DEAL_ENTRY_INOUT", "DEAL_ENTRY_OUT_BY", "1", "2", "3")
    return False

def parse_deals(source: Any) -> list[dict]:
    """Normalize MT5 deal objects/dicts. Deposits, withdrawals and orders are excluded."""
    if not isinstance(source, (list, tuple)):
        raise HistoryUnavailable("Broker history did not return a list of deals")
    normalized = []
    for item in source:
        if isinstance(item, dict):
            d = item
        elif hasattr(item, "_asdict"):
            d = item._asdict()
        else:
            continue
        typ = d.get("type", d.get("deal_type"))
        if not _is_trade_type(typ) or not d.get("symbol"):
            continue
        try:
            timestamp = _time(d.get("time", d.get("timestamp", d.get("time_msc"))))
        except (TypeError, ValueError, OverflowError):
            continue
        if timestamp <= 0:
            continue
        net = sum(_number(d.get(name)) for name in ("profit", "commission", "swap", "fee"))
        normalized.append({
            "time": timestamp,
            "ticket": str(d.get("ticket", d.get("deal", ""))),
            "symbol": str(d["symbol"]),
            "side": "BUY" if typ == 0 or str(typ).upper() in ("0", "BUY", "DEAL_TYPE_BUY") else "SELL",
            "volume": _number(d.get("volume")),
            "net": round(net, 6),
            "is_exit": _is_exit(d.get("entry", d.get("deal_entry"))),
            "position_id": str(d.get("position_id", "")),
        })
    normalized.sort(key=lambda x: (x["time"], x["ticket"]))
    return normalized

def _as_history_deals(payload: Any) -> list:
    """Extract *deals*, never confuse order requests with executed deals."""
    if isinstance(payload, (list, tuple)):
        # Only accept a bare list if entries have a deal-like field.
        if not payload:
            return []
        first = payload[0]
        if not isinstance(first, dict):
            raise HistoryUnavailable("Unexpected MCP history list")
        if "entry" in first or "deal_entry" in first or "deal" in first:
            return list(payload)
        raise HistoryUnavailable("MCP returned orders, not execution deals")
    if isinstance(payload, dict):
        for key in ("deals", "history_deals", "trade_deals"):
            val = payload.get(key)
            if isinstance(val, list):
                return val
        for key in ("result", "data", "history"):
            val = payload.get(key)
            if val is not None:
                return _as_history_deals(val)
    raise HistoryUnavailable("MCP history returned no recognizable executed-deals collection")

def _native_history(cfg, start: datetime, end: datetime) -> list:
    from .native_mt5 import _get_tool, _read_tool
    tool = _get_tool("get_trading_history_orders", cfg)
    schema = tool.get("inputSchema") or {}
    props = schema.get("properties") or {}
    required = set(schema.get("required") or [])
    if not isinstance(props, dict):
        raise HistoryUnavailable("Native history tool has invalid argument schema")
    args: dict = {}
    for possible in ("from_time", "date_from", "start_time", "start_date", "from_date", "from", "start"):
        if possible in props:
            typ = props[possible].get("type") if isinstance(props[possible], dict) else "string"
            args[possible] = int(start.timestamp()) if typ in ("integer", "number") else start.isoformat()
            break
    for possible in ("to_time", "date_to", "end_time", "end_date", "to_date", "to", "end"):
        if possible in props:
            typ = props[possible].get("type") if isinstance(props[possible], dict) else "string"
            args[possible] = int(end.timestamp()) if typ in ("integer", "number") else end.isoformat()
            break
    if required - args.keys() or len(args) < 2:
        raise HistoryUnavailable(
            "Schema history MCP native belum dikenali. Buka MT5 MCP untuk melihat parameter tool."
        )
    try:
        return _as_history_deals(_read_tool("get_trading_history_orders", args, cfg))
    except HistoryUnavailable:
        raise
    except Exception as exc:
        raise HistoryUnavailable("Gagal membaca history MCP native: " + type(exc).__name__) from None

def fetch_deals(cfg, start: datetime, end: datetime) -> list[dict]:
    if cfg.mt5_mode == "local":
        from .mt5_bridge import _connected
        mt5 = _connected()
        raw = mt5.history_deals_get(start, end)
        if raw is None:
            raise HistoryUnavailable("MT5 tidak dapat membaca history deals: " + str(mt5.last_error()))
        return parse_deals(raw)
    if cfg.mt5_mode == "mt5_native":
        return parse_deals(_native_history(cfg, start, end))
    raise HistoryUnavailable("LUMAVUN Gateway belum menyediakan tool riwayat transaksi")

def period_start_utc(period: str, now: datetime | None = None) -> datetime:
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        raise ValueError("Target period requires timezone-aware UTC date")
    now = now.astimezone(timezone.utc)
    today = now.replace(hour=0, minute=0, second=0, microsecond=0)
    if period == "day":
        return today
    if period == "week":
        return today - timedelta(days=today.weekday())
    if period == "month":
        return today.replace(day=1)
    raise ValueError("Unsupported target period")

def _summarize_deals(deals: list[dict], start: datetime) -> dict:
    cutoff = int(start.timestamp())
    entries = [d for d in deals if d["time"] >= cutoff]
    closed = [d for d in entries if d["is_exit"]]
    total = sum(d["net"] for d in entries)
    wins = sum(1 for d in closed if d["net"] > 0)
    losses = sum(1 for d in closed if d["net"] < 0)
    return {
        "realized": round(total, 2),
        "wins": wins, "losses": losses, "closed": len(closed),
        "win_rate": round(wins / len(closed) * 100, 1) if closed else None,
        "deals": entries,
    }

def _position_profit(positions: Any) -> float | None:
    if not isinstance(positions, list):
        return None
    total = 0.0
    for position in positions:
        if not isinstance(position, dict):
            return None
        raw = position.get("profit", position.get("floating_profit"))
        if raw is None:
            return None
        try:
            total += float(raw)
        except (ValueError, TypeError):
            return None
    return round(total, 2)

def make_snapshot(cfg, days: int = 30, now: datetime | None = None) -> dict:
    """Independent account + history availability, so unavailable is never shown as zero."""
    from .mt5_access import account_status, list_positions
    now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    days = min(90, max(1, int(days)))
    account = account_status(cfg)
    positions_error = None
    history_error = None
    try:
        positions = list_positions(cfg)
        floating = _position_profit(positions)
    except Exception as exc:
        positions = []
        floating = None
        positions_error = type(exc).__name__
    target_start = period_start_utc(cfg.profit_target_period, now)
    history_start = min(target_start, now - timedelta(days=days))
    try:
        deals = fetch_deals(cfg, history_start, now)
        window_start = now - timedelta(days=days)
        summary = _summarize_deals(deals, window_start)
        target = _summarize_deals(deals, target_start)
        available = True
    except (HistoryUnavailable, ValueError) as exc:
        summary = {"realized": None, "wins": None, "losses": None,
                   "closed": None, "win_rate": None, "deals": []}
        target = {"realized": None}
        available = False
        history_error = str(exc)
    amount = _number(cfg.profit_target_amount)
    achieved = target["realized"] if available else None
    progress = None if not available or amount <= 0 else min(
        100.0, max(0.0, achieved / amount * 100.0))
    reached = bool(available and amount > 0 and achieved >= amount)
    return {
        "account": account, "floating": floating, "positions": positions,
        "positions_error": positions_error, "history_error": history_error,
        "history_available": available, "history": summary,
        "target_realized": achieved, "target_amount": amount,
        "target_period": cfg.profit_target_period, "progress": progress,
        "target_reached": reached, "updated_at": now.isoformat(),
        "window_days": days,
    }

def check_profit_target(cfg) -> dict:
    """Stop auto trading if a configured target is met, or cannot be checked."""
    from datetime import datetime, timezone
    if cfg.profit_target_amount <= 0 or not cfg.pause_at_profit_target:
        return {"enabled": False, "reached": False}
    now = datetime.now(timezone.utc)
    start = period_start_utc(cfg.profit_target_period, now)
    deals = fetch_deals(cfg, start, now)  # errors are intentionally NOT swallowed
    actual = _summarize_deals(deals, start)["realized"]
    return {
        "enabled": True, "reached": actual >= cfg.profit_target_amount,
        "realized": actual, "target": cfg.profit_target_amount,
        "period": cfg.profit_target_period,
    }
