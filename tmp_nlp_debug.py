import os
import sys

sys.path.insert(0, os.getcwd())
sys.path.insert(0, os.path.join(os.getcwd(), 'execution'))

from main import run_full_analysis
from execution.nlp_engine import parse_report_to_prompt, generate_nlp_summary

symbol = 'ETH/USD'
report = run_full_analysis(symbol, stack_name='intraday', no_news=True, use_nlp=False)
print('SIGNAL:', report.get('FINAL_SIGNAL'))
print('CONFIDENCE:', report.get('CONFIDENCE'))
print('RISK_ENTRY:', report.get('RISK_ADVISORY', {}).get('ENTRY_PRICE'))
print('PROMPT_START')
print(parse_report_to_prompt(report, symbol))
print('PROMPT_END')
print('SUMMARY_START')
print(generate_nlp_summary(report, symbol))
print('SUMMARY_END')
