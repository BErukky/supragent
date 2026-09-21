import sys
import os
import time
import threading

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'execution'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import market_scanner as ms
from main import run_full_analysis

errors = []
logs = []

def run_scan():
    t0 = time.time()
    try:
        ms.main(stack='scalp', no_news=True)
        t1 = time.time()
        logs.append(f"SCAN_3_WORKERS_DURATION: {t1-t0:.2f}s")
    except Exception as e:
        errors.append(f"scan_error: {e}")

def run_analyze(sym):
    t0 = time.time()
    try:
        rep = run_full_analysis(sym, stack_name='intraday', no_news=True)
        l3_source = rep.get("LAYER_3_HISTORICAL", {}).get("history_source", "N/A") if rep else "N/A"
        logs.append(f"ANALYZE_{sym.replace('/', '_')}_DONE in {time.time()-t0:.2f}s (L3 source: {l3_source})")
    except Exception as e:
        errors.append(f"analyze_{sym}_error: {e}")

if __name__ == "__main__":
    t_start = time.time()
    threads = [
        threading.Thread(target=run_scan, name="ScanWorker"),
        threading.Thread(target=run_analyze, args=('BTC/USD',), name="AnalyzeBTC"),
        threading.Thread(target=run_analyze, args=('ETH/USD',), name="AnalyzeETH"),
        threading.Thread(target=run_analyze, args=('SOL/USD',), name="AnalyzeSOL"),
    ]

    print("="*60)
    print(">>> STARTING CONCURRENT STRESS TEST:")
    print("    - 1 parallel /scan (3 workers across 10 assets)")
    print("    - 3 simultaneous /analyze commands (BTC/USD, ETH/USD, SOL/USD)")
    print("="*60 + "\n")

    for t in threads:
        t.start()

    for t in threads:
        t.join()

    print("\n" + "="*60)
    print(f"CONCURRENT STRESS TEST FINISHED IN {time.time()-t_start:.2f}s")
    print("="*60)
    for l in logs:
        print(" ", l)
    if errors:
        print("ERRORS ENCOUNTERED:", errors)
    else:
        print("SUCCESS: Zero unhandled errors across all concurrent threads.")
    print("="*60)
