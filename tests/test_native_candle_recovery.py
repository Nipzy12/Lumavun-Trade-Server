"""Regression cases for MT5 native MCP candle tool discovery and safe recovery."""
from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from lumavun import engine, mt5_bridge, native_mt5
from lumavun.config import Settings


def _tool(name):
    return SimpleNamespace(name=name, description=name, inputSchema={"type": "object", "properties": {}})


def test_native_tool_discovery_reads_all_mcp_pages(monkeypatch):
    """MetaTrader may publish get_chart_history on a later tools/list page."""
    import mcp
    import mcp.client.streamable_http as transport

    cursors = []

    class Context:
        def __init__(self, value):
            self.value = value

        async def __aenter__(self):
            return self.value

        async def __aexit__(self, exc_type, exc, tb):
            return False

    class Session:
        async def initialize(self):
            pass

        async def list_tools(self, *, cursor=None):
            cursors.append(cursor)
            if cursor is None:
                return SimpleNamespace(
                    tools=[_tool("get_trading_account_info")],
                    next_cursor="second-page",
                )
            if cursor == "second-page":
                return SimpleNamespace(
                    tools=[_tool("get_chart_history")],
                    next_cursor=None,
                )
            raise AssertionError("Unknown pagination cursor")

    monkeypatch.setattr(transport, "streamablehttp_client",
                        lambda **kwargs: Context((None, None, None)))
    monkeypatch.setattr(mcp, "ClientSession", lambda *args: Context(Session()))

    tools = asyncio.run(native_mt5._list_tools("http://127.0.0.1:22346/mcp", "placeholder-secret"))
    assert [tool["name"] for tool in tools] == [
        "get_trading_account_info", "get_chart_history"
    ]
    assert cursors == [None, "second-page"]


def test_missing_chart_history_reports_available_tools_and_local_option(monkeypatch):
    cfg = Settings(mt5_mode="mt5_native")
    monkeypatch.setattr(native_mt5, "list_native_tools", lambda _: [
        {"name": "get_trading_account_info", "inputSchema": {}},
        {"name": "get_chart_ticks_history", "inputSchema": {}},
    ])
    with pytest.raises(native_mt5.NativeMT5Error) as err:
        native_mt5.get_candles("XAUUSD", "M5", 60, cfg)
    message = str(err.value)
    assert "get_chart_history" in message
    assert "get_chart_ticks_history" in message
    assert "MT5" in message
    assert "fallback" in message.lower()


def test_explicit_local_candle_fallback_accepts_same_broker_account(monkeypatch):
    cfg = Settings(mt5_mode="mt5_native")
    cfg.native_local_candle_fallback = True

    monkeypatch.setattr(native_mt5, "list_native_tools", lambda _: [
        {"name": "get_trading_account_info", "inputSchema": {}}
    ])
    monkeypatch.setattr(native_mt5, "account_status", lambda *_: {
        "login": 482919, "server": "Demo-Broker", "demo": True,
    })
    monkeypatch.setattr(mt5_bridge, "account_status", lambda: {
        "login": 482919, "server": "Demo-Broker", "demo": True,
    })
    expected = [{"time": 1700000000, "open": 1, "high": 2, "low": 0, "close": 1}]
    received = []
    monkeypatch.setattr(mt5_bridge, "get_candles",
                        lambda symbol, tf, count: received.append((symbol, tf, count)) or expected)
    result = native_mt5.get_candles("XAUUSD", "M5", 60, cfg)
    assert result == expected
    assert received == [("XAUUSD", "M5", 60)]


def test_local_fallback_never_reads_wrong_account(monkeypatch):
    cfg = Settings(mt5_mode="mt5_native")
    cfg.native_local_candle_fallback = True
    monkeypatch.setattr(native_mt5, "list_native_tools", lambda _: [])
    monkeypatch.setattr(native_mt5, "account_status", lambda *_: {
        "login": 482919, "server": "Demo-Broker"
    })
    monkeypatch.setattr(mt5_bridge, "account_status", lambda: {
        "login": 111000, "server": "Different-Broker"
    })
    monkeypatch.setattr(mt5_bridge, "get_candles",
                        lambda *args: pytest.fail("Different accounts must never share candles"))
    with pytest.raises(native_mt5.NativeMT5Error, match="akun|account"):
        native_mt5.get_candles("XAUUSD", "M5", 60, cfg)


def test_engine_pauses_before_ai_if_native_bars_are_unavailable(monkeypatch):
    cfg = Settings(mt5_mode="mt5_native")
    monkeypatch.setattr(Settings, "load", classmethod(lambda cls: cfg))
    monkeypatch.setattr(engine, "resolve_broker_symbol", lambda symbol,cfg: symbol)
    monkeypatch.setattr(engine, "get_candles",
                        lambda *args: (_ for _ in ()).throw(
                            native_mt5.NativeMT5Error("Candle MCP tidak tersedia")))
    monkeypatch.setattr(engine, "propose_trade",
                        lambda *args: pytest.fail("Cannot analyze absent broker candles"))
    result = engine.run_strategy_once()
    assert result["status"] == "DATA_UNAVAILABLE"
    assert "Candle" in result["reason"]
