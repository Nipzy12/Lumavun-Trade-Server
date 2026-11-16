"""Local stdio MCP for MT5. Read-only by default; order placement requires UI arming."""
from __future__ import annotations
from mcp.server.fastmcp import FastMCP
from .config import Settings
from .mt5_bridge import account_status, list_positions, get_candles, preview_order, execute_order, broker_symbols
from .risk import OrderIntent

mcp = FastMCP("LUMAVUN MT5", instructions=(
    "This server connects to the user's own local MT5 terminal. "
    "Every trading request is subject to deterministic limits. "
    "Orders are disabled unless explicitly enabled in the desktop GUI."))

@mcp.tool()
def mt5_account() -> dict:
    """Read MT5 account status and whether it is DEMO or LIVE."""
    return account_status()

@mcp.tool()
def mt5_positions() -> list[dict]:
    """Read open positions, including SL and TP."""
    return list_positions()

@mcp.tool()
def mt5_symbols() -> list[str]:
    """List exact available instrument names from this account's broker catalog."""
    return broker_symbols()

@mcp.tool()
def mt5_candles(symbol: str, timeframe: str = "M15", count: int = 60) -> list[dict]:
    """Read historical CLOSED bars. No unclosed current bar is returned."""
    return get_candles(symbol, timeframe, count)

@mcp.tool()
def mt5_order_preview(symbol: str, side: str, sl: float, tp: float) -> dict:
    """Calculate a proposed market order and risk-sized lot WITHOUT placing it."""
    return preview_order(OrderIntent(symbol, side.upper(), sl, tp), Settings.load())

@mcp.tool()
def mt5_place_order(symbol: str, side: str, sl: float, tp: float) -> dict:
    """Place a market order ONLY if UI has explicitly enabled execution and MCP orders.
    LIVE trading requires separate authorization; SL/TP and risk checks cannot be bypassed.
    """
    return execute_order(OrderIntent(symbol, side.upper(), sl, tp), from_mcp=True)

def main():
    mcp.run(transport="stdio")

if __name__ == "__main__":
    main()
