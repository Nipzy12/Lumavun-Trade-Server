"""Live MCP handshake over localhost with the actual SDK and HTTP transport."""
from __future__ import annotations
import socket
import threading
import time
import httpx
import uvicorn
from lumavun import mcp_server, mt5_access
from lumavun.config import Settings
from lumavun.gateway_server import build_app

def test_mcp_http_handshake_auth_and_tool_calls(monkeypatch):
    # Fake ONLY the broker boundary. The MCP server, transport and client are real.
    monkeypatch.setattr(mcp_server, "account_status", lambda: {
        "login": 42, "server": "Demo-Simulated", "balance": 100.0,
        "equity": 100.0, "currency": "USD", "demo": True,
        "terminal_trade_allowed": False, "account_trade_allowed": False,
    })
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    token = "test-secret-" + ("x" * 32)
    app = build_app(token, bind="127.0.0.1", port=port)
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1",
                        port=port, access_log=False, log_level="error"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    try:
        for _ in range(100):
            if server.started:
                break
            time.sleep(0.1)
        assert server.started, "Gateway did not start"
        url = f"http://127.0.0.1:{port}/mcp"
        with httpx.Client(timeout=5) as client:
            response = client.post(url, json={"jsonrpc":"2.0", "method":"initialize", "id":1})
            assert response.status_code == 401, response.text
            from_browser = client.post(url, headers={"Authorization":"Bearer " + token,
                                "Origin":"http://evil.example"}, json={})
            assert from_browser.status_code == 403
        monkeypatch.setattr(mt5_access, "remote_key", lambda: token)
        account = mt5_access.gateway_call("mt5_account", {},
                    Settings(mt5_mode="mcp_http", mt5_mcp_url=url))
        assert account["login"] == 42
        assert account["demo"] is True
    finally:
        server.should_exit = True
        thread.join(timeout=8)
        assert not thread.is_alive(), "Gateway did not stop cleanly"
