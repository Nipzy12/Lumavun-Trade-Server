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
    last_signal_bar: str = ""

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
