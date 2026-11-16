"""Compare original Pine v6 exported PLAN flags with Python SMC candidates.

This measures discrepancies. It does NOT certify Pine equivalence. Model
internals and fill accounting are intentionally not assumed identical.
"""
from __future__ import annotations
import argparse
import csv
import json
from bisect import bisect_right
from pathlib import Path
from .smc_engine import evaluate
from .smc_history import _timestamp, read_csv

FIELDS=("LUMA_PLAN_BUY","LUMA_PLAN_SELL")


def _flags(value):
    if value is None or str(value).strip()=="":
        return 0
    return 1 if float(str(value).strip()) >= .5 else 0


def _find_field(headers, wanted):
    # TradingView often adds a prefix (e.g. indicator title) to plot columns.
    matches=[h for h in headers if h==wanted or h.endswith("."+wanted) or
             h.endswith(" "+wanted)]
    if len(matches)!=1:
        raise ValueError("Unique Pine export field missing: "+wanted)
    return matches[0]


def compare_pine_export(entry: list[dict], htf: list[dict],
                        exported: str | Path, last_bars: int = 10000) -> dict:
    if last_bars < 35:
        raise ValueError("last_bars must be >=35")
    with Path(exported).open("r",encoding="utf-8-sig",newline="") as handle:
        reader=csv.DictReader(handle)
        headings=reader.fieldnames or []
        time_col=next((k for k in headings if k.lower() in ("time","timestamp")),None)
        if not time_col:
            raise ValueError("Pine CSV needs a time column")
        columns={key:_find_field(headings,key) for key in FIELDS}
        pine={}
        for row in reader:
            stamp=_timestamp(row[time_col])
            if stamp > 10**11:
                stamp//=1000
            if stamp in pine:
                raise ValueError("Duplicate Pine timestamp: "+str(stamp))
            pine[stamp]={key:_flags(row[col]) for key,col in columns.items()}
    times=[b["time"] for b in entry]
    htf_times=[b["time"] for b in htf]
    shared=[i for i,b in enumerate(entry) if b["time"] in pine and i>=35]
    shared=shared[-last_bars:]
    stats={key:{"TP":0,"FP":0,"FN":0,"TN":0} for key in FIELDS}
    mismatches=[]
    cache={}
    for i in shared:
        b=entry[i]
        h_end=bisect_right(htf_times,b["time"])
        signal=evaluate(entry[max(0,i-350):i+1],
                        htf[max(0,h_end-350):h_end],
                        "AUTO",cache)
        actual={"LUMA_PLAN_BUY":int(signal is not None and signal.side=="BUY"),
                "LUMA_PLAN_SELL":int(signal is not None and signal.side=="SELL")}
        expected=pine[b["time"]]
        for key in FIELDS:
            x,y=expected[key],actual[key]
            bucket="TP" if x and y else ("FP" if y else ("FN" if x else "TN"))
            stats[key][bucket]+=1
            if x!=y and len(mismatches)<40:
                mismatches.append({"time":b["time"],"field":key,"pine":x,"python":y})
    metrics={}
    for key,counts in stats.items():
        tp,fp,fn=counts["TP"],counts["FP"],counts["FN"]
        metrics[key]={**counts,"precision":tp/(tp+fp) if tp+fp else None,
                      "recall":tp/(tp+fn) if tp+fn else None,
                      "exact_agreement":(tp+counts["TN"])/len(shared) if shared else None}
    return {"bars_compared":len(shared),"pine_rows":len(pine),
            "python_rows":len(entry),"metrics":metrics,
            "first_mismatches":mismatches,
            "parity_certified":False,
            "warning":"These independently implemented models can disagree. Check source rules and OHLC feed; no equality inferred."}


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--entry-csv",required=True)
    parser.add_argument("--h4-csv",required=True)
    parser.add_argument("--pine-csv",required=True)
    parser.add_argument("--timeframe",choices=("M1","M5","M15","M30","H1"),default="M15")
    parser.add_argument("--last-bars",type=int,default=10000)
    parser.add_argument("--report")
    args=parser.parse_args()
    entry=read_csv(args.entry_csv,args.timeframe)
    htf=read_csv(args.h4_csv,"H4")
    result=compare_pine_export(entry,htf,args.pine_csv,args.last_bars)
    if result["bars_compared"]==0:
        parser.error("No matching closed UTC timestamps between Pine and broker exports")
    output=json.dumps(result,indent=2)
    if args.report:
        Path(args.report).write_text(output,encoding="utf-8")
        print("Saved Pine comparison: "+args.report)
    else:
        print(output)


if __name__=="__main__":
    main()
