import pytest
from lumavun import mt5_bridge
from lumavun.config import Settings
from lumavun.risk import OrderIntent, TradeRejected

def test_order_send_is_never_reached_when_disarmed(monkeypatch, tmp_path):
    class FakeMT5:
        def __init__(self):
            self.order_send_calls = 0
        def order_send(self, request):
            self.order_send_calls += 1
            raise AssertionError("Should not be called")
    fake = FakeMT5()
    monkeypatch.setattr(mt5_bridge, "_connected", lambda: fake)
    monkeypatch.setattr(mt5_bridge, "config_path", lambda: tmp_path / "settings.json")
    monkeypatch.setattr(Settings, "load", classmethod(lambda cls: Settings(execution_enabled=False)))
    with pytest.raises(TradeRejected, match="DISARMED"):
        mt5_bridge.execute_order(OrderIntent("XAUUSD", "BUY", 3990, 4020))
    assert fake.order_send_calls == 0

def test_mcp_cannot_send_without_separate_permission(monkeypatch, tmp_path):
    monkeypatch.setattr(mt5_bridge, "config_path", lambda: tmp_path / "settings.json")
    monkeypatch.setattr(Settings, "load", classmethod(lambda cls: Settings(execution_enabled=True, allow_mcp_orders=False)))
    with pytest.raises(TradeRejected, match="MCP order"):
        mt5_bridge.execute_order(OrderIntent("XAUUSD", "BUY", 3990, 4020), from_mcp=True)

def test_mt5_dll_import_failure_includes_original_diagnostic(monkeypatch):
    import builtins
    real_import = builtins.__import__

    def broken_mt5_import(name, *args, **kwargs):
        if name == "MetaTrader5":
            raise ImportError("DLL load failed while importing _core: The specified module could not be found")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", broken_mt5_import)
    with pytest.raises(RuntimeError, match="DLL load failed"):
        mt5_bridge._api()
