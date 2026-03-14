"""
oi_engine.py — Phase 10.8: Open Interest Analysis

Fetches Binance Futures Open Interest history and classifies the
OI / price relationship to detect conviction vs. short-covering.

OI Regime Classification:
  OI up + Price up   → BULLISH_CONVICTION  (+6 for longs)
  OI up + Price down → SHORT_BUILD         (−5 for longs, +5 for shorts)
  OI down + Price up → SHORT_COVER         (+3 for longs — fragile rally)
  OI down + Price down → LONG_LIQUIDATION  (−5 for longs — capitulation risk)

Usage:
    from execution.oi_engine import analyze_oi
    result = analyze_oi("BTC/USD", "LONG_BIAS")
"""

import requests
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Binance symbol map (no slash, USDT-margined)
BINANCE_SYMBOL_MAP = {
    "BTC/USD":  "BTCUSDT",
    "ETH/USD":  "ETHUSDT",
    "SOL/USD":  "SOLUSDT",
    "XRP/USD":  "XRPUSDT",
    "ADA/USD":  "ADAUSDT",
    "DOT/USD":  "DOTUSDT",
    "DOGE/USD": "DOGEUSDT",
    "AVAX/USD": "AVAXUSDT",
    "MATIC/USD":"MATICUSDT",
}

BINANCE_BASE = "https://fapi.binance.com"


def _get_oi_history(binance_symbol: str, period: str = "1h", limit: int = 48) -> list:
    """Fetches Open Interest history from Binance Futures."""
    url = f"{BINANCE_BASE}/futures/data/openInterestHist"
    params = {"symbol": binance_symbol, "period": period, "limit": limit}
    try:
        resp = requests.get(url, params=params, timeout=6)
        if resp.status_code == 200:
            return resp.json()
        return []
    except Exception:
        return []


def _get_current_price(binance_symbol: str) -> float:
    """Gets latest mark price from Binance Futures."""
    try:
        url  = f"{BINANCE_BASE}/fapi/v1/ticker/price"
        resp = requests.get(url, params={"symbol": binance_symbol}, timeout=4)
        if resp.status_code == 200:
            return float(resp.json()["price"])
        return 0.0
    except Exception:
        return 0.0


def classify_oi_regime(oi_change_pct: float, price_change_pct: float,
                        signal_bias: str) -> tuple:
    """
    Classifies OI/price relationship and returns (regime, modifier).
    signal_bias: 'LONG_BIAS' | 'SHORT_BIAS' | other
    """
    oi_rising    = oi_change_pct > 1.0     # >1% OI increase
    oi_falling   = oi_change_pct < -1.0    # >1% OI decrease
    price_rising = price_change_pct > 0.3  # >0.3% price increase
    price_falling = price_change_pct < -0.3

    is_long  = "LONG"  in signal_bias
    is_short = "SHORT" in signal_bias

    if oi_rising and price_rising:
        regime   = "BULLISH_CONVICTION"
        modifier = +6 if is_long else -4
    elif oi_rising and price_falling:
        regime   = "SHORT_BUILD"
        modifier = -5 if is_long else +5
    elif oi_falling and price_rising:
        regime   = "SHORT_COVER"
        modifier = +3 if is_long else -3   # fragile, not full conviction
    elif oi_falling and price_falling:
        regime   = "LONG_LIQUIDATION"
        modifier = -5 if is_long else +4
    else:
        regime   = "NEUTRAL"
        modifier = 0

    return regime, modifier


def analyze_oi(symbol: str, signal_bias: str = "WAIT / NO_TRADE") -> dict:
    """
    Phase 10.8: Main entry point for OI analysis.

    Returns:
        oi_available   : bool
        oi_value       : float — current total OI in contracts
        oi_change_pct  : float — % change over lookback window
        oi_regime      : str
        oi_modifier    : int — score modifier
        reasoning      : str
    """
    binance_sym = BINANCE_SYMBOL_MAP.get(symbol)
    if not binance_sym:
        return {"oi_available": False, "oi_regime": "N/A", "oi_modifier": 0,
                "reasoning": f"OI analysis not available for {symbol} (not a Binance perp)"}

    history = _get_oi_history(binance_sym, period="1h", limit=24)
    if not history or len(history) < 4:
        return {"oi_available": True, "oi_regime": "UNAVAILABLE", "oi_modifier": 0,
                "reasoning": "Binance OI history unavailable"}

    try:
        oi_old  = float(history[0].get("sumOpenInterest", 0))
        oi_new  = float(history[-1].get("sumOpenInterest", 0))
        oi_now  = oi_new
        oi_change_pct = round((oi_new - oi_old) / oi_old * 100, 2) if oi_old > 0 else 0.0

        # Price change: use OI value-based timestamps to derive price change
        price_old = float(history[0].get("sumOpenInterestValue", 0))
        price_new = float(history[-1].get("sumOpenInterestValue", 0))
        # Proxy price change: OI value change / OI change  (rough)
        current_price = _get_current_price(binance_sym)

        # Get a rough price change from the last data point timestamps
        old_oi_usd = float(history[0].get("sumOpenInterestValue", 0))
        new_oi_usd = float(history[-1].get("sumOpenInterestValue", 0))
        price_change_pct = round(
            (new_oi_usd / oi_new - old_oi_usd / oi_old) / (old_oi_usd / oi_old) * 100
            if (oi_old > 0 and old_oi_usd > 0) else 0.0, 2)

        oi_regime, oi_modifier = classify_oi_regime(
            oi_change_pct, price_change_pct, signal_bias)

        return {
            "oi_available":    True,
            "oi_value":        round(oi_now, 2),
            "oi_change_pct":   oi_change_pct,
            "price_change_pct": price_change_pct,
            "oi_regime":       oi_regime,
            "oi_modifier":     oi_modifier,
            "reasoning": (
                f"OI {'+' if oi_change_pct >= 0 else ''}{oi_change_pct}% (24h). "
                f"Regime: {oi_regime}. Modifier: {'+' if oi_modifier >= 0 else ''}{oi_modifier}"
            )
        }
    except Exception as e:
        return {"oi_available": True, "oi_regime": "ERROR", "oi_modifier": 0,
                "reasoning": f"OI calculation error: {e}"}


if __name__ == "__main__":
    import json
    print("=== OI Engine — BTC/USD ===")
    result = analyze_oi("BTC/USD", "LONG_BIAS")
    print(json.dumps(result, indent=2))
