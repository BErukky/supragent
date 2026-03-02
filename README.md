# 🌌 Super Signals v2.0: Predictive Market Intelligence

Super Signals is a high-precision, non-executing analytical framework designed for cryptocurrency trading research. It utilizes an upgraded **5-Layer Intelligence Engine** to convert raw market data into institutional-grade decision intelligence.

---

## 🧠 The v2.0 Intelligence Model

The system analyzes the market through a series of numeric, weighted filters to ensure maximum objectivity:

1.  **📊 Layer 1: Structure & Liquidity**: Quantifies **Swing Clarity** (0.0-1.0) and detects **Liquidity Sweeps**. It ignores news and indicators to find the pure "market truth."
2.  **🔗 Layer 2: Trend Coherence**: Measures the precision of alignment between Higher Timeframes (HTF) and Lower Timeframes (LTF). Full alignment earns a 1.0 coherence score.
3.  **⏳ Layer 3: Probabilistic Similarity**: Uses Euclidean pattern matching to find historical analogs and calculates a **Probability %** of success based on past returns.
4.  **🗞️ Layer 4: Autonomous News IQ**: Automatically scrapes **CoinDesk, CoinTelegraph, and CryptoPanic**. It applies **Risk Penalties** for high-impact negative events.
5.  **⚖️ Layer 5: Governance & Synthesis**: Aggregates all weights, applies safety overrides, and outputs automated **TP/SL advisory levels**.

---

## 🛡️ Governance & Safety Locks

- **Critical Risk Lock**: Any "Critical" news (hacks, sanctions) triggers a mandatory `WAIT` state.
- **Selective Threshold**: A signal is only issued if total confidence is **≥ 75%**.
- **Analytical Feedback Loop**: All predictions are logged to `.tmp/prediction_logs.json` to track accuracy over time.

---

## 🚀 Usage

```powershell
# Multi-Asset Autonomous Scanner
# Scans top 10 assets and alerts on high-confidence setups
python execution/market_scanner.py

# Performance Feedback Loop
# Compares past predictions to current market price to measure accuracy
python execution/performance_analyzer.py
```

---

## 📈 Analysis Examples

### Case A: Active Trade Bias (High Confidence)

_When layers align and the environment is safe._

```text
=============================================
=== SUPER SIGNALS v2.0 LIVE REPORT ===
Symbol: BTC/USD | 2026-02-02 12:00:00
---------------------------------------------
 SIGNAL:      LONG_BIAS (88/100 Conf)
 STOP LOSS:   42,150.00
 TAKE PROFIT: 43,500.00 | 44,200.00
 RISK OFFSET: 1.0x (Standard)
---------------------------------------------
--- LAYER-WISE REASONING ---
 [L1/L2] Trend Coherent: 92%. Clear HH/HL on both timeframes.
 [L3]    Probabilistic Match: 75% (Bullish history).
 [L4]    Sentiment: Positive. No Risk Penalties detected.
=============================================
```

### Case B: Governance Wait (Safety First)

_When structure is unclear or external risk is too high._

```text
=============================================
=== SUPER SIGNALS v2.0 LIVE REPORT ===
Symbol: BTC/USD | 2026-02-02 14:00:00
---------------------------------------------
 SIGNAL:      WAIT / NO_TRADE (20/100 Conf)
---------------------------------------------
--- LAYER-WISE REASONING ---
 [L1/L2] Trend Coherent: 45%. Ranging structure.
 [L3]    Probabilistic Match: 30% (Uncertain history).
 [L4]    [!] CRITICAL: Risk Penalty (80) - News Hack Detected.
=============================================
```

---

## 📱 Telegram Integration (New)

The system now sends **Real-Time Alerts** for:

- 🚀 **High-Confidence Signals** (>= 75%)
- ⚠️ **Governance Warnings** (Critical News Risk)
- 🎯 **Market Scanner Hits**

### Setup

1.  **Create Bot via @BotFather** on Telegram.
2.  **Get Chat ID**: Run the helper script:
    ```powershell
    python execution/get_telegram_id.py <YOUR_BOT_TOKEN>
    ```
3.  **Configure .env**: The script above will give you the ID. Ensure your `.env` file looks like this:
    ```ini
    TELEGRAM_BOT_TOKEN=your_token_here
    TELEGRAM_CHAT_ID=your_chat_id_here
    ```

---

## 📂 System Structure

- `main.py`: Pipeline Orchestrator.
- `execution/`: Core engines (Structure, History, News, Scraper).
- `directives/`: Governance SOPs.
- `.tmp/`: Data buffers and Prediction Logs.

---

**Strategic Intelligence. Absolute Objectivity.**
