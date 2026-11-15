"""Windows build smoke test: validate that bundled MetaTrader5 native extension imports.

This does NOT need a broker account, terminal login or network connection.
It writes a machine-readable report so windowed .exe builds can be checked in CI.
"""
from __future__ import annotations
import json
import sys
from pathlib import Path

def self_test_mt5(report_path: str) -> int:
    try:
        from .mt5_bridge import _api
        mt5 = _api()
        # A successful import also loads MetaTrader5._core native extension.
        report = {
            "ok": True,
            "module": mt5.__name__,
            "version": getattr(mt5, "__version__", "unknown"),
            "python": sys.version.split()[0],
            "frozen": bool(getattr(sys, "frozen", False)),
            "terminal_required_for_test": False,
        }
        status = 0
    except Exception as exc:
        report = {
            "ok": False,
            "error_type": type(exc).__name__,
            "error": str(exc),
            "python": sys.version.split()[0],
            "frozen": bool(getattr(sys, "frozen", False)),
        }
        status = 2
    Path(report_path).write_text(json.dumps(report, indent=2), encoding="utf-8")
    return status

def self_test_native_mcp(report_path: str) -> int:
    """Validate that frozen dashboard includes MCP Streamable HTTP client."""
    try:
        from mcp import ClientSession
        from mcp.client.streamable_http import streamablehttp_client
        report = {
            "ok": True,
            "module": "mcp.client.streamable_http",
            "client_session": ClientSession.__name__,
            "frozen": bool(getattr(sys, "frozen", False)),
        }
        status = 0
    except Exception as exc:
        report = {
            "ok": False,
            "error_type": type(exc).__name__,
            "error": str(exc),
            "frozen": bool(getattr(sys, "frozen", False)),
        }
        status = 2
    Path(report_path).write_text(json.dumps(report, indent=2), encoding="utf-8")
    return status
