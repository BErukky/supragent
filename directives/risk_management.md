# Directive: Risk Management (TP/SL)

## Goal

Enhance the final report with specific Take Profit (TP) and Stop Loss (SL) price levels based on market structure.

## Inputs

- `structure_points`: List of recent HH, HL, LL, LH, with prices.
- `current_bias`: LONG or SHORT.
- `current_price`: Close price of the last candle.

## Tools / Scripts

- `execution/report_engine.py` (Extended)

## Logic

1.  **Stop Loss (Invalidation)**:
    - **LONG**: Find the most recent _Swing Low_ (HL or LL) from the structure list. Set SL slightly below it (e.g. 0.5% buffer or ATR based, simplifed to absolute price for now).
    - **SHORT**: Find the most recent _Swing High_ (HH or LH). Set SL slightly above it.

2.  **Take Profit (Targets)**:
    - **LONG**: Find the most recent _Swing High_ above current price. If none, project a 1.5R distance.
    - **SHORT**: Find the most recent _Swing Low_ below current price. If none, project a 1.5R distance.

## Outputs

Added to Final Report JSON:

```json
"RISK_ADVISORY": {
  "STOP_LOSS": 42100.0,
  "TP_TARGETS": [43500.0, 44200.0],
  "RISK_REWARD_RATIO": 2.5
}
```
