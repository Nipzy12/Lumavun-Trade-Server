"""Direct connection to MetaQuotes' built-in MetaTrader 5 terminal MCP server.

This is NOT the separate LUMAVUN gateway. The built-in server uses Bearer
authentication and has its OWN tool names and schemas, discovered at runtime.
Read-only functionality is available immediately; dangerous tool calls are
never exposed to an unbounded AI agent.
"""
from __future__ import annotations
import asyncio
from datetime import datetime, timedelta, timezone
import json
import math
from typing import Any

from .config import Settings
from .gateway_auth import validate_endpoint
from .risk import OrderIntent
from .symbols import symbols_from_payload, resolve_symbol, search_catalogue, SymbolResolutionError

class NativeMT5Error(RuntimeError):
    pass

class NativeToolMissingError(NativeMT5Error):
    """Capability is genuinely absent after full MCP discovery, not a network error."""
    pass

TIMEFRAME_MINUTES = {"M1": 1, "M5": 5, "M15": 15, "M30": 30,
                     "H1": 60, "H4": 240, "D1": 1440}

# Explicit read-only tools. Never pass arbitrary user/AI names to the broker.
READ_TOOLS = frozenset({
    "get_trading_account_info",
    "get_trading_open_positions",
    "get_trading_history_orders",
    "get_chart_history",
    "get_marketwatch_symbols",
    "list_open_charts",
})

def _config(cfg: Settings) -> tuple[str, str]:
    from .gateway_auth import native_api_key
    url = validate_endpoint(cfg.mt5_native_url)
    token = native_api_key()
    if not token:
        raise NativeMT5Error("Simpan API Key dari MT5 → Options → MCP terlebih dahulu")
    return url, token

async def _list_tools(url: str, token: str):
    from mcp import ClientSession
    from mcp.client.streamable_http import streamablehttp_client
    async with streamablehttp_client(url=url, headers={"Authorization": "Bearer " + token},
                                    timeout=15, sse_read_timeout=30) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            # MCP tools/list is paginated. Reading only page one can hide the
            # native MT5 history tools even when the terminal does expose them.
            all_tools = []
            cursor = None
            seen_cursors = set()
            for _ in range(100):
                result = (await session.list_tools() if cursor is None
                          else await session.list_tools(cursor=cursor))
                all_tools.extend({
                    "name": item.name,
                    "description": (item.description or "")[:1200],
                    "inputSchema": item.inputSchema or {},
                } for item in result.tools)
                next_cursor = getattr(result, "next_cursor", None)
                if not next_cursor:
                    return all_tools
                if next_cursor in seen_cursors:
                    raise NativeMT5Error("Server MCP mengulang pagination cursor; daftar tool tidak lengkap")
                seen_cursors.add(next_cursor)
                cursor = next_cursor
            raise NativeMT5Error("Server MCP melebihi 100 halaman tool; daftar tidak lengkap")

def list_native_tools(cfg: Settings | None = None) -> list[dict]:
    cfg = cfg or Settings.load()
    url, key = _config(cfg)
    try:
        return asyncio.run(_list_tools(url, key))
    except Exception as exc:
        # Avoid leaking the token or network URL in errors.
        raise NativeMT5Error("Koneksi MCP native gagal (" + type(exc).__name__
                             + "). Periksa server aktif, URL, API key, dan tombol OK di MT5.") from None

def _get_tool(name: str, cfg: Settings) -> dict:
    available = list_native_tools(cfg)
    matches = [x for x in available if x["name"] == name]
    if matches:
        return matches[0]
    # Distinguish a missing server capability from authentication or transport
    # failures. Never silently substitute marketdata (different symbol feed).
    related = sorted({
        t["name"] for t in available if
        ("history" in t["name"].lower() or "chart" in t["name"].lower()
         or "rates" in t["name"].lower())
    })
    examples = related or sorted({t["name"] for t in available})[:8]
    raise NativeToolMissingError(
        "Server MCP MT5 tidak menyediakan tool: " + name
        + ". Tools tersedia: " + (", ".join(examples) if examples else "(kosong)")
        + ". Perbarui terminal/cek tab MT5 MCP, atau aktifkan opsi fallback "
          "candle MT5 lokal (read-only) pada LUMAVUN bila menggunakan PC yang sama."
    )

