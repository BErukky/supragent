import argparse
import sys
import pandas as pd
import json
import os
import numpy as np
from datetime import datetime, timezone

# Ensure we can import structure_engine from the same directory
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
try:
    from structure_engine import analyze_layer1
except ImportError:
    from execution.structure_engine import analyze_layer1

# ─────────────────────────────────────────────────────────────────────────────
# Phase 7.5: Trading Session Timing Bonus
# Institutional activity is heavily concentrated in 3 windows (UTC).
# Signals during active sessions have higher follow-through probability.
# ─────────────────────────────────────────────────────────────────────────────
# Phase 8.7: ICT Kill Zones — precise 30–60 min windows where institutions execute
# These replace the broad session windows. Kill zones are empirically the most
# reliable periods in price action: London (02:00–05:00) sweeps the Asian range
# and sets the weekly direction; NY (08:30–11:00) continues or reverses it.
_KILL_ZONES = [
    # (start_h, start_m, end_h, end_m), name, bonus
    ((2,  0,  5,  0), "LONDON_KILL_ZONE",  +8),   # Sweeps Asian range, sets week direction
    ((8, 30, 11,  0), "NY_KILL_ZONE",      +8),   # Most liquid, highest follow-through
    ((15, 0, 16,  0), "LONDON_CLOSE",      +5),   # Stops run, common reversals
    ((12, 0, 15,  0), "LONDON_NY_OVERLAP", +5),   # Broad overlap (outside tight KZ windows)
    ((7,  0,  8, 30), "PRE_LONDON",        +3),   # London pre-market
    ((20, 0, 24,  0), "DEAD_ZONE",         -5),   # Very low liquidity, avoid
    ((0,  0,  2,  0), "DEAD_ZONE_LATE",    -5),   # Late dead zone
    ((5,  0,  7,  0), "ASIAN_CLOSE",       -1),   # Asian session closing, fading
]

def get_session_info(utc_hour=None, utc_minute=None):
    """
    Phase 8.7: Returns (session_name, bonus_pts) using precise ICT Kill Zone windows.
    Defaults to current UTC time if not provided.
    """
    now_utc = datetime.now(timezone.utc)
    if utc_hour   is None: utc_hour   = now_utc.hour
    if utc_minute is None: utc_minute = now_utc.minute

    current_minutes = utc_hour * 60 + utc_minute

    for (sh, sm, eh, em), name, bonus in _KILL_ZONES:
        start_min = sh * 60 + sm
        end_min   = eh * 60 + em
        if start_min <= current_minutes < end_min:
            return name, bonus

    return "OFF_HOURS", 0


# ─────────────────────────────────────────────────────────────────────────────
# Phase 7.6: 3-Way Trend Coherence (HTF + 4H + LTF)
# Replaces the old 2-way HTF/LTF check.
# All 3 aligned → full score. 2/3 → 70%. 1/3 → 30%.
# ─────────────────────────────────────────────────────────────────────────────

def calculate_trend_coherence_3way(htf_state, itf_state, ltf_state,
                                    htf_conf, itf_conf, ltf_conf):
    """
    Phase 7.6: 3-way timeframe coherence (HTF / 4H intermediate / LTF).
    Returns coherence float 0.0–1.0.
    """
    states = {"BULLISH": 1, "BEARISH": -1, "NEUTRAL": 0, "RANGE": 0, "UNCLEAR": 0}
    h = states.get(htf_state, 0)
    m = states.get(itf_state, 0)
    l = states.get(ltf_state, 0)

    aligned_count = sum(1 for v in [h, m, l] if v != 0 and v == (h or m or l))

    # How many non-zero TFs agree on direction
    directional = [v for v in [h, m, l] if v != 0]
    if not directional:
        base_coherence = 0.4   # All neutral — no trend, preserve some base
    else:
        dominant = max(set(directional), key=directional.count)
        agree = directional.count(dominant)
        total = len(directional)
        if agree == total:
            base_coherence = 1.0   # All directional TFs agree
        elif agree / total >= 0.67:
            base_coherence = 0.7   # 2/3 agree
        else:
            base_coherence = 0.3   # Conflicting TFs

    # Weight by average structural confidence across TFs
    avg_conf = (htf_conf + itf_conf + ltf_conf) / 3.0
    return round(float(base_coherence * avg_conf), 2)


