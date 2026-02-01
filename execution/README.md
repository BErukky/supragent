# 🛠️ Execution Engines

This directory contains the deterministic logic for each intelligence layer of the **Super Signals** system.

## 📁 Engine List

| Script                     | Responsibility                                                                             |
| :------------------------- | :----------------------------------------------------------------------------------------- |
| **`market_data.py`**       | Fetches real-time OHLCV data from **yfinance** and exchange APIs.                          |
| **`structure_engine.py`**  | Detects fractal swings, HH/HL/LL/LH, and **Liquidity Pools/Sweeps**.                       |
| **`confluence_engine.py`** | Performs multi-timeframe analysis (HTF vs LTF Alignment).                                  |
| **`historical_engine.py`** | Pattern matching via Euclidean distance to find historical analogs.                        |
| **`news_engine.py`**       | Keyword-based sentiment and system risk level classification.                              |
| **`report_engine.py`**     | Synthesizes all layers into a final score and **Governance-aware** signals. Handles TP/SL. |
| **`mock_data.py`**         | Fallback for simulating market conditions (used for testing).                              |

## ⚙️ Data Flow

1. `market_data` saves CSVs to `.tmp/`.
2. `confluence` uses `structure_engine` logic to output structure JSON.
3. `historical` and `news` generate specific bias JSONs.
4. `report_engine` reads all JSONs and produces the final actionable report.

---

**Core Determinism Layer.**
