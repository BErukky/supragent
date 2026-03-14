"""
historical_engine.py — Layer 3: Historical Pattern Similarity
Phase 4.2: Now reads from the SQLite historical DB (via db_manager) instead of
comparing the target CSV against itself. This gives ~8,760 real analogues
(1 year of hourly candles) rather than 50 candles vs 50 candles.

Fallback: if the DB has no data for the symbol yet, silently falls back to the
original self-comparison behaviour so analysis still completes.
"""

import pandas as pd
import numpy as np
import argparse
import json
import sys
import os

# ─────────────────────────────────────────────────────────────────────────────
# Symbol → yfinance ticker map (mirrors market_data.py)
# db_manager needs this to know what to fetch on first initialisation.
# ─────────────────────────────────────────────────────────────────────────────
SYMBOL_YF_MAP = {
    "BTC/USD": "BTC-USD", "ETH/USD": "ETH-USD", "SOL/USD": "SOL-USD",
    "XRP/USD": "XRP-USD", "ADA/USD": "ADA-USD", "DOGE/USD": "DOGE-USD",
    "DOT/USD": "DOT-USD", "MATIC/USD": "MATIC-USD", "LTC/USD": "LTC-USD",
    "LINK/USD": "LINK-USD", "AVAX/USD": "AVAX-USD", "BNB/USD": "BNB-USD",
    "XAU/USD": "GC=F", "XAG/USD": "SI=F", "OIL/USD": "CL=F",
    "EUR/USD": "EURUSD=X", "GBP/USD": "GBPUSD=X", "USD/JPY": "USDJPY=X",
}


def normalize(series):
    if len(series) == 0: return series
    if series.max() == series.min(): return np.zeros(len(series))
    return (series - series.min()) / (series.max() - series.min())

def find_similar_patterns(target_df, history_df, window_size=50, top_k=5):
    """
    Euclidean distance pattern matching.
    target_df  : recent OHLCV (the current market shape, last window_size candles used)
    history_df : deep OHLCV pool (ideally 8,760+ rows from SQLite DB)
    """
    if len(target_df) < window_size or len(history_df) < window_size + 24:
        return []

    target_pattern = target_df['close'].iloc[-window_size:].values
    target_norm = normalize(target_pattern)

    matches = []
    hist_closes = history_df['close'].values
    prediction_window = 24   # Look 24 candles ahead to measure outcome
    limit = len(hist_closes) - window_size - prediction_window

    # Step size: 5 for very large DB (>5000 rows), 3 for standard (>500), 1 for small.
    # B3 Fix: Previously step=5 on an 8,600-row DB checked only ~20% of available history.
    if len(hist_closes) > 5000:
        step = 5
    elif len(hist_closes) > 500:
        step = 3
    else:
        step = 1

    for i in range(0, limit, step):
        candidate = hist_closes[i: i + window_size]
        candidate_norm = normalize(candidate)
        dist = np.linalg.norm(target_norm - candidate_norm)
        prob = np.exp(-dist)   # e^-distance → similarity score (0-1)

        future_close = hist_closes[i + window_size + prediction_window]
        entry_close  = hist_closes[i + window_size]
        next_return  = (future_close - entry_close) / entry_close if entry_close != 0 else 0.0

        matches.append({
            "index":        i,
            "probability":  float(prob),
            "next_returns": float(next_return)
        })

    matches.sort(key=lambda x: x['probability'], reverse=True)
    return matches[:top_k]

def analyze_probabilistic_bias(matches):
    if not matches:
        return "UNCLEAR", 0.0, 0.0, False

    weighted_sum  = sum(m['next_returns'] * m['probability'] for m in matches)
    total_prob    = sum(m['probability'] for m in matches)
    avg_return    = weighted_sum / total_prob if total_prob > 0 else 0

    confidence    = total_prob / len(matches) if matches else 0
    variance      = np.var([m['next_returns'] for m in matches])
    fp_risk       = bool(variance > 0.005)   # High variance = mixed outcomes = unstable analog

    bias = "UNCLEAR"
    if avg_return  >  0.002: bias = "BULLISH"
    elif avg_return < -0.002: bias = "BEARISH"

    return bias, float(avg_return), float(confidence), fp_risk


