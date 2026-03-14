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

# FIX 1.2: Explicit whitelist of L1/L2 chains for protocol-level detection.
# Previously 'protocol' the English word triggered the same code path as
# 'protocol' the chain-level severity — causing DeFi app news to be misclassified.
PROTOCOL_CHAINS = [
    "bitcoin", "ethereum", "solana", "avalanche", "polygon",
    "btc", "eth", "sol", "xrp", "bnb", "ada", "dot",
    "consensus", "validator", "mainnet halt", "chain halt", "hard fork"
]

# Base Risk Keywords
KEYWORDS = {
    "CRITICAL": ["hack", "exploit", "halt", "locked", "insolvent", "bankruptcy", "vulnerability"],
    "NEGATIVE": ["inflation", "lawsuit", "dump", "bearish", "ban"],
    "POSITIVE": ["etf", "partnership", "adoption", "bullish", "ath", "breakout"]
}

def classify_scope(headline):
    headline = headline.lower()
    # FIX 1.2: Protocol level is only triggered when a known L1/L2 chain
    # is mentioned alongside a severity keyword. Previously the English word
    # 'protocol' (e.g. 'Uniswap protocol update') was matching the hard-lock path.
    severity_words = ["hack", "exploit", "halt", "bug", "vulnerability", "attack", "outage", "fork"]
    has_severity = any(w in headline for w in severity_words)
    if has_severity and any(chain in headline for chain in PROTOCOL_CHAINS):
        return "protocol"
    # Infrastructure triggers
    if any(x in headline for x in ["bridge", "rpc", "wallet", "ledger", "metamask", "custody"]):
        return "infrastructure"
    # Application triggers (dApp / DeFi)
    if any(x in headline for x in ["dapp", "dex", "swap", "dao", "yield", "defi", "uniswap", "aave", "compound"]):
        return "application"
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

    # FIX 1.3: Calculate positive sentiment score.
    # Previously KEYWORDS["POSITIVE"] was defined but never used — news could only
    # reduce confidence, never increase it. Now we compute a positive boost that
    # partially offsets the penalty and lifts the L4 score.
    positive_boost = 0
    for item in news_items:
        headline_pos = item.get("text", "").lower()
        if any(w in headline_pos for w in KEYWORDS["POSITIVE"]):
            trust = SOURCES.get(item.get("source_type", "AGGREGATOR"), 0.4)
            decay = calculate_decay(item.get("timestamp", str(datetime.now())))
            positive_boost += 10 * trust * decay

    # B2 Fix: Cap positive_boost to prevent deeply negative effective_penalty,
    # which would inflate final confidence above 100% via proportional scaling.
    positive_boost = min(30, positive_boost)

    # Effective penalty is reduced by positive sentiment (floor at 0)
    effective_penalty = max(0, final_penalty - positive_boost)
    
    # 7. 3-State Logic (uses effective_penalty which accounts for positive sentiment)
    risk_state = "NORMAL"
    if effective_penalty >= 75:
        risk_state = "CRITICAL"
    elif effective_penalty >= 35:
        risk_state = "CAUTION"
    elif effective_penalty >= 15 and len(domains) < 2 and SOURCES.get(news_items[0].get("source_type", "AGGREGATOR"), 0.4) < 0.5:
        risk_state = "WAIT_VERIFICATION"

    # 8. Metadata for Governance
    highest_scope = "unknown"
    max_trust = 0.0
    if results:
        scope_priority = {"protocol": 4, "infrastructure": 3, "application": 2, "unknown": 1}
        highest_scope = max([r['scope'] for r in results], key=lambda s: scope_priority.get(s, 0))
        trusted_items = [SOURCES.get(item.get("source_type", "AGGREGATOR"), 0.4) for item in news_items if any(w in item.get("text", "").lower() for w in KEYWORDS["CRITICAL"] + KEYWORDS["NEGATIVE"])]
        if trusted_items: max_trust = max(trusted_items)

    # L4 score: ranges 0-10.
    # FIX 1.3: Now symmetric — positive news can raise score above 5, negative lowers it.
    # Base is 5.0, effective_penalty pulls it down, positive_boost lifts it (max 10).
    l4_score = round(max(0, min(10, 5.0 + (positive_boost / 10.0) - (effective_penalty / 10.0))), 2)

    return {
        "risk_state": risk_state,
        "final_penalty": round(min(100, effective_penalty), 2),
        "positive_boost": round(positive_boost, 2),
        "consensus_count": len(domains),
        "permits_trade": risk_state != "CRITICAL",
        "highest_scope": highest_scope,
        "max_trust": max_trust,
        "details": results,
        "layer4_score": l4_score,
        "reasoning": f"Risk: {risk_state}. Penalty: {round(effective_penalty, 1)} (Positive Boost: {round(positive_boost, 1)}). Consensus: {len(domains)} (Domains: {', '.join(list(domains)[:3])})"
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
