import sys
sys.path.insert(0, 'execution')
from report_engine import calculate_v2_risk

# Simulate what confluence_engine actually passes to report_engine:
# details.ltf_layer1.atr is populated by structure_engine.analyze_layer1
str_data = {
    'final_signal': 'LONG_BIAS',
    'details': {
        'ltf_layer1': {'atr': 205.0, 'choch': None},
        'raw_ltf_structure': [
            {'type': 'HL', 'price': 83800.0, 'index': 45, 'confidence': 0.8},
            {'type': 'HH', 'price': 84900.0, 'index': 55, 'confidence': 0.9}
        ]
    }
}

# 10% news penalty = risk_multi 0.95
risk = calculate_v2_risk('LONG_BIAS', str_data, 10)
last_p = 84900.0  # last structure point price
atr    = 205.0
multi  = 1.0 - (10 / 200.0)  # = 0.95

print('=== 3.1 ATR TP/SL Verification ===\n')
print(f'  Method     : {risk["METHOD"]}  (expected: ATR)')
print(f'  ATR Value  : {risk["ATR_VALUE"]}  (expected: 205.0)')
print(f'  Stop Loss  : {risk["STOP_LOSS"]}  (expected: {round(last_p - 1.5 * atr, 2)})')
print(f'  TP1        : {risk["TAKE_PROFIT"][0]}  (expected: {round(last_p + 1.0 * atr * multi, 2)})')
print(f'  TP2        : {risk["TAKE_PROFIT"][1]}  (expected: {round(last_p + 2.0 * atr * multi, 2)})')
print(f'  Risk Multi : {risk["RISK_OFFSET"]}  (expected: {multi})')

ok = (
    risk['METHOD'] == 'ATR' and
    risk['ATR_VALUE'] == 205.0 and
    risk['STOP_LOSS'] == round(last_p - 1.5 * atr, 2)
)
print()
print('  Pass: ✅ ATR method working correctly' if ok else '  FAIL ❌')
