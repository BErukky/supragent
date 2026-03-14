"""
options_engine.py — Phase 10.10: Options Max Pain & Put-Call Ratio

Fetches live options data from Deribit (public API, no auth required)
for BTC and ETH. Calculates:

  - Max Pain: the strike at which total option payout is minimized
    (market makers benefit from price expiring here).
  - Put-Call Ratio (PCR): total put OI / total call OI.
    PCR > 1.0 = bearish positioning → contrarian bullish signal.
    PCR < 0.7 = bullish positioning → contrarian bearish signal.

Score modifier:
  +5 if PCR is extreme (>1.2 or <0.5) and aligns contrarianly with signal.
  Note: max pain used as informational TP/gravity level only (no score mod).

Usage:
    from execution.options_engine import analyze_options
    result = analyze_options("BTC/USD", current_price=82000)
"""

import requests
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import datetime, timezone

DERIBIT_BASE    = "https://www.deribit.com/api/v2/public"
OPTIONS_ASSETS  = {"BTC/USD": "BTC", "ETH/USD": "ETH"}

# PCR thresholds
PCR_BEARISH_EXTREME = 1.2   # Crowd overly bearish → contrarian bullish
PCR_BULLISH_EXTREME = 0.5   # Crowd overly bullish → contrarian bearish


def _get_instruments(currency: str) -> list:
    """Fetches all active options instruments for a currency."""
    try:
        url = f"{DERIBIT_BASE}/get_instruments"
        resp = requests.get(url, params={
            "currency": currency, "kind": "option", "expired": "false"
        }, timeout=6)
        if resp.status_code == 200:
            return resp.json().get("result", [])
        return []
    except Exception:
        return []


def _get_book_summary(currency: str) -> list:
    """Fetches order book summaries for all options of a currency."""
    try:
        url = f"{DERIBIT_BASE}/get_book_summary_by_currency"
        resp = requests.get(url, params={
            "currency": currency, "kind": "option"
        }, timeout=8)
        if resp.status_code == 200:
            return resp.json().get("result", [])
        return []
    except Exception:
        return []


def _parse_strike_and_type(instrument_name: str) -> tuple:
    """
    Parses Deribit instrument name: BTC-28MAR25-90000-C
    Returns (strike: float, option_type: 'C'|'P', expiry_str: str)
    """
    try:
        parts = instrument_name.split("-")
        if len(parts) < 4:
            return None, None, None
        expiry_str  = parts[1]   # e.g. '28MAR25'
        strike      = float(parts[2])
        option_type = parts[3]   # 'C' or 'P'
        return strike, option_type, expiry_str
    except Exception:
        return None, None, None


def _parse_expiry_date(expiry_str: str) -> datetime | None:
    """Parses Deribit expiry format: '28MAR25' → datetime."""
    try:
        return datetime.strptime(expiry_str, "%d%b%y").replace(tzinfo=timezone.utc)
    except Exception:
        return None


def _days_to_expiry(expiry_dt: datetime) -> int:
    """Returns days until expiry from now."""
    now = datetime.now(timezone.utc)
    return max(0, (expiry_dt - now).days)


def calculate_max_pain(options_data: list, current_price: float) -> dict:
    """
    Calculates max pain price — the strike at which total option payout
    is minimized (i.e., market makers lose least money).
    Returns {max_pain_price, pain_range_low, pain_range_high, strike_oi_map}.
    """
    # Build {strike: {call_oi, put_oi}} map
    strike_map: dict = {}
    for item in options_data:
        name = item.get("instrument_name", "")
        oi   = float(item.get("open_interest", 0) or 0)
        strike, opt_type, _ = _parse_strike_and_type(name)
        if strike is None:
            continue
        if strike not in strike_map:
            strike_map[strike] = {"call_oi": 0.0, "put_oi": 0.0}
        if opt_type == "C":
            strike_map[strike]["call_oi"] += oi
        elif opt_type == "P":
            strike_map[strike]["put_oi"] += oi

    if not strike_map:
        return {"max_pain_price": None, "pain_range_low": None,
                "pain_range_high": None, "strike_count": 0}

    strikes = sorted(strike_map.keys())

    # Total payout at expiry S: sum of intrinsic value x OI for each option
    def total_payout(S: float) -> float:
        total = 0.0
        for strike, ois in strike_map.items():
            total += max(0, S - strike) * ois["call_oi"]   # call payout
            total += max(0, strike - S) * ois["put_oi"]    # put payout
        return total

    min_pain  = float("inf")
    max_pain_strike = strikes[0]
    for s in strikes:
        pain = total_payout(s)
        if pain < min_pain:
            min_pain         = pain
            max_pain_strike  = s

    # Pain range: strikes within 5% of max pain (pinning zone)
    pain_low  = max_pain_strike * 0.95
    pain_high = max_pain_strike * 1.05

    return {
        "max_pain_price":  round(max_pain_strike, 2),
        "pain_range_low":  round(pain_low, 2),
        "pain_range_high": round(pain_high, 2),
        "strike_count":    len(strikes),
    }


