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

def run_analysis(symbol, no_news=False):
    """
    Runs the main.py script for a specific symbol and returns the final report JSON.
    """
    print(f"Scanning {symbol}...")
    cmd = [sys.executable, "main.py", "--symbol", symbol]
    if no_news:
        cmd.append("--no_news")
    result = subprocess.run(cmd, capture_output=True, text=True)
    
    # Extract JSON part from output
    output = result.stdout.strip()
    start = output.find('{')
    if start != -1:
        try:
            return json.loads(output[start:])
        except:
            return None
    return None

def main():
    import argparse
    parser = argparse.ArgumentParser(description='Multi-Asset Scanner')
    parser.add_argument('--no_news', action='store_true', help='Skip news analysis')
    args = parser.parse_args()

    print("="*60)
    print("SUPER SIGNALS v2.0: MULTI-ASSET MARKET SCANNER")
    if args.no_news: print("(MODE: PURE TECHNICAL SCAN)")
    print(f"Time: {time.ctime()}")
    print(f"Scanning {len(ASSETS)} high-liquidity assets...")
    print("="*60 + "\n")

    hits = []
    
    for symbol in ASSETS:
        report = run_analysis(symbol, no_news=args.no_news)
        
        if report:
            conf = report.get("CONFIDENCE", 0)
            signal = report.get("FINAL_SIGNAL", "WAIT / NO_TRADE")
            
            # Identify High Confidence Hits (>= 75)
            if conf >= 75 and "WAIT" not in signal:
                hits.append({
                    "symbol": symbol,
                    "signal": signal,
                    "confidence": conf,
                    "report": report
                })
        
        # Avoid rate limits if many assets
        time.sleep(1)

    print("\n" + "="*60)
    print("SCAN SUMMARY")
    print("="*60)
    
    if not hits:
        print("No high-confidence setups found in the current market conditions.")
        print("System Governance: Market uncertainty remains high.")
        
        # Optional: Send a daily summary if no hits
        # send_telegram_alert(f"📉 *MARKET SCAN REPORT*\n\nScanned {len(ASSETS)} assets.\nResult: No high-confidence setups found.\nStatus: Governance Wait / Defensive Mode.")
        
    else:
        print(f"Found {len(hits)} High-Confidence Setups:\n")
        for hit in hits:
            rep = hit['report']
            risk = rep.get("RISK_ADVISORY", {})
            print(f"HIT: [{hit['symbol']}] -> {hit['signal']} ({hit['confidence']}/100 Conf)")
            
            # --- TELEGRAM ALERT FOR HIT ---
            msg = f"🎯 *MARKET SCANNER HIT* 🎯\n\n*Symbol:* {hit['symbol']}\n*Signal:* {hit['signal']}\n*Confidence:* {hit['confidence']}/100\n\n*Status:* Actionable Setup Found."
            if risk:
                msg += f"\n*SL:* {risk.get('STOP_LOSS')}"
            send_telegram_alert(msg)
            # ------------------------------

            if risk:
                print(f"   STOP LOSS:   {risk.get('STOP_LOSS')}")
                print(f"   TAKE PROFIT: {' | '.join(map(str, risk.get('TAKE_PROFIT', [])))}")
            print("-" * 30)

    print("\nScan Complete. All predictions logged to Prediction Database.")
    print("="*60 + "\n")

if __name__ == "__main__":
    main()
