"""Run MCP Streamable HTTP on the computer that has a logged-in MT5 terminal."""
from __future__ import annotations

import argparse
import ipaddress
from .gateway_auth import BearerGate, get_gateway_key

def _is_loopback(bind: str) -> bool:
    try:
        return ipaddress.ip_address(bind).is_loopback
    except ValueError:
        return bind.lower() == "localhost"

def validate_bind(bind: str, public_host: str, cert: str, cert_key: str) -> None:
    try:
        ipaddress.ip_address(bind)
    except ValueError as exc:
        raise ValueError("Bind address must be an explicit IP, e.g. 127.0.0.1 or 192.168.1.10") from exc
    if _is_loopback(bind):
        return
    if not all((public_host, cert, cert_key)):
        raise ValueError("Non-loopback MCP requires --public-host, --certfile and --keyfile (HTTPS)")
    if "/" in public_host or ":" in public_host or "@" in public_host:
        raise ValueError("Public host must be hostname/IP only, without scheme or port")

def build_app(key: str, bind: str = "127.0.0.1", port: int = 8765, public_host: str = ""):
    from mcp.server.transport_security import TransportSecuritySettings
    from .mcp_server import mcp
    # v1 SDK's FastMCP settings own the transport configuration. Explicit
    # host allowlisting avoids 421 errors while retaining DNS-rebinding defense.
    host_allow = ["localhost:*", "127.0.0.1:*", "[::1]:*"]
    if public_host:
        host_allow.append(public_host + ":*")
    mcp.settings.transport_security = TransportSecuritySettings(
        enable_dns_rebinding_protection=True,
        allowed_hosts=host_allow,
        allowed_origins=[],
    )
    mcp.settings.host = bind
    mcp.settings.port = port
    return BearerGate(mcp.streamable_http_app(), key)

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="LUMAVUN MT5 MCP internal gateway")
    parser.add_argument("--bind", default="127.0.0.1", help="Listen IP (default: localhost)")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--public-host", default="", help="Hostname or IP on the trusted TLS certificate")
    parser.add_argument("--certfile", default="", help="Trusted TLS certificate chain for LAN")
    parser.add_argument("--keyfile", default="", help="TLS private key file for LAN")
    parser.add_argument("--rotate-key", action="store_true", help="Replace old API key and print the new key")
    args = parser.parse_args(argv)
    if not 1 <= args.port <= 65535:
        parser.error("Port must be between 1 and 65535")
    try:
        validate_bind(args.bind, args.public_host, args.certfile, args.keyfile)
        key = get_gateway_key(rotate=args.rotate_key)
    except (ValueError, Exception) as exc:
        parser.error("Gateway setup failed: " + str(exc))
    # Only console on the gateway host displays this key; never place it in URL/log files.
    print("LUMAVUN MCP URL: "
          + ("http://" if _is_loopback(args.bind) else "https://")
          + (args.public_host or args.bind) + ":" + str(args.port) + "/mcp", flush=True)
    print("LUMAVUN MCP API KEY: " + key, flush=True)
    print("Keep this terminal and MT5 running. Do not share this key.", flush=True)
    app = build_app(key, bind=args.bind, port=args.port, public_host=args.public_host)
    import uvicorn
    uvicorn.run(app, host=args.bind, port=args.port,
                ssl_certfile=args.certfile or None, ssl_keyfile=args.keyfile or None,
                access_log=False, server_header=False)
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
