"""Orchestrates closed-candle AI proposals and the shared risk-checked MT5 bridge."""
from __future__ import annotations
from .ai import propose_trade
from .config import Settings
from .mt5_access import get_candles, preview_order, execute_order
from .risk import TradeRejected

def run_strategy_once() -> dict:
    cfg = Settings.load()
    candles = get_candles(cfg.symbol, cfg.timeframe, 60, cfg)
    bar_key = cfg.symbol + ":" + cfg.timeframe + ":" + str(candles[-1]["time"])
    if cfg.last_signal_bar == bar_key:
        return {"status": "SKIP", "reason": "Already evaluated the latest closed candle"}
    intent, reason = propose_trade(cfg, candles)
    # Never retry this candle automatically, including rejected proposals.
    fresh = Settings.load()
    fresh.last_signal_bar = bar_key
    fresh.save()
    if intent is None:
        return {"status": "HOLD", "reason": reason}
    try:
        preview = preview_order(intent, cfg)
    except TradeRejected as exc:
        return {"status": "REJECTED", "reason": str(exc), "ai_reason": reason}
    if not Settings.load().execution_enabled:
        return {"status": "PREVIEW", "reason": reason, "order": preview}
    result = execute_order(intent)
    return {"status": "EXECUTED", "reason": reason, "order": result}
