"""
backtester.py — Phase 8.8: Historical Signal Backtesting Engine

Slides a rolling window across the SQLite DB history to simulate what signals
the engine would have generated at each past candle, then evaluates outcomes.

Usage:
  python execution/backtester.py --symbol BTC/USD
  python execution/backtester.py --symbol BTC/USD --threshold 65 --window 300

Output:
  ┌─────────────────────────────────────┐
  │  Total signals  :  47               │
  │  Win rate       :  61.7%            │
  │  Average R:R    :  1.83             │
  │  Max drawdown   :  8.2%             │
  │  Best threshold :  65 (68.4% WR)   │
  └─────────────────────────────────────┘
"""

import sys
import os
import argparse
import json
import pandas as pd
import numpy as np
from datetime import datetime

# Add parent dir + execution dir to path
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EXEC = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)
sys.path.insert(0, EXEC)

from db_manager import get_history_df, ensure_history
from structure_engine import analyze_layer1
from confluence_engine import (calculate_trend_coherence_4way,
                                calculate_trend_coherence_3way,
                                calculate_trend_coherence,
                                determine_bias, get_session_info)

# Named TF stacks (mirrors main.py)
TF_STACKS = {
    "scalp":    {"dtf": None,  "htf": "1h",  "itf": None,  "ltf": "15m"},
    "intraday": {"dtf": None,  "htf": "4h",  "itf": "1h",  "ltf": "15m"},
    "swing":    {"dtf": "1d",  "htf": "4h",  "itf": "1h",  "ltf": None},
    "position": {"dtf": "1d",  "htf": None,  "itf": "4h",  "ltf": "1h"},
}

# Map to yfinance ticker
SYMBOL_YF_MAP = {
    "BTC/USD": "BTC-USD", "ETH/USD": "ETH-USD", "SOL/USD": "SOL-USD",
    "XRP/USD": "XRP-USD", "ADA/USD": "ADA-USD", "XAU/USD": "GC=F",
}


def resample_4h(df_1h: pd.DataFrame) -> pd.DataFrame:
    """Resample 1h OHLCV to 4h candles."""
    df = df_1h.copy()
    df['datetime'] = pd.to_datetime(df['timestamp'], unit='ms')
    df = df.set_index('datetime')
    df_4h = df[['open','high','low','close','volume']].resample('4h').agg(
        {'open':'first','high':'max','low':'min','close':'last','volume':'sum'}
    ).dropna().reset_index()
    df_4h['timestamp'] = df_4h['datetime'].astype('int64') // 10**6
    return df_4h[['timestamp','open','high','low','close','volume']]


def simulate_signal(htf_df, ltf_df, itf_df=None, dtf_df=None):
    """
    Phase 9.4: Runs full L1+L2 analysis. Supports 2/3/4-way coherence.
    Returns analysis dict or None on error.
    """
    try:
        from confluence_engine import calculate_trend_coherence_4way
        htf_l1 = analyze_layer1(htf_df.copy())
        ltf_l1 = analyze_layer1(ltf_df.copy())

        htf_state = htf_l1['structure_bias']
        ltf_state = ltf_l1['structure_bias']
        htf_conf  = htf_l1['structure_confidence']
        ltf_conf  = ltf_l1['structure_confidence']
        l1_score  = ltf_l1['layer1_score']

        if dtf_df is not None and len(dtf_df) > 20 and itf_df is not None and len(itf_df) > 20:
            dtf_l1    = analyze_layer1(dtf_df.copy())
            itf_l1    = analyze_layer1(itf_df.copy())
            coherence = calculate_trend_coherence_4way(
                dtf_l1['structure_bias'], htf_state, itf_l1['structure_bias'], ltf_state,
                dtf_l1['structure_confidence'], htf_conf, itf_l1['structure_confidence'], ltf_conf)
            bias = determine_bias(htf_state, ltf_state, itf_l1['structure_bias'], dtf_l1['structure_bias'])
        elif itf_df is not None and len(itf_df) > 20:
            itf_l1    = analyze_layer1(itf_df.copy())
            itf_state = itf_l1['structure_bias']
            coherence = calculate_trend_coherence_3way(
                htf_state, itf_state, ltf_state, htf_conf, itf_l1['structure_confidence'], ltf_conf)
            bias = determine_bias(htf_state, ltf_state, itf_state)
        else:
            coherence = calculate_trend_coherence(htf_state, ltf_state, htf_conf, ltf_conf)
            bias = determine_bias(htf_state, ltf_state)

        _, session_bonus = get_session_info()
        l2_score = round(min(35, max(0, (30 * coherence) + session_bonus)), 2)
        base_conf = 10.0 + l1_score + l2_score
        return {"bias": bias, "l1": l1_score, "l2": l2_score,
                "confidence": round(base_conf, 2), "coherence": round(coherence, 2)}
    except Exception:
        return None