def calculate_pcr(options_data: list, max_dte: int = 45) -> dict:
    """
    Calculates Put-Call Ratio from aggregated OI.
    Filters to options expiring within max_dte days for relevance.
    Returns {pcr, total_call_oi, total_put_oi, regime}.
    """
    total_calls = 0.0
    total_puts  = 0.0
    now = datetime.now(timezone.utc)

    for item in options_data:
        name = item.get("instrument_name", "")
        oi   = float(item.get("open_interest", 0) or 0)
        strike, opt_type, expiry_str = _parse_strike_and_type(name)
        if strike is None or expiry_str is None:
            continue
        expiry_dt = _parse_expiry_date(expiry_str)
        if expiry_dt is None:
            continue
        dte = _days_to_expiry(expiry_dt)
        if dte > max_dte:
            continue

        if opt_type == "C":
            total_calls += oi
        elif opt_type == "P":
            total_puts  += oi

    if total_calls == 0:
        return {"pcr": None, "total_call_oi": 0, "total_put_oi": total_puts,
                "regime": "UNAVAILABLE"}

    pcr = round(total_puts / total_calls, 3)

    if pcr > PCR_BEARISH_EXTREME:
        regime = "BEARISH_CROWDED"    # Contrarian → bullish signal
    elif pcr < PCR_BULLISH_EXTREME:
        regime = "BULLISH_CROWDED"    # Contrarian → bearish signal
    elif pcr > 1.0:
        regime = "SLIGHTLY_BEARISH"
    else:
        regime = "SLIGHTLY_BULLISH"

    return {
        "pcr":            pcr,
        "total_call_oi":  round(total_calls, 2),
        "total_put_oi":   round(total_puts, 2),
        "regime":         regime,
    }


def analyze_options(symbol: str, current_price: float = None,
                    signal_bias: str = "WAIT / NO_TRADE") -> dict:
    """
    Phase 10.10: Main entry point for options analysis.

    Returns:
        options_available  : bool
        max_pain           : dict
        pcr_data           : dict
        near_max_pain      : bool — price within 2% of max pain
        options_modifier   : int — score modifier (0 or +5)
        reasoning          : str
    """
    currency = OPTIONS_ASSETS.get(symbol)
    if not currency:
        return {"options_available": False, "options_modifier": 0,
                "reasoning": f"Options analysis not available for {symbol}"}

    summaries = _get_book_summary(currency)
    if not summaries:
        return {"options_available": True, "options_modifier": 0,
                "max_pain": {}, "pcr_data": {},
                "reasoning": "Deribit options data unavailable"}

    max_pain = calculate_max_pain(summaries, current_price or 0)
    pcr_data = calculate_pcr(summaries, max_dte=45)

    # Near max pain: price within 2% of max pain strike
    near_max_pain = False
    gravity_note  = ""
    if max_pain.get("max_pain_price") and current_price:
        mp  = max_pain["max_pain_price"]
        pct = abs(current_price - mp) / mp * 100
        if pct < 2.0:
            near_max_pain = True
            gravity_note  = f"Price within 2% of max pain ({mp:,.0f}) — pinning likely"

    # Score modifier: contrarian PCR signal
    options_modifier = 0
    is_long  = "LONG"  in signal_bias
    is_short = "SHORT" in signal_bias
    pcr_regime = pcr_data.get("regime", "")

    if is_long  and pcr_regime == "BEARISH_CROWDED":
        options_modifier = +5   # Crowd too bearish → contrarian long boost
    elif is_short and pcr_regime == "BULLISH_CROWDED":
        options_modifier = +5   # Crowd too bullish → contrarian short boost
    elif is_long  and pcr_regime == "BULLISH_CROWDED":
        options_modifier = -3   # Crowd aligned bearish risk for longs
    elif is_short and pcr_regime == "BEARISH_CROWDED":
        options_modifier = -3

    pcr_val = pcr_data.get("pcr", "N/A")
    reasons = []
    if pcr_val != "N/A":
        reasons.append(f"PCR:{pcr_val} ({pcr_regime})")
    if max_pain.get("max_pain_price"):
        reasons.append(f"MaxPain:{max_pain['max_pain_price']:,.0f}")
    if gravity_note:
        reasons.append(gravity_note)
    if options_modifier != 0:
        reasons.append(f"Modifier:{'+' if options_modifier > 0 else ''}{options_modifier}")

    return {
        "options_available":  True,
        "max_pain":           max_pain,
        "pcr_data":           pcr_data,
        "near_max_pain":      near_max_pain,
        "options_modifier":   options_modifier,
        "reasoning":          " | ".join(reasons) or "Options data loaded, no extreme positioning"
    }


if __name__ == "__main__":
    import json
    print("=== Options Engine — BTC/USD ===")
    result = analyze_options("BTC/USD", current_price=82000, signal_bias="LONG_BIAS")
    print(json.dumps(result, indent=2, default=str))
