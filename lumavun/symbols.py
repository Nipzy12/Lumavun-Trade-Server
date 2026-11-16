"""Broker-specific MT5 symbol discovery and fail-closed resolution.

Never guess a broker suffix. Only choose a single proven instrument from the
connected terminal's catalogue; the user must explicitly choose among variants.
The canonical alias is for discovery/allowlists, not for submitting orders.
"""
from __future__ import annotations

import re
from typing import Any

NAME = re.compile(r"^[A-Za-z0-9#._-]{1,64}$")
# Common account-tier suffixes. Explicitly excludes futures, 247, and USDT.
SUFFIXES = frozenset({
    "m", "c", "r", "z", "x", "p", "s", "n", "a", "b", "i",
    "pro", "raw", "ecn", "stp", "cent", "mini", "micro", "standard",
    "classic", "prime", "zero", "plus", "fx", "cash",
})
ALIASES = {
    "GOLD": "XAUUSD", "SPOTGOLD": "XAUUSD", "GOLDUSD": "XAUUSD",
    "SILVER": "XAGUSD", "SPOTSILVER": "XAGUSD", "SILVERUSD": "XAGUSD",
    "NAS100": "US100", "USTEC": "US100", "US100": "US100",
    "SP500": "US500", "SPX500": "US500", "US500": "US500",
    "DOW30": "US30", "DJ30": "US30", "US30": "US30",
}
# Do not strip arbitrary trailing letters: BTCUSDT is NOT BTCUSD.
SUFFIX_PATTERN = re.compile(
    r"(?i)(?:\.(?:%s)|_(?:%s)|-(?:%s))$"
    % tuple("|".join(sorted(SUFFIXES, key=len, reverse=True)) for _ in range(3))
)
PLAIN_SUFFIXES = tuple(sorted((s for s in SUFFIXES if s not in {"cash", "fx"}), key=len, reverse=True))
# A broker can decorate any currency pair, crypto CFD, equity or index.
# Underlying comparison still requires equality AFTER stripping only known tier markers.
KNOWN_BASE = re.compile(r"^[A-Z0-9]{4,16}$", re.I)


class SymbolResolutionError(RuntimeError):
    """No verified broker symbol or ambiguous variants. No order may follow."""


def symbol_name(item: Any) -> str | None:
    if isinstance(item, str):
        value = item
    elif isinstance(item, dict):
        value = item.get("symbol", item.get("name", ""))
    else:
        value = getattr(item, "name", getattr(item, "symbol", ""))
    return value if isinstance(value, str) and NAME.fullmatch(value) else None


def symbols_from_payload(payload: Any) -> list[dict]:
    """Support native MCP / JSON gateway arrays and MetaTrader5 namedtuples."""
    for _ in range(5):
        if isinstance(payload, dict):
            for key in ("symbols", "marketwatch", "data", "result", "items", "instruments"):
                if key in payload and isinstance(payload[key], (dict, list, tuple)):
                    payload = payload[key]
                    break
            else:
                # A single symbol object, or a dictionary keyed by broker symbol.
                if symbol_name(payload):
                    payload = [payload]
                else:
                    payload = [{"symbol": key, **value} if isinstance(value, dict)
                               else {"symbol": key}
                               for key, value in payload.items() if NAME.fullmatch(str(key))]
                break
        else:
            break
    if not isinstance(payload, (tuple, list)):
        raise SymbolResolutionError("Katalog simbol broker tidak tersedia atau formatnya berbeda")
    seen: set[str] = set()
    results: list[dict] = []
    for item in payload:
        name = symbol_name(item)
        if not name or name in seen:
            continue
        seen.add(name)
        obj = item if isinstance(item, dict) else {}
        visible = obj.get("visible", getattr(item, "visible", None))
        description = obj.get("description", getattr(item, "description", ""))
        results.append({"symbol": name, "visible": visible is True,
                        "description": str(description or "")[:120]})
    return results


