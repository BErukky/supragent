"""
db_manager.py — Phase 9.1: Multi-Timeframe SQLite OHLCV Store

Upgraded from Phase 4.1 single-TF table to a unified schema keyed by
(symbol, timeframe, timestamp). Supports 15m, 1h, 4h (resampled), 1d.

Auto-migrates the old per-symbol ohlcv_BTC_USD style tables to the new
unified 'ohlcv' table on first run.

API:
    ensure_history(symbol, yf_sym, timeframe, verbose=True)
    get_history_df(symbol, timeframe)
    get_db_stats()
"""

import sqlite3
import pandas as pd
import numpy as np
import os
from datetime import datetime, timedelta

DB_PATH = ".tmp/market_history.db"
MIN_ROWS_FOR_L3 = 200

# How many days to fetch on first seed, per timeframe
SEED_DAYS = {
    "15m": 59,      # yfinance 15m limit ≈ 60 days
    "1h":  729,     # yfinance 1h limit ≈ 730 days
    "4h":  729,     # derived from 1h
    "1d":  1825,    # 5 years
}

# yfinance intervals
YF_INTERVALS = {
    "15m": "15m",
    "1h":  "1h",
    "4h":  "1h",    # resample from 1h
    "1d":  "1d",
}

# C1: Unified symbol → yfinance ticker map.
# Previously only crypto was auto-seeded; Forex symbols always fell back to self-comparison.
SYMBOL_YF_MAP = {
    # Crypto
    "BTC/USD": "BTC-USD", "ETH/USD": "ETH-USD", "SOL/USD": "SOL-USD",
    "XRP/USD": "XRP-USD", "ADA/USD": "ADA-USD", "DOGE/USD": "DOGE-USD",
    "DOT/USD": "DOT-USD", "MATIC/USD": "MATIC-USD", "LTC/USD": "LTC-USD",
    "LINK/USD": "LINK-USD", "AVAX/USD": "AVAX-USD", "BNB/USD": "BNB-USD",
    # Forex & Commodities
    "EUR/USD": "EURUSD=X", "GBP/USD": "GBPUSD=X", "USD/JPY": "USDJPY=X",
    "AUD/USD": "AUDUSD=X", "USD/CAD": "USDCAD=X", "USD/CHF": "USDCHF=X",
    "XAU/USD": "GC=F",     "XAG/USD": "SI=F",     "OIL/USD": "CL=F",
}


def _get_connection() -> sqlite3.Connection:
    os.makedirs(".tmp", exist_ok=True)
    return sqlite3.connect(DB_PATH)


def _create_unified_table(con: sqlite3.Connection):
    """Creates the unified ohlcv table if it doesn't exist."""
    con.execute("""
        CREATE TABLE IF NOT EXISTS ohlcv (
            symbol    TEXT    NOT NULL,
            timeframe TEXT    NOT NULL,
            timestamp INTEGER NOT NULL,
            open      REAL,
            high      REAL,
            low       REAL,
            close     REAL,
            volume    REAL,
            PRIMARY KEY (symbol, timeframe, timestamp)
        )
    """)
    con.execute("CREATE INDEX IF NOT EXISTS idx_sym_tf ON ohlcv(symbol, timeframe)")
    con.commit()


def _migrate_legacy_tables(con: sqlite3.Connection, verbose=True):
    """
    Detects old per-symbol ohlcv_* tables and migrates them into the unified
    table under timeframe='1h'. Drops the old tables after migration.
    """
    cur = con.cursor()
    cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'ohlcv_%'")
    legacy = [r[0] for r in cur.fetchall()]
    for old_table in legacy:
        sym_raw = old_table[len("ohlcv_"):]
        # Convert ohlcv_BTC_USD → BTC/USD (reverse of _sanitise)
        symbol = sym_raw.replace("_", "/", 1)
        try:
            df = pd.read_sql(f"SELECT * FROM {old_table} ORDER BY timestamp ASC", con)
            if df.empty:
                continue
            df["symbol"]    = symbol
            df["timeframe"] = "1h"
            df = df[["symbol","timeframe","timestamp","open","high","low","close","volume"]]
            df.to_sql("ohlcv", con, if_exists="append", index=False)
            cur.execute(f"DROP TABLE {old_table}")
            con.commit()
            if verbose:
                print(f"  [DB] Migrated {old_table} → ohlcv (symbol={symbol}, tf=1h, {len(df)} rows)")
        except Exception as e:
            if verbose:
                print(f"  [DB] Migration warning for {old_table}: {e}")


