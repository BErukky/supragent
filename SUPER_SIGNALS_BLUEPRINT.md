# Trading Strategy Specification

## Fractal Geometry + Probabilistic Market Intelligence (AI-Assisted)

---

## 1. PURPOSE OF THIS DOCUMENT

This document defines a **non-executing analytical trading system**.

The system is designed to:

- Analyze crypto markets using fractal geometry and market structure
- Incorporate probabilistic reasoning (often misnamed “quantum trading”)
- Cross-check signals with historical similarity and macro/news context
- Produce **decision intelligence**, not trade execution

This document is the **single source of truth** for the AI agent.

If a rule or capability is not written here, it does not exist.

---

## 2. WHAT THIS SYSTEM IS (AND IS NOT)

### IS:

- A market analysis framework
- A probabilistic decision-support engine
- A pattern-recognition and structure-detection system
- An AI-assisted research and signal-validation tool
- **Risk Management Advisor (TP/SL suggestions only)**

### IS NOT:

- An automated trading bot
- A Telegram execution bot
- A guarantee of profit
- A high-frequency trading system

The system **does not place trades**.
It only outputs structured analytical conclusions.

---

## 3. MARKET SCOPE

### Asset Class

- Cryptocurrency markets only

### Primary Assets

- BTC/USD
- ETH/USD

---

## 4. CORE CONCEPTS

### 4.1 Fractal Geometry in Markets

Fractal geometry is used to describe **self-similar price behavior across timeframes**.
Focuses on HH/HL/LH/LL swings.

### 4.2 Probabilistic Reasoning

Assigns confidence levels. Allows uncertainty. Can output NO-TRADE.

---

## 5. SYSTEM INTELLIGENCE LAYERS

### Layer 1: Market Structure & Liquidity Intelligence

Responsible for determining directional bias by analyzing price structure (HH/HL/LL/LH) and liquidity behavior (Sweeps, Runs, Grabs).

- **Liquidity Detection**: Identifies Equal Highs/Lows and Session Extremes.
- **Interaction Analysis**: Detects Liquidity Sweeps (wick breaches) vs Runs (acceptance).
- **Scoring**: Max 30 points (Structure + Liquidity Modifiers).

### Layer 2: Multi-Timeframe Confluence

HTF (Context) vs LTF (Confirmation).

### Layer 3: Historical Pattern Similarity

Compare current setup with historical analogs.

### Layer 4: News & Narrative Context

Keyword-based risk weighting.

### Layer 5: Probability Assessment & Risk Output

Synthesizes all inputs into Confidence Score and Bias.
**Calculates TP and SL advisory levels.**

---

## 6. RISK MANAGEMENT SPECIFICATION (TP/SL)

**Advisory Only**. Not instructions.

### Logic Rules

#### Stop Loss (SL)

- Placed beyond structure invalidation point.
- **Long**: Below last Higher Low (HL) or significant Swing Low.
- **Short**: Above last Lower High (LH) or significant Swing High.

#### Take Profit (TP)

- **TP1**: Recent Range Boundary or previous Swing High/Low.
- **TP2**: Extension or R:R based.

---

## 7. OUTPUT RULES

The system may output:

- Market Bias
- Structural Reasoning
- Confidence Level
- **TP/SL Advisory Zones**

The system must NOT:

- Execute trades.

End of specification.
