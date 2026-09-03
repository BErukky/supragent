import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from execution.nlp_engine import parse_report_to_prompt


def test_wait_no_trade_prompt_explicitly_forbids_invented_metrics_when_no_levels():
    report = {
        "FINAL_SIGNAL": "WAIT / NO_TRADE (Structural Floor)",
        "CONFIDENCE": 0.0,
        "RISK_ADVISORY": {},
        "GOVERNANCE_ALERTS": ["No actionable setup"],
        "REASONING": {
            "l2_confluence": "Trend Coherence: 95.0%. HTF(NEUTRAL) 4H(BULLISH) LTF(NEUTRAL)",
            "l3_history": "Probabilistic Similarity: 25.3%. Result: BULLISH",
            "l4_news": "News Analysis Skipped"
        }
    }

    prompt = parse_report_to_prompt(report, "ETH/USD")

    assert "Do not invent, assume, or estimate any figure" in prompt
    assert "Entry: not provided" in prompt
    assert "Stop Loss: not provided" in prompt
    assert "Take Profit 1: not provided" in prompt
    assert "Risk/Reward Ratio: not provided" in prompt
    assert "Pending Limit Order Details:" not in prompt


def test_wait_no_trade_prompt_includes_calculated_reference_levels():
    report = {
        "FINAL_SIGNAL": "WAIT / NO_TRADE",
        "CONFIDENCE": 58.26,
        "RISK_ADVISORY": {
            "ENTRY_PRICE": 0.206595,
            "ENTRY_TYPE": "MARKET",
            "STOP_LOSS": 0.209003,
            "TAKE_PROFIT": [0.199372, 0.19215, 0.18252],
            "TP_RR_ACTUAL": [3.0, 6.0, 10.0]
        },
        "GOVERNANCE_ALERTS": ["[!] HIST: High instability detected."],
        "REASONING": {
            "l2_confluence": "Trend Coherence: 92.0%. HTF(NEUTRAL) 4H(BULLISH) LTF(NEUTRAL)",
            "l3_history": "Probabilistic Similarity: 20.6%. Result: BULLISH",
            "l4_news": "News Analysis Skipped"
        }
    }
    prompt = parse_report_to_prompt(report, "ADA/USD")

    assert "Calculated Trade Setup (Reference Levels):" in prompt
    assert "0.206595" in prompt
    assert "0.209003" in prompt
    assert "0.199372 | 0.19215 | 0.18252" in prompt
    assert "Do NOT claim that no entry, SL, or TP levels exist" in prompt
    assert "Do not invent, assume, or estimate any figure" in prompt


def test_wait_locked_prompt_omits_levels():
    report = {
        "FINAL_SIGNAL": "WAIT / LOCKED (CRITICAL NEWS)",
        "CONFIDENCE": 0.0,
        "RISK_ADVISORY": {},
        "GOVERNANCE_ALERTS": ["[!] NEWS: Risk Penalty 100 applied."],
        "REASONING": {
            "l2_confluence": "Trend Coherence: 80.0%",
            "l3_history": "Probabilistic Similarity: 40.0%",
            "l4_news": "Critical exploit detected"
        }
    }

    prompt = parse_report_to_prompt(report, "SOL/USD")

    assert "Entry: not provided (Trade Locked)" in prompt
    assert "Stop Loss: not provided" in prompt
    assert "For WAIT / LOCKED decisions" in prompt
    assert "No trade setup (Entry, Stop Loss, Take Profit) is provided" in prompt
    assert "Calculated Trade Setup" not in prompt
