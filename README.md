# 🌌 Super Signals v2.1: Precision Market Intelligence

Super Signals is a high-precision, non-executing analytical framework designed for cryptocurrency and forex trading research. It utilizes an upgraded **5-Layer Intelligence Engine** with **v2.1 Precision Governance** to convert raw market data into institutional-grade decision intelligence.

---

## 🧠 The v2.1 Intelligence Model

The system analyzes the market through a series of numeric, weighted filters to ensure maximum objectivity:

1.  **📊 Layer 1: Structure & Liquidity**: Quantifies **Swing Clarity** (0.0-1.0) and detects **Liquidity Sweeps**. It ignores news and indicators to find the pure "market truth."
2.  **🔗 Layer 2: Trend Coherence**: Measures the precision of alignment between Higher Timeframes (HTF) and Lower Timeframes (LTF). Full alignment earns a 1.0 coherence score.
3.  **⏳ Layer 3: Probabilistic Similarity**: Uses Euclidean pattern matching to find historical analogs and calculates a **Probability %** of success based on past returns.
4.  **🗞️ Layer 4: Context-Aware Risk Intelligence (CARI)**: Automatically scrapes **CoinDesk, CoinTelegraph, and CryptoPanic**. It applies **Source-Weighted Penalties** for high-impact negative events.
5.  **⚖️ Layer 5: Precision Governance**: Aggregates all weights using **Proportional Scaling** and outputs automated **Robust TP/SL advisory levels**.

**✨ Phase 12+: NLP Intelligence (Groq)**: Automatically generates a concise, 2-3 sentence AI summary for every signal using the Llama-3.1-8b-instant model on Groq.

---

## 🛡️ v2.1 Governance & Safety (Precision Upgrade)

- **Proportional Risk Scaling**: Confidence is no longer simply subtracted. It follows the formula: `FinalConfidence = BaseConfidence * (1 - RiskPenalty / 100)`. This prevents "brittle" signals while maintaining safety.
- **Protocol-Level Hard Lock**: Any **Protocol-level** risk (e.g., chain halt) from a **Trusted Source** (>= 0.8 trust) triggers a mandatory `WAIT/LOCKED` state regardless of technicals.
- **Reliability Fallback (TP/SL)**: If structural confidence is low, the system applies a mandatory buffer:
  - **SL**: 0.3% from entry.
  - **TP1**: 0.6% from entry.
  - **TP2**: 1.2% from entry.
- **Analytical Feedback Loop**: All predictions are logged to `.tmp/prediction_logs.json` to track accuracy over time.

---

## 🚀 Usage

```powershell
# Full Market Scan (Top 10 + News Filtering)
python execution/market_scanner.py

# Technical-Only Scan (Ignores News Risk)
python execution/market_scanner.py --no_news

# Performance Feedback Loop
python execution/performance_analyzer.py
```

---

## 📂 System Structure

- `app.py`: Unified Web Service & Telegram Listener (Deployment Ready).
- `main.py`: Pipeline Orchestrator.
- `execution/`: Core engines (Structure, History, CARI News, Scraper).
- `directives/`: Governance SOPs.
- `.tmp/`: Data buffers and Prediction Logs.

---

**Strategic Intelligence. Absolute Objectivity.**
