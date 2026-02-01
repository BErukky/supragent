# Directive: Analyze News & Narrative Risk

## Goal

Implement Layer 4 intelligence: Assess market risk based on news sentiment and narrative keywords.

## Inputs

- `headlines`: List of text strings (headlines) or a JSON file containing news items.
- `keywords_db`: Dictionary of keywords with associated risk scores/weights.

## Tools / Scripts

- `execution/news_engine.py`

## Outputs

- Console Output / JSON:
  ```json
  {
    "risk_level": "HIGH",
    "sentiment_score": -0.8,
    "permits_trade": false,
    "flagged_keywords": ["SEC lawsuit", "hack"]
  }
  ```

## Logic (Keyword Scoring)

1.  **Sentiment Scoring**: Simple lexicon-based finding (e.g. "hack", "ban", "lawsuit" = Negative; "ETF approval", "partnership" = Positive).
2.  **Risk Flagging**: If a "CRITICAL" keyword (e.g. "insolvency") is found in the last 24h, set `permits_trade = false`.
3.  **Narrative Weight**:
    - If Sentiment is strongly NEGATIVE -> Bias for SHORT trades increases.
    - If Sentiment is strongly POSITIVE -> Bias for LONG trades increases.

## Data Source

- Since we don't have a paid News API, the script will accept a JSON file input (which can be populated manually or by a separate scraper in future).