def _required(tool: dict) -> set[str]:
    schema = tool.get("inputSchema") or {}
    return set(schema.get("required") or [])

def _read_tool(name: str, params: dict, cfg: Settings):
    if name not in READ_TOOLS:
        raise NativeMT5Error("Tool native MCP tidak termasuk allowlist read-only")
    tool = _get_tool(name, cfg)
    if _required(tool) - params.keys():
        raise NativeMT5Error("Argumen tool MT5 yang wajib belum tersedia: "
                             + ", ".join(sorted(_required(tool) - params.keys())))
    from .mt5_access import _invoke, _unwrap
    url, key = _config(cfg)
    try:
        return _unwrap(asyncio.run(_invoke(url, key, name, params)))
    except Exception as exc:
        raise NativeMT5Error("Tool MCP MT5 gagal: " + name + " (" + type(exc).__name__ + ")") from None

def _as_mapping(payload: Any) -> dict:
    if not isinstance(payload, dict):
        raise NativeMT5Error("Format data MCP tidak sesuai: objek diharapkan")
    for key in ("account", "account_info", "result", "data"):
        item = payload.get(key)
        if isinstance(item, dict):
            return item
    return payload

def _demo_flag(account: dict) -> bool | None:
    if isinstance(account.get("demo"), bool):
        return account["demo"]
    if isinstance(account.get("is_demo"), bool):
        return account["is_demo"]
    for key in ("account_type", "type", "trade_mode", "mode"):
        value = account.get(key)
        if isinstance(value, str):
            val = value.strip().lower()
            if val in ("demo", "demo account", "account_trade_mode_demo"):
                return True
            if val in ("real", "live", "real account", "account_trade_mode_real"):
                return False
        # MT5 trade mode enums: 0 demo, 1 contest, 2 real.
        if key == "trade_mode" and isinstance(value, int):
            if value == 0:
                return True
            if value in (1, 2):
                return False
    return None

def account_status(cfg: Settings | None = None) -> dict:
    cfg = cfg or Settings.load()
    obj = _as_mapping(_read_tool("get_trading_account_info", {}, cfg))
    return {
        "login": obj.get("login", obj.get("account")),
        "server": obj.get("server"),
        "balance": obj.get("balance"),
        "equity": obj.get("equity"),
        "currency": obj.get("currency"),
        "demo": _demo_flag(obj),
        "account_type": obj.get("type", obj.get("trade_mode")),
        "source": "MetaTrader 5 built-in MCP",
        "raw": obj,
    }

def list_positions(cfg: Settings | None = None):
    cfg = cfg or Settings.load()
    data = _read_tool("get_trading_open_positions", {}, cfg)
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for name in ("positions", "open_positions", "data", "result"):
            item = data.get(name)
            if isinstance(item, list):
                return item
            if isinstance(item, dict) and isinstance(item.get("positions"), list):
                return item["positions"]
    return data

def inspect_connection(cfg: Settings | None = None) -> dict:
    cfg = cfg or Settings.load()
    tools = list_native_tools(cfg)
    names = {tool["name"] for tool in tools}
    account = None
    if "get_trading_account_info" in names:
        tool = next(x for x in tools if x["name"] == "get_trading_account_info")
        if not _required(tool):
            account = account_status(cfg)
    return {
        "connected": True,
        "transport": "MCP Streamable HTTP",
        "provider": "MetaTrader 5 native terminal",
        "total_tools": len(tools),
        "tools": [{"name": t["name"], "description": t["description"],
                   "required": sorted(_required(t))}
                  for t in tools],
        "account": account,
        "read_only": True,
        "candle_history_available": "get_chart_history" in names,
        "local_read_fallback_enabled": bool(cfg.native_local_candle_fallback),
    }