def run_historical_analysis(target_csv, history_csv=None, symbol=None):
    """
    Phase 4.2: Main entry point — now DB-aware.

    Priority:
      1. SQLite DB via db_manager.get_history_df(symbol)  ← deep analog pool
      2. history_csv argument (explicit path)
      3. target_csv as its own history (original fallback)
    """
    try:
        target_df = pd.read_csv(target_csv)

        history_df = None
        history_source = "self (fallback)"
        db_rows = 0

        # ── 1. Try SQLite DB ─────────────────────────────────────────────────
        if symbol:
            try:
                # Resolve the execution directory for db_manager import
                exec_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)))
                if exec_dir not in sys.path:
                    sys.path.insert(0, exec_dir)

                from db_manager import ensure_history, get_history_df
                yf_sym = SYMBOL_YF_MAP.get(symbol, symbol.replace("/", "-"))

                # Ensure DB is initialised/updated (non-blocking, silent if already fresh)
                db_rows = ensure_history(symbol, yf_sym, verbose=False)
                if db_rows >= 100:
                    history_df = get_history_df(symbol)
                    history_source = f"SQLite DB ({db_rows} rows)"
            except Exception as db_err:
                print(f"  [L3] DB unavailable: {db_err}. Using fallback.")

        # ── 2. Explicit history_csv ──────────────────────────────────────────
        if history_df is None and history_csv and os.path.exists(history_csv):
            history_df = pd.read_csv(history_csv)
            history_source = f"CSV ({history_csv})"

        # ── 3. Self-comparison fallback ─────────────────────────────────────
        if history_df is None:
            history_df = target_df
            history_source = "self (shallow — no DB yet)"

        # Adaptive window: larger pool = larger window for better shape resolution
        if db_rows >= 500:
            window = 50
        elif len(target_df) < 100:
            window = 30
        else:
            window = 40

        matches = find_similar_patterns(target_df, history_df, window_size=window)
        bias, ret, conf, fp_risk = analyze_probabilistic_bias(matches)

        # L3 score: 0–20. FP risk halves the score.
        l3_score = round(20 * conf * (1.0 - (0.5 if fp_risk else 0.0)), 2)

        return {
            "historical_bias":      bias,
            "avg_weighted_return":  round(ret * 100, 4),
            "match_confidence":     round(conf, 2),
            "false_positive_risk":  fp_risk,
            "layer3_score":         l3_score,
            "history_depth":        db_rows if db_rows else len(history_df),
            "history_source":       history_source,
            "analogues_checked":    len(matches),
            "reasoning": (
                f"Probabilistic Similarity: {round(conf * 100, 1)}%. "
                f"Result: {bias} (FP Risk: {fp_risk}). "
                f"Source: {history_source}."
            )
        }
    except Exception as e:
        return {"error": str(e)}



# ─────────────────────────────────────────────────────────────────────────────
# Phase 10.11: Seasonality / Statistical Edge Matrix
# ─────────────────────────────────────────────────────────────────────────────

