# Directive: Orchestrate Full Pipeline v2.1

## Goal

Maintain a unified entry point (`python main.py`) for individual analysis and a multi-asset scanner (`python execution/market_scanner.py`) for autonomous monitoring.

## 1. Primary Orchestrator (`main.py`)

Runs the 5-layer analysis for a single symbol.

- **Inputs**: `--symbol`, `--htf`, `--ltf`.
- **Logic**:
  1.  Fetch real-time data via `yfinance`.
  2.  Execute Layer 1 & 2 (Structure & Confluence).
  3.  Execute Layer 3 (Historical Analog Matching).
  4.  Execute Layer 4 (CARI News Risk Analysis).
  5.  Execute Layer 5 (Precision Governance aggregation).
- **Output**: Detailed console JSON or clean summary.

## 2. Market Scanner (`execution/market_scanner.py`)

Iterates through Top 10 assets for high-confidence setups.

- **v2.1 Precision Option**: Use `--no_news` to run a pure technical scan, bypassing the Layer 4 news filter.
- **Alerting**: Automatically triggers Telegram alerts if `Confidence >= 85`.

## 3. Deployment (`app.py`)

Unified Flask service and Telegram listener.

- **Health Check**: `GET /` returns system status.
- **Bot Commands**: Responds to `/scan`, `/scan_tech`, and `/analyze` directly in Telegram.

---

**Instruction to Agent**: Ensure all entry points respect the v2.1 precision scaling and TP/SL fallback rules.
