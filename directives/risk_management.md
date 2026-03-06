# Directive: Risk Management (TP/SL) v2.1

## Goal

Enhance the final report with specific Take Profit (TP) and Stop Loss (SL) price levels based on market structure with **v2.1 Reliability Fallbacks**.

## 1. Structural Logic (Primary)

1.  **Stop Loss (Invalidation)**:
    - **LONG**: Use a recent _Swing Low_ (HL or LL).
    - **SHORT**: Use a recent _Swing High_ (HH or LH).
2.  **Take Profit (Targets)**:
    - Distance is calculated based on Price - SL distance (Risk).
    - **TP1**: 1.0R (1x Risk).
    - **TP2**: 2.0R (2x Risk).

## 2. v2.1 Reliability Fallbacks (Secondary)

If the structural distance (Risk) is less than **0.3% of current price**, or the structure is unclear, the system must apply a mandatory buffer to prevent overlapping levels:

- **Stop Loss (SL)**: Entry ± 0.3%.
- **Take Profit 1 (TP1)**: Entry ± 0.6%.
- **Take Profit 2 (TP2)**: Entry ± 1.2%.

Direction follows the structural bias.

## 3. Governance Tightening

- **NORMAL**: Structural targets with 1.0x Risk Multiplier.
- **CAUTION**: News risk scales the `TP` distance down (e.g., locking in profits early), but **never moves the Stop Loss** into an unsafe range.
- Formula: `Risk_Multi = 1 - (News_Penalty / 200)`.

---

**Instruction to Agent**: Stability is paramount. If the chart is "quiet," provide the 0.3% fallback rather than a zero-distance TP/SL.

## Outputs
