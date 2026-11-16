"""Broker-symbol regression tests. All terminals are fake: no real orders."""
from __future__ import annotations

from types import SimpleNamespace
import pytest

from lumavun import engine, mt5_bridge, native_mt5, mt5_access
from lumavun.config import Settings
from lumavun.risk import OrderIntent
from lumavun.symbols import (
    SymbolResolutionError, symbols_from_payload, resolve_symbol,
    search_catalogue, allowlisted, matches_canonical, candidate_symbols
)


def catalog(*symbols):
    return [{"symbol": name, "description": name, "visible": True} for name in symbols]


@pytest.mark.parametrize("requested,broker,expected", [
    ("XAUUSD", ["XAUUSDm"], "XAUUSDm"),
    ("XAUUSD", ["XAUUSDc"], "XAUUSDc"),
    ("XAUUSD", ["XAUUSD.pro"], "XAUUSD.pro"),
    ("XAUUSD", ["#XAUUSD"], "#XAUUSD"),
    ("XAUUSD", ["GOLD"], "GOLD"),
    ("GOLD", ["XAUUSDm"], "XAUUSDm"),
    ("EURUSD", ["EURUSD.a"], "EURUSD.a"),
    ("GBPUSD", ["GBPUSDm"], "GBPUSDm"),
    ("AUDCAD", ["AUDCADm"], "AUDCADm"),
    ("USDZAR", ["USDZAR.pro"], "USDZAR.pro"),
    ("USDZAR", ["USDZAR"], "USDZAR"),
    ("USDZAR", ["USDZARr"], "USDZARr"),
    ("AAPL", ["AAPLm"], "AAPLm"),
    ("DOGEUSD", ["DOGEUSDm"], "DOGEUSDm"),
    ("BTCUSD", ["BTCUSDc"], "BTCUSDc"),
    ("US100", ["NAS100m"], "NAS100m"),
    ("US30", ["DJ30.cash"], "DJ30.cash"),
    ("XAUUSD", ["XAUUSD", "XAUUSDm"], "XAUUSD"),
    ("xauusdm", ["XAUUSDm", "XAUUSDc"], "XAUUSDm"),
])
def test_unique_broker_symbol_resolution(requested, broker, expected):
    assert resolve_symbol(requested, catalog(*broker)) == expected


def test_multiple_valid_suffixes_must_be_selected_by_user():
    with pytest.raises(SymbolResolutionError, match="AMBIGUOUS_SYMBOL") as err:
        resolve_symbol("XAUUSD", catalog("XAUUSDm", "XAUUSDc"))
    assert "XAUUSDm" in str(err.value) and "XAUUSDc" in str(err.value)


def test_explicit_broker_suffix_never_switches_account_tier():
    with pytest.raises(SymbolResolutionError, match="SYMBOL_UNAVAILABLE"):
        resolve_symbol("XAUUSDm", catalog("XAUUSDc"))
    with pytest.raises(SymbolResolutionError, match="SYMBOL_UNAVAILABLE"):
        resolve_symbol("EURUSD.pro", catalog("EURUSD.raw"))


def test_no_cross_quote_pair_or_forward_contract_substitution():
    assert not matches_canonical("BTCUSD", "BTCUSDT")
    assert not matches_canonical("BTCUSD", "BTCUSDC")
    assert not matches_canonical("XAUUSD", "XAUUSDF")
    with pytest.raises(SymbolResolutionError, match="SYMBOL_UNAVAILABLE"):
        resolve_symbol("BTCUSD", catalog("BTCUSDT"))
    with pytest.raises(SymbolResolutionError, match="SYMBOL_UNAVAILABLE"):
        resolve_symbol("BTCUSD", catalog("BTCUSDC"))
    with pytest.raises(SymbolResolutionError, match="SYMBOL_UNAVAILABLE"):
        resolve_symbol("XAUUSD", catalog("XAUUSDF"))


def test_risk_allowlist_accepts_broker_tier_only_for_generic_entry():
    assert allowlisted("XAUUSD,EURUSD,BTCUSD", "XAUUSDm")
    assert allowlisted("GOLD", "XAUUSDc")
    assert not allowlisted("XAUUSDm", "XAUUSDc")
    assert not allowlisted("BTCUSD", "BTCUSDT")
    assert not allowlisted("XAUUSD", "XAUUSDF")


def test_marketwatch_search_keeps_actual_symbol_case_and_unusual_suffix():
    x = catalog("XAUUSDm", "XAUUSDc", "XAUUSD.special", "BTCUSDc")
    values = [v["symbol"] for v in search_catalogue("XAUUSD", x)]
    assert set(values) == {"XAUUSDm", "XAUUSDc", "XAUUSD.special"}
    assert "BTCUSDc" not in values