def calculate_trend_coherence_4way(dtf_state, htf_state, itf_state, ltf_state,
                                    dtf_conf, htf_conf, itf_conf, ltf_conf):
    """
    Phase 9.2: 4-way timeframe coherence (1D / 4H / 1H / 15M).
    Returns coherence float 0.0–1.0.
    """
    states = {"BULLISH": 1, "BEARISH": -1, "NEUTRAL": 0, "RANGE": 0, "UNCLEAR": 0}
    vals   = [states.get(s, 0) for s in [dtf_state, htf_state, itf_state, ltf_state]]
    confs  = [dtf_conf, htf_conf, itf_conf, ltf_conf]

    directional = [v for v in vals if v != 0]
    if not directional:
        base_coherence = 0.4
    else:
        dominant = max(set(directional), key=directional.count)
        agree    = directional.count(dominant)
        total    = len(directional)
        ratio    = agree / total
        if ratio == 1.0:   base_coherence = 1.0
        elif ratio >= 0.75: base_coherence = 0.80
        elif ratio >= 0.5:  base_coherence = 0.50
        else:               base_coherence = 0.20

    avg_conf = sum(confs) / len(confs)
    return round(float(base_coherence * avg_conf), 2)

def calculate_trend_coherence(htf_state, ltf_state, htf_conf, ltf_conf):
    # A3 Fix: Corrected neutral/partial coherence branch values.
    # Both neutral → near-zero coherence (no direction at all).
    # One directional, one neutral → moderate coherence (partial signal).
    states = {"BULLISH": 1, "BEARISH": -1, "NEUTRAL": 0, "RANGE": 0, "UNCLEAR": 0}
    h_val = states.get(htf_state, 0)
    l_val = states.get(ltf_state, 0)

    coherence = 0.0
    if h_val == l_val and h_val != 0:    coherence = 1.0   # Both aligned directionally
    elif h_val != 0 and l_val != 0:      coherence = 0.2   # Both directional but opposing
    elif h_val == 0 and l_val == 0:      coherence = 0.1   # Both neutral — no trend signal
    else:                                coherence = 0.5   # One directional, one neutral

    total_conf = (htf_conf + ltf_conf) / 2.0
    return round(float(coherence * total_conf), 2)


def get_layer1_analysis(csv_path):
    try:
        df = pd.read_csv(csv_path)
        return analyze_layer1(df)
    except Exception as e:
        print(f"Error processing {csv_path}: {e}")
        return None