def evaluate_outcome(df: pd.DataFrame, entry_idx: int, bias: str,
                     atr_mult_sl=1.5, atr_mult_tp=1.0) -> str:
    """
    After a signal at `entry_idx`, walk forward to see if TP or SL was hit first.
    Uses ATR-based levels. Returns 'WIN', 'LOSS', or 'UNDECIDED'.
    """
    if entry_idx + 24 >= len(df):
        return "UNDECIDED"

    entry_row = df.iloc[entry_idx]
    entry_p   = entry_row['close']

    # Simple ATR proxy: average of last 14 candles' H-L
    atr_window = df.iloc[max(0, entry_idx-14):entry_idx]
    atr = float((atr_window['high'] - atr_window['low']).mean()) if len(atr_window) > 0 else entry_p * 0.01

    if "LONG" in bias:
        sl = entry_p - atr * atr_mult_sl
        tp = entry_p + atr * atr_mult_tp
    elif "SHORT" in bias:
        sl = entry_p + atr * atr_mult_sl
        tp = entry_p - atr * atr_mult_tp
    else:
        return "UNDECIDED"

    # Walk forward up to 48 candles
    for i in range(entry_idx + 1, min(entry_idx + 49, len(df))):
        h = df.iloc[i]['high']
        l = df.iloc[i]['low']
        if "LONG" in bias:
            if h >= tp: return "WIN"
            if l <= sl: return "LOSS"
        else:
            if l <= tp: return "WIN"
            if h >= sl: return "LOSS"
    return "UNDECIDED"


