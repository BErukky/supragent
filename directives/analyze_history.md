# Directive: Analyze Historical Similarity

## Goal

Implement Layer 3 intelligence: Identify statistically similar market conditions from the past to estimate current probability.

## Inputs

- `target_data`: CSV file of current market action (e.g. last 100 candles).
- `historical_db`: Large CSV buffer of historical data (e.g. past 1-2 years).

## Tools / Scripts

- `execution/historical_engine.py`

## Outputs

- Console Output / JSON:
  ```json
  {
    "pattern_match_score": 0.85,
    "similar_dates": ["2023-04-12", "2024-01-05"],
    "historical_outcome": "BULLISH",
    "avg_return_next_24h": "1.5%"
  }
  ```

## Logic (Pattern Matching)

1.  **Normalization**: Normalize the close prices (e.g. % change from start of window or z-score) to make patterns comparable across different price levels.
2.  **Search**: Compare the current window (e.g. last 50 candles) with sliding windows in the historical DB.
3.  **Distance Metric**: Use Euclidean Distance or Correlation Coefficient.
    - High Correlation (> 0.8) = Valid Match.
4.  **Outcome Analysis**: For the top 3-5 matches, look at what happened in the _next_ N candles.
    - If majority went UP -> Historical Bias = BULLISH.
    - If majority went DOWN -> Historical Bias = BEARISH.
