"""Orchestrates closed-candle AI proposals and the shared risk-checked MT5 bridge."""
from __future__ import annotations
from dataclasses import replace
from .ai import propose_trade
from .config import Settings
from .mt5_access import get_candles, preview_order, execute_order, resolve_broker_symbol, MCPGatewayError
from .symbols import SymbolResolutionError
from .risk import TradeRejected
from .native_mt5 import NativeMT5Error
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
    try:
        actual = resolve_broker_symbol(cfg.symbol, cfg)
        candles = get_candles(actual, cfg.timeframe, 60, cfg)
    except (NativeMT5Error, SymbolResolutionError, MCPGatewayError, RuntimeError, ValueError) as exc:
        return {"status": "DATA_UNAVAILABLE", "reason": str(exc),
                "requested_symbol": cfg.symbol,
                "note": "Simbol/data broker belum diverifikasi. AI tidak dijalankan dan tidak ada order dikirim."}
    bar_key = actual + ":" + cfg.timeframe + ":" + str(candles[-1]["time"])
    if cfg.last_signal_bar == bar_key:
        return {"status": "SKIP", "reason": "Already evaluated the latest closed candle"}
    intent, reason = propose_trade(replace(cfg, symbol=actual), candles)
    # Never retry this candle automatically, including rejected proposals.
    fresh = Settings.load()
    fresh.last_signal_bar = bar_key
    fresh.save()
    if intent is None:
        return {"status": "HOLD", "reason": reason, "requested_symbol": cfg.symbol,
                "broker_symbol": actual}
    if cfg.mt5_mode == "mt5_native":
        # The native broker tools are dynamically typed and NOT yet risk-validated.
        # Return an AI proposal without turning it into a market order.
        return {"status": "SIGNAL_ONLY", "reason": reason, "requested_symbol": cfg.symbol,
                "broker_symbol": actual,
                "proposal": {"symbol": intent.symbol, "side": intent.side,
                             "sl": intent.sl, "tp": intent.tp},
                "note": "Native MetaTrader MCP is read-only for automatic trading. "
                        "Use Local Terminal mode for risk-checked execution."}
    try:
        preview = preview_order(intent, cfg)
    except TradeRejected as exc:
        return {"status": "REJECTED", "reason": str(exc), "ai_reason": reason,
                "broker_symbol": actual}
    if not Settings.load().execution_enabled:
        return {"status": "PREVIEW", "reason": reason, "order": preview,
                "broker_symbol": actual}
    result = execute_order(intent)
    return {"status": "EXECUTED", "reason": reason, "order": result,
            "broker_symbol": actual}
