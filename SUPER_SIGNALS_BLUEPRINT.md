# Super Signals Blueprint (v2.1) - High-Precision Analytical Engine

## 1. Core Architecture

Super Signals operates on a 5-layer system designed for maximum objectivity.

---

## 2. Intelligence Layers (v2.1 Upgrade)

### Layer 1: Market Structure & Liquidity

- **Purpose**: Pure structural truth.
- **Upgrade**: Numeric weights for fractal clarity (0-1.0) and sweep magnitude.
- **Constraints**: No indicators, no news, no higher timeframe cross-talk.

### Layer 2: Multi-Timeframe Confluence

- **Purpose**: Coherence check.
- **Upgrade**: **Trend Coherence Score**. Measures alignment between HTF (1h) and LTF (15m).
- **Confidence Logic**: 1.0 = Perfect alignment. <0.5 = Conflict/Transition.

### Layer 3: Historical Pattern Similarity

- **Purpose**: Statistical context.
- **Upgrade**: **Probabilistic Matching**. Returns returns results based on Euclidean distance analogs.

### Layer 4: Context-Aware Risk Intelligence (CARI)

- **Precision Rules (v2.1)**:
  1. **Source Reliability**: Official (1.0) > Tier 1 (0.8) > Aggregator (0.4).
  2. **Event Scope**: Protocol (1.0), Infrastructure (0.7), Application (0.3).
  3. **Temporal Decay**: Risk diminishes exponentially.
- **Hard Lock Rule**: `If event_scope == "protocol" AND source_trust >= 0.8 -> Force CRITICAL lock`.
- **Governance**: 3-State Logic: NORMAL, CAUTION, CRITICAL.

### Layer 5: Precision Governance

- **Proportional Aggregation**: `FinalConfidence = BaseConfidence * (1 - RiskPenalty / 100)`.
- **Risk Hardening**: Mandatory fallback buffers ensure stability if structure is too tight:
  - **Stop Loss**: Entry ± 0.3%.
  - **Take Profit 1**: Entry ± 0.6%.
  - **Take Profit 2**: Entry ± 1.2%.
- **Feedback Loop**: Every prediction is logged to `.tmp/prediction_logs.json` for drift analysis.

---

## 3. Governance Decision Logic (Hard Rules)

- **Wait State**: Mandatory if `risk_state == "CRITICAL"` or `Confidence < 70`.
- **Actionable Threshold**: `LONG_BIAS` or `SHORT_BIAS` only issued if `Confidence >= 70`.

---

**Instruction to Agent: Preserve structural truth above all. Confidence is earned, not assumed.**
