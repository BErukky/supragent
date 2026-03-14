"""
Full end-to-end live data test — runs the complete 5-layer pipeline
on real market data and prints a detailed report showing all new Phase fields.
"""
import sys, os, json
# Resolve paths relative to project root regardless of where script is run from
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, 'execution'))
os.chdir(ROOT)  # ensure .tmp/ writes go to the right place

from main import run_full_analysis

SYMBOL = "BTC/USD"
print(f"\n{'='*60}")
print(f"  LIVE END-TO-END TEST — {SYMBOL}")
print(f"{'='*60}\n")

report = run_full_analysis(SYMBOL, htf='1h', ltf='15m', no_news=False)

if not report or "error" in report:
    print(f"Analysis failed: {report}")
    sys.exit(1)

# ── Core Signal ───────────────────────────────────────────────────────────────
print(f"SIGNAL     : {report['FINAL_SIGNAL']}")
print(f"CONFIDENCE : {report['CONFIDENCE']}/100\n")

# ── Risk Advisory (Phase 3.1 - ATR) ─────────────────────────────────────────
risk = report.get("RISK_ADVISORY") or {}
print(f"RISK ADVISORY:")
print(f"  Method     : {risk.get('METHOD', 'N/A')}")
print(f"  ATR Value  : {risk.get('ATR_VALUE', 'N/A')}")
print(f"  Stop Loss  : {risk.get('STOP_LOSS', 'N/A')}")
print(f"  Take Profit: {risk.get('TAKE_PROFIT', 'N/A')}")
print(f"  Risk Multi : {risk.get('RISK_OFFSET', 'N/A')}x\n")

# ── Governance Alerts (includes CHoCH 3.3) ───────────────────────────────────
alerts = report.get("GOVERNANCE_ALERTS", [])
if alerts:
    print("GOVERNANCE ALERTS:")
    for a in alerts:
        print(f"  {a}")
    print()
else:
    print("GOVERNANCE ALERTS: None\n")

# ── Layer Reasoning ──────────────────────────────────────────────────────────
reasons = report.get("REASONING", {})
print("LAYER REASONING:")
print(f"  [L1/L2] {reasons.get('l2_confluence')}")
print(f"  [L3]    {reasons.get('l3_history')}")
print(f"  [L4]    {reasons.get('l4_news')}")
print()

# ── Phase Features Summary ───────────────────────────────────────────────────
print("=" * 60)
print("  PHASE FEATURE VERIFICATION")
print("=" * 60)
method = risk.get('METHOD', 'MISSING')
print(f"  3.1 ATR TP/SL   : {'✅ ' + method if method != 'MISSING' else '❌ MISSING'}")
print(f"  1.4 L3 Source   : {reasons.get('l4_news', '')[:70]}")
choch_alert = next((a for a in alerts if 'CHOCH' in a), None)
print(f"  3.3 CHoCH Alert : {'✅ ' + choch_alert if choch_alert else '➖ No CHoCH (clean structure)'}")
print(f"  Timestamp       : {report.get('TIMESTAMP')}")
print("=" * 60)
