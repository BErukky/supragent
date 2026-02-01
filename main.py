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
    # Filter out text logs to find JSON start
    output = result.stdout.strip()
    if not output.startswith('{'):
        # Try to find the JSON block if there's log noise
        start = output.find('{')
        if start != -1:
            output = output[start:]
            
    try:
        return json.loads(output)
    except json.JSONDecodeError:
        print(f"Failed to parse JSON from {script_name}: {output}")
        return None

def main():
    parser = argparse.ArgumentParser(description='Super Signals Orchestrator')
    parser.add_argument('--symbol', type=str, default='BTC/USD')
    parser.add_argument('--htf', type=str, default='1h')
    parser.add_argument('--ltf', type=str, default='15m')
    parser.add_argument('--use_mock', action='store_true', help='Force use of mock data')
    parser.add_argument('--news', type=str, nargs='+', help='Custom news headlines')
    args = parser.parse_args()

    print(f"Running Super Signals LIVE Analysis for {args.symbol}...")

    # 1. Fetch Data
    if args.use_mock:
        print("Using MOCK data as requested via flag...")
        subprocess.run([sys.executable, "execution/mock_data.py", "--symbol", args.symbol.replace('/','_'), "--limit", "100"], check=False)
        subprocess.run([sys.executable, "execution/mock_data.py", "--symbol", args.symbol.replace('/','_') + "_LTF", "--limit", "100"], check=False)
        htf_file = f".tmp/{args.symbol.replace('/', '_')}_1h.csv" # mock default
        ltf_file = f".tmp/{args.symbol.replace('/', '_')}_LTF_1h.csv"
    else:
        # Fetch REAL HTF Data
        subprocess.run([sys.executable, "execution/market_data.py", "--symbol", args.symbol, "--timeframe", args.htf, "--limit", "100"], check=False)
        # Fetch REAL LTF Data
        subprocess.run([sys.executable, "execution/market_data.py", "--symbol", args.symbol, "--timeframe", args.ltf, "--limit", "100"], check=False)
        
        htf_file = f".tmp/{args.symbol.replace('/', '_')}_{args.htf}.csv"
        ltf_file = f".tmp/{args.symbol.replace('/', '_')}_{args.ltf}.csv"

    if not os.path.exists(htf_file) or not os.path.exists(ltf_file):
        print("Error: Could not find data files for analysis.")
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
    if args.news:
        news_headlines = args.news
        print(f"Using manual news inputs: {len(news_headlines)} headlines")
    else:
        # Autonomous Scrape
        subprocess.run([sys.executable, "execution/news_scraper.py"], check=False)
        try:
            with open(".tmp/latest_headlines.json", "r") as f:
                news_headlines = json.load(f)
        except:
            news_headlines = ["Market status stable", "No headlines found"]
            
    news_json = run_script("news_engine.py", ["--text"] + news_headlines)
    if not news_json: sys.exit(1)
    with open(".tmp/latest_news.json", "w") as f: json.dump(news_json, f)

    # 5. Report (Layer 5 + Risk)
    final_report = run_script("report_engine.py", [
        "--structure", ".tmp/latest_struct.json",
        "--history", ".tmp/latest_hist.json",
        "--news", ".tmp/latest_news.json"
    ])
    
    if not final_report: sys.exit(1)

    # --- PRINT CLEAN OUTPUT ---
    sig = final_report.get("FINAL_SIGNAL")
    conf = final_report.get("CONFIDENCE_SCORE")
    risk = final_report.get("RISK_ADVISORY", {})
    
    print("\n" + "="*40)
    print(f"=== SUPER SIGNALS LIVE REPORT ===")
    print(f"Symbol: {args.symbol} | HTF: {args.htf} | LTF: {args.ltf}")
    print(f"Time:   {final_report.get('TIMESTAMP')}")
    print("-" * 40)
    print(f" SIGNAL:      {sig} ({conf}/100 Conf)")
    
    if risk:
        sl = risk.get("STOP_LOSS", "N/A")
        tps = risk.get("TAKE_PROFIT", [])
        tp_str = " | ".join(map(str, tps)) if tps else "N/A"
        print(f" STOP LOSS:   {sl}")
        print(f" TAKE PROFIT: {tp_str}")
    
    print("-" * 40)
    print("--- REASONING & GOVERNANCE ---")
    for reason in final_report.get("REASONING", []):
        print(f" {reason}")
    print("="*40 + "\n")

if __name__ == "__main__":
    main()
