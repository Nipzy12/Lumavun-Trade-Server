"""Secrets and minimal ASGI bearer-token gate for the MT5 MCP HTTP gateway."""
from __future__ import annotations

import hmac
import ipaddress
import secrets
from urllib.parse import urlsplit
import keyring

VAULT_SERVICE = "LUMAVUN-Trade-Server"
VAULT_USER = "mt5-mcp-gateway"

def get_gateway_key(*, rotate: bool = False) -> str:
    """An independent LUMAVUN API token. MT5 itself does not issue MCP API keys."""
    if not rotate:
        existing = keyring.get_password(VAULT_SERVICE, VAULT_USER)
        if existing:
            return existing
    key = "luma_" + secrets.token_urlsafe(32)
    keyring.set_password(VAULT_SERVICE, VAULT_USER, key)
    return key

def save_remote_key(key: str) -> None:
    if not key or len(key.strip()) < 24:
        raise ValueError("MCP API key is empty or too short")
    keyring.set_password(VAULT_SERVICE, "mt5-mcp-remote", key.strip())

def remote_key() -> str:
    return keyring.get_password(VAULT_SERVICE, "mt5-mcp-remote") or ""

def validate_endpoint(url: str) -> str:
    """Credentials are never sent to arbitrary cleartext remote hosts."""
    candidate = url.strip()
    try:
        parsed = urlsplit(candidate)
        host = parsed.hostname
        port = parsed.port
    except ValueError as exc:
        raise ValueError("Invalid MCP server address") from exc
    if parsed.scheme not in ("http", "https") or not host:
        raise ValueError("MCP endpoint must be a complete HTTP(S) URL")
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError("MCP endpoint must not contain credentials, queries or fragments")
    if parsed.path != "/mcp":
        raise ValueError("MCP endpoint must end in /mcp")
    if parsed.scheme == "http":
        try:
            loopback = ipaddress.ip_address(host).is_loopback
        except ValueError:
            loopback = host.lower() == "localhost"
        if not loopback:
            raise ValueError("Non-local MCP addresses must use HTTPS (or an encrypted localhost tunnel)")
    if port is not None and not 1 <= port <= 65535:
        raise ValueError("Invalid MCP port")
    return candidate

class BearerGate:
    """Pure ASGI middleware; BaseHTTPMiddleware breaks streaming MCP transports."""
    def __init__(self, app, token: str):
        if not token:
            raise ValueError("Gateway API key cannot be empty")
        self.app = app
        self.token = token.encode("utf-8")

    async def __call__(self, scope, receive, send):
        if scope.get("type") != "http":
            return await self.app(scope, receive, send)
        headers = {k.lower(): v for k, v in scope.get("headers", [])}
        # MCP clients are native apps; browser Origins are deliberately rejected.
        if b"origin" in headers:
            return await self._deny(send, 403, b"Browser origin is not permitted")
        expected_prefix = b"Bearer "
        authorization = headers.get(b"authorization", b"")
        bearer = authorization[len(expected_prefix):] if authorization.startswith(expected_prefix) else b""
        if not bearer or not hmac.compare_digest(bearer, self.token):
            return await self._deny(send, 401, b"Unauthorized")
        return await self.app(scope, receive, send)

    @staticmethod
    async def _deny(send, status: int, body: bytes):
        await send({"type": "http.response.start", "status": status,
                    "headers": [(b"content-type", b"text/plain; charset=utf-8"),
                                (b"cache-control", b"no-store")]})
        await send({"type": "http.response.body", "body": body})
