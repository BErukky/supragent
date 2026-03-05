import subprocess
import json
import sys
import os
import time
from telegram_bot import send_telegram_alert

# Top Liquidity Assets to Scan
ASSETS = [
    "BTC/USD", "ETH/USD", "SOL/USD", "XRP/USD", "ADA/USD", 
    "DOGE/USD", "DOT/USD", "MATIC/USD", "LTC/USD", "LINK/USD"
]

# Ensure we can import from the parent directory (root)
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))
try:
    from main import run_full_analysis
except ImportError:
    # Fallback if run from root
    from main import run_full_analysis

def run_technical_filter(symbol):
    """
    Runs a lightweight technical scan (Layer 1 + Layer 2 only).
    """
    # Now calls the function directly instead of subprocess
    return run_full_analysis(symbol, no_news=True)

def main():
    import argparse
    parser = argparse.ArgumentParser(description='Multi-Asset Scanner v2.1 (Tiered & OOM Optimized)')
    parser.add_argument('--no_news', action='store_true', help='Skip news analysis entirely')
    args = parser.parse_args()

    print("="*60)
    print("SUPER SIGNALS v2.1: OOM-OPTIMIZED MARKET SCANNER")
    print(f"Time: {time.ctime()} | Mode: {'Fast-Tech' if args.no_news else 'Adaptive Scan'}")
    print(f"Scanning {len(ASSETS)} assets...")
    print("="*60 + "\n")

    hits = []
    total = len(ASSETS)
    
    for i, symbol in enumerate(ASSETS):
        # 1. Technical Pulse Update
        if i > 0 and i % 3 == 0:
            send_telegram_alert(f"📡 *Scan Pulse*: Processed {i}/{total} assets. Continuing deep dive...")

        # 2. Tier 1: Technical Pre-Filter
        tech_report = run_technical_filter(symbol)
        if not tech_report:
            continue
            
        sig = tech_report.get("FINAL_SIGNAL", "WAIT")
        conf = tech_report.get("CONFIDENCE", 0)

        # If technically unclear, skip Tier 2 (Expensive Layers)
        if "WAIT" in sig and conf < 65:
            print(f"[-] {symbol}: Skipping (Technically Weak - {conf}%)")
            continue

        # 3. Tier 2: Full Institutional Analysis
        print(f"[+] {symbol}: satisfying Technicals ({conf}%). Running CARI/History...")
        report = run_full_analysis(symbol, no_news=args.no_news)
        
        if report:
            conf = report.get("CONFIDENCE", 0)
            signal = report.get("FINAL_SIGNAL", "WAIT")
            
            # High Confidence Hit (>= 75) - Now including CAUTION signals
            is_blocked = "WAIT / NO_TRADE" in signal or "CRITICAL" in signal
            
            if conf >= 70 and not is_blocked:
                hits.append({
                    "symbol": symbol,
                    "signal": signal,
                    "confidence": conf,
                    "report": report
                })
        
        time.sleep(1)

    print("\n" + "="*60)
    print(f"SCAN COMPLETE: Found {len(hits)} actionable setups.")
    print("="*60)
    
    if not hits:
        send_telegram_alert(f"📉 *MARKET SCAN REPORT*\n\nScanned {total} assets. No actionable institutional setups found.")
    else:
        for hit in hits:
            rep = hit['report']
            risk = rep.get("RISK_ADVISORY", {})
            msg = f"🎯 *MARKET HIT: {hit['symbol']}* 🎯\n\n*Signal:* `{hit['signal']}`\n*Confidence:* {hit['confidence']}/100\n\n*Analysis:* Actionable Opportunity Found."
            if risk:
                msg += f"\n*SL:* `{risk.get('STOP_LOSS')}`\n*TP:* `{risk.get('TAKE_PROFIT', ['N/A'])[0]}`"
            send_telegram_alert(msg)

if __name__ == "__main__":
    main()
