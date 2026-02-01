# Directive: Analyze Multi-Timeframe Confluence

## Goal

Implement Layer 2 intelligence: Cross-reference Higher Timeframe (HTF) structure with Lower Timeframe (LTF) confirmation.

## Inputs

- `htf_data`: CSV file for Higher Timeframe (e.g. 1H).
- `ltf_data`: CSV file for Lower Timeframe (e.g. 15M).

## Tools / Scripts

- `execution/confluence_engine.py` (New script)
- Uses `structure_engine.py` as a library.

## Outputs

- Console Output / JSON:
  ```json
  {
    "bias": "BULLISH",
    "confidence": "HIGH",
    "reasoning": "HTF is BULLISH (HH+HL sequence). LTF is BULLISH (aligned).",
    "htf_state": "BULLISH",
    "ltf_state": "BULLISH"
  }
  ```

## Logic

1.  **Analyze HTF**: Determine market state (BULLISH, BEARISH, RANGE).
2.  **Analyze LTF**: Determine market state.
3.  **Confluence Rules**:
    - **HIGH CONFIDENCE**: HTF == LTF (e.g. Both Bullish).
    - **MEDIUM CONFIDENCE**: HTF is Clear, LTF is Range/Unclear.
    - **NO TRADE (LOW)**: HTF and LTF contradict (e.g. Bullish vs Bearish). -> Wait for LTF to align.

## Strategy

- Use `execution/structure_engine.py` functions to process both files.
- Compare the resulting states.
