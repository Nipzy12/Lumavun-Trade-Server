"""Run local, read-only SMC comparison on closed MT5 bars.

Usage: python -m lumavun.smc_report --symbol XAUUSD --timeframe M15 --spread 0.29
Spread is a price-unit assumption, NOT points or commission.
"""
import argparse
import json
from .mt5_access import get_candles
from .config import Settings
from .smc_engine import compare_models

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--symbol",default="XAUUSD")
    p.add_argument("--timeframe",choices=("M1","M5","M15","M30","H1"),default="M15")
    p.add_argument("--spread",type=float,default=0.0)
    p.add_argument("--count",type=int,default=500)
    args=p.parse_args()
    if not 35<=args.count<=500:
        p.error("count must be 35..500")
    cfg=Settings.load()
    if cfg.mt5_mode!="local":
        p.error("Read-only research CLI currently requires local MT5 mode")
    entry=get_candles(args.symbol,args.timeframe,args.count,cfg)
    htf=get_candles(args.symbol,"H4",500,cfg)
    report=compare_models(entry,htf,args.spread)
    print(json.dumps({"symbol":args.symbol,"timeframe":args.timeframe,
                      "spread_price_units":args.spread,
                      "entry_bars":len(entry),"h4_bars":len(htf),
                      **report},indent=2))

if __name__=="__main__":
    main()
