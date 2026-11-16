"""Auditable multi-year OHLC import/export for SMC research.

No generated/fabricated market bars. MT5 is read-only and candles remain
unadjusted broker OHLC. Timestamp units: Unix seconds UTC, bars timestamped
at OPEN. Never use the still-forming current candle.
"""
from __future__ import annotations
import csv
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

SECONDS = {"M1":60, "M5":300, "M15":900, "M30":1800,
           "H1":3600, "H4":14400, "D1":86400}


def utc_date(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("Expected ISO UTC date (YYYY-MM-DD or timestamp)") from exc
    return parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed.astimezone(timezone.utc)


def _timestamp(value) -> int:
    if isinstance(value, (int,float)):
        return int(value)
    value = str(value).strip()
    try:
        return int(float(value))
    except ValueError:
        return int(utc_date(value).timestamp())


def normalize(bars: list[dict], interval: str, now: datetime | None = None) -> list[dict]:
    if interval not in SECONDS:
        raise ValueError("Unsupported timeframe")
    current = now or datetime.now(timezone.utc)
    current_ts = int(current.timestamp())
    result = []
    prev = -1
    for raw in bars:
        timestamp = _timestamp(raw["time"])
        if timestamp <= prev:
            raise ValueError("Historical candles must be strictly chronological, no duplicate times")
        prev = timestamp
        # Historical source may contain an unfinished bar: exclude it.
        if timestamp + SECONDS[interval] > current_ts:
            continue
        row = {"time":timestamp}
        for key in ("open", "high", "low", "close"):
            row[key] = float(raw[key])
        if not (0 < row["low"] <= min(row["open"],row["close"]) and
                row["high"] >= max(row["open"],row["close"])):
            raise ValueError("Invalid broker OHLC candle at " + str(timestamp))
        result.append(row)
    if len(result) < 35:
        raise ValueError("Insufficient closed historical bars")
    return result


def read_csv(path: str | Path, interval: str) -> list[dict]:
    with Path(path).open("r",encoding="utf-8-sig",newline="") as handle:
        reader=csv.DictReader(handle)
        if not reader.fieldnames or not set(("time","open","high","low","close")).issubset(reader.fieldnames):
            raise ValueError("CSV requires time,open,high,low,close columns")
        return normalize(list(reader),interval)


def write_csv(path: str | Path, bars: list[dict]) -> None:
    dst=Path(path)
    dst.parent.mkdir(parents=True,exist_ok=True)
    with dst.open("w",encoding="utf-8",newline="") as handle:
        writer=csv.DictWriter(handle,fieldnames=["time","open","high","low","close"])
        writer.writeheader()
        for b in bars:
            writer.writerow({k:b[k] for k in writer.fieldnames})


def fetch_mt5_range(symbol: str, interval: str, start: datetime, end: datetime,
                    max_bars: int = 2_000_000) -> list[dict]:
    """Read historical candles from the locally logged-in MT5 terminal.

    MT5's terminal 'Max. bars in chart' may truncate requested history.
    Report coverage instead of assuming all requested years were returned.
    """
    if interval not in SECONDS or not symbol:
        raise ValueError("Invalid symbol or timeframe")
    if start.tzinfo is None or end.tzinfo is None or not start < end:
        raise ValueError("Start/end must be UTC-aware and increasing")
    from .mt5_bridge import _connected, TIMEFRAMES
    mt5=_connected()
    if mt5.symbol_info(symbol) is None or not mt5.symbol_select(symbol,True):
        raise RuntimeError("MT5 symbol unavailable: "+symbol)
    rates=mt5.copy_rates_range(symbol,getattr(mt5,TIMEFRAMES[interval]),start,end)
    if rates is None:
        raise RuntimeError("MT5 history download failed: "+str(mt5.last_error()))
    if len(rates) > max_bars:
        raise ValueError("Too many candles, reduce date range or interval")
    rows=[{"time":int(r["time"]),"open":float(r["open"]),
           "high":float(r["high"]),"low":float(r["low"]),
           "close":float(r["close"])} for r in rates]
    return normalize(rows,interval)


def coverage(bars: list[dict], interval: str, requested_start: datetime | None = None,
             requested_end: datetime | None = None) -> dict:
    if not bars:
        raise ValueError("Empty OHLC history")
    start=datetime.fromtimestamp(bars[0]["time"],timezone.utc)
    end=datetime.fromtimestamp(bars[-1]["time"],timezone.utc)
    counts=Counter(str(datetime.fromtimestamp(b["time"],timezone.utc).year) for b in bars)
    return {"timeframe":interval,"bars":len(bars),
            "first_utc":start.isoformat(),"last_utc":end.isoformat(),
            "calendar_years":dict(sorted(counts.items())),
            "requested_start_utc":requested_start.isoformat() if requested_start else None,
            "requested_end_utc":requested_end.isoformat() if requested_end else None,
            "start_not_covered":bool(requested_start and start.timestamp()>requested_start.timestamp()+SECONDS[interval]*3),
            "end_not_covered":bool(requested_end and end.timestamp()+SECONDS[interval]<min(requested_end.timestamp(),datetime.now(timezone.utc).timestamp())-SECONDS[interval]*3),
            "note":"Weekends/holidays may cause expected gaps. Coverage flags are diagnostic, not proof of missing broker data."}
