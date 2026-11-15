"""Orchestrates closed-candle AI proposals and the shared risk-checked MT5 bridge."""
from __future__ import annotations
from .ai import propose_trade
from .config import Settings
from .mt5_access import get_candles, preview_order, execute_order
from .risk import TradeRejected
from .performance import check_profit_target, HistoryUnavailable

def run_strategy_once() -> dict:
    cfg = Settings.load()
    if cfg.pause_at_profit_target and cfg.profit_target_amount > 0:
        try:
            goal = check_profit_target(cfg)
        except (HistoryUnavailable, ValueError) as exc:
            return {"status": "TARGET_CHECK_UNAVAILABLE",
                    "reason": "Target aktif; riwayat broker tidak dapat diverifikasi: " + str(exc)}
        if goal["reached"]:
            return {"status": "TARGET_REACHED", "realized": goal["realized"],
                    "target": goal["target"], "period": goal["period"],
                    "reason": "Target tercapai, tidak mengirim order baru."}
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
    if cfg.mt5_mode == "mt5_native":
        # The native broker tools are dynamically typed and NOT yet risk-validated.
        # Return an AI proposal without turning it into a market order.
        return {"status": "SIGNAL_ONLY", "reason": reason,
                "proposal": {"symbol": intent.symbol, "side": intent.side,
                             "sl": intent.sl, "tp": intent.tp},
                "note": "Native MetaTrader MCP is read-only for automatic trading. "
                        "Use Local Terminal mode for risk-checked execution."}
    try:
        preview = preview_order(intent, cfg)
    except TradeRejected as exc:
        return {"status": "REJECTED", "reason": str(exc), "ai_reason": reason}
    if not Settings.load().execution_enabled:
        return {"status": "PREVIEW", "reason": reason, "order": preview}
    result = execute_order(intent)
    return {"status": "EXECUTED", "reason": reason, "order": result}