def _fetch_yfinance(yf_symbol: str, days: int, interval: str) -> pd.DataFrame:
    """Fetches OHLCV from yfinance and returns a clean DataFrame."""
    import yfinance as yf
    period = f"{days}d"
    data   = yf.download(yf_symbol, period=period, interval=interval, progress=False)
    if data.empty:
        return pd.DataFrame()
    df = data.reset_index()
    df.columns = [c[0].lower() if isinstance(c, tuple) else c.lower() for c in df.columns]
    ts_col = "datetime" if "datetime" in df.columns else "date"
    df["timestamp"] = pd.to_datetime(df[ts_col]).astype("int64") // 10**6
    return df[["timestamp","open","high","low","close","volume"]].dropna()


def _resample_4h(df_1h: pd.DataFrame) -> pd.DataFrame:
    """Resamples 1h OHLCV to 4h candles."""
    df = df_1h.copy()
    df["dt"] = pd.to_datetime(df["timestamp"], unit="ms")
    df = df.set_index("dt")
    r = df[["open","high","low","close","volume"]].resample("4h").agg(
        {"open":"first","high":"max","low":"min","close":"last","volume":"sum"}
    ).dropna().reset_index()
    r["timestamp"] = r["dt"].astype("int64") // 10**6
    return r[["timestamp","open","high","low","close","volume"]]


def _row_count(con, symbol, timeframe):
    cur = con.execute(
        "SELECT COUNT(*), MAX(timestamp) FROM ohlcv WHERE symbol=? AND timeframe=?",
        (symbol, timeframe)
    )
    return cur.fetchone()


def ensure_history(symbol: str, yf_symbol: str, timeframe: str = "1h",
                   verbose: bool = True) -> int:
    """
    Phase 9.1: Guarantees the DB has up-to-date OHLCV for (symbol, timeframe).

    - First call  : fetches full seed history.
    - Later calls : incremental append — only new candles since last stored ts.

    timeframe: '15m' | '1h' | '4h' | '1d'
    Returns the total row count for (symbol, timeframe).
    """
    con = _get_connection()
    _create_unified_table(con)
    _migrate_legacy_tables(con, verbose=False)   # silent migration on normal use

    row_count, latest_ts = _row_count(con, symbol, timeframe)
    days = SEED_DAYS.get(timeframe, 365)

    if timeframe == "4h":
        # 4h is always derived from 1h — seed 1h first if needed
        h1_count, _ = _row_count(con, symbol, "1h")
        if h1_count < MIN_ROWS_FOR_L3:
            ensure_history(symbol, yf_symbol, "1h", verbose=verbose)

        # Pull 1h from DB and resample
        if verbose:
            print(f"  [DB] {symbol} 4h: Resampling from 1h DB data...")
        df_1h = pd.read_sql(
            "SELECT * FROM ohlcv WHERE symbol=? AND timeframe='1h' ORDER BY timestamp ASC",
            con, params=(symbol,)
        )
        df_4h = _resample_4h(df_1h)
        if df_4h.empty:
            con.close()
            return 0
        # Upsert all 4h rows
        con.execute("DELETE FROM ohlcv WHERE symbol=? AND timeframe='4h'", (symbol,))
        df_4h["symbol"]    = symbol
        df_4h["timeframe"] = "4h"
        df_4h[["symbol","timeframe","timestamp","open","high","low","close","volume"]].to_sql(
            "ohlcv", con, if_exists="append", index=False)
        con.commit()
        row_count, _ = _row_count(con, symbol, "4h")
        if verbose:
            print(f"  [DB] {symbol} 4h: {row_count} candles stored.")
        con.close()
        return row_count

    if row_count < MIN_ROWS_FOR_L3:
        # Full seed
        if verbose:
            print(f"  [DB] {symbol} {timeframe}: Fetching {days}d history from yfinance...")
        yf_interval = YF_INTERVALS.get(timeframe, "1h")
        df = _fetch_yfinance(yf_symbol, days, yf_interval)
        if df.empty:
            if verbose:
                print(f"  [DB] {symbol} {timeframe}: yfinance returned no data.")
            con.close()
            return 0
        con.execute("DELETE FROM ohlcv WHERE symbol=? AND timeframe=?", (symbol, timeframe))
        df["symbol"]    = symbol
        df["timeframe"] = timeframe
        df[["symbol","timeframe","timestamp","open","high","low","close","volume"]].to_sql(
            "ohlcv", con, if_exists="append", index=False)
        con.commit()
        row_count = len(df)
        if verbose:
            print(f"  [DB] {symbol} {timeframe}: Stored {row_count} rows.")
    else:
        # Incremental update
        latest_dt   = datetime.fromtimestamp(latest_ts / 1000)
        days_behind = max(1, (datetime.now() - latest_dt).days + 1)
        fetch_days  = min(days_behind + 2, days)

        if verbose:
            print(f"  [DB] {symbol} {timeframe}: Appending ~{days_behind}d of new candles...")
        yf_interval = YF_INTERVALS.get(timeframe, "1h")
        df_new = _fetch_yfinance(yf_symbol, fetch_days, yf_interval)
        if not df_new.empty:
            df_new = df_new[df_new["timestamp"] > latest_ts]
            if not df_new.empty:
                df_new["symbol"]    = symbol
                df_new["timeframe"] = timeframe
                df_new[["symbol","timeframe","timestamp","open","high","low","close","volume"]].to_sql(
                    "ohlcv", con, if_exists="append", index=False)
                con.commit()
                row_count += len(df_new)
                if verbose:
                    print(f"  [DB] {symbol} {timeframe}: +{len(df_new)} rows. Total: {row_count}.")
            else:
                if verbose:
                    print(f"  [DB] {symbol} {timeframe}: No new candles since last update.")

    con.close()
    return row_count


