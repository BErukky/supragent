"""
macro_engine.py — Phase 10.9: Cross-Asset Correlation Filter

Fetches DXY (Dollar Index) and SPX (S&P 500) and checks whether the
macro environment supports or opposes the current signal bias.

BTC/crypto assets have an inverse correlation with DXY.
Gold (XAU) has an even tighter inverse correlation (~0.85).
Forex pairs are inherently affected by their USD component.

Conflict rules:
  BTC LONG  + DXY BULLISH → −15 pts  (major headwind)
  BTC LONG  + DXY BEARISH → +8 pts   (macro tailwind)
  BTC SHORT + DXY BULLISH → +8 pts   (aligned)
  BTC SHORT + DXY BEARISH → −15 pts  (contra)

Gold modifiers are stronger: −20 / +10.

Usage:
    from execution.macro_engine import analyze_macro
    result = analyze_macro("BTC/USD", "LONG_BIAS")
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd
import numpy as np
from datetime import datetime

MACRO_ASSETS = {
    "DXY": "DX-Y.NYB",    # Dollar Index
    "SPX": "^GSPC",        # S&P 500
}

# Asset categories and their DXY relationship
ASSET_PROFILES = {
    # Crypto — inverse DXY
    "BTC/USD": {"dxy_conflict_mod": -15, "dxy_aligned_mod": +8,  "category": "CRYPTO"},
    "ETH/USD": {"dxy_conflict_mod": -15, "dxy_aligned_mod": +8,  "category": "CRYPTO"},
    "SOL/USD": {"dxy_conflict_mod": -12, "dxy_aligned_mod": +6,  "category": "CRYPTO"},
    "XRP/USD": {"dxy_conflict_mod": -10, "dxy_aligned_mod": +5,  "category": "CRYPTO"},
    # Gold — strong inverse DXY
    "XAU/USD": {"dxy_conflict_mod": -20, "dxy_aligned_mod": +10, "category": "GOLD"},
    # Forex — pairs against USD directly
    "EUR/USD": {"dxy_conflict_mod": -12, "dxy_aligned_mod": +7,  "category": "FOREX"},
    "GBP/USD": {"dxy_conflict_mod": -12, "dxy_aligned_mod": +7,  "category": "FOREX"},
}


def _fetch_macro_data(yf_symbol: str, days: int = 60) -> pd.DataFrame:
    """Fetches 1D OHLCV for a macro index from yfinance."""
    try:
        import yfinance as yf
        data = yf.download(yf_symbol, period=f"{days}d", interval="1d", progress=False)
        if data.empty:
            return pd.DataFrame()
        df = data.reset_index()
        df.columns = [c[0].lower() if isinstance(c, tuple) else c.lower() for c in df.columns]
        df["close"] = pd.to_numeric(df["close"], errors="coerce")
        return df[["close"]].dropna()
    except Exception:
        return pd.DataFrame()


def _classify_trend(df: pd.DataFrame, short=10, long=20) -> tuple:
    """
    Classifies trend state using dual MA crossover on daily closes.
    Returns (state, confidence) where state is BULLISH / BEARISH / NEUTRAL.
    """
    if len(df) < long + 2:
        return "NEUTRAL", 0.4

    closes = df['close'].values
    sma_s  = float(pd.Series(closes).rolling(short).mean().iloc[-1])
    sma_l  = float(pd.Series(closes).rolling(long).mean().iloc[-1])

    # Separation as % of long MA
    sep_pct = abs(sma_s - sma_l) / sma_l * 100

    if sma_s > sma_l:
        state = "BULLISH"
    elif sma_s < sma_l:
        state = "BEARISH"
    else:
        state = "NEUTRAL"

    # Confidence grows with MA separation (capped at 0.9)
    confidence = round(min(0.9, 0.5 + sep_pct * 0.1), 2)
    return state, confidence


def analyze_macro(symbol: str, signal_bias: str = "WAIT / NO_TRADE") -> dict:
    """
    Phase 10.9: Main entry point for cross-asset macro analysis.

    Returns:
        macro_available : bool
        dxy_state       : BULLISH | BEARISH | NEUTRAL
        spx_state       : BULLISH | BEARISH | NEUTRAL
        macro_regime    : RISK_ON | RISK_OFF | NEUTRAL
        macro_modifier  : int — score modifier
        dxy_conflict    : bool
        reasoning       : str
    """
    profile = ASSET_PROFILES.get(symbol)
    if not profile:
        return {"macro_available": False, "macro_modifier": 0,
                "dxy_state": "N/A", "spx_state": "N/A", "macro_regime": "N/A",
                "reasoning": f"No macro correlation profile for {symbol}"}

    # Fetch DXY and SPX
    df_dxy = _fetch_macro_data(MACRO_ASSETS["DXY"], days=60)
    df_spx = _fetch_macro_data(MACRO_ASSETS["SPX"], days=60)

    dxy_state, dxy_conf = _classify_trend(df_dxy) if not df_dxy.empty else ("NEUTRAL", 0.4)
    spx_state, spx_conf = _classify_trend(df_spx) if not df_spx.empty else ("NEUTRAL", 0.4)

    # Macro regime
    if spx_state == "BULLISH" and dxy_state == "BEARISH":
        macro_regime = "RISK_ON"   # Classic: stocks up, dollar down
    elif spx_state == "BEARISH" and dxy_state == "BULLISH":
        macro_regime = "RISK_OFF"  # Classic: stocks down, dollar up (flight to safety)
    else:
        macro_regime = "NEUTRAL"

    is_long  = "LONG"  in signal_bias
    is_short = "SHORT" in signal_bias

    # Determine conflict/alignment based on asset category
    category = profile["category"]
    macro_modifier = 0
    dxy_conflict   = False
    reason_parts   = []

    if category in ("CRYPTO", "GOLD", "FOREX"):
        # DXY inverse relationship
        if is_long and dxy_state == "BULLISH":
            macro_modifier = profile["dxy_conflict_mod"]
            dxy_conflict   = True
            reason_parts.append(f"DXY {dxy_state} conflicts with LONG {symbol}")
        elif is_long and dxy_state == "BEARISH":
            macro_modifier = profile["dxy_aligned_mod"]
            reason_parts.append(f"DXY {dxy_state} supports LONG {symbol}")
        elif is_short and dxy_state == "BEARISH":
            macro_modifier = profile["dxy_conflict_mod"]
            dxy_conflict   = True
            reason_parts.append(f"DXY {dxy_state} conflicts with SHORT {symbol}")
        elif is_short and dxy_state == "BULLISH":
            macro_modifier = profile["dxy_aligned_mod"]
            reason_parts.append(f"DXY {dxy_state} supports SHORT {symbol}")
        else:
            reason_parts.append(f"DXY {dxy_state} — neutral signal alignment")

    # SPX context for crypto
    if category == "CRYPTO" and spx_state != "NEUTRAL":
        if (is_long and spx_state == "BEARISH") or (is_short and spx_state == "BULLISH"):
            macro_modifier -= 5
            reason_parts.append(f"SPX {spx_state} adds headwind")
        elif (is_long and spx_state == "BULLISH") or (is_short and spx_state == "BEARISH"):
            macro_modifier += 3
            reason_parts.append(f"SPX {spx_state} adds tailwind")

    return {
        "macro_available":  True,
        "dxy_state":        dxy_state,
        "dxy_confidence":   dxy_conf,
        "spx_state":        spx_state,
        "spx_confidence":   spx_conf,
        "macro_regime":     macro_regime,
        "macro_modifier":   macro_modifier,
        "dxy_conflict":     dxy_conflict,
        "asset_category":   category,
        "reasoning": " | ".join(reason_parts) or f"DXY:{dxy_state} SPX:{spx_state} — macro neutral"
    }


if __name__ == "__main__":
    import json
    print("=== Macro Engine — BTC/USD LONG_BIAS ===")
    result = analyze_macro("BTC/USD", "LONG_BIAS")
    print(json.dumps(result, indent=2))
    print("\n=== Macro Engine — XAU/USD LONG_BIAS ===")
    result2 = analyze_macro("XAU/USD", "LONG_BIAS")
    print(json.dumps(result2, indent=2))
