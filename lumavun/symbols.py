"""Pure, broker-agnostic symbol matching (no orders, no MT5 connection).

Only accept actual names from a broker's own symbols catalog. Exact matches
take precedence. Unknown/ambiguous suffixes require explicit user selection.
Do not confuse crypto USD, USDT and USDC quote currencies.
"""
from __future__ import annotations
from dataclasses import dataclass
import re


class SymbolResolutionError(ValueError):
    def __init__(self, message: str, *, code: str, candidates: list[str] | None = None):
        super().__init__(message)
        self.code = code
        self.candidates = candidates or []


@dataclass(frozen=True)
class SymbolMatch:
    requested: str
    resolved: str
    kind: str  # EXACT, CASE_ONLY, NORMALIZED, UNIQUE_SUFFIX

    @property
    def changed(self) -> bool:
        return self.requested != self.resolved


def _normalize(s: str) -> str:
    return re.sub(r"[^A-Z0-9]", "", s.upper())


_CRYPTO_BASES = ("BTCUSD", "ETHUSD", "SOLUSD", "LTCUSD", "XRPUSD", "DOGEUSD",
                 "BNBUSD", "ADAUSD", "AVAXUSD", "DOTUSD")
_VALID_SUFFIX = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,11}$")


def _possible_suffix(requested: str, candidate: str) -> bool:
    base = requested.casefold()
    name = candidate.casefold()
    if not name.startswith(base) or len(name) <= len(base):
        return False
    suffix = candidate[len(requested):]
    if suffix[0] in "._-#":
        suffix = suffix[1:]
        if not suffix:
            return False
    if not _VALID_SUFFIX.fullmatch(suffix):
        return False
    # A quote currency extension is not a broker suffix:
    # BTCUSD + T = BTCUSDT, BTCUSD + C = BTCUSDC.
    if requested.upper() in _CRYPTO_BASES and suffix.upper() in ("T", "C"):
        return False
    # XAUUSDJPY means a new instrument/cross, not a symbol suffix.
    if suffix.upper() in ("USD", "USDT", "USDC", "EUR", "JPY", "GBP", "AUD", "CAD", "CHF"):
        return False
    return True


def match_symbol(requested: str, names: list[str]) -> SymbolMatch:
    requested = str(requested).strip()
    if not requested or len(requested) > 80:
        raise SymbolResolutionError("Enter a valid broker symbol.", code="INVALID_SYMBOL")
    catalog = sorted({str(x).strip() for x in names if isinstance(x, str) and x.strip()},
                     key=lambda v:(v.casefold(),v))
    if not catalog:
        raise SymbolResolutionError(
            "Broker symbol catalog is empty/unavailable; cannot resolve " + requested,
            code="CATALOG_UNAVAILABLE")
    if requested in catalog:
        return SymbolMatch(requested,requested,"EXACT")
    case = [name for name in catalog if name.casefold() == requested.casefold()]
    if len(case) == 1:
        return SymbolMatch(requested,case[0],"CASE_ONLY")
    if len(case) > 1:
        raise SymbolResolutionError(
            "Multiple broker symbols match case-insensitively: "+", ".join(case),
            code="AMBIGUOUS",candidates=case)
    norm = _normalize(requested)
    normalized = [name for name in catalog if _normalize(name) == norm]
    if len(normalized) == 1:
        return SymbolMatch(requested,normalized[0],"NORMALIZED")
    if len(normalized) > 1:
        raise SymbolResolutionError(
            "Multiple broker symbols have the same normalized name: "+", ".join(normalized[:10]),
            code="AMBIGUOUS",candidates=normalized[:50])
    options = [name for name in catalog if _possible_suffix(requested,name)]
    if len(options) == 1:
        return SymbolMatch(requested,options[0],"UNIQUE_SUFFIX")
    if len(options) > 1:
        raise SymbolResolutionError(
            "Multiple broker variants for " + requested + ": " +
            ", ".join(options[:12]) + ". Select the exact symbol manually.",
            code="AMBIGUOUS",candidates=options[:50])
    nearby = [name for name in catalog if norm in _normalize(name)]
    raise SymbolResolutionError(
        "Symbol unavailable: " + requested +
        ". No safe unique match in connected broker catalog.",
        code="NOT_FOUND",candidates=nearby[:25])


def suggestions(requested: str, names: list[str]) -> list[str]:
    needle = _normalize(str(requested).strip())
    pool = sorted({n for n in names if isinstance(n,str) and n.strip()},key=str.casefold)
    if not needle:
        return pool
    return [n for n in pool if needle in _normalize(n)]
