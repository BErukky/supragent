# Directive: Orchestrate Full Pipeline

## Goal

Create a single command (`python main.py`) that runs the entire analysis pipeline and produces a consolidated, clean summary report.

## Inputs

- `--symbol`: e.g. BTC/USDT
- `--htf`: e.g. 1h
- `--ltf`: e.g. 15m

## Tools / Scripts

- `main.py`: This script will:
  1.  Call `market_data.py` (or mock) to get HTF and LTF data.
  2.  Call `confluence_engine.py` to get Structure/Trend.
  3.  Call `historical_engine.py` to get History Bias.
  4.  Call `news_engine.py` to get Risk Score.
  5.  Call `report_engine.py` to get Final Signal & Risk Levels.
  6.  **Print a "Clean" Summary** to the console.

## Desired Output Format

```text
=== SUPER SIGNALS REPORT ===
Symbol: BTC/USDT | Date: 2026-01-31 10:00

 SIGNAL:      LONG_BIAS (High Confidence)
 ENTRY ZONE:  LTF Market Price

 STOP LOSS:   42,280.00
 TAKE PROFIT: 45,720.00 | 47,440.00

--- CONFIRMATION ---
 [X] Structure: Bullish Confluence
 [X] History:   Bullish (+2.5% avg return)
 [X] News:      Positive Sentiment

--- RISK NOTE ---
 No critical news risks detected.
=============================
```
