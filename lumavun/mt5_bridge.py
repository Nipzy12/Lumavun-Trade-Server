"""MetaTrader 5 bridge. All executable orders go through the same hard risk gate."""
from __future__ import annotations
from datetime import datetime, timedelta, timezone
from dataclasses import asdict
import math
import time
from filelock import FileLock
from .config import Settings, config_path
from .risk import OrderIntent, TradeRejected, ensure_direction, calculate_lot

MAGIC = 260115
TIMEFRAMES = {"M1": "TIMEFRAME_M1", "M5": "TIMEFRAME_M5",
              "M15": "TIMEFRAME_M15", "M30": "TIMEFRAME_M30",
              "H1": "TIMEFRAME_H1", "H4": "TIMEFRAME_H4",
              "D1": "TIMEFRAME_D1"}

def _api():
    try:
        import MetaTrader5 as mt5
        return mt5
    except ModuleNotFoundError as exc:
        missing = exc.name or "unknown"
        if missing == "MetaTrader5":
            raise RuntimeError(
                "MetaTrader5 module was not bundled with the application. "
                "Download the newest Windows build. Original error: " + str(exc)
            ) from exc
        raise RuntimeError(
            "MetaTrader5 dependency '" + missing + "' is missing: " + str(exc)
        ) from exc
    except ImportError as exc:
        raise RuntimeError(
            "MetaTrader5 binary/DLL import failed: " + str(exc) +
            ". On Windows, verify the x64 Visual C++ runtime and use the latest EXE."
        ) from exc

def _connected():
    mt5 = _api()
    if not mt5.initialize():
        raise RuntimeError("MT5 initialize failed: " + str(mt5.last_error()))
    return mt5

def _account(mt5):
    account = mt5.account_info()
    if account is None:
        raise RuntimeError("No logged-in MT5 account: " + str(mt5.last_error()))
    return account

def account_status() -> dict:
    mt5 = _connected()
    account = _account(mt5)
    terminal = mt5.terminal_info()
    return {
        "login": account.login,
        "server": account.server,
        "balance": account.balance,
        "equity": account.equity,
        "currency": account.currency,
        "demo": account.trade_mode == mt5.ACCOUNT_TRADE_MODE_DEMO,
        "terminal_trade_allowed": bool(terminal and terminal.trade_allowed),
        "account_trade_allowed": bool(account.trade_allowed),
    }

def list_positions() -> list[dict]:
    mt5 = _connected()
    positions = mt5.positions_get()
    if positions is None:
        raise RuntimeError("MT5 could not retrieve positions")
    return [{"ticket": p.ticket, "symbol": p.symbol, "volume": p.volume,
             "side": "BUY" if p.type == mt5.POSITION_TYPE_BUY else "SELL",
             "open_price": p.price_open, "sl": p.sl, "tp": p.tp,
             "profit": p.profit} for p in positions]

def get_candles(symbol: str, timeframe: str = "M15", count: int = 60) -> list[dict]:
    mt5 = _connected()
    if timeframe not in TIMEFRAMES:
        raise ValueError("Unsupported timeframe")
    if not (10 <= count <= 500):
        raise ValueError("Candles count must be between 10 and 500")
    if mt5.symbol_info(symbol) is None or not mt5.symbol_select(symbol, True):
        raise RuntimeError("Symbol unavailable: " + symbol)
    rates = mt5.copy_rates_from_pos(symbol, getattr(mt5, TIMEFRAMES[timeframe]), 1, count)
    if rates is None or len(rates) < 10:
        raise RuntimeError("Not enough CLOSED MT5 candles available")
    return [{"time": int(r["time"]), "open": float(r["open"]),
             "high": float(r["high"]), "low": float(r["low"]),
             "close": float(r["close"]), "tick_volume": int(r["tick_volume"])}
            for r in rates]

def _daily_stats(mt5) -> tuple[float, int]:
    now = datetime.now(timezone.utc)
    start = datetime(now.year, now.month, now.day, tzinfo=timezone.utc)
    deals = mt5.history_deals_get(start, now + timedelta(minutes=1))
    if deals is None:
        raise TradeRejected("Daily deal history unavailable; fail closed")
    net = 0.0
    entries = 0
    for d in deals:
        if d.type in (mt5.DEAL_TYPE_BUY, mt5.DEAL_TYPE_SELL):
            net += float(d.profit + d.commission + d.swap + getattr(d, "fee", 0))
        if d.magic == MAGIC and d.entry == mt5.DEAL_ENTRY_IN:
            entries += 1
    return net, entries

