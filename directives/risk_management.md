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

## Governance States

1. **NORMAL**: No critical risks. Full execution based on structure.
2. **CAUTION**: Medium-risk/Unconfirmed alerts. Tighten SL/TP.
3. **WAIT_VERIFICATION**: Temporary state (30-90m) for unconfirmed low-trust signals. System holds while seeking consensus.
4. **CRITICAL / LOCKED**: Mandatory wait. No trades permitted until risk resolved or decays.

## Outputs
