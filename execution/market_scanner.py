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

def run_technical_filter(symbol):
    """
    Runs a lightweight technical scan (Layer 1 + Layer 2 only).
    Returns basic signal and coherence score.
    """
    # We use main.py with --no_news to avoid expensive news/history layers
    cmd = [sys.executable, "main.py", "--symbol", symbol, "--no_news", "--json_only"]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        output = result.stdout.strip()
        start = output.find('{')
        if start != -1:
            return json.loads(output[start:])
    except:
        return None
    return None

def main():
    import argparse
    parser = argparse.ArgumentParser(description='Multi-Asset Scanner v2.1 (Tiered)')
    parser.add_argument('--no_news', action='store_true', help='Skip news analysis entirely')
    args = parser.parse_args()

    print("="*60)
    print("SUPER SIGNALS v2.1: TIERED MULTI-ASSET SCANNER")
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
        report = run_analysis(symbol, no_news=args.no_news)
        
        if report:
            conf = report.get("CONFIDENCE", 0)
            signal = report.get("FINAL_SIGNAL", "WAIT")
            
            # High Confidence Hit (>= 75) - Now including CAUTION signals if technicals are strong
            # We strictly block "CRITICAL" news, but allow "CAUTION" if signal is solid.
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
        send_telegram_alert(f"📉 *MARKET SCAN REPORT*\n\nScanned {total} assets. No high-confidence institutional setups found.\nStatus: Market remains defensive.")
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

if __name__ == "__main__":
    main()