def calculate_seasonality_stats(symbol: str = None,
                                 current_dt: "datetime | None" = None) -> dict:
    """
    Phase 10.11: Computes empirical hourly and monthly seasonality edges
    from the SQLite historical DB (8,600+ rows of 1H candles).

    Builds a {weekday: {hour: avg_return_pct}} matrix and a {month: avg_return_pct}
    dict from the stored history, then looks up the current weekday+hour and month.

    Returns:
        seasonality_available : bool
        hourly_avg_return     : float — avg % return for this weekday+hour slot
        monthly_avg_return    : float — avg % return for this month
        seasonality_edge      : BULLISH_SEASONAL | BEARISH_SEASONAL | NEUTRAL
        seasonality_modifier  : int — +3 if edge aligns with signal, 0 otherwise
        reasoning             : str
    """
    from datetime import datetime as _dt
    import sqlite3

    NULL = {"seasonality_available": False, "seasonality_modifier": 0,
            "seasonality_edge": "NEUTRAL", "hourly_avg_return": 0.0,
            "monthly_avg_return": 0.0, "reasoning": "Seasonality N/A"}

    try:
        import sys, os
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        from db_manager import DB_PATH
    except Exception:
        return NULL

    now = current_dt or _dt.utcnow()
    current_weekday = now.weekday()  # 0=Mon … 6=Sun
    current_hour    = now.hour
    current_month   = now.month

    try:
        conn = sqlite3.connect(DB_PATH)
        cur  = conn.cursor()
        # Check new unified schema first
        cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='ohlcv'")
        has_new = cur.fetchone()

        if has_new:
            query = (
                "SELECT timestamp, open, close FROM ohlcv "
                "WHERE symbol=? AND timeframe='1h' ORDER BY timestamp"
            )
            rows = cur.execute(query, (symbol or "BTC/USD",)).fetchall()
        else:
            # Legacy: scan for a single matching table
            cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
            tables = [r[0] for r in cur.fetchall()]
            tbl = tables[0] if tables else None
            if not tbl:
                conn.close()
                return NULL
            rows = cur.execute(
                f"SELECT timestamp, open, close FROM {tbl} ORDER BY timestamp"
            ).fetchall()
        conn.close()
    except Exception as e:
        return {**NULL, "reasoning": f"DB error: {e}"}

    if len(rows) < 200:
        return {**NULL, "reasoning": f"Insufficient history ({len(rows)} rows) for seasonality"}

    import pandas as pd
    df = pd.DataFrame(rows, columns=["ts", "open", "close"])
    df["dt"]         = pd.to_datetime(df["ts"], unit="s", utc=True)
    df["return_pct"] = (df["close"] - df["open"]) / df["open"] * 100
    df["weekday"]    = df["dt"].dt.weekday
    df["hour"]       = df["dt"].dt.hour
    df["month"]      = df["dt"].dt.month

    # Hourly edge matrix (weekday × hour)
    hourly = df.groupby(["weekday", "hour"])["return_pct"].mean()
    slot_return = 0.0
    try:
        slot_return = float(hourly.loc[(current_weekday, current_hour)])
    except KeyError:
        slot_return = 0.0

    # Monthly edge matrix
    monthly = df.groupby("month")["return_pct"].mean()
    month_return = 0.0
    try:
        month_return = float(monthly.loc[current_month])
    except KeyError:
        month_return = 0.0

    # Classify edge
    EDGE_THRESHOLD = 0.04  # 0.04% avg return per candle = meaningful edge
    if slot_return > EDGE_THRESHOLD:
        edge = "BULLISH_SEASONAL"
    elif slot_return < -EDGE_THRESHOLD:
        edge = "BEARISH_SEASONAL"
    else:
        edge = "NEUTRAL"

    # Days of week for display
    day_names = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    day_name  = day_names[current_weekday]

    return {
        "seasonality_available": True,
        "hourly_avg_return":    round(slot_return, 4),
        "monthly_avg_return":   round(month_return, 4),
        "seasonality_edge":     edge,
        # B1 Fix: Signed modifier — adverse seasonality now penalizes (-3), not silently ignored.
        "seasonality_modifier": +3 if edge == "BULLISH_SEASONAL" else (-3 if edge == "BEARISH_SEASONAL" else 0),
        "reasoning": (
            f"{day_name} {current_hour:02d}:00 UTC historically "
            f"{'+' if slot_return >= 0 else ''}{round(slot_return, 3)}% avg per candle "
            f"({edge}). Monthly: {'+' if month_return >= 0 else ''}{round(month_return, 3)}%"
        )
    }


def main():
    parser = argparse.ArgumentParser(description="Analyze Historical Similarity v3 (Phase 4).")
    parser.add_argument("--target",  type=str, required=True, help="Current market data CSV")
    parser.add_argument("--history", type=str, help="Historical CSV (optional override)")
    parser.add_argument("--symbol",  type=str, help="Symbol (e.g. BTC/USD) — enables DB lookup")
    args = parser.parse_args()

    result = run_historical_analysis(args.target, args.history, args.symbol)
    if "error" in result:
        print(json.dumps(result))
        sys.exit(1)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
