"""Deterministic, closed-bar SMC candidate evaluator. Advisory only.

This is an independently defined approximation, not a Pine Script runtime.
All inputs must be historical CLOSED OHLC bars sorted ascending.
"""
from __future__ import annotations
from dataclasses import dataclass, asdict
from math import isfinite

@dataclass(frozen=True)
class Setup:
    model: str
    side: str
    entry: float
    sl: float
    tp: float
    score: int
    signal_time: int
    reason: str
    zone_bottom: float = 0.0
    zone_top: float = 0.0

    def to_dict(self):
        return asdict(self)

def _valid(bars):
    if len(bars) < 35:
        return False
    last = -1
    for b in bars:
        try:
            t = int(b["time"])
            o, h, l, c = (float(b[k]) for k in ("open", "high", "low", "close"))
            if t <= last or not all(map(isfinite, (o,h,l,c))) or l > min(o,c) or h < max(o,c) or l <= 0:
                return False
            last = t
        except (KeyError, ValueError, TypeError):
            return False
    return True

def _atr(bars, period=14):
    tr = [max(b["high"]-b["low"], abs(b["high"]-bars[i-1]["close"]),
              abs(b["low"]-bars[i-1]["close"])) for i,b in enumerate(bars) if i]
    return sum(tr[-period:])/period if len(tr) >= period else 0

def _fvg(bars, i, side, atr):
    if i < 2 or atr <= 0:
        return None
    a, c = bars[i-2], bars[i]
    if side == "BUY" and c["low"] > a["high"] and c["low"]-a["high"] >= .12*atr:
        return (a["high"], c["low"])
    if side == "SELL" and c["high"] < a["low"] and a["low"]-c["high"] >= .12*atr:
        return (c["high"], a["low"])
    return None

def _bias(htf, at_time):
    # Only H4 bars whose CLOSE timestamp is not after the entry bar are eligible.
    # MT5 timestamps represent bar opens; H4 completes 4h after that timestamp.
    closed = [b for b in htf if b["time"]+14400 <= at_time]
    if len(closed) < 35:
        return None
    recent = closed[-1]
    avg = sum(b["close"] for b in closed[-20:])/20
    # Conservative H4 directional filter; NOT a full OB/FVG POI confirmation.
    if recent["close"] > avg and recent["close"] > closed[-6]["close"]:
        return "BUY"
    if recent["close"] < avg and recent["close"] < closed[-6]["close"]:
        return "SELL"
    return None

def _candidate(bars, htf, context_cache=None, prevalidated=False):
    if len(bars) < 35 or len(htf) < 35:
        return []
    if not prevalidated and (not _valid(bars) or not _valid(htf)):
        return []
    i = len(bars)-1
    now = bars[i]
    atr = _atr(bars)
    if atr <= 0:
        return []
    body = abs(now["close"]-now["open"])
    span = now["high"]-now["low"]
    mid = bars[i-1]
    mid_span = mid["high"]-mid["low"]
    mid_body = abs(mid["close"]-mid["open"])
    mid_displacement = mid_span > 0 and mid_body/mid_span >= .60 and mid_body >= _atr(bars[:-1])
    prev = bars[i-21:i]
    swing_high = max(b["high"] for b in prev)
    swing_low = min(b["low"] for b in prev)
    possible_bull = now["close"] > swing_high+.06*atr
    possible_bear = now["close"] < swing_low-.06*atr
    raw_fvg_bull = _fvg(bars,i,"BUY",atr)
    raw_fvg_bear = _fvg(bars,i,"SELL",atr)
    # Short-circuit the expensive HTF zone/freshness check on non-signal bars.
    if not ((span > 0 and body/span >= .60 and body >= .70*atr and
             (possible_bull or possible_bear)) or
            (mid_displacement and (raw_fvg_bull or raw_fvg_bear))):
        return []
    from .smc_htf import context as h4_context
    h4 = h4_context(htf, bars, int(now["time"]), cache=context_cache)
    if h4.poi is None or h4.poi.side != h4.bias or h4.bias not in (-1, 1):
        return []
    side = "BUY" if h4.bias == 1 else "SELL"
    sign = h4.bias
    breakout = possible_bull if sign == 1 else possible_bear
    displacement = body >= .70*atr and span > 0 and body/span >= .60
    fvg = raw_fvg_bull if sign == 1 else raw_fvg_bear
    candidates = []
    # M1: find earlier confirmed sweep of opposite liquidity, followed by shift.
    sweep = False
    for j in range(max(21,i-14),i):
        prior = bars[j-20:j]
        if not prior:
            continue
        level = min(b["low"] for b in prior) if sign==1 else max(b["high"] for b in prior)
        b = bars[j]
        if (sign==1 and b["low"] < level-.04*atr and b["close"] > level) or (
            sign==-1 and b["high"] > level+.04*atr and b["close"] < level):
            sweep = True
            break
    if sweep and breakout and displacement:
        zone = fvg
        if zone:
            candidates.append(("M1",zone,90,"Sweep + confirmed structural close + FVG"))
    # M2: recent opposite-body OB and FVG within 6 bars of BOS.
    if breakout and displacement:
        fvgs = [(j,_fvg(bars,j,side,atr)) for j in range(max(2,i-6),i+1)]
        fvgs = [(j,z) for j,z in fvgs if z]
        origin = next((b for b in reversed(bars[max(0,i-8):i])
                       if (b["close"]<b["open"] if sign==1 else b["close"]>b["open"])),None)
        if fvgs and origin:
            zone = (origin["low"],origin["high"])
            if .04*atr <= zone[1]-zone[0] <= 2.2*atr:
                candidates.append(("M2",zone,87,"Close-confirmed BOS + opposite OB + nearby FVG"))
    # M3: displacement FVG
    middle = bars[i-1]
    middle_body = abs(middle["close"]-middle["open"])
    middle_range = middle["high"]-middle["low"]
    if fvg and mid_displacement:
        candidates.append(("M3",fvg,85,"Three-candle FVG + middle displacement"))
    result=[]
    for model,zone,score,reason in candidates:
        entry = zone[1] if sign==1 else zone[0]  # proximal
        stop = (min(zone[0],now["low"])-.12*atr if sign==1
                else max(zone[1],now["high"])+.12*atr)
        dist=abs(entry-stop)
        if not 0 < dist <= 10*atr:
            continue
        tp=entry+sign*2*dist
        if (sign==1 and stop < entry < tp) or (sign==-1 and tp < entry < stop):
            result.append(Setup(model,side,entry,stop,tp,score,int(now["time"]),reason,zone[0],zone[1]))
    return result

