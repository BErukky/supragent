import argparse
import subprocess
import json
import sys
import os

# Helper to run script and get JSON output
def run_script(script_name, args):
    cmd = [sys.executable, f"execution/{script_name}"] + args
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"Error running {script_name}: {result.stderr}")
        return None
    output = result.stdout.strip()
    if not output.startswith('{'):
        start = output.find('{')
        if start != -1: output = output[start:]
            
    try:
        return json.loads(output)
    except json.JSONDecodeError:
        print(f"Failed to parse JSON from {script_name}: {output}")
        return None

def main():
    parser = argparse.ArgumentParser(description='Super Signals 2.0 Orchestrator')
    parser.add_argument('--symbol', type=str, default='BTC/USD')
    parser.add_argument('--htf', type=str, default='1h')
    parser.add_argument('--ltf', type=str, default='15m')
    parser.add_argument('--use_mock', action='store_true', help='Force use of mock data')
    parser.add_argument('--news', type=str, nargs='+', help='Custom news headlines')
    parser.add_argument('--no_news', action='store_true', help='Skip news analysis for pure technical focus')
    args = parser.parse_args()

    print(f"Running Super Signals LIVE v2.0 Analysis for {args.symbol}...")

    # 1. Fetch Data
    subprocess.run([sys.executable, "execution/market_data.py", "--symbol", args.symbol, "--timeframe", args.htf, "--limit", "100"], check=False)
    subprocess.run([sys.executable, "execution/market_data.py", "--symbol", args.symbol, "--timeframe", args.ltf, "--limit", "100"], check=False)
    htf_file = f".tmp/{args.symbol.replace('/', '_')}_{args.htf}.csv"
    ltf_file = f".tmp/{args.symbol.replace('/', '_')}_{args.ltf}.csv"

    if not os.path.exists(htf_file) or not os.path.exists(ltf_file):
        print("Error: Could not find data files.")
        sys.exit(1)

    # 2. Confluence (Layer 1 & 2)
    structure_json = run_script("confluence_engine.py", ["--htf", htf_file, "--ltf", ltf_file])
    if not structure_json: sys.exit(1)
    with open(".tmp/latest_struct.json", "w") as f: json.dump(structure_json, f)

    # 3. History (Layer 3)
    history_json = run_script("historical_engine.py", ["--target", htf_file, "--history", htf_file])
    if not history_json: sys.exit(1)
    with open(".tmp/latest_hist.json", "w") as f: json.dump(history_json, f)

    # 4. News (Layer 4)
    if args.no_news:
        news_json = {
            "risk_level": "LOW",
            "sentiment_score": 0.0,
            "risk_penalty": 0,
            "permits_trade": True,
            "layer4_score": 5.0,
            "flagged_keywords": [],
            "reasoning": "News Analysis Skipped (Pure Technical Focus)"
        }
    elif args.news:
        news_headlines = args.news
        news_json = run_script("news_engine.py", ["--text"] + news_headlines)
    else:
        # Autonomous Scrape
        subprocess.run([sys.executable, "execution/news_scraper.py"], check=False)
        try:
            with open(".tmp/latest_headlines.json", "r") as f: news_headlines = json.load(f)
        except: news_headlines = ["Stable market conditions"]
        news_json = run_script("news_engine.py", ["--text"] + news_headlines)

    if not news_json: sys.exit(1)
    with open(".tmp/latest_news.json", "w") as f: json.dump(news_json, f)

    # 5. Report (Layer 5 + Risk)
    final_report = run_script("report_engine.py", [
        "--structure", ".tmp/latest_struct.json",
        "--history", ".tmp/latest_hist.json",
        "--news", ".tmp/latest_news.json",
        "--symbol", args.symbol
    ])
    
    if not final_report: sys.exit(1)

    # --- PRINT 2.0 OUTPUT ---
    sig = final_report.get("FINAL_SIGNAL")
    conf = final_report.get("CONFIDENCE")
    risk = final_report.get("RISK_ADVISORY", {})
    reasons = final_report.get("REASONING", {})
    alerts = final_report.get("GOVERNANCE_ALERTS", [])
    
    print("\n" + "="*45)
    print(f"=== SUPER SIGNALS v2.0 LIVE REPORT ===")
    print(f"Symbol: {args.symbol} | {final_report.get('TIMESTAMP')[:19]}")
    print("-" * 45)
    print(f" SIGNAL:      {sig} ({conf}/100 Conf)")

    if alerts:
        print("\n [!] GOVERNANCE ALERTS:")
        for alert in alerts:
            print(f"     {alert}")
    
    if risk:
        print(f" STOP LOSS:   {risk.get('STOP_LOSS')}")
        print(f" TAKE PROFIT: {' | '.join(map(str, risk.get('TAKE_PROFIT', [])))}")
        print(f" RISK OFFSET: {risk.get('RISK_OFFSET')}x (Tightened for safety)")
    
    print("-" * 45)
    print("--- LAYER-WISE REASONING ---")
    print(f" [L1/L2] {reasons.get('l2_confluence')}")
    print(f" [L3]    {reasons.get('l3_history')}")
    print(f" [L4]    {reasons.get('l4_news')}")
    print("="*45 + "\n")

if __name__ == "__main__":
    main()
