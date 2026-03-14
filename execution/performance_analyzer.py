import json
import os
import sys
import pandas as pd
from datetime import datetime

# ─────────────────────────────────────────────────────────────────────────────
# Phase 2.1: Feedback Loop - Fixed Performance Analyzer
#
# Root cause of the original bug:
#   - report_engine.py only logged entry_price (a structural swing point).
#   - This script then read "current price" from a .tmp/ CSV that had already
#     been overwritten by the next analysis run → drift numbers were nonsense.
#
# Fix applied:
#   1. report_engine.py now snapshots the live close price at analysis time
#      and stores it as snapshot_close in prediction_logs.json.
#   2. This script now fetches a fresh live close via yfinance to compare
#      against snapshot_close for each symbol, giving a real drift reading.
# ─────────────────────────────────────────────────────────────────────────────

def fetch_current_price(symbol):
    """
    Fetches the latest close price for a symbol via yfinance.
    Returns float or None on failure.
    """
    try:
        import yfinance as yf
        yf_symbol = symbol.replace('/', '-')
        if 'BTC' in yf_symbol: yf_symbol = 'BTC-USD'
        elif 'ETH' in yf_symbol: yf_symbol = 'ETH-USD'
        elif 'SOL' in yf_symbol: yf_symbol = 'SOL-USD'
        elif 'XRP' in yf_symbol: yf_symbol = 'XRP-USD'
        elif 'ADA' in yf_symbol: yf_symbol = 'ADA-USD'
        elif 'DOGE' in yf_symbol: yf_symbol = 'DOGE-USD'
        elif 'DOT' in yf_symbol: yf_symbol = 'DOT-USD'
        elif 'MATIC' in yf_symbol: yf_symbol = 'MATIC-USD'
        elif 'LTC' in yf_symbol: yf_symbol = 'LTC-USD'
        elif 'LINK' in yf_symbol: yf_symbol = 'LINK-USD'

        data = yf.download(yf_symbol, period='1d', interval='1h', progress=False)
        if data.empty:
            return None
        # Handle multi-index columns from yfinance
        close_col = [c for c in data.columns if 'close' in str(c).lower() or 'Close' in str(c)]
        if close_col:
            return float(data[close_col[0]].iloc[-1])
        return float(data.iloc[-1, -1])
    except Exception as e:
        print(f"  [!] Could not fetch live price for {symbol}: {e}")
        return None


def analyze_performance():
    log_file = ".tmp/prediction_logs.json"
    if not os.path.exists(log_file):
        print("No prediction logs found. Run some analysis first!")
        return

    try:
        with open(log_file, 'r') as f:
            logs = json.load(f)
    except Exception as e:
        print(f"Error reading logs: {e}")
        return

    if not logs:
        print("Logs are empty.")
        return

    print("=" * 65)
    print("  SUPER SIGNALS: ANALYTICAL FEEDBACK LOOP  ")
    print(f"  Total Predictions Tracked: {len(logs)}")
    print("=" * 65 + "\n")

    # Group by symbol so we only fetch each live price once
    symbols_needed = {e['symbol'] for e in logs if "WAIT" not in e.get('action', 'WAIT')}
    print(f"Fetching live prices for {len(symbols_needed)} symbol(s)...\n")

    live_prices = {}
    for sym in symbols_needed:
        price = fetch_current_price(sym)
        if price:
            live_prices[sym] = price
            print(f"  {sym}: ${price:,.2f}")

    results = []
    skipped_wait = 0
    skipped_no_price = 0

    for entry in logs:
        action = entry.get('action', 'WAIT')
        if "WAIT" in action:
            skipped_wait += 1
            continue

        symbol        = entry['symbol']
        # FIX 2.1: Use snapshot_close (live price at signal time) as the baseline.
        # Existing logs that pre-date this fix will fall back to entry_price.
        baseline      = entry.get('snapshot_close', entry.get('entry_price', 0))
        timestamp     = entry.get('timestamp', 'Unknown')
        confidence    = entry.get('confidence', 0)

        current_price = live_prices.get(symbol)
        if not current_price or not baseline:
            skipped_no_price += 1
            continue

        drift = ((current_price - baseline) / baseline) * 100

        # Determine outcome based on bias direction
        PROFIT_THRESHOLD = 0.5   # % movement considered meaningful
        if action == "LONG_BIAS":
            status = "PROFITABLE" if drift > PROFIT_THRESHOLD else "DRAWDOWN" if drift < -PROFIT_THRESHOLD else "NEUTRAL"
        elif "SHORT" in action:
            status = "PROFITABLE" if drift < -PROFIT_THRESHOLD else "DRAWDOWN" if drift > PROFIT_THRESHOLD else "NEUTRAL"
        else:
            status = "NEUTRAL"

        results.append({
            "symbol":   symbol,
            "time":     timestamp[:16],
            "bias":     action,
            "conf":     round(confidence, 1),
            "baseline": round(baseline, 2),
            "current":  round(current_price, 2),
            "drift":    round(drift, 2),
            "status":   status
        })

    # ── Output Table ──────────────────────────────────────────────────────────
    if not results:
        print("No evaluable trade biases found.")
        print(f"  WAIT signals skipped:     {skipped_wait}")
        print(f"  Missing price data:       {skipped_no_price}")
    else:
        header = f"{'ASSET':<10} | {'TIME':<16} | {'CONF':>5} | {'BASELINE':>10} | {'CURRENT':>10} | {'DRIFT':>7} | STATUS"
        print(header)
        print("-" * len(header))
        for r in results:
            direction = "↑" if r['drift'] > 0 else "↓"
            print(f"{r['symbol']:<10} | {r['time']:<16} | {r['conf']:>5} | {r['baseline']:>10,.2f} | {r['current']:>10,.2f} | {direction}{abs(r['drift']):>5.2f}% | {r['status']}")

        # ── Summary Statistics ────────────────────────────────────────────────
        profitable = sum(1 for r in results if "PROFITABLE" in r['status'])
        drawdown   = sum(1 for r in results if "DRAWDOWN" in r['status'])
        neutral    = sum(1 for r in results if "NEUTRAL" in r['status'])
        win_rate   = (profitable / len(results) * 100) if results else 0

        print("\n" + "=" * 65)
        print(f"  SUMMARY: {len(results)} evaluated | {profitable} Profitable | {drawdown} Drawdown | {neutral} Neutral")
        print(f"  WIN RATE: {win_rate:.1f}%")
        avg_drift = sum(r['drift'] for r in results) / len(results)
        print(f"  AVG DRIFT: {avg_drift:+.2f}%")
        print(f"  WAIT signals skipped: {skipped_wait} | No-price skipped: {skipped_no_price}")
        print("=" * 65 + "\n")

        advice = "Governance is performing well. Maintain current weights." if win_rate >= 60 else \
                 "Win rate below 60%. Consider raising the confidence threshold." if win_rate >= 40 else \
                 "Low win rate. Review L1/L2 structure sensitivity settings."
        print(f"  Feedback Recommendation: {advice}\n")


if __name__ == "__main__":
    analyze_performance()
