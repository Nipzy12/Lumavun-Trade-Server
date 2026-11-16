"""Add opt-in numeric plot channels to the user's ORIGINAL Pine v6 source.

Run:
  python tools/instrument_pine.py "SMC Entry Models PRO.pine"
Paste generated .pine into TradingView, run on EXACT symbol/timeframe,
export chart data CSV, and compare via lumavun.smc_parity. The original
indicator's alert and signal logic is unmodified.
"""
from __future__ import annotations
import argparse
from pathlib import Path

PLOTS = """
// LUMAVUN PARITY EXPORT CHANNELS (append-only; no changes to entry logic).
plot(newLongPlan ? 1 : 0, title="LUMA_PLAN_BUY", display=display.data_window)
plot(newShortPlan ? 1 : 0, title="LUMA_PLAN_SELL", display=display.data_window)
plot(filledBuyBar ? 1 : 0, title="LUMA_ENTRY_BUY", display=display.data_window)
plot(filledSellBar ? 1 : 0, title="LUMA_ENTRY_SELL", display=display.data_window)
plot(hitTPBar ? 1 : 0, title="LUMA_TP", display=display.data_window)
plot(hitSLBar ? 1 : 0, title="LUMA_SL", display=display.data_window)
plot(htfBias, title="LUMA_HTF_BIAS", display=display.data_window)
"""


def instrument(source: str) -> str:
    if not source.lstrip().startswith("//@version=6"):
        raise ValueError("Pine Script v6 source expected")
    expected=("newLongPlan","newShortPlan","filledBuyBar","filledSellBar",
              "hitTPBar","hitSLBar","htfBias")
    if not all(term in source for term in expected):
        raise ValueError("Original SMC indicator variables not found")
    if "LUMAVUN PARITY EXPORT CHANNELS" in source:
        raise ValueError("Already instrumented")
    return source.rstrip()+"\n\n"+PLOTS


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("source",type=Path)
    parser.add_argument("--output",type=Path)
    args=parser.parse_args()
    destination=args.output or args.source.with_name(args.source.stem+"_parity.pine")
    if destination.resolve()==args.source.resolve():
        parser.error("Output must differ from original source")
    destination.write_text(instrument(args.source.read_text(encoding="utf-8-sig")),
                           encoding="utf-8")
    print("Generated Pine comparison export source:",destination)


if __name__=="__main__":
    main()
