import argparse
import json
import sys
import math
from datetime import datetime, timedelta

# CARI: Context-Aware Risk Intelligence
# Source Reliability Weights
SOURCES = {
    "OFFICIAL": 1.0,     # @Ethereum, @SolanaConf, etc.
    "TIER_1": 0.8,       # Bloomberg, Blockworks, Reuters
    "AGGREGATOR": 0.4,   # CryptoPanic, NewsBots
    "SIGNAL_BOT": 0.1    # Unverified private signal bots
}

# Scope Intelligence Weights
SCOPE_WEIGHTS = {
    "protocol": 1.0,     # Layer 1/2 chain halt, consensus bug
    "infrastructure": 0.7, # Bridges, RPC providers, Wallets
    "application": 0.3,   # dApp exploit (UniSwap, Aave), phishing
    "unknown": 0.5
}

# Base Risk Keywords
KEYWORDS = {
    "CRITICAL": ["hack", "exploit", "halt", "locked", "insolvent", "bankruptcy", "vulnerability"],
    "NEGATIVE": ["inflation", "lawsuit", "dump", "bearish", "ban"],
    "POSITIVE": ["etf", "partnership", "adoption", "bullish", "ath", "breakout"]
}

def classify_scope(headline):
    headline = headline.lower()
    # Protocol level triggers
    if any(x in headline for x in ["mainnet", "chain", "consensus", "validator", "halting", "fork"]):
        return "protocol"
    # Infrastructure triggers
    if any(x in headline for x in ["bridge", "rpc", "wallet", "ledger", "metamask", "custody"]):
        return "infrastructure"
    # Application triggers
    if any(x in headline for x in ["dapp", "dex", "swap", "protocol", "dao", "yield"]):
        # Note: "protocol" can be ambiguous, default to application if it looks like a dApp
        if any(x in headline for x in ["hack", "exploit"]): return "application"
    return "unknown"

def calculate_decay(news_time_str, lam=0.1):
    try:
        news_time = datetime.fromisoformat(news_time_str)
        now = datetime.now()
        hours_passed = (now - news_time).total_seconds() / 3600.0
        return math.exp(-lam * hours_passed)
    except:
        return 1.0 # No decay if timestamp missing

def analyze_news_cari(news_items):
    """
    CARI Analysis:
    FinalPenalty = BasePenalty * SourceTrust * ScopeWeight * Decay * Consensus
    """
    results = []
    total_weighted_penalty = 0
    domains = set()

    for item in news_items:
        headline = item.get("text", "").lower()
        source_type = item.get("source_type", "AGGREGATOR")
        source_domain = item.get("domain", "unknown.com")
        news_time = item.get("timestamp", str(datetime.now()))
        
        # 1. Base Penalty Detection
        base_penalty = 0
        if any(w in headline for w in KEYWORDS["CRITICAL"]): base_penalty = 90
        elif any(w in headline for w in KEYWORDS["NEGATIVE"]): base_penalty = 30
        
        if base_penalty == 0: continue

        # 2. Source Trust
        trust = SOURCES.get(source_type, 0.4)
        
        # 3. Scope Intelligence
        scope = classify_scope(headline)
        scope_weight = SCOPE_WEIGHTS.get(scope, 0.5)
        
        # 4. Temporal Decay
        decay = calculate_decay(news_time)
        
        # 5. Independent Domain Logging
        domains.add(source_domain)
        
        # Item Penalty
        item_penalty = base_penalty * trust * scope_weight * decay
        total_weighted_penalty += item_penalty
        
        results.append({
            "headline": headline[:50] + "...",
            "scope": scope,
            "impact": round(item_penalty, 2),
            "decay": round(decay, 2)
        })

    # 6. Consensus Bonus (Boost based on independent domains)
    consensus_bonus = min(0.5, 0.15 * (len(domains) - 1)) if len(domains) > 1 else 0
    final_penalty = total_weighted_penalty * (1 + consensus_bonus)
    
    # 7. 3-State Logic
    risk_state = "NORMAL"
    if final_penalty >= 75: 
        risk_state = "CRITICAL"
    elif final_penalty >= 35: 
        risk_state = "CAUTION"
    elif final_penalty >= 15 and len(domains) < 2 and SOURCES.get(news_items[0].get("source_type", "AGGREGATOR"), 0.4) < 0.5:
        # Only trigger WAIT_VERIFICATION if the penalty is significant enough (>= 15)
        risk_state = "WAIT_VERIFICATION"

    return {
        "risk_state": risk_state,
        "final_penalty": round(min(100, final_penalty), 2),
        "consensus_count": len(domains),
        "permits_trade": risk_state != "CRITICAL",
        "details": results,
        "layer4_score": round(max(0, 10 - (final_penalty / 10.0)), 2),
        "reasoning": f"Risk: {risk_state}. Penalty: {round(final_penalty, 1)}. Consensus: {len(domains)} (Domains: {', '.join(list(domains)[:3])})"
    }

def run_news_analysis(news_items):
    """
    Direct functional entry point for the orchestrator.
    """
    try:
        if not news_items:
            return {"error": "No news items provided"}
        return analyze_news_cari(news_items)
    except Exception as e:
        return {"error": str(e)}

def main():
    parser = argparse.ArgumentParser(description='CARI News Engine.')
    parser.add_argument('--input', type=str, help='JSON file with news items [{text, source_type, domain, timestamp}]')
    parser.add_argument('--text', type=str, nargs='+', help='Direct headline input (Legacy/Technical)')
    args = parser.parse_args()
    
    news_items = []
    
    if args.input:
        try:
            with open(args.input, 'r') as f:
                news_items = json.load(f)
        except Exception as e:
            print(json.dumps({"error": f"Failed to load input file: {e}"}))
            sys.exit(1)
    
    if args.text:
        # Convert raw text to structured CARI format with default/safe values
        for txt in args.text:
            news_items.append({
                "text": txt,
                "source_type": "AGGREGATOR",
                "domain": "passed_text",
                "timestamp": str(datetime.now())
            })
            
    result = run_news_analysis(news_items)
    if "error" in result:
        print(json.dumps(result))
        sys.exit(1)
    else:
        print(json.dumps(result, indent=2))

if __name__ == "__main__":
    main()
