"""
main.py — Super Signals v2.1 Orchestrator
Phase 9.3: Named Timeframe Stacks + Daily TF + multi-TF DB seeding.

Usage:
  python main.py --symbol BTC/USD                      # default: intraday stack
  python main.py --symbol BTC/USD --stack swing         # 1D / 4H / 1H
  python main.py --symbol BTC/USD --stack scalp         # 1H / 15M
  python main.py --symbol BTC/USD --htf 4h --ltf 15m   # raw override
  python main.py --symbol BTC/USD --no_news             # skip news
"""

import argparse
import json
import sys
import os
import pandas as pd
from dotenv import load_dotenv, find_dotenv

load_dotenv(find_dotenv())

# Ensure we can import from the execution directory
sys.path.append(os.path.join(os.path.dirname(__file__), 'execution'))

try:
    from market_data import fetch_data
    from confluence_engine import run_confluence_analysis
    from historical_engine import run_historical_analysis, calculate_seasonality_stats
    from news_scraper import run_scraper
    from news_engine import run_news_analysis
    from report_engine import generate_report
    from funding_engine import analyze_funding
    from db_manager import ensure_history
    from cme_engine import analyze_cme_gaps
    from oi_engine import analyze_oi
    from macro_engine import analyze_macro
    from options_engine import analyze_options
    from nlp_engine import generate_nlp_summary
    from datetime import datetime
except ImportError as e:
    print(f"Error: Missing execution components. {e}")
    sys.exit(1)


# ─────────────────────────────────────────────────────────────────────────────
# Phase 9.3: Named Timeframe Stacks
# Each stack defines which TFs are active. None = that slot is not used.
#   dtf = Daily        (macro direction, highest weight)
#   htf = High TF      (main structure)
#   itf = Intermediate (4H, mid-term confirmation)
#   ltf = Low TF       (entry precision)
# ─────────────────────────────────────────────────────────────────────────────
TF_STACKS = {
    "scalp_ultra":  {"dtf": None,  "htf": "15m", "itf": "5m",  "ltf": "1m"},
    "scalp_fast":   {"dtf": None,  "htf": "1h",  "itf": "15m", "ltf": "5m"},
    "scalp":        {"dtf": None,  "htf": "1h",  "itf": None,  "ltf": "15m"},
    "intraday":     {"dtf": None,  "htf": "4h",  "itf": "1h",  "ltf": "15m"},
    "swing":        {"dtf": "1d",  "htf": "4h",  "itf": "1h",  "ltf": None},
    "position":     {"dtf": "1d",  "htf": None,  "itf": "4h",  "ltf": "1h"},
}

VALID_STACKS = list(TF_STACKS.keys())

# yfinance ticker map for DB seeding
SYMBOL_YF_MAP = {
    "BTC/USD":  "BTC-USD",  "ETH/USD":  "ETH-USD",  "SOL/USD":  "SOL-USD",
    "XRP/USD":  "XRP-USD",  "ADA/USD":  "ADA-USD",  "DOT/USD":  "DOT-USD",
    "DOGE/USD": "DOGE-USD", "MATIC/USD":"MATIC-USD","AVAX/USD": "AVAX-USD",
    "XAU/USD":  "GC=F",     "EUR/USD":  "EURUSD=X", "GBP/USD":  "GBPUSD=X",
    "USD/JPY":  "USDJPY=X", "BTC/GBP":  "BTC-GBP",
}


def _resolve_stack(stack_name=None, htf_override=None, ltf_override=None,
                   itf_override=None, dtf_override=None) -> dict:
    """
    Returns the resolved TF stack dict.
    Raw overrides take priority; stack name is applied next; default = intraday.
    """
    if htf_override or ltf_override:
        return {
            "dtf": dtf_override,
            "htf": htf_override or "1h",
            "itf": itf_override,
            "ltf": ltf_override or "15m",
        }
    if stack_name:
        if stack_name not in TF_STACKS:
            print(f"Warning: Unknown stack '{stack_name}'. Using 'intraday'.")
        return TF_STACKS.get(stack_name, TF_STACKS["intraday"])
    return TF_STACKS["intraday"]


def _csv_path(symbol: str, tf: str) -> str:
    return f".tmp/{symbol.replace('/', '_')}_{tf}.csv"