def test_native_marketwatch_handles_nested_payloads():
    source = {"result": {"symbols": [
        {"symbol": "XAUUSDm", "visible": True, "description": "Gold Micro"},
        {"symbol": "BTCUSDc", "visible": True},
    ]}}
    result = symbols_from_payload(source)
    assert [x["symbol"] for x in result] == ["XAUUSDm", "BTCUSDc"]


def test_python_namedtuple_catalog_retains_broker_name():
    mt5 = [SimpleNamespace(name="XAUUSDm", visible=True, description="Gold")]
    assert resolve_symbol("XAUUSD", symbols_from_payload(tuple(mt5))) == "XAUUSDm"


def test_local_bridge_reads_closed_candles_using_resolved_symbol(monkeypatch):
    calls = []
    class FakeMT5:
        TIMEFRAME_M5 = 5
        def symbols_get(self):
            return (SimpleNamespace(name="XAUUSDc", visible=True),)
        def symbol_info(self, symbol):
            calls.append(("info", symbol))
            return SimpleNamespace(name=symbol) if symbol == "XAUUSDc" else None
        def symbol_select(self, symbol, show):
            calls.append(("select", symbol, show))
            return symbol == "XAUUSDc"
        def copy_rates_from_pos(self, symbol, tf, pos, count):
            calls.append(("rates", symbol, tf, pos, count))
            return [{"time": 1700000000+i*300, "open": 100, "high": 102,
                     "low": 99, "close": 101, "tick_volume": 12}
                    for i in range(count)]
    fake = FakeMT5()
    monkeypatch.setattr(mt5_bridge, "_connected", lambda: fake)
    data = mt5_bridge.get_candles("XAUUSD", "M5", 60)
    assert len(data) == 60
    assert ("rates", "XAUUSDc", 5, 1, 60) in calls


def test_native_mcp_calls_readonly_marketwatch_for_broker_name(monkeypatch):
    cfg = Settings(mt5_mode="mt5_native")
    received = []
    def fake_read(tool, args, cfg):
        received.append(tool)
        if tool != "get_marketwatch_symbols":
            pytest.fail("No other native tool should be called for symbol discovery")
        return {"symbols": [{"symbol": "BTCUSDc"}, {"symbol": "XAUUSDm"}]}
    monkeypatch.setattr(native_mt5, "_read_tool", fake_read)
    assert native_mt5.resolve_broker_symbol("XAUUSD", cfg) == "XAUUSDm"
    assert received == ["get_marketwatch_symbols"]
    assert native_mt5.list_broker_symbols("BTC", cfg)[0]["symbol"] == "BTCUSDc"


def test_engine_uses_exact_symbol_for_ai_and_preview_without_executing(monkeypatch):
    cfg = Settings(symbol="XAUUSD", timeframe="M5", execution_enabled=False)
    monkeypatch.setattr(Settings, "load", classmethod(lambda cls: cfg))
    monkeypatch.setattr(Settings, "save", lambda self: None)
    monkeypatch.setattr(engine, "resolve_broker_symbol", lambda *args: "XAUUSDm")
    monkeypatch.setattr(engine, "get_candles", lambda symbol,tf,count,cfg: [
        {"time": i} for i in range(60)] if symbol == "XAUUSDm" else pytest.fail("wrong candle source"))
    def ai_read(model_cfg, bars):
        assert model_cfg.symbol == "XAUUSDm"
        return OrderIntent(model_cfg.symbol, "BUY", 3990, 4020), "Mock AI result"
    monkeypatch.setattr(engine, "propose_trade", ai_read)
    monkeypatch.setattr(engine, "preview_order", lambda intent,cfg: {
        "symbol": intent.symbol} if intent.symbol == "XAUUSDm" else pytest.fail("wrong order symbol"))
    monkeypatch.setattr(engine, "execute_order", lambda *args,**kwargs: pytest.fail("No real order"))
    result = engine.run_strategy_once()
    assert result["status"] == "PREVIEW"
    assert result["broker_symbol"] == "XAUUSDm"
    assert result["order"]["symbol"] == "XAUUSDm"


def test_ambiguous_broker_catalog_prevents_ai_and_order(monkeypatch):
    cfg = Settings(symbol="XAUUSD", execution_enabled=True, live_allowed=True)
    monkeypatch.setattr(Settings, "load", classmethod(lambda cls: cfg))
    def reject(*args,**kwargs):
        raise SymbolResolutionError("AMBIGUOUS_SYMBOL: XAUUSD. XAUUSDm, XAUUSDc")
    monkeypatch.setattr(engine, "resolve_broker_symbol", reject)
    monkeypatch.setattr(engine, "get_candles", lambda *args: pytest.fail("No candles from ambiguous symbol"))
    monkeypatch.setattr(engine, "propose_trade", lambda *args: pytest.fail("No AI call"))
    monkeypatch.setattr(engine, "execute_order", lambda *args: pytest.fail("No order"))
    result = engine.run_strategy_once()
    assert result["status"] == "DATA_UNAVAILABLE"
    assert "AMBIGUOUS_SYMBOL" in result["reason"]
