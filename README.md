# 🌌 Super Signals: Predictive Market Intelligence

Super Signals is an advanced, non-executing analytical framework designed for high-probability cryptocurrency trading research. It utilizes a **5-Layer Intelligence Engine** to synthesize market structure, liquidity behavior, historical analogs, and real-world sentiment into actionable decision data.

---

## 🧠 The 5-Layer Engine

The system analyzes the market through five distinct lenses:

1.  **📊 Layer 1: Market Structure & Liquidity**: Detects fractal swing points (HH, HL, LL, LH) and **Liquidity Sweeps** (Equal Highs/Lows).
2.  **🔗 Layer 2: Multi-Timeframe Confluence**: Cross-references Higher Timeframe (HTF) context with Lower Timeframe (LTF) confirmation.
3.  **⏳ Layer 3: Historical Similarity**: Compares current setups to 1,000 candle windows of history to find statistical analogs.
4.  **🗞️ Layer 4: News & Narrative**: Automatically scrapes the latest headlines from **CoinDesk, CoinTelegraph, and CryptoPanic** to assign real-time risk weights.
5.  **⚖️ Layer 5: Probability & Risk**: Synthesizes all layers into a final score (0-100) and calculates **automated TP/SL advisory levels**.

---

## 🛡️ Confidence Governance (Safety First)

The system is governed by a strict safety protocol:

- **News Override**: High-risk news (e.g., hacks, macro data) forces an automatic `WAIT` state.
- **Uncertainty Moderation**: Confidence is automatically reduced if historical data is unstable or news is mixed.
- **Selective Signaling**: Bias is only issued if trust exceeds the **75%** threshold.

---

## 🚀 Getting Started

### Prerequisites

- Python 3.10+
- Dependencies: `pandas`, `numpy`, `ccxt`, `yfinance`

### Usage (Live Data)

Run the entire analysis pipeline with a single command:

```powershell
python main.py --symbol BTC/USD --htf 1h --ltf 15m
```

---

## 📈 Output Breakdown

| Component        | Description                                     |
| :--------------- | :---------------------------------------------- |
| **FINAL_SIGNAL** | `LONG_BIAS`, `SHORT_BIAS`, or `WAIT / NO_TRADE` |
| **CONFIDENCE**   | 0-100 score (Trust Level)                       |
| **STOP_LOSS**    | Automated structural invalidation zone          |
| **TAKE_PROFIT**  | Targets based on R:R and volatility             |
| **REASONING**    | Detailed checklist + safety governance notes    |

### Example Live Report

```text
========================================
=== SUPER SIGNALS LIVE REPORT ===
Symbol: BTC/USD | HTF: 1h | LTF: 15m
----------------------------------------
 SIGNAL:      LONG_BIAS (82/100 Conf)
 STOP LOSS:   42,150.00
 TAKE PROFIT: 43,500.00 | 44,200.00

--- REASONING & GOVERNANCE ---
 Layer 1: BULLISH structure. Last sweep: SELL_SIDE_SWEEP (+10)
 History: Past analogs ended Bullish (+10)
 [!] News: Positive Sentiment (+10)
========================================
```

---

## 🛡️ Risk Disclaimer

**NOT FINANCIAL ADVICE.** Super Signals is an analytical tool for informational purposes only. It does NOT execute trades. Use suggested levels as discretionary guidance only.

---

## 📂 Project Structure

- `main.py`: The central pipeline orchestrator.
- `execution/`: Core Python engines (Structure, History, News, Report).
- `directives/`: Standard Operating Procedures (SOPs) for the logic.
- `.tmp/`: Data buffers and intermediate JSON outputs.

---

**Build For Strategic Consistency.**