def evaluate(bars, htf, model="AUTO", context_cache=None, prevalidated=False):
    """Return best current candidate or None; AUTO priority is M1 > M2 > M3."""
    choices=_candidate(bars,htf,context_cache,prevalidated)
    if model != "AUTO":
        choices=[c for c in choices if c.model==model]
    return choices[0] if choices else None

def backtest(bars, htf, model="AUTO", spread=0.0, expiry=40):
    """Conservative single-position OHLC replay, no lookahead, no broker PnL.

    Signals are evaluated at bar close; orders activate from the NEXT bar.
    If both SL and TP are hit on one candle, SL wins. Results in R units.
    """
    if not _valid(bars) or not _valid(htf):
        raise ValueError("Need >=35 ordered, valid closed candles on both timeframes")
    if spread < 0 or expiry < 1:
        raise ValueError("Invalid spread/expiry")
    from bisect import bisect_right
    htf_times=[int(b["time"]) for b in htf]
    context_cache={}
    trades=[]
    pending=None
    active=None
    for i in range(35,len(bars)):
        b=bars[i]
        exited_this_bar = False
        if active:
            s=active["setup"]
            stop_hit=b["low"]<=s.sl if s.side=="BUY" else b["high"]>=s.sl
            target_hit=b["high"]>=s.tp if s.side=="BUY" else b["low"]<=s.tp
            if stop_hit or target_hit:
                # Spread is charged as a fixed adverse round-trip price amount.
                risk=abs(s.entry-s.sl)
                gross=-1.0 if stop_hit else 2.0
                r=gross-spread/risk
                trades.append({"model":s.model,"side":s.side,"entry_time":active["time"],
                               "exit_time":b["time"],"r":round(r,6),
                               "outcome":"SL" if stop_hit else "TP"})
                active=None
                exited_this_bar = True
        if pending and not active:
            s=pending["setup"]
            age=i-pending["created"]
            if age>expiry:
                pending=None
            else:
                # Intrabar order is unknown: fill and stop take precedence over close cancellation.
                # Pine-style close break of zone edge (not the stop price).
                buffer=.03*_atr(bars[:i+1])
                invalid=(b["close"]<s.zone_bottom-buffer if s.side=="BUY"
                         else b["close"]>s.zone_top+buffer)
                if b["low"]<=s.entry<=b["high"]:
                    active={"setup":s,"time":b["time"]}
                    pending=None
                    # Conservative same-bar stop after entry, never same-bar TP.
                    hit=b["low"]<=s.sl if s.side=="BUY" else b["high"]>=s.sl
                    if hit:
                        trades.append({"model":s.model,"side":s.side,"entry_time":b["time"],
                                       "exit_time":b["time"],"r":round(-1-spread/abs(s.entry-s.sl),6),
                                       "outcome":"SL"})
                        active=None
                        exited_this_bar = True
                elif invalid:
                    pending=None
        if not active and not pending and not exited_this_bar:
            # Candidate formed at this bar close; next bar first eligible for fill.
            cutoff=bisect_right(htf_times,int(b["time"]))
            history_htf=htf[max(0,cutoff-350):cutoff]
            candidate=evaluate(bars[max(0,i-350):i+1],history_htf,model,context_cache,True)
            if candidate:
                pending={"setup":candidate,"created":i}
    total=sum(t["r"] for t in trades)
    wins=sum(t["r"]>0 for t in trades)
    peak=0.0
    equity=0.0
    dd=0.0
    for t in trades:
        equity+=t["r"]
        peak=max(peak,equity)
        dd=max(dd,peak-equity)
    positive=sum(max(0,t["r"]) for t in trades)
    negative=-sum(min(0,t["r"]) for t in trades)
    return {"model":model,"trades":len(trades),"wins":wins,
            "open_position_at_end":active is not None,
            "pending_order_at_end":pending is not None,
            "win_rate":wins/len(trades) if trades else None,
            "total_r":round(total,4),
            "expectancy_r":round(total/len(trades),4) if trades else None,
            "profit_factor":round(positive/negative,4) if negative else None,
            "max_drawdown_r":round(dd,4),"history":trades}