def _strip_decoration(symbol: str) -> str:
    s = symbol.strip().upper()
    for prefix in ("FX.", "FX_", "SPOT_", "SPOT.", "#", "_"):
        if s.startswith(prefix):
            s = s[len(prefix):]
            break
    s = re.sub(r"(?<=XAU)_(?=USD)|(?<=XAG)_(?=USD)|(?<=[A-Z]{3})_(?=[A-Z]{3}$)", "", s)
    match = SUFFIX_PATTERN.search(s)
    if match:
        s = s[:match.start()]
    else:
        for postfix in PLAIN_SUFFIXES:
            if len(s) <= len(postfix) or not s.lower().endswith(postfix):
                continue
            root = s[:-len(postfix)]
            if not KNOWN_BASE.fullmatch(root):
                continue
            # BTCUSDC (USD Coin quote) must not be confused with BTCUSDc
            # (broker cent suffix). Never silently treat uppercase USDC as USD.
            if (postfix == "c" and symbol.endswith("C")
                    and root.endswith("USD")):
                continue
            s = root
            break
    return s


def canonical(symbol: str) -> str:
    base = _strip_decoration(symbol)
    return ALIASES.get(base, base)


def matches_canonical(requested: str, actual: str) -> bool:
    """Compare canonical underlying *after* safe account-tier stripping."""
    if not NAME.fullmatch(str(requested)) or not NAME.fullmatch(str(actual)):
        return False
    return canonical(requested) == canonical(actual)


def is_generic(symbol: str) -> bool:
    s = symbol.strip().upper()
    # Once user enters an explicit .suffix / m / c / pro symbol, require exact.
    if not NAME.fullmatch(s):
        return False
    return s in ALIASES or canonical(s) == s


def candidate_symbols(query: str, catalogue: list[dict]) -> list[dict]:
    q = str(query or "").strip()
    if not NAME.fullmatch(q):
        raise SymbolResolutionError("Nama simbol MT5 tidak valid")
    # Case-insensitive exact match always wins, but retain broker spelling.
    exact = [entry for entry in catalogue if entry["symbol"].casefold() == q.casefold()]
    if exact:
        return exact
    if not is_generic(q):
        return []
    return [entry for entry in catalogue if matches_canonical(q, entry["symbol"])]


def resolve_symbol(query: str, catalogue: list[dict]) -> str:
    choices = candidate_symbols(query, catalogue)
    if len(choices) == 1:
        return choices[0]["symbol"]
    if len(choices) > 1:
        alternatives = ", ".join(sorted({x["symbol"] for x in choices})[:12])
        raise SymbolResolutionError(
            "AMBIGUOUS_SYMBOL: " + query + ". Broker menyediakan " + alternatives
            + ". Pilih nama persis di Strategy → Cari Simbol Broker, lalu Save Strategy."
        )
    q = str(query or "")
    suggestions = [str(item["symbol"]) for item in catalogue
                   if str(item["symbol"]).upper().startswith(q.upper())][:8]
    raise SymbolResolutionError(
        "SYMBOL_UNAVAILABLE: " + q + ". Tidak ditemukan pada katalog broker MT5."
        + (" Simbol mirip: " + ", ".join(suggestions) + "." if suggestions else "")
        + " Buka Market Watch, tampilkan simbol di MT5, atau pilih simbol broker yang tersedia."
    )


def search_catalogue(query: str, catalogue: list[dict], limit: int = 80) -> list[dict]:
    q = str(query or "").strip()
    if q and not NAME.fullmatch(q):
        raise SymbolResolutionError("Pencarian simbol MT5 tidak valid")
    if not q:
        return catalogue[:limit]
    ranked = candidate_symbols(q, catalogue)
    other = [entry for entry in catalogue if entry not in ranked and
             (q.casefold() in entry["symbol"].casefold()
              or q.casefold() in entry["description"].casefold())]
    return (ranked + other)[:limit]


def allowlisted(config_allowlist: str, exact_symbol: str) -> bool:
    """Trade gate accepts generic underlying only for a validated broker symbol.

    Explicit decorated allowlist entries are exact only; never silently switch
    between account tiers. Called after successful MT5 symbol_info resolution.
    """
    for item in str(config_allowlist or "").split(","):
        allowed = item.strip()
        if not allowed:
            continue
        if allowed.casefold() == exact_symbol.casefold():
            return True
        if is_generic(allowed) and matches_canonical(allowed, exact_symbol):
            return True
    return False
