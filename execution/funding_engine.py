"""
funding_engine.py — Phase 8.6: Funding Rate Sentiment Layer
Fetches the current funding rate from Binance's free public API (no key needed)
and converts it into a confidence score modifier.

Funding Rate Logic:
  > +0.10%  : Extreme crowded long  → fade longs, penalty if LONG signal
  +0.03–0.10%: Bullish sentiment    → bonus if LONG signal
  ±0.03%    : Neutral              → 0 modifier
  -0.03 to -0.10%: Bearish sentiment → bonus if SHORT signal
  < -0.10%  : Extreme crowded short → fade shorts, penalty if SHORT signal

Non-crypto assets (XAU, EUR/USD, etc.) skip funding rate and return neutral.
Falls back to neutral silently if Binance API is unreachable.
"""

import requests
import json

# Map from our internal symbol format to Binance perpetual futures ticker
BINANCE_TICKER_MAP = {
    "BTC/USD":  "BTCUSDT",
    "ETH/USD":  "ETHUSDT",
    "SOL/USD":  "SOLUSDT",
    "XRP/USD":  "XRPUSDT",
    "ADA/USD":  "ADAUSDT",
    "DOGE/USD": "DOGEUSDT",
    "DOT/USD":  "DOTUSDT",
    "MATIC/USD":"MATICUSDT",
    "LTC/USD":  "LTCUSDT",
    "LINK/USD": "LINKUSDT",
    "AVAX/USD": "AVAXUSDT",
    "BNB/USD":  "BNBUSDT",
}

FUNDING_API = "https://fapi.binance.com/fapi/v1/premiumIndex"


def get_funding_rate(symbol: str) -> tuple:
    """
    Fetches the latest funding rate for the given symbol.
    Returns (funding_rate_pct, funding_rate_raw) or (None, None) if unavailable.
    funding_rate_pct is expressed as a percentage (e.g. 0.0082 for 0.0082%).
    """
    ticker = BINANCE_TICKER_MAP.get(symbol)
    if not ticker:
        return None, None    # Non-crypto asset — skip

    try:
        resp = requests.get(FUNDING_API, params={"symbol": ticker}, timeout=5)
        data = resp.json()
        raw  = float(data.get("lastFundingRate", 0))
        pct  = round(raw * 100, 6)    # Convert from decimal to %
        return pct, raw
    except Exception:
        return None, None


def analyze_funding(symbol: str, signal_bias: str) -> dict:
    """
    Phase 8.6 main entry point called from main.py or report_engine.
    Returns a funding sentiment dict to be merged into the L4 score or
    surfaced as a governance alert.

    signal_bias: 'LONG_BIAS' | 'SHORT_BIAS' | 'WAIT / NO_TRADE' or similar
    """
    pct, raw = get_funding_rate(symbol)

    # Non-crypto or API unavailable — return neutral
    if pct is None:
        return {
            "funding_available": False,
            "funding_rate_pct":  None,
            "funding_regime":    "N/A",
            "funding_modifier":  0,
            "reasoning":         "Funding rate not applicable for this asset."
        }

    # Classify regime
    if pct > 0.10:
        regime    = "EXTREME_LONG"    # Crowded long → expect flush
    elif pct > 0.03:
        regime    = "BULLISH"
    elif pct < -0.10:
        regime    = "EXTREME_SHORT"   # Crowded short → expect squeeze
    elif pct < -0.03:
        regime    = "BEARISH"
    else:
        regime    = "NEUTRAL"

    # Score modifier based on alignment with signal
    is_long  = "LONG"  in signal_bias
    is_short = "SHORT" in signal_bias
    modifier = 0

    if regime == "EXTREME_LONG":
        modifier = -10 if is_long else +5    # Fade crowded longs
    elif regime == "BULLISH":
        modifier = +3 if is_long else 0
    elif regime == "EXTREME_SHORT":
        modifier = -10 if is_short else +5   # Fade crowded shorts
    elif regime == "BEARISH":
        modifier = +3 if is_short else 0

    return {
        "funding_available": True,
        "funding_rate_pct":  pct,
        "funding_regime":    regime,
        "funding_modifier":  modifier,
        "reasoning": (
            f"Funding Rate: {pct:+.4f}% ({regime}). "
            f"{'Confirms' if modifier > 0 else 'Opposes' if modifier < 0 else 'Neutral to'} "
            f"{signal_bias} bias. Modifier: {'+' if modifier >= 0 else ''}{modifier}pts."
        )
    }


if __name__ == "__main__":
    # Quick CLI test: python execution/funding_engine.py
    for sym in ["BTC/USD", "ETH/USD", "XAU/USD"]:
        print(f"\n[{sym}]")
        result = analyze_funding(sym, "LONG_BIAS")
        print(json.dumps(result, indent=2))
