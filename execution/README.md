# 🛠️ Execution Engines (v2.0)

This directory contains the core analytical logic for each intelligence layer of the **Super Signals v2.0** system.

## 📁 Engine List

| Script                     | Responsibility                                                                               | Key v2.0 Feature                    |
| :------------------------- | :------------------------------------------------------------------------------------------- | :---------------------------------- |
| **`market_data.py`**       | Fetches live real-time OHLCV data from **yfinance**.                                         | Live Connectivity                   |
| **`structure_engine.py`**  | Detects fractal swings and liquidity levels.                                                 | **Numeric Swing Clarity** (0-1.0)   |
| **`confluence_engine.py`** | Coordinates multi-timeframe alignment.                                                       | **Trend Coherence Score**           |
| **`historical_engine.py`** | Finds pattern analogs in history.                                                            | **Probabilistic matching**          |
| **`news_scraper.py`**      | Automatically fetches live headlines from CoinDesk, CoinTelegraph, etc.                      | **Autonomous Intelligence**         |
| **`news_engine.py`**       | Analyzes sentiment and risk impact.                                                          | **Reaction & Penalty Assimilation** |
| **`report_engine.py`**     | Integrates all layers into a governed final score. Saves predictions to **Prediction Logs**. | **Aggregation & Feedback Loop**     |

## ⚙️ v2.0 Data Flow

1. **Scrape**: `news_scraper` and `market_data` refresh the data in `.tmp/`.
2. **Analyze**: `confluence` and `historical` perform weighted calculations.
3. **Govern**: `news_engine` calculates risk penalties.
4. **Synthesize**: `report_engine` aggregates all weights and logs the final result for the feedback loop.

---

**Build For Strategic Consistency.**