def _schema_args(tool: dict, symbol: str, timeframe: str, count: int) -> dict:
    """Construct ONLY schema-declared parameters; never guess unknown required ones."""
    props = (tool.get("inputSchema") or {}).get("properties", {})
    if not isinstance(props, dict):
        raise NativeMT5Error("Schema get_chart_history tidak valid")
    args: dict = {}
    if "symbol" not in props:
        raise NativeMT5Error("Schema get_chart_history tidak mengenali symbol")
    args["symbol"] = symbol
    for field in ("timeframe", "period"):
        if field in props:
            spec = props[field]
            choices = spec.get("enum") if isinstance(spec, dict) else None
            if choices:
                compatible = [v for v in (timeframe, "PERIOD_" + timeframe, timeframe.lower())
                              if v in choices]
                if not compatible:
                    raise NativeMT5Error("Timeframe tidak didukung oleh schema MCP MT5")
                args[field] = compatible[0]
            else:
                args[field] = timeframe
            break
    else:
        raise NativeMT5Error("Schema history tidak menyertakan timeframe/period")
    for field in ("count", "bars", "limit"):
        if field in props:
            args[field] = count + 2
            break
    minutes = TIMEFRAME_MINUTES[timeframe]
    end = datetime.now(timezone.utc)
    start = end - timedelta(minutes=minutes * (count + 10))
    for field in ("start_time", "from_time", "start_date", "date_from", "start"):
        if field in props:
            args[field] = start.isoformat()
            break
    for field in ("end_time", "to_time", "end_date", "date_to", "end"):
        if field in props:
            args[field] = end.isoformat()
            break
    unknown = _required(tool) - args.keys()
    if unknown:
        raise NativeMT5Error("Schema candle MT5 memerlukan argumen tambahan: "
                             + ", ".join(sorted(unknown)))
    return args

def _extract_bars(data: Any) -> list[dict]:
    if isinstance(data, dict):
        for field in ("rates", "bars", "candles", "history", "data", "result"):
            child = data.get(field)
            if child is not None:
                return _extract_bars(child)
    if not isinstance(data, list):
        raise NativeMT5Error("Server MT5 tidak mengembalikan daftar candle")
    items = []
    for b in data:
        if not isinstance(b, dict):
            continue
        try:
            val = b.get("time", b.get("timestamp", b.get("datetime")))
            if isinstance(val, str):
                ts = int(datetime.fromisoformat(val.replace("Z", "+00:00")).timestamp())
            else:
                ts = int(val)
                if ts > 100000000000:
                    ts //= 1000
            o = float(b["open"]); h = float(b["high"])
            l = float(b["low"]); c = float(b["close"])
            if not (ts > 0 and all(math.isfinite(v) for v in (o, h, l, c)) and l <= min(o,c) <= max(o,c) <= h):
                continue
            items.append({"time": ts, "open": o, "high": h, "low": l,
                          "close": c, "tick_volume": int(b.get("tick_volume", b.get("volume", 0)))})
        except (TypeError, ValueError, KeyError, OverflowError):
            continue
    return sorted(items, key=lambda x: x["time"])

def list_broker_symbols(query: str = "", cfg: Settings | None = None) -> list[dict]:
    """Read only the visible symbols published by the native MT5 Market Watch."""
    cfg = cfg or Settings.load()
    catalogue = symbols_from_payload(_read_tool("get_marketwatch_symbols", {}, cfg))
    return search_catalogue(query, catalogue, limit=100)


def resolve_broker_symbol(symbol: str, cfg: Settings | None = None) -> str:
    cfg = cfg or Settings.load()
    catalogue = symbols_from_payload(_read_tool("get_marketwatch_symbols", {}, cfg))
    try:
        return resolve_symbol(symbol, catalogue)
    except SymbolResolutionError as exc:
        raise NativeMT5Error(str(exc)) from exc