def compare_models(bars,htf,spread=0.0):
    results=[backtest(bars,htf,m,spread) for m in ("M1","M2","M3","AUTO")]
    # No winner if sample too small; ranking is descriptive, not predictive.
    eligible=[r for r in results if r["trades"]>=30]
    winner=max(eligible,key=lambda r:(r["expectancy_r"],-r["max_drawdown_r"]))["model"] if eligible else None
    return {"results":results,"best_historical_model":winner,
            "minimum_trades_for_ranking":30,
            "warning":"Illustrative OHLC replay, not broker execution or out-of-sample validation."}

def walk_forward(bars, htf, spread=0.0, train_fraction=0.7, minimum_trades=30):
    """Select on train only, then report holdout independently.

    The holdout retains warm-up price history for indicator context but its
    accounting is restricted to entries signaled after the split.
    No guarantee of predictive performance.
    """
    if not _valid(bars) or not _valid(htf):
        raise ValueError("Need ordered valid closed OHLC history")
    if not .5 <= train_fraction <= .85:
        raise ValueError("train_fraction must be between 0.5 and 0.85")
    split=int(len(bars)*train_fraction)
    if split < 35 or len(bars)-split < 35:
        raise ValueError("Insufficient bars for train/holdout")
    train=compare_models(bars[:split],htf,spread)
    eligible=[r for r in train["results"] if r["model"]!="AUTO" and r["trades"]>=minimum_trades]
    selected=max(eligible,key=lambda r:(r["expectancy_r"],-r["max_drawdown_r"]))["model"] if eligible else None
    if selected is None:
        return {"selected_model":None,"train":train,
                "holdout":None,"reason":"Insufficient training trades; no model selected"}
    # Prefix is context only. Discard entries before the split from holdout metrics.
    # Replay starts from 35 prior candles; all entries at/after split are included.
    holdout_start=max(0,split-350)
    test=backtest(bars[holdout_start:],htf,selected,spread)
    filtered=[t for t in test["history"] if t["entry_time"]>=bars[split]["time"]]
    return {"selected_model":selected,"train":train,
            "holdout":_summarize_trades(selected,filtered),
            "split_time":bars[split]["time"],
            "warning":"Single chronological holdout, not nested walk-forward optimization."}

def _summarize_trades(model,trades):
    total=sum(t["r"] for t in trades)
    gross_profit=sum(max(0,t["r"]) for t in trades)
    gross_loss=-sum(min(0,t["r"]) for t in trades)
    equity=peak=dd=0.0
    for t in trades:
        equity+=t["r"]
        peak=max(peak,equity)
        dd=max(dd,peak-equity)
    return {"model":model,"trades":len(trades),
            "win_rate":sum(t["r"]>0 for t in trades)/len(trades) if trades else None,
            "total_r":round(total,4),
            "expectancy_r":round(total/len(trades),4) if trades else None,
            "profit_factor":round(gross_profit/gross_loss,4) if gross_loss else None,
            "max_drawdown_r":round(dd,4),"history":trades}
