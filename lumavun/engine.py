"""Orchestrates closed-candle AI proposals and the shared risk-checked MT5 bridge."""
from __future__ import annotations
from .ai import propose_trade
from .config import Settings
from .mt5_access import get_candles, preview_order, execute_order
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
    is_smc_preset = cfg.strategy.lstrip().startswith(("SMC Entry Models PRO", "Evaluate three models independently", "Only M1:", "Only M2:", "Only M3:"))
    try:
        candles = get_candles(cfg.symbol, cfg.timeframe, 350 if is_smc_preset else 60, cfg)
    except (NativeMT5Error, RuntimeError, ValueError) as exc:
        return {"status": "DATA_UNAVAILABLE", "reason": str(exc),
                "note": "AI tidak dijalankan dan tidak ada order dikirim."}
    htf_candles = None
    if is_smc_preset:
        if cfg.timeframe in ("H4", "D1"):
            return {"status": "DATA_UNAVAILABLE",
                    "reason": "SMC H4 confirmation requires a lower execution timeframe.",
                    "note": "No AI proposal or order was sent."}
        try:
            htf_candles = get_candles(cfg.symbol, "H4", 350, cfg)
            if len(htf_candles) < 30 or int(htf_candles[-1]["time"]) > int(candles[-1]["time"]):
                return {"status": "DATA_UNAVAILABLE",
                        "reason": "Closed H4 history is missing or newer than the last execution candle.",
                        "note": "No AI proposal or order was sent."}
        except Exception as exc:
            return {"status": "DATA_UNAVAILABLE",
                    "reason": "Cannot verify closed H4 candles: " + type(exc).__name__,
                    "note": "No AI proposal or order was sent."}
    bar_key = cfg.symbol + ":" + cfg.timeframe + ":" + str(candles[-1]["time"])
    if cfg.last_signal_bar == bar_key:
        return {"status": "SKIP", "reason": "Already evaluated the latest closed candle"}
    if is_smc_preset:
        from .smc_engine import evaluate
        strategy = cfg.strategy.lstrip()
        model = ("M1" if strategy.startswith("Only M1:") else
                 "M2" if strategy.startswith("Only M2:") else
                 "M3" if strategy.startswith("Only M3:") else "AUTO")
        try:
            setup = evaluate(candles, htf_candles, model)
        except (ValueError, KeyError, TypeError) as exc:
            return {"status": "DATA_UNAVAILABLE", "reason": "SMC evaluation: " + str(exc)}
        fresh = Settings.load()
        fresh.last_signal_bar = bar_key
        fresh.save()
        if setup is None:
            return {"status": "HOLD", "reason": "No deterministic SMC setup meets model and H4 filters."}
        return {"status": "SIGNAL_ONLY", "reason": setup.reason,
                "proposal": setup.to_dict(),
                "note": "Deterministic SMC research signal; order execution disabled."}
    intent, reason = propose_trade(cfg, candles, htf_candles)
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
