import os
import sys
import traceback

sys.path.insert(0, os.getcwd())
sys.path.insert(0, os.path.join(os.getcwd(), 'execution'))

from main import run_full_analysis
from execution.market_scanner import ASSETS

for symbol in ASSETS:
    try:
        report = run_full_analysis(symbol, stack_name='intraday', no_news=True, use_nlp=False)
    except Exception as exc:
        print(f'{symbol}: ERROR {exc}')
        traceback.print_exc()
        continue

    conf = report.get('CONFIDENCE', 0)
    signal = report.get('FINAL_SIGNAL', 'WAIT / NO_TRADE')
    is_blocked = 'WAIT / NO_TRADE' in signal or 'CRITICAL' in signal
    gate = 'PASS' if conf >= 70 and not is_blocked else 'FAIL'
    reasoning = report.get('REASONING', {}) or {}
    l2 = reasoning.get('l2_confluence', '')
    l3 = reasoning.get('l3_history', '')
    l4 = reasoning.get('l4_news', '')
    print(f'{symbol}: confidence={conf}, signal={signal}, gate={gate}, blocked={is_blocked}, l2={l2[:160]!r}, l3={l3[:160]!r}, l4={l4[:160]!r}')
