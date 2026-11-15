"""Contract tests for MetaQuotes' native MCP adapter.

The native server uses tool names different from the LUMAVUN gateway.
These tests never connect to a real trading account or place orders.
"""
from datetime import datetime, timezone
import pytest

from lumavun import native_mt5, mt5_access
from lumavun.config import Settings
from lumavun.gateway_auth import native_api_key, save_native_api_key
from lumavun.risk import OrderIntent

def native_config():
    return Settings(mt5_mode="mt5_native", mt5_native_url="http://127.0.0.1:22346/mcp")

def test_bearer_key_comes_from_mt5_specific_credential(monkeypatch):
    from lumavun import gateway_auth
    vault = {}
    monkeypatch.setattr(gateway_auth.keyring, "set_password",
                        lambda service, user, value: vault.__setitem__(user, value))
    monkeypatch.setattr(gateway_auth.keyring, "get_password",
                        lambda service, user: vault.get(user))
    save_native_api_key("fresh-mt5-only-secret")
    assert native_api_key() == "fresh-mt5-only-secret"
    assert gateway_auth.remote_key() == ""
    assert native_mt5._config(native_config()) == (
        "http://127.0.0.1:22346/mcp", "fresh-mt5-only-secret")

def test_native_connection_finds_actual_metaquotes_tool_names(monkeypatch):
    tools = [
        {"name": "get_trading_account_info", "description": "Account status",
         "inputSchema": {"type": "object", "properties": {}, "required": []}},
        {"name": "trade_send_market_order", "description": "Place an order",
         "inputSchema": {"type": "object", "properties": {"symbol": {"type": "string"}}}},
    ]
    monkeypatch.setattr(native_mt5, "list_native_tools", lambda cfg: tools)
    monkeypatch.setattr(native_mt5, "account_status",
                        lambda cfg: {"login": 123, "demo": True})
    data = native_mt5.inspect_connection(native_config())
    assert data["total_tools"] == 2
    assert data["account"]["login"] == 123
    assert data["read_only"] is True

def test_native_account_routes_to_metaquotes_not_old_gateway(monkeypatch):
    data = {"login": 1000, "server": "DemoServer", "equity": 100.0,
            "balance": 100.0, "currency": "USD", "trade_mode": 0}
    monkeypatch.setattr(native_mt5, "_read_tool",
                        lambda tool, args, cfg: data if tool == "get_trading_account_info"
                        else pytest.fail("Wrong tool"))
    account = mt5_access.account_status(native_config())
    assert account["source"] == "MetaTrader 5 built-in MCP"
    assert account["demo"] is True
    assert account["login"] == 1000

def test_unknown_account_type_is_not_assumed_demo(monkeypatch):
    monkeypatch.setattr(native_mt5, "_read_tool",
                        lambda tool, args, cfg: {"login": 888, "type": "unknown"})
    account = native_mt5.account_status(native_config())
    assert account["demo"] is None

def test_native_only_invokes_allowed_read_tools(monkeypatch):
    monkeypatch.setattr(native_mt5, "_get_tool",
                        lambda name, cfg: pytest.fail("Unsafe tool discovered"))
    with pytest.raises(native_mt5.NativeMT5Error, match="allowlist"):
        native_mt5._read_tool("trade_send_market_order", {"symbol":"XAUUSD"}, native_config())

def test_native_order_execution_is_always_blocked(monkeypatch):
    monkeypatch.setattr(Settings, "load", classmethod(lambda cls: Settings(
        mt5_mode="mt5_native", execution_enabled=True, live_allowed=True)))
    # Even an already-armed setting does not grant native order execution.
    with pytest.raises(native_mt5.NativeMT5Error, match="terkunci"):
        mt5_access.execute_order(OrderIntent("XAUUSD", "BUY", 4000, 4030))

def test_candle_args_follow_discovered_schema():
    tool = {"name": "get_chart_history", "inputSchema": {"type": "object",
            "properties": {"symbol": {}, "period": {"enum": ["M5", "M15"]},
                           "count": {"type": "integer"}},
            "required": ["symbol", "period", "count"]}}
    args = native_mt5._schema_args(tool, "BTCUSDc", "M5", 60)
    assert args == {"symbol": "BTCUSDc", "period": "M5", "count": 62}

def test_unknown_required_candle_arguments_fail_closed():
    tool = {"name": "get_chart_history", "inputSchema": {"type": "object",
        "properties": {"symbol": {}, "period": {}, "account_secret": {}},
        "required": ["symbol", "period", "account_secret"]}}
    with pytest.raises(native_mt5.NativeMT5Error, match="account_secret"):
        native_mt5._schema_args(tool, "XAUUSD", "M15", 60)

def test_candle_timestamp_excludes_unclosed_bar(monkeypatch):
    from datetime import timedelta
    now = datetime.now(timezone.utc).timestamp()
    cutoff = int(now // 300 * 300)
    bars = [{"time": cutoff - (j * 300), "open": 100, "high": 110, "low": 90, "close": 101}
            for j in range(12, -1, -1)]
    monkeypatch.setattr(native_mt5, "_get_tool", lambda name, cfg: {
        "name": name, "inputSchema": {"type": "object",
        "properties": {"symbol": {}, "timeframe": {}, "count": {}},
        "required": ["symbol","timeframe","count"]}})
    monkeypatch.setattr(native_mt5, "_read_tool", lambda name, params, cfg: {"bars":bars})
    result = native_mt5.get_candles("XAUUSD", "M5", 60, native_config())
    assert len(result) == 12
    assert result[-1]["time"] < cutoff

def test_native_strategy_returns_signal_without_sending_order(monkeypatch):
    from lumavun import engine
    monkeypatch.setattr(Settings, "load", classmethod(lambda cls: Settings(
        mt5_mode="mt5_native", last_signal_bar="", symbol="XAUUSD", timeframe="M15",
        execution_enabled=True)))
    monkeypatch.setattr(engine, "get_candles",
                        lambda *args: [{"time": i} for i in range(60)])
    monkeypatch.setattr(engine, "propose_trade",
                        lambda cfg, candles: (OrderIntent("XAUUSD","BUY",3990,4020),"test"))
    monkeypatch.setattr(engine, "preview_order", lambda *args:
                        pytest.fail("Native preview MUST be blocked"))
    monkeypatch.setattr(engine, "execute_order", lambda *args:
                        pytest.fail("Native order MUST not be placed"))
    monkeypatch.setattr(Settings, "save", lambda self: None)
    result = engine.run_strategy_once()
    assert result["status"] == "SIGNAL_ONLY"
    assert result["proposal"]["side"] == "BUY"