def ensure_all_timeframes(symbol: str, yf_symbol: str, verbose: bool = True) -> dict:
    """
    Phase 9.1: Seeds all supported timeframes for a symbol in one call.
    Order: 1h first (4h depends on it), then 15m and 1d in parallel.
    Returns {timeframe: row_count}.
    """
    results = {}
    for tf in ["1h", "4h", "15m", "1d"]:
        results[tf] = ensure_history(symbol, yf_symbol, tf, verbose=verbose)
    return results


def get_history_df(symbol: str, timeframe: str = "1h") -> pd.DataFrame:
    """
    Phase 9.1: Returns full OHLCV history for (symbol, timeframe) as DataFrame.
    Returns empty DataFrame if no data is stored.
    """
    try:
        con = _get_connection()
        _create_unified_table(con)
        df = pd.read_sql(
            "SELECT timestamp,open,high,low,close,volume FROM ohlcv "
            "WHERE symbol=? AND timeframe=? ORDER BY timestamp ASC",
            con, params=(symbol, timeframe)
        )
        con.close()
        return df
    except Exception:
        return pd.DataFrame()


def get_db_stats() -> dict:
    """Returns a summary of all stored (symbol, timeframe) combinations."""
    try:
        con = _get_connection()
        _create_unified_table(con)
        rows = con.execute(
            "SELECT symbol, timeframe, COUNT(*), MIN(timestamp), MAX(timestamp) "
            "FROM ohlcv GROUP BY symbol, timeframe ORDER BY symbol, timeframe"
        ).fetchall()
        con.close()
        stats = {}
        for sym, tf, count, ts_min, ts_max in rows:
            key = f"{sym} [{tf}]"
            stats[key] = {
                "rows": count,
                "from": str(datetime.fromtimestamp(ts_min / 1000))[:10] if ts_min else None,
                "to":   str(datetime.fromtimestamp(ts_max / 1000))[:10] if ts_max else None,
            }
        return stats
    except Exception as e:
        return {"error": str(e)}


if __name__ == "__main__":
    SEED_SYMBOLS = {
        "BTC/USD": "BTC-USD",
        "ETH/USD": "ETH-USD",
        "SOL/USD": "SOL-USD",
    }
    print("=== DB Manager v2: Seeding Multi-TF Store ===\n")
    for sym, yf_sym in SEED_SYMBOLS.items():
        ensure_all_timeframes(sym, yf_sym)

    print("\n=== DB Stats ===")
    for key, info in get_db_stats().items():
        print(f"  {key}: {info['rows']} rows  [{info['from']} → {info['to']}]")
