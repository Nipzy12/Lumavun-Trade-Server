"""Broker-specific symbol variants: pure matching, MT5 catalog and fail-closed engine."""
from __future__ import annotations
from types import SimpleNamespace
import pytest
from lumavun.config import Settings
from lumavun.symbols import match_symbol, SymbolResolutionError, SymbolMatch


@pytest.mark.parametrize(("request","catalog","chosen"),[
    ("XAUUSD",["EURUSD","XAUUSDm"],"XAUUSDm"),
    ("XAUUSD",["XAUUSDc"],"XAUUSDc"),
    ("XAUUSD",["XAUUSD.pro"],"XAUUSD.pro"),
    ("XAUUSD",["xauusd.r"],"xauusd.r"),
    ("GBPUSD",["GBPUSDm"],"GBPUSDm"),
    ("US30",["US30.cash"],"US30.cash"),
    ("BTCUSD",["BTCUSDm"],"BTCUSDm"),
    ("EURUSD",["EUR/USD"],"EUR/USD"),
])
def test_unique_valid_variants(request,catalog,chosen):
    match=match_symbol(request,catalog)
    assert match.resolved==chosen and match.changed


def test_exact_preferred_over_any_suffix():
    matched=match_symbol("XAUUSD",["XAUUSDc","XAUUSDm","XAUUSD"])
    assert matched.resolved=="XAUUSD"
    assert matched.kind=="EXACT"


def test_case_only_variant():
    matched=match_symbol("xauusdm",["XAUUSDm"])
    assert matched.resolved=="XAUUSDm"
    assert matched.kind=="CASE_ONLY"


def test_multiple_suffixes_fail_closed():
    with pytest.raises(SymbolResolutionError) as e:
        match_symbol("XAUUSD",["XAUUSDm","XAUUSDc","EURUSD"])
    assert e.value.code=="AMBIGUOUS"
    assert set(e.value.candidates)=={"XAUUSDm","XAUUSDc"}


@pytest.mark.parametrize("other",["BTCUSDT","BTCUSDC"])
def test_btcusd_not_mistaken_for_different_crypto_quote(other):
    with pytest.raises(SymbolResolutionError) as e:
        match_symbol("BTCUSD",[other])
    assert e.value.code=="NOT_FOUND"


def test_no_catalog_fails_closed():
    with pytest.raises(SymbolResolutionError) as e:
        match_symbol("XAUUSD",[])
    assert e.value.code=="CATALOG_UNAVAILABLE"


def test_readonly_mt5_bridge_uses_actual_broker_symbol(monkeypatch):
    from lumavun import mt5_bridge
    called=[]
    class FakeMT5:
        TIMEFRAME_M15=15
        def symbol_info(self,name):
            return None if name=="XAUUSD" else object()
        def symbols_get(self):
            return [SimpleNamespace(name="XAUUSDm"),SimpleNamespace(name="EURUSDm")]
        def symbol_select(self,name,visible):
            called.append(("select",name,visible))
            return True
        def copy_rates_from_pos(self,name,tf,start,count):
            called.append(("rates",name,tf,start,count))
            return [{"time":i*900,"open":1,"high":2,"low":.5,"close":1.5,
                     "tick_volume":100} for i in range(15)]
    monkeypatch.setattr(mt5_bridge,"_connected",lambda:FakeMT5())
    result=mt5_bridge.get_candles("XAUUSD","M15",15)
    assert len(result)==15
    assert ("select","XAUUSDm",True) in called
    assert ("rates","XAUUSDm",15,1,15) in called


def test_engine_alias_update_disarms_and_propagates_exact_symbol(monkeypatch):
    from lumavun import engine
    cfg=Settings(symbol="XAUUSD",mt5_mode="local",
                 allow_symbols="XAUUSD", execution_enabled=True,
                 live_allowed=True,allow_mcp_orders=True)
    seen=[]
    monkeypatch.setattr(Settings,"load",classmethod(lambda cls:cfg))
    monkeypatch.setattr(Settings,"save",lambda self:None)
    monkeypatch.setattr(engine,"resolve_broker_symbol",
                        lambda symbol,config:SymbolMatch(symbol,"XAUUSDc","UNIQUE_SUFFIX"))
    monkeypatch.setattr(engine,"get_candles",
                        lambda symbol,*args:seen.append(symbol) or
                        [{"time":i*900,"open":100,"high":101,"low":99,"close":100}
                         for i in range(60)])
    monkeypatch.setattr(engine,"propose_trade",lambda config,candles:(None,"HOLD"))
    result=engine.run_strategy_once()
    assert result["status"]=="HOLD"
    assert seen==["XAUUSDc"]
    assert cfg.symbol=="XAUUSDc"
    assert result["broker_symbol"]=="XAUUSDc"
    assert not cfg.execution_enabled and not cfg.live_allowed and not cfg.allow_mcp_orders
    assert cfg.allow_symbols=="XAUUSD"  # user must explicitly approve new execution symbol


def test_engine_ambiguous_variants_do_not_read_market_or_send_order(monkeypatch):
    from lumavun import engine
    cfg=Settings(symbol="XAUUSD",mt5_mode="local",pause_at_profit_target=False)
    monkeypatch.setattr(Settings,"load",classmethod(lambda cls:cfg))
    def ambiguous(*_):
        raise SymbolResolutionError("Choose broker symbol",code="AMBIGUOUS",
                                    candidates=["XAUUSDc","XAUUSDm"])
    monkeypatch.setattr(engine,"resolve_broker_symbol",ambiguous)
    monkeypatch.setattr(engine,"get_candles",lambda *_:pytest.fail("Cannot read ambiguous symbol"))
    monkeypatch.setattr(engine,"execute_order",lambda *_:pytest.fail("Cannot send order"))
    result=engine.run_strategy_once()
    assert result["status"]=="SYMBOL_SELECTION_REQUIRED"
    assert len(result["candidate_symbols"])==2


def test_gateway_symbol_catalog_is_transport_specific(monkeypatch):
    from lumavun import mt5_access
    captured=[]
    monkeypatch.setattr(mt5_access,"gateway_call",
                        lambda name,args,cfg:captured.append(name) or ["XAUUSDc","EURUSDc"])
    cfg=Settings(mt5_mode="mcp_http")
    matched=mt5_access.resolve_broker_symbol("XAUUSD",cfg)
    assert matched.resolved=="XAUUSDc"
    assert captured==["mt5_symbols"]


def test_native_does_not_use_unverified_local_broker(monkeypatch):
    from lumavun import mt5_access
    cfg=Settings(mt5_mode="mt5_native")
    assert mt5_access.resolve_broker_symbol("XAUUSD",cfg).kind=="NATIVE_MANUAL"
    with pytest.raises(mt5_access.MCPGatewayError):
        mt5_access.broker_symbols(cfg)