def _fetch_and_resample(symbol: str, stack: dict):
    """
    Fetches live data for all active TFs in the stack.
    4H is always resampled from 1H (not fetched directly).
    Daily (1d) is fetched via yfinance with a wider period.
    """
    fetched = {}

    # HTF / ITF — standard fetch
    for role in ["htf", "itf", "ltf"]:
        tf = stack.get(role)
        if not tf or tf == "4h":
            continue
        candles = 500 if role in ["htf", "itf"] else 200
        # Fetch more candles for lower timeframes
        if tf in ["1m", "5m"]:
            candles = min(candles, 100)  # yfinance limits on 1m/5m
        fetch_data(symbol, tf, candles)
        fetched[role] = _csv_path(symbol, tf)

    # Daily TF — fetch 500 daily candles ≈ ~2 years
    if stack.get("dtf") == "1d":
        fetch_data(symbol, "1d", 500)
        fetched["dtf"] = _csv_path(symbol, "1d")

    # 4H — resample from 1H source (HTF or ITF)
    needs_4h = (stack.get("htf") == "4h") or (stack.get("itf") == "4h")
    if needs_4h:
        # Find the 1H CSV to resample from
        src_1h = _csv_path(symbol, "1h")
        if not os.path.exists(src_1h):
            # Try fetching 1h if not already there
            fetch_data(symbol, "1h", 500)
        if os.path.exists(src_1h):
            try:
                df_1h = pd.read_csv(src_1h)
                df_1h['datetime'] = pd.to_datetime(df_1h['timestamp'], unit='ms', utc=True)
                df_4h = (df_1h.set_index('datetime')[['open','high','low','close','volume']]
                         .resample('4h')
                         .agg({'open':'first','high':'max','low':'min',
                               'close':'last','volume':'sum'})
                         .dropna().reset_index())
                df_4h['timestamp'] = (df_4h['datetime'].astype('int64') // 10**6).astype(int)
                df_4h[['timestamp','open','high','low','close','volume']].to_csv(
                    _csv_path(symbol, "4h"), index=False)
                if stack.get("htf") == "4h":
                    fetched["htf"] = _csv_path(symbol, "4h")
                if stack.get("itf") == "4h":
                    fetched["itf"] = _csv_path(symbol, "4h")
            except Exception as e:
                print(f"  4H resample failed: {e}")
                pass

    return fetched


def _seed_db(symbol: str):
    """Phase 9.1: Seeds the DB with 1H history if needed (fast incremental update)."""
    yf_sym = SYMBOL_YF_MAP.get(symbol, symbol.replace("/", "-"))
    try:
        ensure_history(symbol, yf_sym, "1h", verbose=True)
    except Exception:
        pass


def run_full_analysis(symbol, stack_name="intraday", htf=None, ltf=None,
                      itf=None, dtf=None, no_news=False, custom_news=None, use_nlp=False):
    """
    Phase 9.3: Modular analysis entry point with named stack support.
    Returns the final report dict.
    """
    stack = _resolve_stack(stack_name, htf, ltf, itf, dtf)
    stack_label = stack_name or f"custom({stack.get('htf')}/{stack.get('ltf')})"

    print(f"  Stack: {stack_label} — DTF:{stack['dtf']} HTF:{stack['htf']} "
          f"ITF:{stack['itf']} LTF:{stack['ltf']}")

    # 1a. Seed DB (1H history for L3 historical analysis)
    _seed_db(symbol)

    # 1b. Fetch live CSVs for all active TFs
    fetched = _fetch_and_resample(symbol, stack)

    # Determine the primary HTF file (used for L3 history)
    htf_file = fetched.get("htf") or fetched.get("itf")
    ltf_file = fetched.get("ltf") or fetched.get("itf") or fetched.get("htf")
    itf_file = fetched.get("itf")
    dtf_file = fetched.get("dtf")

    if not htf_file or not os.path.exists(htf_file):
        return {"error": f"Could not find HTF data file for {symbol}"}
    if not ltf_file or not os.path.exists(ltf_file):
        return {"error": f"Could not find LTF data file for {symbol}"}

    # 2. Confluence (Layer 1 & 2)
    structure_json = run_confluence_analysis(
        htf_file, ltf_file, itf_csv=itf_file, dtf_csv=dtf_file)
    if not structure_json: return {"error": "Confluence analysis failed."}

    # 3. History (Layer 3)
    history_json = run_historical_analysis(htf_file, htf_file, symbol=symbol)
    if not history_json: return {"error": "Historical analysis failed."}

    # 4. News (Layer 4)
    if no_news:
        news_json = {
            "risk_level": "LOW", "sentiment_score": 0.0,
            "risk_state": "NORMAL", "final_penalty": 0,
            "permits_trade": True, "layer4_score": 5.0,
            "flagged_keywords": [],
            "reasoning": f"News Analysis Skipped (Stack: {stack_label})"
        }
    elif custom_news:
        news_json = run_news_analysis([
            {"text": t, "source_type": "AGGREGATOR",
             "domain": "passed_text", "timestamp": str(datetime.now())}
            for t in custom_news
        ])
    else:
        news_json = run_news_analysis(run_scraper())

    if not news_json or "error" in news_json:
        return {"error": "News analysis failed."}

    # Phase 8.6: Funding Rate
    signal_bias = structure_json.get("final_signal", "WAIT / NO_TRADE")
    funding = analyze_funding(symbol, signal_bias)
    if funding.get("funding_available"):
        news_json["layer4_score"] = round(
            max(0, news_json.get("layer4_score", 5.0) + funding["funding_modifier"]), 2)
        news_json["funding"] = funding

    # Phase 10.7: CME Gap
    try:
        cme = analyze_cme_gaps(symbol, structure_json.get("current_price"))
        if cme.get("cme_available") and cme.get("nearest_gap"):
            news_json["layer4_score"] = round(
                max(0, news_json.get("layer4_score", 5.0) + cme["cme_modifier"]), 2)
            news_json["cme_gap"] = cme
    except Exception:
        pass

    # Phase 10.8: Open Interest
    try:
        oi = analyze_oi(symbol, signal_bias)
        if oi.get("oi_available") and oi.get("oi_regime") not in ("N/A", "UNAVAILABLE", "ERROR"):
            news_json["layer4_score"] = round(
                max(0, news_json.get("layer4_score", 5.0) + oi["oi_modifier"]), 2)
            news_json["oi_data"] = oi
    except Exception:
        pass

    # Phase 10.9: Macro / DXY Correlation
    try:
        macro = analyze_macro(symbol, signal_bias)
        if macro.get("macro_available"):
            news_json["layer4_score"] = round(
                max(0, news_json.get("layer4_score", 5.0) + macro["macro_modifier"]), 2)
            news_json["macro"] = macro
    except Exception:
        pass

    # Phase 10.10: Options Max Pain / PCR (BTC/ETH only)
    try:
        current_px = structure_json.get("current_price")
        options = analyze_options(symbol, current_price=current_px, signal_bias=signal_bias)
        if options.get("options_available") and options.get("options_modifier") != 0:
            news_json["layer4_score"] = round(
                max(0, news_json.get("layer4_score", 5.0) + options["options_modifier"]), 2)
        if options.get("options_available"):
            news_json["options"] = options
    except Exception:
        pass

    # Phase 10.11: Seasonality Edge
    # B1 Fix: Modifier is now signed (±3) in historical_engine.
    # Apply it directly — no alignment check needed. Adverse seasonality now penalizes score.
    try:
        seasonality = calculate_seasonality_stats(symbol=symbol)
        if seasonality.get("seasonality_available"):
            s_modifier = seasonality["seasonality_modifier"]  # +3, -3, or 0
            if s_modifier != 0:
                news_json["layer4_score"] = round(
                    max(0, news_json.get("layer4_score", 5.0) + s_modifier), 2)
            news_json["seasonality"] = seasonality
    except Exception:
        pass

    # 5. Report (Layer 5 + Risk)
    report = generate_report(symbol, structure_json, history_json, news_json)
    
    # Phase 12.3: Generate LLM text explanation if requested
    if use_nlp and report and "error" not in report:
        report["NLP_SUMMARY"] = generate_nlp_summary(report, symbol)
        
    return report


def main():
    parser = argparse.ArgumentParser(
        description='Super Signals v2.1 — Multi-Timeframe Orchestrator')
    parser.add_argument('--symbol',   type=str, default='BTC/USD',
                        help='Asset to analyse (e.g. BTC/USD, XAU/USD)')
    parser.add_argument('--stack',    type=str, choices=VALID_STACKS, default='intraday',
                        help=f'TF stack: {", ".join(VALID_STACKS)} (default: intraday)')
    parser.add_argument('--htf',      type=str, help='Raw HTF override (e.g. 4h)')
    parser.add_argument('--ltf',      type=str, help='Raw LTF override (e.g. 15m)')
    parser.add_argument('--itf',      type=str, help='Raw ITF override (e.g. 1h)')
    parser.add_argument('--dtf',      type=str, help='Raw DTF override (e.g. 1d)')
    parser.add_argument('--no_news',  action='store_true', help='Skip news analysis')
    parser.add_argument('--news',     type=str, nargs='+', help='Custom news headlines')
    parser.add_argument('--json_only',action='store_true', help='Output raw JSON only')
    parser.add_argument('--nlp',      action='store_true', help='Generate text summary via Groq LLM')
    args = parser.parse_args()

    if not args.json_only:
        print(f"Running Super Signals LIVE v2.0 Analysis for {args.symbol}...")

    final_report = run_full_analysis(
        args.symbol, args.stack, args.htf, args.ltf,
        args.itf, args.dtf, args.no_news, args.news, args.nlp)

    if not final_report or "error" in final_report:
        print(f"Analysis Failed: {final_report.get('error', 'Unknown')}", file=sys.stderr)
        sys.exit(1)

    if args.json_only:
        print(json.dumps(final_report))
        return

    sig     = final_report.get("FINAL_SIGNAL")
    conf    = final_report.get("CONFIDENCE")
    risk    = final_report.get("RISK_ADVISORY", {}) or {}
    reasons = final_report.get("REASONING", {})
    alerts  = final_report.get("GOVERNANCE_ALERTS", [])

    print("\n" + "="*45)
    print("=== SUPER SIGNALS v2.0 LIVE REPORT ===")
    print(f"Symbol: {args.symbol} | {final_report.get('TIMESTAMP', '')[:19]}")
    print("-" * 45)
    print(f" SIGNAL:      {sig} ({conf}/100 Conf)")

    if alerts:
        print("\n [!] GOVERNANCE ALERTS:")
        for alert in alerts:
            print(f"     {alert}")

    if risk and risk.get("ENTRY_PRICE"):
        print("\n [!] TRADE SETUP:")
        print(f"     ENTRY:       {risk.get('ENTRY_TYPE')} @ {risk.get('ENTRY_PRICE')}")
        print(f"     STOP LOSS:   {risk.get('STOP_LOSS')} — Risk ${risk.get('RISK_AMOUNT_USD')} ({risk.get('RISK_PER_TRADE_PCT')}% of ${risk.get('ACCOUNT_BALANCE')} acct)")
        tps      = risk.get('TAKE_PROFIT', [])
        tp_usd   = risk.get('TP_PROFIT_USD', [])
        tp_rr    = risk.get('TP_RR_ACTUAL', [])
        for i, (tp, usd, rr) in enumerate(zip(tps, tp_usd, tp_rr), 1):
            print(f"     TP{i}:         {tp} — +${usd} profit ({rr}x R)")
        if risk.get('POSITION_SIZE_UNITS'):
            print(f"     POSITION:    {risk.get('POSITION_SIZE_UNITS')} units (${risk.get('POSITION_SIZE_USD')} notional)")
        rr = risk.get("RR_RATIO")
        rr_str = f"PROJECTED R:R: {rr}:1 [{risk.get('RR_GATE')}]" if rr else ""
        if rr_str: print(f"     {rr_str}")

    print("-" * 45)
    print("--- LAYER-WISE REASONING ---")
    print(f" [L1/L2] {reasons.get('l2_confluence')}")
    print(f" [L3]    {reasons.get('l3_history')}")
    print(f" [L4]    {reasons.get('l4_news')}")
    
    if final_report.get("NLP_SUMMARY"):
        print("-" * 45)
        print("AI ANALYSIS:")
        print(f" {final_report.get('NLP_SUMMARY')}")
        
    print("="*45 + "\n")


if __name__ == "__main__":
    main()
