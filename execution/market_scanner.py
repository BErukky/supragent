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
    from main import run_full_analysis

# C3: Scan history for deduplication — prevents re-alerting within 60 minutes
_SCAN_HISTORY_FILE = ".tmp/scan_history.json"
_SCAN_COOLDOWN = 3600  # seconds


def _load_scan_history() -> dict:
    """Returns {symbol: last_alert_timestamp} from disk."""
    try:
        if os.path.exists(_SCAN_HISTORY_FILE):
            with open(_SCAN_HISTORY_FILE, "r") as f:
                return json.load(f)
    except Exception:
        pass
    return {}


def _save_scan_history(history: dict):
    """Persists scan history to disk."""
    try:
        os.makedirs(".tmp", exist_ok=True)
        with open(_SCAN_HISTORY_FILE, "w") as f:
            json.dump(history, f)
    except Exception:
        pass


def _already_alerted(symbol: str, history: dict) -> bool:
    """Returns True if symbol was alerted within the cooldown window."""
    last_ts = history.get(symbol, 0)
    return (time.time() - last_ts) < _SCAN_COOLDOWN


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
    scan_history = _load_scan_history()
    
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
            
            # High Confidence Hit (>= 70) - Now including CAUTION signals
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
            
            # C3: Skip if already alerted within cooldown window
            if _already_alerted(hit['symbol'], scan_history):
                print(f"[=] {hit['symbol']}: Skipping alert (already sent within 60 min)")
                continue

            msg = f"🎯 *MARKET HIT: {hit['symbol']}* 🎯\n\n*Signal:* `{hit['signal']}`\n*Confidence:* {hit['confidence']}/100\n\n*Analysis:* Actionable Opportunity Found."
            if risk:
                msg += f"\n*SL:* `{risk.get('STOP_LOSS')}`\n*TP:* `{risk.get('TAKE_PROFIT', ['N/A'])[0]}`"
            send_telegram_alert(msg)
            scan_history[hit['symbol']] = time.time()

        _save_scan_history(scan_history)

if __name__ == "__main__":
    main()
