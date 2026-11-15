"""URL validation, generated key storage and ASGI permission tests."""
import asyncio
from types import SimpleNamespace
import pytest
from lumavun.gateway_auth import validate_endpoint, get_gateway_key, BearerGate
from lumavun.gateway_server import validate_bind

def test_internal_loopback_endpoint_allowed():
    assert validate_endpoint("http://127.0.0.1:8765/mcp") == "http://127.0.0.1:8765/mcp"

@pytest.mark.parametrize("url", ["http://192.168.1.20:8765/mcp", "http://example.com/mcp",
                                 "ftp://localhost/mcp", "https://user:password@example.com/mcp",
                                 "http://localhost:8765/not-mcp"])
def test_unsafe_or_invalid_url_refused(url):
    with pytest.raises(ValueError):
        validate_endpoint(url)

def test_tls_internal_endpoint_allowed():
    assert validate_endpoint("https://192.168.1.20:8765/mcp") == "https://192.168.1.20:8765/mcp"

def test_nonlocal_gateway_requires_tls_certificate():
    with pytest.raises(ValueError, match="HTTPS"):
        validate_bind("0.0.0.0", "", "", "")
    validate_bind("192.168.1.20", "192.168.1.20", "cert.pem", "key.pem")

def test_generated_key_is_persistent_and_rotatable(monkeypatch):
    from lumavun import gateway_auth
    vault = {}
    monkeypatch.setattr(gateway_auth.keyring, "get_password", lambda service, name: vault.get(name))
    monkeypatch.setattr(gateway_auth.keyring, "set_password", lambda service, name, key: vault.__setitem__(name, key))
    a = get_gateway_key()
    assert a.startswith("luma_") and len(a) > 35
    assert a == get_gateway_key()
    b = get_gateway_key(rotate=True)
    assert a != b
    assert b == get_gateway_key()

def test_invalid_api_key_denied_before_any_tool():
    seen = []
    async def inner(scope, receive, send):
        seen.append(True)
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"OK"})
    gate = BearerGate(inner, "long-secret-value")
    async def check(headers):
        sent = []
        async def send(msg):
            sent.append(msg)
        async def receive():
            return {"type": "http.request", "body": b"", "more_body": False}
        await gate({"type": "http", "headers": headers},
                   receive, send)
        return sent[0]["status"]
    assert asyncio.run(check([])) == 401
    assert asyncio.run(check([(b"authorization", b"Bearer wrong")])) == 401
    assert asyncio.run(check([(b"authorization", b"Bearer long-secret-value"),
                              (b"origin", b"http://example.com")])) == 403
    assert asyncio.run(check([(b"authorization", b"Bearer long-secret-value")])) == 200
    assert seen == [True]
