"""Read-only SMC research using genuine MT5 OHLC or an offline CSV export.

Examples:
  python -m lumavun.smc_report --start 2020-01-01 --end 2026-11-01 --timeframe M15
  python -m lumavun.smc_report --entry-csv XAUUSD_M15.csv --h4-csv XAUUSD_H4.csv

Broker spread in PRICE units; R results do not include margin, variable spreads,
slippage, financing or commission. No live orders are created by this tool.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
from .config import Settings
from .mt5_access import get_candles
from .smc_engine import compare_models, walk_forward
from .smc_history import coverage, fetch_mt5_range, read_csv, utc_date, write_csv


def _strip_history(result: dict, max_history: int) -> dict:
    return {**result, "history": result.get("history", [])[-max_history:]}


def main():
    parser=argparse.ArgumentParser(description="LUMAVUN read-only SMC research")
    parser.add_argument("--symbol",default="XAUUSD")
    parser.add_argument("--timeframe",choices=("M1","M5","M15","M30","H1"),default="M15")
    parser.add_argument("--spread",type=float,default=0.0,
                        help="Round-trip spread assumption in broker price units")
    parser.add_argument("--count",type=int,default=500,help="Quick mode: most recent closed bars")
    parser.add_argument("--start",help="Multi-year start date in UTC, e.g. 2016-01-01")
    parser.add_argument("--end",help="Multi-year end date in UTC, e.g. 2026-11-01")
    parser.add_argument("--entry-csv",help="Offline CSV from broker/terminal")
    parser.add_argument("--h4-csv",help="H4 CSV from same broker")
    parser.add_argument("--export-csv-dir",help="Optionally preserve fetched broker OHLC")
    parser.add_argument("--report",help="Write JSON report to this local path")
    parser.add_argument("--history-limit",type=int,default=100,
                        help="Max trade records kept in report per model")
    args=parser.parse_args()
    if args.spread < 0 or args.history_limit < 0:
        parser.error("spread and history-limit cannot be negative")
    csv_mode=bool(args.entry_csv or args.h4_csv)
    dates_mode=bool(args.start or args.end)
    if csv_mode and (not args.entry_csv or not args.h4_csv or dates_mode):
        parser.error("CSV mode needs both --entry-csv and --h4-csv without dates")
    if dates_mode and (not args.start or not args.end):
        parser.error("Multi-year mode needs both --start and --end")
    if not csv_mode and not dates_mode and not 35<=args.count<=500:
        parser.error("Quick-mode count must be between 35 and 500")
    cfg=Settings.load()
    start=utc_date(args.start) if dates_mode else None
    end=utc_date(args.end) if dates_mode else None
    actual_symbol=args.symbol
    if not csv_mode:
        from .mt5_bridge import resolve_broker_symbol
        actual_symbol=resolve_broker_symbol(args.symbol).resolved
    if csv_mode:
        entry=read_csv(args.entry_csv,args.timeframe)
        htf=read_csv(args.h4_csv,"H4")
        source="OFFLINE_CSV"
    else:
        if cfg.mt5_mode!="local":
            parser.error("MT5 historical research currently requires Local MT5 Terminal mode")
        if dates_mode:
            entry=fetch_mt5_range(actual_symbol,args.timeframe,start,end)
            htf=fetch_mt5_range(args.symbol,"H4",start,end)
        else:
            entry=get_candles(actual_symbol,args.timeframe,args.count,cfg)
            htf=get_candles(args.symbol,"H4",500,cfg)
        source="LOCAL_MT5"
    if args.export_csv_dir:
        destination=Path(args.export_csv_dir)
        write_csv(destination/(actual_symbol+"_"+args.timeframe+".csv"),entry)
        write_csv(destination/(actual_symbol+"_H4.csv"),htf)
    training=compare_models(entry,htf,args.spread)
    validation=walk_forward(entry,htf,args.spread)
    # Capture full count/metrics while bounding the human-readable JSON file.
    training["results"]=[_strip_history(r,args.history_limit) for r in training["results"]]
    validation["train"]["results"]=[_strip_history(r,args.history_limit)
                                     for r in validation["train"]["results"]]
    if validation.get("holdout"):
        validation["holdout"]=_strip_history(validation["holdout"],args.history_limit)
    report={"research_only":True,"requested_symbol":args.symbol,
            "symbol":actual_symbol,"timeframe":args.timeframe,
            "source":source,"spread_price_units":args.spread,
            "entry_coverage":coverage(entry,args.timeframe,start,end),
            "h4_coverage":coverage(htf,"H4",start,end),
            **training,"chronological_holdout":validation,
            "caveats":["Not Pine parity certified","No broker margin or slippage",
                       "Fixed round-trip spread assumption","Historical results are not predictive"]}
    output=json.dumps(report,indent=2,ensure_ascii=False)
    if args.report:
        dst=Path(args.report)
        dst.parent.mkdir(parents=True,exist_ok=True)
        dst.write_text(output,encoding="utf-8")
        print("Saved report: "+str(dst))
    else:
        print(output)


if __name__=="__main__":
    main()
