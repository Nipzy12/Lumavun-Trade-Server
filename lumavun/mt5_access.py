"""Select direct Windows MT5 terminal or authenticated network MCP gateway.

The gateway is the *only* network bridge to MT5. Broker credentials are not
handled by the desktop client. Both sides must authorize automatic trading.
"""
from __future__ import annotations

import asyncio
import json
from .config import Settings
from .gateway_auth import remote_key, validate_endpoint
from .risk import OrderIntent
from .symbols import symbols_from_payload, resolve_symbol, search_catalogue, SymbolResolutionError

class MCPGatewayError(RuntimeError):
    pass

async def _invoke(url: str, key: str, tool: str, arguments: dict):
    from mcp import ClientSession
    from mcp.client.streamable_http import streamablehttp_client
    # The SDK v1 transport supplies bearer headers to all MCP HTTP requests.
    async with streamablehttp_client(url=url, headers={"Authorization": "Bearer " + key},
                                    timeout=15, sse_read_timeout=30) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            return await session.call_tool(tool, arguments=arguments)

def _unwrap(result):
    if result.isError:
        raise MCPGatewayError("Remote MT5 MCP tool rejected the request")
    structured = getattr(result, "structuredContent", None)
    if isinstance(structured, dict):
        if set(structured.keys()) == {"result"}:
            return structured["result"]
        return structured
    for chunk in result.content:
        if getattr(chunk, "type", "") == "text":
            try:
                return json.loads(chunk.text)
            except ValueError as exc:
                raise MCPGatewayError("Remote MCP returned non-JSON data") from exc
    raise MCPGatewayError("Remote MCP returned no usable data")

def gateway_call(tool: str, arguments: dict, cfg: Settings | None = None):
    cfg = cfg or Settings.load()
    url = validate_endpoint(cfg.mt5_mcp_url)
    key = remote_key()
    if not key:
        raise MCPGatewayError("Save the gateway API key in the MT5 MCP tab first")
    try:
        result = asyncio.run(_invoke(url, key, tool, arguments))
        return _unwrap(result)
    except MCPGatewayError:
        raise
    except Exception as exc:
        # Never include the secret, URL with credentials, or bearer header in error messages.
        raise MCPGatewayError("MCP gateway connection failed (" + type(exc).__name__
                              + "). Check server address, key, TLS and gateway console.") from None

def _remote(cfg: Settings | None) -> bool:
    return (cfg or Settings.load()).mt5_mode == "mcp_http"

def _native(cfg: Settings | None) -> bool:
    return (cfg or Settings.load()).mt5_mode == "mt5_native"

def account_status(cfg: Settings | None = None):
    if _native(cfg):
        from .native_mt5 import account_status as native_account
        return native_account(cfg)
    if _remote(cfg):
        return gateway_call("mt5_account", {}, cfg)
    from .mt5_bridge import account_status as direct
    return direct()

def list_positions(cfg: Settings | None = None):
    if _native(cfg):
        from .native_mt5 import list_positions as native_positions
        return native_positions(cfg)
    if _remote(cfg):
        return gateway_call("mt5_positions", {}, cfg)
    from .mt5_bridge import list_positions as direct
    return direct()

def list_broker_symbols(query: str = "", cfg: Settings | None = None) -> list[dict]:
    cfg = cfg or Settings.load()
    if _native(cfg):
        from .native_mt5 import list_broker_symbols as native_symbols
        return native_symbols(query, cfg)
    if _remote(cfg):
        data = gateway_call("mt5_symbols", {"query": query}, cfg)
        return search_catalogue(query, symbols_from_payload(data), limit=100)
    from .mt5_bridge import list_broker_symbols as local_symbols
    return local_symbols(query)


def resolve_broker_symbol(symbol: str, cfg: Settings | None = None) -> str:
    cfg = cfg or Settings.load()
    if _native(cfg):
        from .native_mt5 import resolve_broker_symbol as native_resolve
        return native_resolve(symbol, cfg)
    if _remote(cfg):
        # Ask for unfiltered broker inventory, NOT a narrowed exact-name lookup.
        # The resolver must see all candidates before it may choose one.
        data = gateway_call("mt5_symbols", {"query": ""}, cfg)
        return resolve_symbol(symbol, symbols_from_payload(data))
    from .mt5_bridge import resolve_broker_symbol as local_resolve
    return local_resolve(symbol)


def get_candles(symbol: str, timeframe: str = "M15", count: int = 60, cfg: Settings | None = None):
    if _native(cfg):
        from .native_mt5 import get_candles as native_candles
        return native_candles(symbol, timeframe, count, cfg)
    if _remote(cfg):
        return gateway_call("mt5_candles", {"symbol": symbol, "timeframe": timeframe, "count": count}, cfg)
    from .mt5_bridge import get_candles as direct
    return direct(symbol, timeframe, count)

def preview_order(intent: OrderIntent, cfg: Settings | None = None):
    if _native(cfg):
        from .native_mt5 import preview_order as native_preview
        return native_preview(intent, cfg)
    if _remote(cfg):
        return gateway_call("mt5_order_preview", {
            "symbol": intent.symbol, "side": intent.side, "sl": intent.sl, "tp": intent.tp}, cfg)
    from .mt5_bridge import preview_order as direct
    return direct(intent, cfg)

def execute_order(intent: OrderIntent, cfg: Settings | None = None):
    cfg = Settings.load()
    if not cfg.execution_enabled:
        raise MCPGatewayError("Client order execution is DISARMED")
    if _native(cfg):
        from .native_mt5 import execute_order as native_execute
        return native_execute(intent, cfg)
    if _remote(cfg):
        # The gateway calls the shared host-side risk engine with from_mcp=True.
        # It must also be armed on the gateway Windows host.
        status = account_status(cfg)
        if not status.get("demo", False) and not cfg.live_allowed:
            raise MCPGatewayError("Client LIVE trading authorization is disabled")
        return gateway_call("mt5_place_order", {
            "symbol": intent.symbol, "side": intent.side, "sl": intent.sl, "tp": intent.tp}, cfg)
    from .mt5_bridge import execute_order as direct
    return direct(intent)
