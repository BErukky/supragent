import argparse
import json
import sys
import os

# Ensure we can import from the execution directory
sys.path.append(os.path.join(os.path.dirname(__file__), 'execution'))

try:
    from market_data import fetch_data
    from confluence_engine import run_confluence_analysis
    from historical_engine import run_historical_analysis
    from news_scraper import run_scraper
    from news_engine import run_news_analysis
    from report_engine import generate_report
    from datetime import datetime
except ImportError as e:
    print(f"Error: Missing execution components. {e}")
    sys.exit(1)

def run_full_analysis(symbol, htf='1h', ltf='15m', no_news=False, custom_news=None):
    """
    Modular analysis entry point. Returns the final report dict.
    """
    # 1. Fetch Data
    fetch_data(symbol, htf, 100)
    fetch_data(symbol, ltf, 100)
    
    htf_file = f".tmp/{symbol.replace('/', '_')}_{htf}.csv"
    ltf_file = f".tmp/{symbol.replace('/', '_')}_{ltf}.csv"

    if not os.path.exists(htf_file) or not os.path.exists(ltf_file):
        return {"error": f"Could not find market data files for {symbol}"}

    # 2. Confluence (Layer 1 & 2)
    structure_json = run_confluence_analysis(htf_file, ltf_file)
    if not structure_json: return {"error": "Confluence analysis failed."}

    # 3. History (Layer 3)
    history_json = run_historical_analysis(htf_file, htf_file)
    if not history_json: return {"error": "Historical analysis failed."}

    # 4. News (Layer 4)
    if no_news:
        news_json = {
            "risk_level": "LOW",
            "sentiment_score": 0.0,
            "risk_state": "NORMAL",
            "final_penalty": 0,
            "permits_trade": True,
            "layer4_score": 5.0,
            "flagged_keywords": [],
            "reasoning": "News Analysis Skipped (Pure Technical Focus)"
        }
    elif custom_news:
        news_headlines = []
        for txt in custom_news:
            news_headlines.append({
                "text": txt,
                "source_type": "AGGREGATOR",
                "domain": "passed_text",
                "timestamp": str(datetime.now())
            })
        news_json = run_news_analysis(news_headlines)
    else:
        # Autonomous Scrape
        latest_items = run_scraper()
        news_json = run_news_analysis(latest_items)

    if not news_json or "error" in news_json: return {"error": "News analysis failed."}

    # 5. Report (Layer 5 + Risk)
    return generate_report(symbol, structure_json, history_json, news_json)

def main():
    parser = argparse.ArgumentParser(description='Super Signals 2.0 Orchestrator (OOM Optimized)')
    parser.add_argument('--symbol', type=str, default='BTC/USD')
    parser.add_argument('--htf', type=str, default='1h')
    parser.add_argument('--ltf', type=str, default='15m')
    parser.add_argument('--use_mock', action='store_true', help='Force use of mock data')
    parser.add_argument('--news', type=str, nargs='+', help='Custom news headlines')
    parser.add_argument('--no_news', action='store_true', help='Skip news analysis for pure technical focus')
    parser.add_argument('--json_only', action='store_true', help='Output only the final JSON report')
    args = parser.parse_args()

    if not args.json_only:
        print(f"Running Super Signals LIVE v2.0 Analysis for {args.symbol}...")

    final_report = run_full_analysis(args.symbol, args.htf, args.ltf, args.no_news, args.news)
    
    if not final_report or "error" in final_report:
        print(f"Analysis Failed: {final_report.get('error', 'Unknown Error')}", file=sys.stderr)
        sys.exit(1)

    if args.json_only:
        print(json.dumps(final_report))
        return

    # --- PRINT 2.0 OUTPUT ---
    sig = final_report.get("FINAL_SIGNAL")
    conf = final_report.get("CONFIDENCE")
    risk = final_report.get("RISK_ADVISORY", {}) or {}
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
    
    if risk and risk.get("STOP_LOSS"):
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
