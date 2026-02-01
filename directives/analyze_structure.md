# Directive: Analyze Market Structure (Layer 1)

## Goal

Determine directional bias by analyzing price structure and liquidity behavior on the Local Timeframe (LTF).

## Inputs

- `input_file`: CSV file containing OHLCV data.
- `swing_length`: Fractal sensitivity (default: 5).

## Tools / Scripts

- `execution/structure_engine.py`

## Logic & Definitions

### 1. Market Structure (Fractals)

- **HH/HL/LH/LL**: Identified using N-candle swing logic.
- **States**: BULLISH, BEARISH, RANGE, TRANSITION (CHoCH).

### 2. Liquidity Pool Detection

- **Buy-Side Liquidity (BSL)**: Equal Highs or obvious Swing Highs.
- **Sell-Side Liquidity (SSL)**: Equal Lows or obvious Swing Lows.
- **Equal Highs/Lows**: Two or more swings within 0.1% price variance.

### 3. Interaction Detection

- **Liquidity Sweep**: Price breaches a pool (wick) but closes back within structure.
- **Liquidity Run**: Price breaks liquidity and holds (acceptance).
- **Sweep + CHoCH**: High-probability reversal signal.

### 4. Scoring Logic (Max 30)

- **Base (Max 15)**:
  - Strong Trend: +15
  - Range: +5
  - Unclear: 0
- **Liquidity Modifiers (Max ±15)**:
  - Sweep against trend: +10
  - Sweep + CHoCH: +15
  - Run with acceptance: +5
  - No interaction: 0
  - Sweep without confirmation: -5

## Output Schema

```json
{
  "structure_bias": "BULLISH | BEARISH | NEUTRAL",
  "structure_state": "TREND | RANGE | TRANSITION",
  "liquidity_context": {
    "type": "BUY_SIDE | SELL_SIDE | NONE",
    "event": "SWEEP | RUN | NONE",
    "level": 42150.0
  },
  "layer1_score": 0-30,
  "notes": "Text summary"
}
```
