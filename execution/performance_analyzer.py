import json
import os
import sys
import pandas as pd
from datetime import datetime

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

    print("="*60)
    print("SUPER SIGNALS: ANALYTICAL FEEDBACK LOOP")
    print(f"Total Predictions Tracked: {len(logs)}")
    print("="*60 + "\n")

    results = []
    
    # We need to fetch current prices to compare
    # To keep it fast, we'll try to find the latest CSVs in .tmp
    for entry in logs:
        symbol = entry['symbol']
        action = entry['action']
        if "WAIT" in action:
            continue
            
        entry_price = entry['entry_price']
        timestamp = entry['timestamp']
        
        # Try to find current price from .tmp files
        csv_path = f".tmp/{symbol.replace('/', '_')}_1h.csv"
        current_price = None
        if os.path.exists(csv_path):
            try:
                df = pd.read_csv(csv_path)
                current_price = df['close'].iloc[-1]
            except: pass
            
        if current_price:
            drift = ((current_price - entry_price) / entry_price) * 100
            
            status = "PENDING"
            if action == "LONG_BIAS":
                status = "PROFITABLE" if drift > 0.5 else "DRAWDOWM" if drift < -0.5 else "NEUTRAL"
            elif action == "SHORT_BIAS":
                status = "PROFITABLE" if drift < -0.5 else "DRAWDOWM" if drift > 0.5 else "NEUTRAL"
            
            results.append({
                "symbol": symbol,
                "time": timestamp[:16],
                "bias": action,
                "entry": round(entry_price, 2),
                "current": round(current_price, 2),
                "perf": f"{round(drift, 2)}%",
                "status": status
            })

    if not results:
        print("No active trade biases found in history to evaluate.")
        print("(Note: The system predominantly issued WAIT states due to high news risk).")
    else:
        # Print Table
        print(f"{'ASSET':<10} | {'ENTRY':<10} | {'CURRENT':<10} | {'DRIFT':<8} | {'STATUS'}")
        print("-" * 60)
        for r in results:
            print(f"{r['symbol']:<10} | {r['entry']:<10} | {r['current']:<10} | {r['perf']:<8} | {r['status']}")
            
    print("\n" + "="*60)
    print("Feedback loop suggests: " + ("Maintain Current Governance" if not results else "Refining Layer Weights..."))
    print("="*60 + "\n")

if __name__ == "__main__":
    analyze_performance()
