import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from execution.nlp_engine import parse_report_to_prompt


def test_wait_no_trade_prompt_explicitly_forbids_invented_metrics():
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
    assert "R:R ratio" in prompt
    assert "Entry: not provided" in prompt
    assert "Stop Loss: not provided" in prompt
    assert "Take Profit 1: not provided" in prompt
    assert "Risk/Reward Ratio: not provided" in prompt
    assert "Pending Limit Order Details:" not in prompt
    assert "Geometric R:R" not in prompt
