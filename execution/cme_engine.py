"""
cme_engine.py — Phase 10.7: CME Gap Detection

CME Bitcoin futures trade Mon–Fri only. Each weekend creates a gap
between Friday's close and Monday's open. ~80% of these gaps fill
historically, making them powerful price targets.

Usage:
    from execution.cme_engine import analyze_cme_gaps
    result = analyze_cme_gaps("BTC/USD")
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd
from datetime import datetime, timedelta

# Symbols that trade on CME as futures
CME_ELIGIBLE = {"BTC/USD", "BTC/GBP", "ETH/USD"}
YF_MAP = {"BTC/USD": "BTC-USD", "BTC/GBP": "BTC-GBP", "ETH/USD": "ETH-USD"}

MIN_GAP_PCT = 0.003   # 0.3% minimum gap to count


def _fetch_daily_ohlcv(yf_symbol: str, days: int = 180) -> pd.DataFrame:
    """Fetches daily OHLCV from yfinance."""
    try:
        import yfinance as yf
        data = yf.download(yf_symbol, period=f"{days}d", interval="1d", progress=False)
        if data.empty:
            return pd.DataFrame()
        df = data.reset_index()
        df.columns = [c[0].lower() if isinstance(c, tuple) else c.lower() for c in df.columns]
        ts_col = "date" if "date" in df.columns else "datetime"
        df["date"] = pd.to_datetime(df[ts_col])
        df = df[["date", "open", "high", "low", "close", "volume"]].dropna()
        return df
    except Exception:
        return pd.DataFrame()


def find_cme_gaps(df: pd.DataFrame) -> list:
    """
    Scans a 1D OHLCV DataFrame for unfilled Friday→Monday CME gaps.
    A gap exists when Monday's open differs meaningfully from Friday's close.
    Returns list of gap dicts ordered by recency (most recent first).
    """
    if df.empty or len(df) < 5:
        return []

    df = df.sort_values("date").reset_index(drop=True)
    gaps = []
    today = pd.Timestamp.now().normalize()

    for i in range(1, len(df)):
        row      = df.iloc[i]
        prev_row = df.iloc[i - 1]
        day_name = row['date'].day_name()
        prev_day = prev_row['date'].day_name()

        # Monday open vs Friday close
        if day_name == "Monday" and prev_day == "Friday":
            friday_close = float(prev_row['close'])
            monday_open  = float(row['open'])
            gap_size     = monday_open - friday_close
            gap_pct      = abs(gap_size) / friday_close

            if gap_pct < MIN_GAP_PCT:
                continue

            gap_type = "BULLISH_GAP" if gap_size > 0 else "BEARISH_GAP"
            gap_high = max(friday_close, monday_open)
            gap_low  = min(friday_close, monday_open)

            # Check if gap was filled in subsequent candles
            future = df[df['date'] > row['date']]
            filled = False
            if not future.empty:
                if gap_type == "BULLISH_GAP":
                    filled = bool((future['low'] <= friday_close).any())
                else:
                    filled = bool((future['high'] >= friday_close).any())

            age_days = int((today - row['date']).days)

            if not filled:
                gaps.append({
                    "gap_type":       gap_type,
                    "gap_high":       round(gap_high, 4),
                    "gap_low":        round(gap_low, 4),
                    "gap_pct":        round(gap_pct * 100, 2),
                    "friday_close":   round(friday_close, 4),
                    "monday_open":    round(monday_open, 4),
                    "gap_date":       str(row['date'].date()),
                    "filled":         False,
                    "age_days":       age_days,
                })

    # Most recent unfilled gaps first
    gaps.sort(key=lambda g: g['age_days'])
    return gaps


def analyze_cme_gaps(symbol: str, current_price: float = None) -> dict:
    """
    Phase 10.7: Main entry point for CME gap analysis.

    Returns:
        cme_available  : bool — True if CME gaps are applicable for this symbol
        unfilled_gaps  : list — all unfilled gaps
        nearest_gap    : dict | None — closest unfilled gap to current price
        cme_modifier   : int — score modifier (+5 if signal aligns with gap fill, else 0)
        signal_bias    : str — BULLISH, BEARISH, or NEUTRAL toward gap fill
        tp_target      : float | None — nearest gap level as TP suggestion
    """
    if symbol not in CME_ELIGIBLE:
        return {"cme_available": False, "unfilled_gaps": [], "nearest_gap": None,
                "cme_modifier": 0, "signal_bias": "NEUTRAL", "tp_target": None,
                "reasoning": f"CME gap analysis not applicable for {symbol}"}

    yf_sym = YF_MAP.get(symbol, symbol.replace("/", "-"))
    df     = _fetch_daily_ohlcv(yf_sym, days=180)
    if df.empty:
        return {"cme_available": True, "unfilled_gaps": [], "nearest_gap": None,
                "cme_modifier": 0, "signal_bias": "NEUTRAL", "tp_target": None,
                "reasoning": "Failed to fetch daily data for CME analysis"}

    gaps = find_cme_gaps(df)
    if not gaps:
        return {"cme_available": True, "unfilled_gaps": [], "nearest_gap": None,
                "cme_modifier": 0, "signal_bias": "NEUTRAL", "tp_target": None,
                "reasoning": "No unfilled CME gaps found in past 180 days"}

    # Find current price if not supplied
    if current_price is None:
        try:
            current_price = float(df['close'].iloc[-1])
        except Exception:
            current_price = 0.0

    # Nearest unfilled gap (by mid-point distance)
    nearest = min(gaps, key=lambda g: abs(((g['gap_high'] + g['gap_low']) / 2) - current_price))
    gap_mid = (nearest['gap_high'] + nearest['gap_low']) / 2

    # Determine directional bias toward gap fill
    if current_price < gap_mid:
        signal_bias = "BULLISH"   # Need to go up to fill the gap
        tp_target   = nearest['gap_low']  # TP at bottom of gap zone
    elif current_price > gap_mid:
        signal_bias = "BEARISH"   # Need to go down to fill the gap
        tp_target   = nearest['gap_high']
    else:
        signal_bias = "NEUTRAL"
        tp_target   = gap_mid

    cme_modifier = 5 if signal_bias in ("BULLISH", "BEARISH") else 0

    return {
        "cme_available":  True,
        "unfilled_gaps":  gaps[:5],  # Return up to 5 nearest unfilled gaps
        "nearest_gap":    nearest,
        "cme_modifier":   cme_modifier,
        "signal_bias":    signal_bias,
        "tp_target":      round(tp_target, 4),
        "reasoning": (
            f"Nearest CME gap: {nearest['gap_type']} "
            f"[{nearest['gap_low']}–{nearest['gap_high']}] "
            f"({nearest['age_days']}d old, {nearest['gap_pct']}%). "
            f"Price must go {signal_bias} to fill. TP target: {round(tp_target, 2)}"
        )
    }


if __name__ == "__main__":
    print("=== CME Gap Engine — BTC/USD ===")
    result = analyze_cme_gaps("BTC/USD")
    import json
    print(json.dumps(result, indent=2))