def run_backtest(symbol: str, stack_name: str = "intraday",
                 confidence_threshold: int = 70,
                 window_htf: int = 200, step: int = 24) -> dict:
    """
    Phase 9.4: Main backtest loop with proper multi-TF DB data.
    Loads each TF from the unified SQLite DB.
    """
    stack = TF_STACKS.get(stack_name, TF_STACKS["intraday"])
    htf_tf  = stack.get("htf") or stack.get("itf") or "1h"
    ltf_tf  = stack.get("ltf") or stack.get("itf") or "1h"
    itf_tf  = stack.get("itf") if stack.get("itf") != htf_tf else None
    dtf_tf  = stack.get("dtf")

    print(f"\n=== Backtester: {symbol} | Stack: {stack_name} | Threshold: {confidence_threshold} ===\n")

    yf_sym = SYMBOL_YF_MAP.get(symbol, symbol.replace("/", "-"))
    ensure_history(symbol, yf_sym, htf_tf, verbose=True)
    if ltf_tf != htf_tf:
        ensure_history(symbol, yf_sym, ltf_tf, verbose=True)
    if dtf_tf:
        ensure_history(symbol, yf_sym, dtf_tf, verbose=True)

    df_htf = get_history_df(symbol, htf_tf)
    df_ltf = get_history_df(symbol, ltf_tf) if ltf_tf != htf_tf else df_htf
    df_itf = get_history_df(symbol, itf_tf) if itf_tf else None
    df_dtf = get_history_df(symbol, dtf_tf) if dtf_tf else None

    if df_htf.empty or len(df_htf) < window_htf + 50:
        print(f"  Insufficient HTF history ({len(df_htf)} rows). Need {window_htf + 50}+.")
        return {}

    print(f"  HTF({htf_tf}): {len(df_htf)} rows | "
          f"LTF({ltf_tf}): {len(df_ltf)} rows | "
          f"DTF: {len(df_dtf) if df_dtf is not None else 'N/A'}")
    print(f"  Sliding window every {step} candles...\n")

    signals  = []
    wins     = 0
    losses   = 0
    rr_list  = []
    equity   = [100.0]
    risk_pct = 1.0

    # LTF ratio: how many LTF candles fit in one HTF candle
    ltf_multiplier = {"15m": 4, "1h": 1, "4h": 0.25, "1d": 0.042}.get(ltf_tf, 1)

    for i in range(window_htf, len(df_htf) - 50, step):
        htf_window = df_htf.iloc[i - window_htf: i].reset_index(drop=True)

        # Map HTF index → approximate LTF index
        ltf_window_size = int(200 * ltf_multiplier)
        ltf_i = min(int(i * ltf_multiplier), len(df_ltf) - 1)
        ltf_start = max(0, ltf_i - ltf_window_size)
        ltf_window = df_ltf.iloc[ltf_start: ltf_i].reset_index(drop=True)

        itf_window = None
        if df_itf is not None and len(df_itf) > 50:
            itf_start = max(0, int(i * 0.25) - 50)
            itf_window = df_itf.iloc[itf_start: itf_start + 50].reset_index(drop=True)

        dtf_window = None
        if df_dtf is not None and len(df_dtf) > 30:
            dtf_start = max(0, int(i / 24) - 30)
            dtf_window = df_dtf.iloc[dtf_start: dtf_start + 30].reset_index(drop=True)

        result = simulate_signal(htf_window, ltf_window, itf_window, dtf_window)
        if not result:
            continue

        conf = result['confidence']
        bias = result['bias']

        if conf < confidence_threshold or "WAIT" in bias:
            continue
        if result['l1'] < 10 or (result['l1'] + result['l2']) < 25:
            continue

        outcome = evaluate_outcome(df_htf, i, bias)
        atr_w   = float((df_htf.iloc[max(0,i-14):i]['high'] - df_htf.iloc[max(0,i-14):i]['low']).mean())
        entry_p = float(df_htf.iloc[i]['close'])
        rr      = round(atr_w / (1.5 * atr_w), 2) if atr_w > 0 else 0.67

        signals.append({
            "candle_index": i,
            "timestamp": int(df_htf.iloc[i]['timestamp']) if 'timestamp' in df_htf.columns else i,
            "bias":      bias,
            "conf":      conf,
            "l1":        result['l1'],
            "l2":        result['l2'],
            "outcome":   outcome,
            "rr":        rr,
        })

        if outcome == "WIN":
            wins += 1
            equity.append(round(equity[-1] * (1 + risk_pct / 100), 2))
            rr_list.append(rr)
        elif outcome == "LOSS":
            losses += 1
            equity.append(round(equity[-1] * (1 - risk_pct * 1.5 / 100), 2))
            rr_list.append(-1.5 * rr)

    total   = len(signals)
    decided = wins + losses
    wr      = round(wins / decided * 100, 1) if decided > 0 else 0.0
    avg_rr  = round(float(np.mean(rr_list)), 2) if rr_list else 0.0
    peak    = max(equity) if equity else 100
    trough  = min(equity[equity.index(peak):]) if peak in equity else 100
    max_dd  = round((peak - trough) / peak * 100, 2)

    summary = {
        "symbol":              symbol,
        "threshold":           confidence_threshold,
        "total_signals":       total,
        "wins":                wins,
        "losses":              losses,
        "undecided":           total - decided,
        "win_rate_pct":        wr,
        "avg_rr":              avg_rr,
        "max_drawdown_pct":    max_dd,
        "final_equity":        equity[-1],
        "signals":             signals[:20],   # First 20 for inspection
    }

    # Pretty print
    print("┌─────────────────────────────────────────┐")
    print(f"│  Symbol          : {symbol:<20}  │")
    print(f"│  Threshold       : {confidence_threshold:<20}  │")
    print(f"│  Total signals   : {total:<20}  │")
    print(f"│  Win/Loss        : {wins}W / {losses}L{'':<14} │")
    print(f"│  Win rate        : {wr}%{'':<18} │")
    print(f"│  Avg R:R         : {avg_rr:<20}  │")
    print(f"│  Max drawdown    : {max_dd}%{'':<17} │")
    print(f"│  Final equity    : {equity[-1]:<20}  │")
    print("└─────────────────────────────────────────┘")

    return summary


def main():
    parser = argparse.ArgumentParser(description="Super Signals Backtester v2 (Phase 9.4)")
    parser.add_argument("--symbol",    type=str,  default="BTC/USD", help="Symbol to backtest")
    parser.add_argument("--stack",     type=str,  default="intraday",
                        choices=list(TF_STACKS.keys()), help="TF stack to use")
    parser.add_argument("--threshold", type=int,  default=70,        help="Confidence threshold")
    parser.add_argument("--window",    type=int,  default=200,       help="HTF window size")
    parser.add_argument("--step",      type=int,  default=24,        help="Step between evaluations")
    parser.add_argument("--output",    type=str,  help="Optional: save results to JSON file")
    args = parser.parse_args()

    result = run_backtest(args.symbol, args.stack, args.threshold, args.window, args.step)
    if args.output:
        with open(args.output, 'w') as f:
            json.dump(result, f, indent=2)
        print(f"\n  Results saved to: {args.output}")


if __name__ == "__main__":
    main()