def _safe_local_candles(symbol: str, timeframe: str, count: int, cfg: Settings) -> list[dict]:
    """Read-only fallback only after verifying exact native/local broker identity.

    Never write, execute orders or reuse quotes from a different MT5 terminal.
    """
    from . import mt5_bridge
    native = account_status(cfg)
    try:
        local = mt5_bridge.account_status()
    except Exception as exc:
        raise NativeMT5Error(
            "Fallback lokal gagal membuka akun MT5 (" + type(exc).__name__
            + "). Periksa terminal MetaTrader 5 yang sedang berjalan."
        ) from None

    def account_identity(info):
        try:
            login = int(info.get("login"))
            server = str(info.get("server") or "").strip().casefold()
        except (TypeError, ValueError, AttributeError):
            return None
        if login <= 0 or not server:
            return None
        return login, server

    expected = account_identity(native)
    if expected is None or expected != account_identity(local):
        raise NativeMT5Error(
            "Fallback diblokir: akun/server MT5 lokal tidak sama dengan akun "
            "yang terhubung melalui MCP native. Pastikan login dan server cocok."
        )
    if (isinstance(native.get("demo"), bool) and isinstance(local.get("demo"), bool)
            and native["demo"] != local["demo"]):
        raise NativeMT5Error("Fallback diblokir: tipe akun DEMO/LIVE tidak cocok")
    try:
        candles = mt5_bridge.get_candles(symbol, timeframe, count)
        # Detect account switching while rates are being fetched.
        if account_identity(mt5_bridge.account_status()) != expected:
            raise NativeMT5Error("Fallback diblokir: akun MT5 lokal berubah saat mengambil candle")
        return candles
    except NativeMT5Error:
        raise
    except Exception as exc:
        raise NativeMT5Error(
            "Fallback MT5 lokal gagal membaca candle (" + type(exc).__name__
            + "). Periksa nama simbol broker dan data historis di chart."
        ) from None


def get_candles(symbol: str, timeframe: str = "M15", count: int = 60,
                cfg: Settings | None = None) -> list[dict]:
    if timeframe not in TIMEFRAME_MINUTES or not (10 <= count <= 500):
        raise NativeMT5Error("Timeframe atau count candle tidak valid")
    cfg = cfg or Settings.load()
    try:
        tool = _get_tool("get_chart_history", cfg)
    except NativeToolMissingError:
        if cfg.native_local_candle_fallback:
            # Local fallback independently resolves its symbol only after
            # the native and local broker account identities are verified.
            return _safe_local_candles(symbol, timeframe, count, cfg)
        raise
    actual = resolve_broker_symbol(symbol, cfg)
    args = _schema_args(tool, actual, timeframe, count)
    bars = _extract_bars(_read_tool("get_chart_history", args, cfg))
    # Closed-candle only: drop current bar when its interval is still active.
    now = datetime.now(timezone.utc).timestamp()
    duration = TIMEFRAME_MINUTES[timeframe] * 60
    bars = [b for b in bars if b["time"] + duration <= now]
    bars = bars[-count:]
    if len(bars) < 10:
        raise NativeMT5Error("Kurang dari 10 candle tertutup atau schema history berbeda")
    return bars

def preview_order(intent: OrderIntent, cfg: Settings | None = None):
    """No native order preview: broker contract/risk cannot be validated solely by MCP."""
    raise NativeMT5Error(
        "Mode MCP native saat ini READ-ONLY untuk strategi. "
        "Gunakan mode Local MT5 Terminal untuk preview risiko dan eksekusi yang teruji."
    )

def execute_order(intent: OrderIntent, cfg: Settings | None = None):
    """Fail closed rather than call native trade_send_market_order with guessed schema."""
    raise NativeMT5Error(
        "Eksekusi order MCP native masih terkunci sampai schema order dan risk guard diverifikasi."
    )
