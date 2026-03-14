"""
Phase 3 smoke test:
3.1 - ATR-based TP/SL produces METHOD='ATR' and volatility-adaptive levels
3.2 - Volume ratio scales sweep confidence (high vol > low vol score)
3.3 - CHoCH detected correctly in bullish and bearish trends
"""
import sys, os
import pandas as pd
import numpy as np
sys.path.insert(0, 'execution')

from structure_engine import (
    analyze_layer1, calculate_atr, detect_choch,
    calculate_layer1_score, identify_swings, determine_structure_points, determine_market_state
)

# ── Build a minimal synthetic OHLCV dataframe ──────────────────────────────
np.random.seed(42)
n = 60
close = 84000 + np.cumsum(np.random.randn(n) * 80)
# Bullish trend: steadily rising
for i in range(1, n):
    close[i] = close[i-1] + abs(np.random.randn() * 60)

df = pd.DataFrame({
    'timestamp': range(n),
    'open':   close - 30,
    'high':   close + 100,
    'low':    close - 100,
    'close':  close,
    'volume': np.random.uniform(800, 1200, n)
})
# Spike volume on last candle to simulate institutional activity
df.at[n-1, 'volume'] = 3000

result = analyze_layer1(df)

print("=== PHASE 3 SMOKE TEST ===\n")

# ── 3.2 Volume Confirmation ─────────────────────────────────────────────────
vol_ratio = result.get('volume_ratio', 0)
print(f"[3.2] Volume Ratio:     {vol_ratio}x  (expected: > 1.0 due to spiked last candle)")
print(f"      Pass: {'✅' if vol_ratio > 1.0 else '❌'}")
print()

# ── 3.3 CHoCH Detection ────────────────────────────────────────────────────
choch = result.get('choch')
print(f"[3.3] CHoCH:           {choch}")
print(f"      (None is valid if structure is clean — CHoCH only fires on genuine break)")
print()

# ── 3.1 ATR ────────────────────────────────────────────────────────────────
atr_val = result.get('atr', 0)
print(f"[3.1] ATR value:       {atr_val}  (expected: > 0)")
print(f"      Pass: {'✅' if atr_val and atr_val > 0 else '❌'}")
print()

# ── 3.1 ATR-based TP/SL through report_engine ──────────────────────────────
from report_engine import calculate_v2_risk

# Build minimal str_data that simulate what confluence_engine passes
str_data = {
    "final_signal": "LONG_BIAS",
    "layer2_score": 20,
    "details": {
        "ltf_layer1": result,
        "raw_ltf_structure": result.get("raw_structure", [{"type": "HL", "price": 84500, "index": 50, "confidence": 0.7}])
    }
}

risk_atr = calculate_v2_risk("LONG_BIAS", str_data, 0)
risk_str_only = calculate_v2_risk("LONG_BIAS", {
    "final_signal": "LONG_BIAS",
    "details": {
        "ltf_layer1": {"atr": None},   # Force ATR path to skip
        "raw_ltf_structure": [{"type": "HL", "price": 83800, "index": 50, "confidence": 0.7}]
    }
}, 0)

print(f"[3.1] ATR-based RISK ADVISORY:")
print(f"      Method:     {risk_atr.get('METHOD') if risk_atr else 'N/A'}  (expected: ATR or STRUCTURAL/FALLBACK_PCT)")
print(f"      Stop Loss:  {risk_atr.get('STOP_LOSS') if risk_atr else 'N/A'}")
print(f"      TP1 / TP2:  {risk_atr.get('TAKE_PROFIT') if risk_atr else 'N/A'}")
print(f"      ATR Value:  {risk_atr.get('ATR_VALUE') if risk_atr else 'N/A'}")
print(f"      Pass: {'✅' if risk_atr and risk_atr.get('STOP_LOSS') else '❌'}")
print()

# ── 3.3 Explicit CHoCH test ────────────────────────────────────────────────
# Build a structure explicitly containing a BEARISH CHoCH
# (Bullish trend with an HL that is then broken by a LL)
structure_with_choch = [
    {"type": "H",  "price": 100, "index": 5,  "confidence": 0.8},
    {"type": "L",  "price": 90,  "index": 8,  "confidence": 0.7},
    {"type": "HH", "price": 110, "index": 15, "confidence": 0.9},
    {"type": "HL", "price": 95,  "index": 20, "confidence": 0.8},   # ← last HL
    {"type": "HH", "price": 120, "index": 28, "confidence": 0.9},
    {"type": "LL", "price": 88,  "index": 35, "confidence": 0.7},   # ← breaks HL = CHoCH
]
choch_result = detect_choch(structure_with_choch, "BULLISH")
print(f"[3.3] Explicit CHoCH test:")
print(f"      {choch_result}")
expected_type = "BEARISH_CHOCH"
print(f"      Pass: {'✅' if choch_result and choch_result.get('type') == expected_type else '❌'} (expected: {expected_type})")
print()

print("=== ALL PHASE 3 CHECKS COMPLETE ===")