def determine_bias(htf_state, ltf_state, itf_state=None, dtf_state=None, ltf_conf=0.0):
    """
    Determines final trade bias from 2–4 timeframes. Highest TF has most weight.
    A1 Fix: Counter-trend signals now require ltf_conf > 0.70 to avoid weak-tilt false signals.
    B4 Fix: No-majority fallback uses htf_state (4H) not dtf (daily) for intraday context.
    """
    # Build list of available TFs from highest to lowest
    tfs = [s for s in [dtf_state, htf_state, itf_state, ltf_state] if s]

    if len(tfs) >= 3:
        bullish_count = sum(1 for s in tfs if s == "BULLISH")
        bearish_count = sum(1 for s in tfs if s == "BEARISH")
        majority = (len(tfs) // 2) + 1    # >50%, e.g. 2/3 or 3/4
        
        if bullish_count >= majority: return "LONG_BIAS"
        if bearish_count >= majority: return "SHORT_BIAS"
        
        # ─ A1 Fix: Counter-Trend requires strong LTF conviction (conf > 0.70) ─────
        if ltf_state == "BULLISH" and ltf_conf > 0.70: return "LONG_BIAS (Counter-Trend)"
        if ltf_state == "BEARISH" and ltf_conf > 0.70: return "SHORT_BIAS (Counter-Trend)"
        
        # B4 Fix: Fallback to HTF (4H/1H) not DTF (daily) for intraday context
        if htf_state == "BULLISH": return "WAIT / LONG_RECOVERY"
        if htf_state == "BEARISH": return "WAIT / SHORT_RECOVERY"
        return "WAIT / NO_TRADE"

    # 2-way fallback (HTF + LTF only)
    if htf_state == "BULLISH" and ltf_state == "BULLISH": return "LONG_BIAS"
    if htf_state == "BEARISH" and ltf_state == "BEARISH": return "SHORT_BIAS"
    
    # ─ A1 Fix: Counter-Trend requires strong LTF conviction (conf > 0.70) ─────────
    if ltf_state == "BULLISH" and htf_state == "BEARISH" and ltf_conf > 0.70:
        return "LONG_BIAS (Counter-Trend)"
    if ltf_state == "BEARISH" and htf_state == "BULLISH" and ltf_conf > 0.70:
        return "SHORT_BIAS (Counter-Trend)"
    
    if htf_state == "BULLISH" and ltf_state in ["NEUTRAL","RANGE"]: return "WAIT / LONG_RECOVERY"
    if htf_state == "BEARISH" and ltf_state in ["NEUTRAL","RANGE"]: return "WAIT / SHORT_RECOVERY"
    return "WAIT / NO_TRADE"



def run_confluence_analysis(htf_csv, ltf_csv, itf_csv=None, dtf_csv=None):
    """
    Phase 9.2: Accepts optional DTF (daily) and ITF (4H) CSVs.
    Routes to 4-way, 3-way, or 2-way coherence automatically.
    """
    # 1. HTF analysis
    htf_analysis = get_layer1_analysis(htf_csv)
    if not htf_analysis: return None
    htf_state = htf_analysis['structure_bias']
    htf_conf  = htf_analysis['structure_confidence']

    # 2. LTF analysis
    ltf_analysis = get_layer1_analysis(ltf_csv)
    if not ltf_analysis: return None
    ltf_state = ltf_analysis['structure_bias']
    ltf_conf  = ltf_analysis['structure_confidence']

    # 3. ITF (4H) — optional
    itf_analysis = None
    itf_state    = "NEUTRAL"
    itf_conf     = 0.5
    if itf_csv and os.path.exists(itf_csv):
        itf_analysis = get_layer1_analysis(itf_csv)
        if itf_analysis:
            itf_state = itf_analysis['structure_bias']
            itf_conf  = itf_analysis['structure_confidence']

    # 4. DTF (Daily) — optional, Phase 9.2
    dtf_analysis = None
    dtf_state    = "NEUTRAL"
    dtf_conf     = 0.5
    if dtf_csv and os.path.exists(dtf_csv):
        dtf_analysis = get_layer1_analysis(dtf_csv)
        if dtf_analysis:
            dtf_state = dtf_analysis['structure_bias']
            dtf_conf  = dtf_analysis['structure_confidence']

    # 5. Coherence scoring — 4-way > 3-way > 2-way
    if dtf_analysis and itf_analysis:
        coherence_score = calculate_trend_coherence_4way(
            dtf_state, htf_state, itf_state, ltf_state,
            dtf_conf, htf_conf, itf_conf, ltf_conf)
        tf_label = f"1D({dtf_state}) 4H({htf_state}) 1H({itf_state}) 15M({ltf_state})"
    elif itf_analysis:
        coherence_score = calculate_trend_coherence_3way(
            htf_state, itf_state, ltf_state, htf_conf, itf_conf, ltf_conf)
        tf_label = f"HTF({htf_state}) 4H({itf_state}) LTF({ltf_state})"
    else:
        coherence_score = calculate_trend_coherence(htf_state, ltf_state, htf_conf, ltf_conf)
        tf_label = f"HTF({htf_state}) LTF({ltf_state})"

    # 6. Session Timing
    session_name, session_bonus = get_session_info()

    # 7. Final bias — include DTF if available
    # Pass ltf_conf so determine_bias can gate counter-trend signals properly (A1 Fix)
    bias = determine_bias(htf_state, ltf_state,
                          itf_state if itf_analysis else None,
                          dtf_state if dtf_analysis else None,
                          ltf_conf=ltf_conf)

    # 8. A2 Fix: Corrected confluence floor — both values now in the same unit (0.0–1.0).
    # Previously mixed coherence_score*100 (near-zero) with ltf_conf (also near-zero).
    if coherence_score < 0.15 and max(ltf_conf, htf_conf) < 0.5:
        if "WAIT" not in bias:
            bias = f"WAIT / NO_TRADE (Confluence Floor)"

    l2_score = round(min(35, max(0, (30 * coherence_score) + session_bonus)), 2)

    return {
        "final_signal":     bias,
        "coherence_score":  coherence_score,
        "layer2_score":     l2_score,
        "session":          session_name,
        "session_bonus":    session_bonus,
        "reasoning": (
            f"Trend Coherence: {round(coherence_score*100, 1)}%. {tf_label}. "
            f"Session: {session_name} ({'+' if session_bonus >= 0 else ''}{session_bonus}pts)"
        ),
        "details": {
            "dtf_layer1":        dtf_analysis,
            "htf_layer1":        htf_analysis,
            "itf_layer1":        itf_analysis,
            "ltf_layer1":        ltf_analysis,
            "raw_ltf_structure": ltf_analysis['raw_structure']
        }
    }



def main():
    parser = argparse.ArgumentParser(description='Analyze Multi-Timeframe Confluence v3 (Phase 7).')
    parser.add_argument('--htf', type=str, required=True, help='Path to HTF CSV')
    parser.add_argument('--ltf', type=str, required=True, help='Path to LTF CSV')
    parser.add_argument('--itf', type=str, help='Path to 4H intermediate TF CSV (optional)')
    args = parser.parse_args()

    result = run_confluence_analysis(args.htf, args.ltf, args.itf)
    if result:
        print(json.dumps(result, indent=2))
    else:
        sys.exit(1)

if __name__ == "__main__":
    main()
