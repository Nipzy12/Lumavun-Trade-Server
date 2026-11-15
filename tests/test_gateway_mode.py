"""Connection routing and trade permission checks."""
import pytest
from lumavun.config import Settings
from lumavun import mt5_access
from lumavun.risk import OrderIntent

def test_remote_account_uses_gateway_not_local_terminal(monkeypatch):
    called = []
    monkeypatch.setattr(mt5_access, "gateway_call", lambda tool, arguments, cfg: called.append(tool) or {"demo": True})
    state = mt5_access.account_status(Settings(mt5_mode="mcp_http"))
    assert state == {"demo": True}
    assert called == ["mt5_account"]

def test_remote_trade_requires_client_arming(monkeypatch):
    monkeypatch.setattr(Settings, "load", classmethod(lambda cls: Settings(mt5_mode="mcp_http", execution_enabled=False)))
    monkeypatch.setattr(mt5_access, "gateway_call", lambda *a, **k: pytest.fail("Should not be sent"))
    with pytest.raises(mt5_access.MCPGatewayError, match="DISARMED"):
        mt5_access.execute_order(OrderIntent("XAUUSD", "BUY", 3990, 4020))

def test_remote_live_requires_client_live_permission(monkeypatch):
    monkeypatch.setattr(Settings, "load", classmethod(lambda cls: Settings(mt5_mode="mcp_http", execution_enabled=True, live_allowed=False)))
    calls = []
    def tool(name, args, cfg):
        calls.append(name)
        if name == "mt5_account":
            return {"demo": False}
        pytest.fail("Must not request an order on LIVE")
    monkeypatch.setattr(mt5_access, "gateway_call", tool)
    with pytest.raises(mt5_access.MCPGatewayError, match="LIVE"):
        mt5_access.execute_order(OrderIntent("XAUUSD", "BUY", 3990, 4020))
    assert calls == ["mt5_account"]
