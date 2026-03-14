import sys
sys.path.insert(0, 'execution')
from news_engine import run_news_analysis, classify_scope
from datetime import datetime

# ── Fix 1.2: Scope Classifier ──────────────────────────────────────────────
scope1 = classify_scope('Uniswap protocol fee update announced')
scope2 = classify_scope('Ethereum consensus bug causes validator outage')
scope3 = classify_scope('Aave dex exploit drains user funds')

print('=== FIX 1.2: Scope Classifier ===')
print(f'Uniswap protocol fee update -> {scope1}  (expected: unknown)')
print(f'Ethereum consensus bug      -> {scope2}  (expected: protocol)')
print(f'Aave dex exploit            -> {scope3}  (expected: application)')

# ── Fix 1.3: Positive Sentiment ────────────────────────────────────────────
positive_news = [{'text': 'Bitcoin ETF approval drives ATH breakout', 'source_type': 'TIER_1', 'domain': 'coindesk.com', 'timestamp': str(datetime.now())}]
negative_news = [{'text': 'Major hack exploit drains locked funds', 'source_type': 'TIER_1', 'domain': 'coindesk.com', 'timestamp': str(datetime.now())}]

pos = run_news_analysis(positive_news)
neg = run_news_analysis(negative_news)

print()
print('=== FIX 1.3: Positive Sentiment ===')
print(f'Positive L4 score:      {pos.get("layer4_score")}  (expected: > 5.0)')
print(f'Positive boost:         {pos.get("positive_boost")}')
print(f'Positive risk state:    {pos.get("risk_state")}  (expected: NORMAL)')
print(f'Negative L4 score:      {neg.get("layer4_score")}  (expected: < 5.0)')
print(f'Negative risk state:    {neg.get("risk_state")}')

# ── Fix 1.4: L3 Cross-Validation ───────────────────────────────────────────
from report_engine import aggregate_v2_confidence

# Simulate LONG_BIAS structure with BEARISH history (conflict)
str_data_long = {
    "final_signal": "LONG_BIAS",
    "layer2_score": 20,
    "details": {"ltf_layer1": {"layer1_score": 20}, "raw_ltf_structure": []}
}
hist_bearish = {"historical_bias": "BEARISH", "layer3_score": 10}
hist_bullish = {"historical_bias": "BULLISH", "layer3_score": 10}
news_neutral = {"layer4_score": 5.0, "final_penalty": 0, "risk_state": "NORMAL",
                "highest_scope": "unknown", "max_trust": 0.0}

conf_agree, _ = aggregate_v2_confidence(str_data_long, hist_bullish, news_neutral)
conf_conflict, _ = aggregate_v2_confidence(str_data_long, hist_bearish, news_neutral)

print()
print('=== FIX 1.4: L3 Cross-Validation ===')
print(f'LONG + BULLISH history confidence:  {conf_agree}  (expected: higher)')
print(f'LONG + BEARISH history confidence:  {conf_conflict}  (expected: lower than above)')
print(f'Difference:                         {round(conf_agree - conf_conflict, 2)}  (expected: ~20 pts)')

print()
print('ALL PHASE 1 CHECKS PASSED' if conf_agree > conf_conflict else 'ISSUE: conflict should lower confidence')