def _preview(mt5, cfg: Settings, intent: OrderIntent) -> tuple[dict, dict]:
    if not isinstance(intent.symbol, str) or intent.symbol not in {
        item.strip() for item in cfg.allow_symbols.split(",") if item.strip()
    }:
        raise TradeRejected("Symbol is not in the allowlist (exact broker symbol required)")
    if intent.side not in ("BUY", "SELL"):
        raise TradeRejected("Invalid order side")
    account = _account(mt5)
    info = mt5.symbol_info(intent.symbol)
    if info is None or not mt5.symbol_select(intent.symbol, True):
        raise TradeRejected("Symbol not available from broker")
    tick = mt5.symbol_info_tick(intent.symbol)
    if tick is None or tick.ask <= 0 or tick.bid <= 0 or tick.ask < tick.bid:
        raise TradeRejected("No valid tick")
    if time.time() - tick.time > 180:
        raise TradeRejected("Quote is stale or market is closed")
    spread = (tick.ask - tick.bid) / info.point if info.point > 0 else math.inf
    if not math.isfinite(spread) or spread > cfg.max_spread_points:
        raise TradeRejected("Spread exceeds configured cap")
    entry = float(tick.ask if intent.side == "BUY" else tick.bid)
    ensure_direction(intent.side, entry, intent.sl, intent.tp)
    minimum_stop = float(info.trade_stops_level) * float(info.point)
    if min(abs(entry - intent.sl), abs(entry - intent.tp)) < minimum_stop:
        raise TradeRejected("SL/TP violates broker minimum stop distance")
    if account.equity <= 0:
        raise TradeRejected("Account has no positive equity")
    active = mt5.positions_get()
    if active is None:
        raise TradeRejected("Cannot read open positions")
    if len(active) >= cfg.max_positions:
        raise TradeRejected("Maximum open positions reached")
    daily_net, trade_count = _daily_stats(mt5)
    if daily_net <= -(account.equity * cfg.max_daily_loss_pct / 100):
        raise TradeRejected("Daily loss cap reached")
    if trade_count >= cfg.max_trades_day:
        raise TradeRejected("Maximum daily bot trades reached")
    trade_type = mt5.ORDER_TYPE_BUY if intent.side == "BUY" else mt5.ORDER_TYPE_SELL
    one_lot_pnl = mt5.order_calc_profit(trade_type, intent.symbol, 1.0, entry, intent.sl)
    if one_lot_pnl is None or not math.isfinite(one_lot_pnl) or one_lot_pnl >= 0:
        raise TradeRejected("MT5 cannot calculate valid stop-loss risk")
    lot = calculate_lot(float(account.equity), float(cfg.risk_per_trade_pct),
                        -float(one_lot_pnl), float(info.volume_min),
                        float(info.volume_max), float(info.volume_step), float(cfg.max_lot))
    actual_pnl = mt5.order_calc_profit(trade_type, intent.symbol, lot, entry, intent.sl)
    if actual_pnl is None or -float(actual_pnl) > account.equity * cfg.risk_per_trade_pct / 100 + 0.01:
        raise TradeRejected("Rounded volume exceeds risk budget")
    base_req = {"action": mt5.TRADE_ACTION_DEAL, "symbol": intent.symbol,
                "volume": lot, "type": trade_type, "price": round(entry, info.digits),
                "sl": round(intent.sl, info.digits), "tp": round(intent.tp, info.digits),
                "deviation": 20, "magic": MAGIC, "comment": "LUMAVUN AI guarded",
                "type_time": mt5.ORDER_TIME_GTC}
    summary = {"symbol": intent.symbol, "side": intent.side, "entry": entry,
               "sl": intent.sl, "tp": intent.tp, "lot": lot,
               "estimated_sl_loss": round(-float(actual_pnl), 2),
               "spread_points": round(spread, 2), "account_demo": account.trade_mode == mt5.ACCOUNT_TRADE_MODE_DEMO,
               "equity": account.equity, "currency": account.currency, "daily_net": round(daily_net, 2)}
    return base_req, summary

def preview_order(intent: OrderIntent, cfg: Settings | None = None) -> dict:
    cfg = cfg or Settings.load()
    mt5 = _connected()
    _, summary = _preview(mt5, cfg, intent)
    return summary

def execute_order(intent: OrderIntent, cfg: Settings | None = None, *, from_mcp: bool = False) -> dict:
    # Load disk settings inside the lock to make emergency disarm effective across processes.
    with FileLock(str(config_path()) + ".trade.lock", timeout=10):
        cfg = Settings.load()
        if not cfg.execution_enabled:
            raise TradeRejected("Order execution is DISARMED in the desktop app")
        if from_mcp and not cfg.allow_mcp_orders:
            raise TradeRejected("MCP order execution is disabled")
        mt5 = _connected()
        account = _account(mt5)
        if account.trade_mode != mt5.ACCOUNT_TRADE_MODE_DEMO and not cfg.live_allowed:
            raise TradeRejected("LIVE account execution is not approved")
        terminal = mt5.terminal_info()
        if not terminal or not terminal.trade_allowed or not account.trade_allowed:
            raise TradeRejected("MT5 auto trading is not permitted by terminal/account")
        request, summary = _preview(mt5, cfg, intent)
        # Use order_check to select broker-supported filling policy. A failed check never sends an order.
        chosen = None
        for filling in (mt5.ORDER_FILLING_IOC, mt5.ORDER_FILLING_FOK, mt5.ORDER_FILLING_RETURN):
            candidate = {**request, "type_filling": filling}
            check = mt5.order_check(candidate)
            if check is not None and check.retcode == 0:
                chosen = candidate
                break
        if chosen is None:
            raise TradeRejected("MT5 order_check rejected order for all filling modes")
        result = mt5.order_send(chosen)  # Only actual brokerage side effect in the project.
        if result is None:
            raise RuntimeError("MT5 order_send returned no result: " + str(mt5.last_error()))
        if result.retcode not in (mt5.TRADE_RETCODE_DONE, getattr(mt5, "TRADE_RETCODE_DONE_PARTIAL", -1)):
            raise RuntimeError("MT5 rejected order: " + str(result.retcode) + " " + str(result.comment))
        return {**summary, "executed": True, "partial_fill": result.retcode != mt5.TRADE_RETCODE_DONE,
                "ticket": result.order, "deal": result.deal}
