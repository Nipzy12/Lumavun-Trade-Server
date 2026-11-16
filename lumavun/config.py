"""Persistent non-secret settings; API credentials live in OS credential storage."""
from __future__ import annotations
from dataclasses import asdict, dataclass, fields
import json
import os
from pathlib import Path
import keyring

PROVIDER_URLS = {
    "OpenAI": "https://api.openai.com/v1",
    "OpenRouter": "https://openrouter.ai/api/v1",
    "Groq": "https://api.groq.com/openai/v1",
    "DeepSeek": "https://api.deepseek.com/v1",
    "xAI": "https://api.x.ai/v1",
    "Together": "https://api.together.xyz/v1",
    "Mistral": "https://api.mistral.ai/v1",
    "Ollama": "http://127.0.0.1:11434/v1",
    "Anthropic": "https://api.anthropic.com/v1",
    "Gemini": "https://generativelanguage.googleapis.com/v1beta",
    "Custom (OpenAI-compatible)": "",
}

# Strategy presets translated from user-provided Pine Script v6 SMC Entry Models PRO.
# These are editable AI instructions, NOT a bar-by-bar Pine execution engine.
SMC_SHARED = """SMC Entry Models PRO | confirmed CLOSED candles only.
Higher timeframe H4: require bullish/bearish structure bias aligned with proposed trade; HTF POI source OB or FVG. If H4 candles/POI cannot be verified from supplied data, HOLD, never fabricate HTF confirmation.
Entry zone Proximal: BUY at upper zone boundary, SELL at lower zone boundary.
Quality strict (Ketat): heuristic score >=85/100, impulse body/range >=0.60, structural breakout body >=0.70 ATR, close beyond swing >=0.06 ATR, zone width 0.04-2.2 ATR. ATR period 14.
Invalidate OB/FVG only on confirmed candle CLOSE beyond zone edge plus 0.03 ATR buffer. Discard deeply mitigated (>=95%), non-fresh retested zones (max retests 0), or expired zones (>250 candles).
SL beyond structural extreme with 0.12 ATR buffer; TP exactly 2x entry-to-SL distance (RR 1:2). Pending valid 40 bars. Reject if stop distance >10 ATR. No future data or same-bar creation fills.
If insufficient historical candles, pivots or H4 context: HOLD. Score is heuristic, never a win-rate estimate. Do not send orders; return BUY/SELL/HOLD proposal only."""

SMC_MODELS = {
    "Manual / Custom": None,
    "Auto | M1 + M2 + M3 (priority)": """Evaluate three models independently and select only a fully qualified setup. When multiple qualify, prioritize M1, then M2, then M3; this is rule priority, NOT backtest-proven profitability. If no qualified model, HOLD.
M1: confirmed liquidity sweep penetrating swing by >=0.04 ATR, close back inside; within 14 bars require opposite structure CHoCH/MSS confirmed by CLOSE and shift candle body >=0.55 ATR; enter fresh OB, else qualified FVG retracement.
M2: trend continuation BOS confirmed by CLOSE, opposite candle OB origin <=8 bars, departure >=0.08 ATR, MUST have qualified fresh FVG within 6 bars of BOS; enter proximal OB.
M3: 3-candle FVG with middle candle displacement body >=1.0 ATR, gap >=0.12 ATR, trend/HTF alignment, enter proximal FVG.
""" + SMC_SHARED,
    "M1 | Sweep → CHoCH/MSS": """Only M1: liquidity sweep below/above confirmed swing penetrating >=0.04 ATR, candle closes back within swing; within 14 closed bars require opposing structural CLOSE break (CHoCH/MSS) with shift body >=0.55 ATR. Fresh OB retracement preferred; qualified fresh FVG fallback. No sweep + shift = HOLD.
""" + SMC_SHARED,
    "M2 | OB + FVG BOS": """Only M2: continuation BOS confirmed by candle CLOSE, body >=0.70 ATR, body/range >=0.60, close beyond structure >=0.06 ATR. Identify last opposite candle OB within 8 bars, clean departure >=0.08 ATR. Qualified fresh FVG near BOS within 6 bars is MANDATORY. Proximal OB entry; otherwise HOLD.
""" + SMC_SHARED,
    "M3 | FVG Sniper": """Only M3: three-candle fair value gap: bullish current low > high two candles ago, bearish current high < low two candles ago; minimum gap 0.12 ATR, middle candle body >=1.0 ATR, body/range >=0.60, structure and H4 bias agree. Proximal FVG entry; otherwise HOLD.
""" + SMC_SHARED,
}

DEFAULT_STRATEGY = """Timeframe M15. Identify confirmed liquidity sweeps with candle close confirmation.
Prefer HOLD unless setup is clear. For BUY, the SL is BELOW entry and TP ABOVE entry.
For SELL, the SL is ABOVE entry and TP BELOW entry.
Never open an order without a defensible stop loss. Do not infer information absent from candles.
One setup per closed candle. Risk reward should be at least 1:2."""

def config_path() -> Path:
    home = Path(os.environ.get("LOCALAPPDATA", "")) if os.name == "nt" else Path.home() / ".config"
    folder = home / "LUMAVUN" / "TradeServer"
    folder.mkdir(parents=True, exist_ok=True)
    return folder / "settings.json"

@dataclass
class Settings:
    provider: str = "OpenRouter"
    model: str = ""
    base_url: str = ""
    symbol: str = "XAUUSD"
    timeframe: str = "M15"
    strategy: str = DEFAULT_STRATEGY
    allow_symbols: str = "XAUUSD,EURUSD,BTCUSD"
    risk_per_trade_pct: float = 0.5
    max_daily_loss_pct: float = 3.0
    max_spread_points: float = 35.0
    max_lot: float = 0.1
    max_positions: int = 1
    max_trades_day: int = 5
    scan_interval_seconds: int = 120
    # Safe by default: cannot send orders until explicitly armed in desktop UI.
    execution_enabled: bool = False
    live_allowed: bool = False
    allow_mcp_orders: bool = False
    mt5_mode: str = "local"  # local | mcp_http (LUMAVUN Gateway) | mt5_native
    mt5_mcp_url: str = "http://127.0.0.1:8765/mcp"
    mt5_native_url: str = "http://127.0.0.1:22346/mcp"
    # Explicit opt-in to read closed candles from the local MT5 Python bridge
    # ONLY after native MCP account ID + broker server match the local account.
    native_local_candle_fallback: bool = False
    last_signal_bar: str = ""
    # Monitoring threshold, not a prediction or guarantee.
    profit_target_amount: float = 0.0
    profit_target_period: str = "day"
    pause_at_profit_target: bool = False

    @classmethod
    def load(cls) -> "Settings":
        path = config_path()
        if not path.exists():
            return cls()
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            valid = {f.name for f in fields(cls)}
            return cls(**{k: v for k, v in data.items() if k in valid})
        except (ValueError, TypeError, OSError):
            return cls()

    def save(self) -> None:
        path = config_path()
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(asdict(self), indent=2, ensure_ascii=False), encoding="utf-8")
        tmp.replace(path)

def put_api_key(provider: str, key: str) -> None:
    if key:
        keyring.set_password("LUMAVUN-Trade-Server", provider, key.strip())

def get_api_key(provider: str) -> str:
    try:
        return keyring.get_password("LUMAVUN-Trade-Server", provider) or ""
    except keyring.errors.KeyringError:
        return ""
