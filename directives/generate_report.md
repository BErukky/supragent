# Directive: Generate Analysis Report

## Goal

Implement Layer 5 intelligence: Synthesize Structure, History, and News data into a final probability score and trade bias.

## Inputs

- `structure_json`: Output from `confluence_engine.py` (Layer 1 & 2).
- `history_json`: Output from `historical_engine.py` (Layer 3).
- `news_json`: Output from `news_engine.py` (Layer 4).

## Tools / Scripts

- `execution/report_engine.py`

## Outputs

- **Final Report** (Text/JSON printed to console).
- Format:
  ```json
  {
    "TIMESTAMP": "...",
    "FINAL_BIAS": "LONG_BIAS",
    "CONFIDENCE_SCORE": 85,
    "RISK_LEVEL": "LOW",
    "COMPONENTS": {
      "Structure": "BULLISH (High Conf)",
      "History": "BULLISH (Avg Return +2.3%)",
      "News": "NEUTRAL (Score -2)"
    },
    "ACTION": "MONITOR_FOR_ENTRY"
  }
  ```

## Scoring Logic (0-100)

1.  **Base Score**: 50.
2.  **Structure Weight (Max +/- 30)**:
    - Confluence (HTF=LTF=Bullish) -> +30
    - HTF Bullish / LTF Range -> +15
    - Conflict -> 0 (Reset to Neutral)
3.  **History Weight (Max +/- 10)**:
    - Historical Bias matches Structure -> +10
    - Historical Bias conflicts -> -10
4.  **News Weight (Max +/- 10)**:
    - Critical Risk -> **FORCE NO_TRADE** (Score = 0).
    - Positive Sentiment -> +10.
    - Negative Sentiment -> -10.

## Thresholds

- **Score > 75**: HIGH CONFIDENCE (Trade Allowed).
- **Score < 25**: HIGH CONFIDENCE BEARISH (Trade Allowed).
- **Score 40-60**: RANGE / NO TRADE.
