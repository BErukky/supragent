import pandas as pd
import numpy as np
import argparse
import sys
import json

# ─────────────────────────────────────────────────────────────────────────────
# Phase 3.2: Volume Confirmation
# Volume ratio measures current candle volume vs 20-period average.
# High-volume sweeps (institutional participation) score much higher than
# thin-market noise sweeps. This directly improves L1 sweep signal precision.
#
# Phase 3.3: Change of Character (CHoCH)
# CHoCH is detected when price breaks the last opposing swing in the
# established trend — the earliest possible reversal warning in ICT/SMC.
# ─────────────────────────────────────────────────────────────────────────────

def calculate_atr(df, period=14):
    """
    Calculates Average True Range (ATR) over `period` candles.
    ATR = average of max(H-L, |H-PrevC|, |L-PrevC|) over period bars.
    Used by report_engine for dynamic TP/SL and passed through the result.
    """
    if len(df) < period + 1:
        return float((df['high'] - df['low']).mean())
    high  = df['high']
    low   = df['low']
    close = df['close'].shift(1)
    tr = pd.concat([
        high - low,
        (high - close).abs(),
        (low  - close).abs()
    ], axis=1).max(axis=1)
    return float(tr.rolling(period).mean().iloc[-1])


# ─────────────────────────────────────────────────────────────────────────────
# Phase 7 Analytical Additions
# ─────────────────────────────────────────────────────────────────────────────

def calculate_adx(df, period=14):
    """
    Phase 7.1 + 10.3: ADX Regime Gate + Slope (acceleration/deceleration).
    Returns (adx_value, regime, slope_regime).
    slope_regime: ACCELERATING | DECELERATING | FLAT
    """
    if len(df) < period * 2:
        return 0.0, "RANGING", "FLAT"

    high  = df['high'].values
    low   = df['low'].values
    close = df['close'].values

    plus_dm  = np.where((high[1:] - high[:-1]) > (low[:-1] - low[1:]),
                         np.maximum(high[1:] - high[:-1], 0), 0)
    minus_dm = np.where((low[:-1] - low[1:]) > (high[1:] - high[:-1]),
                         np.maximum(low[:-1] - low[1:], 0), 0)

    tr = np.maximum(high[1:] - low[1:],
         np.maximum(abs(high[1:] - close[:-1]),
                    abs(low[1:]  - close[:-1])))

    def wilder_smooth(arr, p):
        out = np.zeros(len(arr))
        out[p-1] = arr[:p].sum()
        for i in range(p, len(arr)):
            out[i] = out[i-1] - (out[i-1] / p) + arr[i]
        return out

    atr_s    = wilder_smooth(tr, period)
    plus_s   = wilder_smooth(plus_dm, period)
    minus_s  = wilder_smooth(minus_dm, period)

    with np.errstate(divide='ignore', invalid='ignore'):
        plus_di  = np.where(atr_s != 0, 100 * plus_s  / atr_s, 0)
        minus_di = np.where(atr_s != 0, 100 * minus_s / atr_s, 0)
        dx       = np.where((plus_di + minus_di) != 0,
                            100 * np.abs(plus_di - minus_di) / (plus_di + minus_di), 0)

    adx_arr = wilder_smooth(dx, period)
    adx_val = float(adx_arr[-1])

    if adx_val > 25:   regime = "TRENDING"
    elif adx_val > 20: regime = "WEAK"
    else:              regime = "RANGING"

    # Phase 10.3: 5-candle ADX slope
    if len(adx_arr) >= 6:
        slope = float(adx_arr[-1] - adx_arr[-6])
        if slope > 1.5:    slope_regime = "ACCELERATING"
        elif slope < -1.5: slope_regime = "DECELERATING"
        else:              slope_regime = "FLAT"
    else:
        slope_regime = "FLAT"

    return round(adx_val, 2), regime, slope_regime



def detect_order_blocks(df, structure, impulse_threshold=0.005):
    """
    Phase 7.2: Order Block Detection.
    An OB is the last opposing candle before a significant impulse move.
    - Bullish OB: last BEARISH candle before a bullish impulse → demand zone
    - Bearish OB: last BULLISH candle before a bearish impulse → supply zone
    Returns up to 3 most recent active OBs.
    """
    obs = []
    closes = df['close'].values
    opens  = df['open'].values
    highs  = df['high'].values
    lows   = df['low'].values
    n = len(closes)
    current_price = closes[-1]

    for i in range(3, n - 3):
        # Detect bullish impulse starting at candle i+1
        impulse_up = (closes[i+1] - closes[i]) / closes[i] if closes[i] != 0 else 0
        if impulse_up > impulse_threshold:
            # Look back for last bearish candle (close < open)
            for j in range(i, max(i-5, 0)-1, -1):
                if closes[j] < opens[j]:   # bearish candle
                    ob_high = highs[j]
                    ob_low  = lows[j]
                    active  = ob_low <= current_price <= ob_high
                    near    = abs(current_price - ob_low) / ob_low < 0.003 if not active else False
                    obs.append({"type": "BULLISH_OB", "high": round(ob_high, 4),
                                "low": round(ob_low, 4), "index": j,
                                "active": active, "near": near})
                    break

        # Detect bearish impulse starting at candle i+1
        impulse_dn = (closes[i] - closes[i+1]) / closes[i] if closes[i] != 0 else 0
        if impulse_dn > impulse_threshold:
            for j in range(i, max(i-5, 0)-1, -1):
                if closes[j] > opens[j]:   # bullish candle
                    ob_high = highs[j]
                    ob_low  = lows[j]
                    active  = ob_low <= current_price <= ob_high
                    near    = abs(current_price - ob_high) / ob_high < 0.003 if not active else False
                    obs.append({"type": "BEARISH_OB", "high": round(ob_high, 4),
                                "low": round(ob_low, 4), "index": j,
                                "active": active, "near": near})
                    break

    # Return only the 3 most recent, deduplicated by index
    seen = set()
    result = []
    for ob in reversed(obs):
        if ob['index'] not in seen:
            seen.add(ob['index'])
            result.append(ob)
        if len(result) == 3:
            break
    return result


def detect_fvgs(df, min_gap_pct=0.001):
    """
    Phase 7.3: Fair Value Gap (FVG) Detection.
    Three-candle imbalance zones price is statistically drawn to fill.
    - Bullish FVG: candle[i-2].high < candle[i].low  → gap below current price
    - Bearish FVG: candle[i-2].low  > candle[i].high → gap above current price
    Only returns FVGs from the last 50 candles (older ones likely filled).
    """
    fvgs = []
    highs  = df['high'].values
    lows   = df['low'].values
    closes = df['close'].values
    n = len(closes)
    current_price = closes[-1]
    lookback = min(50, n - 2)

    for i in range(n - lookback, n):
        if i < 2: continue

        # Bullish FVG: gap between candle[i-2] high and candle[i] low
        if highs[i-2] < lows[i]:
            gap_pct = (lows[i] - highs[i-2]) / highs[i-2]
            if gap_pct >= min_gap_pct:
                top = lows[i]
                bottom = highs[i-2]
                inside = bottom <= current_price <= top
                approaching = not inside and abs(current_price - top) / top < 0.002
                fvgs.append({"type": "BULLISH_FVG", "top": round(top, 4),
                             "bottom": round(bottom, 4), "age_candles": n - i,
                             "inside": inside, "approaching": approaching})

        # Bearish FVG: gap between candle[i-2] low and candle[i] high
        if lows[i-2] > highs[i]:
            gap_pct = (lows[i-2] - highs[i]) / lows[i-2]
            if gap_pct >= min_gap_pct:
                top = lows[i-2]
                bottom = highs[i]
                inside = bottom <= current_price <= top
                approaching = not inside and abs(current_price - bottom) / bottom < 0.002
                fvgs.append({"type": "BEARISH_FVG", "top": round(top, 4),
                             "bottom": round(bottom, 4), "age_candles": n - i,
                             "inside": inside, "approaching": approaching})

    # Most recent FVGs first, capped at 5
    return sorted(fvgs, key=lambda x: x['age_candles'])[:5]


def calculate_premium_discount(current_price, structure):
    """
    Phase 7.4: Premium / Discount Zone.
    Uses the most recent significant swing range to determine if price is
    expensive (premium → favours shorts) or cheap (discount → favours longs).
    Returns zone, pct_position, swing_high, swing_low.
    """
    highs = [s['price'] for s in structure if 'H' in s['type']]
    lows  = [s['price'] for s in structure if 'L' in s['type']]
    if not highs or not lows:
        return "NEUTRAL", 50.0, None, None

    swing_high = max(highs)
    swing_low  = min(lows)
    rng = swing_high - swing_low
    if rng == 0:
        return "NEUTRAL", 50.0, swing_high, swing_low

    pct_pos = round((current_price - swing_low) / rng * 100, 1)
    zone    = "DISCOUNT" if current_price < (swing_low + rng * 0.5) else "PREMIUM"
    return zone, pct_pos, round(swing_high, 4), round(swing_low, 4)


def identify_swings(df, length=5):
    """
    Identifies Swing Highs and Swing Lows based on a rolling window.
    """
    df['is_swing_high'] = False
    df['is_swing_low'] = False
    
    for i in range(length, len(df) - length):
        current_high = df['high'].iloc[i]
        left_highs = df['high'].iloc[i-length:i]
        right_highs = df['high'].iloc[i+1:i+length+1]
        
        if current_high > left_highs.max() and current_high > right_highs.max():
            df.at[i, 'is_swing_high'] = True

        current_low = df['low'].iloc[i]
        left_lows = df['low'].iloc[i-length:i]
        right_lows = df['low'].iloc[i+1:i+length+1]
        
        if current_low < left_lows.min() and current_low < right_lows.min():
            df.at[i, 'is_swing_low'] = True
            
    return df

def calculate_swing_clarity(df, index, length=5):
    """
    Measures the 'prominence' of a swing point as a numeric confidence weight (0.0-1.0).
    Higher clarity = more significant rejection from the level.
    """
    is_high = df.at[index, 'is_swing_high']
    price = df.at[index, 'high'] if is_high else df.at[index, 'low']
    
    nearby = df.iloc[index-length:index+length+1]
    # Simple clarity: range of the swing candle relative to average local volatility
    local_range = nearby['high'].max() - nearby['low'].min()
    if local_range == 0: return 0.5
    
    # Distance from nearest high/low
    if is_high:
        rejection = (price - nearby['low'].min()) / local_range
    else:
        rejection = (nearby['high'].max() - price) / local_range
        
    return min(1.0, max(0.1, rejection))

def detect_liquidity_pools(structure, variance=0.001):
    pools = []
    highs = [s for s in structure if 'H' in s['type']]
    lows = [s for s in structure if 'L' in s['type']]
    
    # Check for Equal Highs (BSL)
    for i in range(len(highs)):
        for j in range(i + 1, len(highs)):
            diff = abs(highs[i]['price'] - highs[j]['price']) / highs[i]['price']
            if diff <= variance:
                # Confidence weight based on how 'equal' they are
                weight = 1.0 - (diff / variance)
                pools.append({"type": "BUY_SIDE", "level": max(highs[i]['price'], highs[j]['price']), "weight": weight, "indices": [highs[i]['index'], highs[j]['index']]})
                
    # Check for Equal Lows (SSL)
    for i in range(len(lows)):
        for j in range(i + 1, len(lows)):
            diff = abs(lows[i]['price'] - lows[j]['price']) / lows[i]['price']
            if diff <= variance:
                weight = 1.0 - (diff / variance)
                pools.append({"type": "SELL_SIDE", "level": min(lows[i]['price'], lows[j]['price']), "weight": weight, "indices": [lows[i]['index'], lows[j]['index']]})
                
    return pools

def detect_sweeps(df, pools):
    active_sweeps = []
    for i in range(len(df)):
        current_high = df['high'].iloc[i]
        current_low = df['low'].iloc[i]
        current_close = df['close'].iloc[i]
        
        for pool in pools:
            if pool['type'] == "BUY_SIDE":
                if current_high > pool['level'] and current_close < pool['level']:
                    magnitude = (current_high - pool['level']) / pool['level']
                    confidence = min(1.0, pool['weight'] * (1.0 + magnitude * 100))
                    active_sweeps.append({"type": "BUY_SIDE_SWEEP", "index": int(i), "level": pool['level'], "confidence": confidence})
            elif pool['type'] == "SELL_SIDE":
                if current_low < pool['level'] and current_close > pool['level']:
                    magnitude = (pool['level'] - current_low) / pool['level']
                    confidence = min(1.0, pool['weight'] * (1.0 + magnitude * 100))
                    active_sweeps.append({"type": "SELL_SIDE_SWEEP", "index": int(i), "level": pool['level'], "confidence": confidence})
    return active_sweeps

def detect_choch_or_bos(structure, state):
    """
    Phase 10.1: Distinguishes BOS (Break of Structure) from CHoCH (Change of Character).

    BOS  = price breaks a swing point IN THE SAME DIRECTION as current state → continuation.
           e.g. BULLISH state + new HH above prior HH = structure extending = BOS.
    CHoCH = price breaks a swing point AGAINST current state → reversal warning.
           e.g. BULLISH state + new LL below prior HL = CHoCH.

    Returns a dict with 'event_type': 'BOS' | 'CHoCH', 'direction', 'level', 'note'
    or None if neither detected.
    """
    if len(structure) < 3 or state not in ("BULLISH", "BEARISH"):
        return None

    if state == "BULLISH":
        # BOS: newest point is a HH above the prior HH
        hhs = [s for s in structure if s['type'] == 'HH']
        if len(hhs) >= 2 and hhs[-1]['price'] > hhs[-2]['price']:
            return {"event_type": "BOS", "direction": "BULLISH",
                    "level": hhs[-1]['price'],
                    "note": "Bullish BOS: new HH above prior HH — trend continuation"}
        # CHoCH: LL formed after the last HL
        last_hl = next((s for s in reversed(structure) if s['type'] == 'HL'), None)
        if last_hl:
            after_hl = [s for s in structure if s['index'] > last_hl['index'] and s['type'] == 'LL']
            if after_hl:
                return {"event_type": "CHoCH", "direction": "BEARISH",
                        "level": last_hl['price'],
                        "broken_by": after_hl[-1]['price'],
                        "note": "Bullish trend CHoCH: HL broken by LL — reversal warning"}

    elif state == "BEARISH":
        # BOS: newest point is a LL below prior LL
        lls = [s for s in structure if s['type'] == 'LL']
        if len(lls) >= 2 and lls[-1]['price'] < lls[-2]['price']:
            return {"event_type": "BOS", "direction": "BEARISH",
                    "level": lls[-1]['price'],
                    "note": "Bearish BOS: new LL below prior LL — trend continuation"}
        # CHoCH: HH formed after the last LH
        last_lh = next((s for s in reversed(structure) if s['type'] == 'LH'), None)
        if last_lh:
            after_lh = [s for s in structure if s['index'] > last_lh['index'] and s['type'] == 'HH']
            if after_lh:
                return {"event_type": "CHoCH", "direction": "BULLISH",
                        "level": last_lh['price'],
                        "broken_by": after_lh[-1]['price'],
                        "note": "Bearish trend CHoCH: LH broken by HH — reversal warning"}
    return None


# Keep legacy alias so existing callers don't break
def detect_choch(structure, state):
    result = detect_choch_or_bos(structure, state)
    if result and result.get('event_type') == 'CHoCH':
        # Translate to old format for backwards compatibility
        return {
            "type": result['direction'].upper() + "_CHOCH",
            "level": result['level'],
            "broken_by": result.get('broken_by'),
            "note": result['note']
        }
    return None


def calculate_layer1_score(state, sweep_event, structure_confidence, volume_ratio=1.0,
                            adx_regime="TRENDING", ob_bonus=0, fvg_bonus=0, pd_modifier=0,
                            rsi_bonus=0, rejection_bonus=0, atr_volatility_mult=1.0,
                            bos_bonus=0, fib_bonus=0, adx_slope_bonus=0,
                            stoch_bonus=0, vp_bonus=0, vwap_bonus=0):
    """
    v6 (Phase 10): Score engine with structure precision (Group A) and
    volume/market profile modifiers (Group B).

    Score composition:
      Structure         : 0-15 pts
      Sweep             : 0-15 pts (volume-adjusted)
      Order Block       : 0-10 pts (7.2)
      FVG               : 0-8 pts  (7.3)
      PD zone           : -8 to +5 (7.4)
      ADX gate          : -20 to 0  (7.1)
      RSI divergence    : 0-12 pts  (8.3)
      Rejection candle  : 0-8 pts   (8.4)
      ATR volatility    : x0.75|1.0 (8.5)
      BOS confirmation  : 0-6 pts   (10.1)
      Fibonacci zone    : 0-5 pts   (10.2)
      ADX slope         : -5 to +5  (10.3)
      StochRSI at zone  : 0-7 pts   (10.4)
      Volume Profile    : 0-6 pts   (10.5)
      VWAP alignment    : 0-4 pts   (10.6)
    Max raw ~71, x ATR mult, capped to 60.
    """
    score = 0

    # Structure (Max 15)
    if state in ["BULLISH", "BEARISH"]:
        score += (15 * structure_confidence)
    elif state == "RANGE":
        score += (5 * structure_confidence)

    # Sweep / Liquidity (Max 15, volume-adjusted)
    if sweep_event:
        vol_adjusted_conf = min(1.0, sweep_event.get('confidence', 0.5) * volume_ratio)
        score += (15 * vol_adjusted_conf)

    # Phase 7 bonuses
    score += ob_bonus
    score += fvg_bonus
    score += pd_modifier

    # Phase 7.1: ADX Regime gate
    if adx_regime == "RANGING":
        score -= 20
    elif adx_regime == "WEAK":
        score -= 10

    # Phase 8 bonuses
    score += rsi_bonus
    score += rejection_bonus

    # Phase 10 Group A bonuses
    score += bos_bonus        # +6 BOS continuation
    score += fib_bonus        # +2/3/5 Fibonacci zone
    score += adx_slope_bonus  # +5 ACCELERATING / -5 DECELERATING
    score += stoch_bonus      # +7 oversold/overbought at OB/FVG

    # Phase 10 Group B bonuses
    score += vp_bonus         # +5/6 Volume Profile (POC/VAL/VAH)
    score += vwap_bonus       # +2/3/4 VWAP alignment

    # Phase 8.5: ATR Volatility multiplier (applied last)
    score = score * atr_volatility_mult

    return round(min(60, max(0, score)), 2)



# ─────────────────────────────────────────────────────────────────────────────
# Phase 8: Advanced Confirmation Functions
# ─────────────────────────────────────────────────────────────────────────────

def calculate_rsi(df, period=14):
    """Phase 8.3: Calculates RSI(14) for every row. Returns a Series."""
    delta  = df['close'].diff()
    gain   = delta.clip(lower=0).rolling(period).mean()
    loss   = (-delta.clip(upper=0)).rolling(period).mean()
    rs     = gain / loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))


def detect_rsi_divergence(df, structure, period=14):
    """
    Phase 8.3: RSI Divergence Detection.
    Compares the last two significant swing prices against their RSI values.
    - Bearish div: Price HH but RSI LH at swing high   → momentum dying
    - Bullish div: Price LL but RSI HL at swing low    → selling pressure weakening
    Returns {"type", "strength"} or None.
    """
    if len(df) < period * 2 or len(structure) < 4:
        return None

    rsi = calculate_rsi(df, period)

    # Get last two swing highs and last two swing lows
    highs = [s for s in structure if 'H' in s['type']]
    lows  = [s for s in structure if 'L' in s['type']]

    divergence = None

    if len(highs) >= 2:
        h1, h2 = highs[-2], highs[-1]   # h2 is the more recent
        idx1, idx2 = h1['index'], h2['index']
        if idx1 < len(rsi) and idx2 < len(rsi):
            rsi1, rsi2 = rsi.iloc[idx1], rsi.iloc[idx2]
            if h2['price'] > h1['price'] and rsi2 < rsi1:  # Price HH, RSI LH
                strength = round(abs(rsi1 - rsi2) / 100, 2)
                divergence = {"type": "BEARISH_DIVERGENCE", "strength": strength,
                              "note": f"Price HH ({h2['price']:.2f}) but RSI falling ({rsi2:.1f} < {rsi1:.1f})"}

    if len(lows) >= 2 and divergence is None:
        l1, l2 = lows[-2], lows[-1]
        idx1, idx2 = l1['index'], l2['index']
        if idx1 < len(rsi) and idx2 < len(rsi):
            rsi1, rsi2 = rsi.iloc[idx1], rsi.iloc[idx2]
            if l2['price'] < l1['price'] and rsi2 > rsi1:  # Price LL, RSI HL
                strength = round(abs(rsi2 - rsi1) / 100, 2)
                divergence = {"type": "BULLISH_DIVERGENCE", "strength": strength,
                              "note": f"Price LL ({l2['price']:.2f}) but RSI rising ({rsi2:.1f} > {rsi1:.1f})"}

    return divergence


def detect_rejection_candle(df, active_zones):
    """
    Phase 8.4: Rejection Candle Pattern Detection at OB/FVG zones.
    Checks the last 2 candles for pinbar, engulfing, or inside-bar patterns
    ONLY when price is at or near an active zone.
    Returns {"pattern", "direction", "strength"} or None.
    """
    if len(df) < 3 or not active_zones:
        return None

    last  = df.iloc[-1]
    prev  = df.iloc[-2]
    cur_price = last['close']

    # Only trigger near a known zone
    near_zone = any(
        abs(cur_price - z.get('low', cur_price)) / cur_price < 0.005 or
        abs(cur_price - z.get('high', cur_price)) / cur_price < 0.005
        for z in active_zones
    )
    if not near_zone:
        return None

    body  = abs(last['close'] - last['open'])
    rng   = last['high'] - last['low'] if last['high'] != last['low'] else 0.0001
    upper = last['high'] - max(last['close'], last['open'])
    lower = min(last['close'], last['open']) - last['low']

    # Pinbar: wick > 2× body
    if body > 0 and (upper > 2 * body or lower > 2 * body):
        direction = "BULL" if lower > upper else "BEAR"
        strength  = round(min(upper, lower) / rng if rng else 0.5, 2)
        return {"pattern": "PINBAR", "direction": direction, "strength": strength}

    # Engulfing: current body fully wraps previous body
    prev_body_high = max(prev['close'], prev['open'])
    prev_body_low  = min(prev['close'], prev['open'])
    cur_body_high  = max(last['close'], last['open'])
    cur_body_low   = min(last['close'], last['open'])
    if cur_body_low < prev_body_low and cur_body_high > prev_body_high and body > 0:
        direction = "BULL" if last['close'] > last['open'] else "BEAR"
        strength  = round(body / (prev_body_high - prev_body_low) if (prev_body_high - prev_body_low) > 0 else 0.5, 2)
        return {"pattern": "ENGULFING", "direction": direction, "strength": min(strength, 1.0)}

    # Inside bar: current entirely within previous candle range
    if last['high'] < prev['high'] and last['low'] > prev['low']:
        return {"pattern": "INSIDE_BAR", "direction": "NEUTRAL", "strength": 0.5}

    return None


def calculate_atr_percentile(df, period=14, lookback=60):
    """
    Phase 8.5: ATR Percentile Volatility Filter.
    Finds the percentile rank of the current ATR vs its recent history.
      < 20th pct  → DEAD     — no institutional participation, avoid signals
      20–80th pct → HEALTHY  — ideal volatility for technical signals
      > 80th pct  → VOLATILE — news event / manipulation, reduce confidence
    Returns (percentile, regime, multiplier).
    """
    if len(df) < lookback + period:
        return 50.0, "HEALTHY", 1.0

    # Calculate rolling ATR over the lookback window
    high  = df['high']
    low   = df['low']
    close = df['close'].shift(1)
    tr = pd.concat([
        high - low,
        (high - close).abs(),
        (low  - close).abs()
    ], axis=1).max(axis=1)
    atr_series = tr.rolling(period).mean().dropna()
    if len(atr_series) < lookback:
        return 50.0, "HEALTHY", 1.0

    recent_atrs = atr_series.iloc[-lookback:]
    current_atr = float(atr_series.iloc[-1])
    percentile  = round(float((recent_atrs < current_atr).sum() / len(recent_atrs) * 100), 1)

    if percentile < 20:
        return percentile, "DEAD",     0.75
    elif percentile > 80:
        return percentile, "VOLATILE", 0.75
    else:
        return percentile, "HEALTHY",  1.0


# ─────────────────────────────────────────────────────────────────────────────
# Phase 10: Group A — Structure Precision
# ─────────────────────────────────────────────────────────────────────────────

def calculate_fibonacci_levels(structure, current_price):
    """
    Phase 10.2: Auto-draws Fibonacci retracement and extension levels from
    the most recent significant swing high + swing low in the structure array.
    Returns a dict with retracement levels, extension levels, and a bonus.
    """
    highs = [s['price'] for s in structure if 'H' in s['type']]
    lows  = [s['price'] for s in structure if 'L' in s['type']]
    if not highs or not lows:
        return {"fib_bonus": 0, "fib_entry_zone": None, "fib_levels": {}}

    swing_high = max(highs[-5:]) if len(highs) >= 5 else max(highs)
    swing_low  = min(lows[-5:])  if len(lows)  >= 5 else min(lows)
    rng        = swing_high - swing_low
    if rng <= 0:
        return {"fib_bonus": 0, "fib_entry_zone": None, "fib_levels": {}}

    retracements = {
        "0.236": swing_high - 0.236 * rng,
        "0.382": swing_high - 0.382 * rng,
        "0.500": swing_high - 0.500 * rng,
        "0.618": swing_high - 0.618 * rng,
        "0.705": swing_high - 0.705 * rng,
        "0.786": swing_high - 0.786 * rng,
    }
    extensions = {
        "1.000": swing_low,
        "1.272": swing_low - 0.272 * rng,
        "1.618": swing_low - 0.618 * rng,
        "2.000": swing_low - 1.000 * rng,
    }

    all_levels = {**retracements, **extensions}
    proximity  = 0.003  # 0.3% tolerance

    hit_zone   = None
    fib_bonus  = 0
    for lvl_name, lvl_price in all_levels.items():
        if abs(current_price - lvl_price) / lvl_price < proximity:
            hit_zone = lvl_name
            if lvl_name in ("0.618", "0.705", "0.786"):
                fib_bonus = 5
            elif lvl_name in ("0.382", "0.500"):
                fib_bonus = 3
            else:
                fib_bonus = 2
            break

    return {
        "fib_bonus":      fib_bonus,
        "fib_entry_zone": hit_zone,
        "fib_levels":     {k: round(v, 4) for k, v in all_levels.items()},
        "swing_high":     round(swing_high, 4),
        "swing_low":      round(swing_low, 4),
    }


def calculate_stoch_rsi(df, rsi_period=14, stoch_period=14, smooth_k=3, smooth_d=3):
    """
    Phase 10.4: Stochastic RSI oscillator.
    Returns (stoch_k, stoch_d, regime) where regime is:
      OVERSOLD (<20), OVERBOUGHT (>80), or NEUTRAL.
    """
    if len(df) < rsi_period + stoch_period + smooth_k + 5:
        return 50.0, 50.0, "NEUTRAL"

    rsi_series = calculate_rsi(df, rsi_period).dropna()
    if len(rsi_series) < stoch_period:
        return 50.0, 50.0, "NEUTRAL"

    rsi_min = rsi_series.rolling(stoch_period).min()
    rsi_max = rsi_series.rolling(stoch_period).max()
    stoch_range = (rsi_max - rsi_min).replace(0, np.nan)
    raw_k  = 100 * (rsi_series - rsi_min) / stoch_range
    k_line = raw_k.rolling(smooth_k).mean()
    d_line = k_line.rolling(smooth_d).mean()

    k_val = float(k_line.dropna().iloc[-1]) if not k_line.dropna().empty else 50.0
    d_val = float(d_line.dropna().iloc[-1]) if not d_line.dropna().empty else 50.0

    if k_val < 20:   regime = "OVERSOLD"
    elif k_val > 80: regime = "OVERBOUGHT"
    else:            regime = "NEUTRAL"

    return round(k_val, 2), round(d_val, 2), regime


# ─────────────────────────────────────────────────────────────────────────────
# Phase 10: Group B — Volume & Market Profile
# ─────────────────────────────────────────────────────────────────────────────

def calculate_volume_profile(df, bins=50, lookback=200):
    """
    Phase 10.5: Volume Profile — POC / VAH / VAL / LVN.
    Bins price action into 50 levels and sums volume per level.
    Returns {poc, vah, val, lvn_levels, at_poc, vp_bonus}.
    """
    if 'volume' not in df.columns or len(df) < 30:
        return {"poc": None, "vah": None, "val": None,
                "lvn_levels": [], "at_poc": False, "vp_bonus": 0}

    window = df.tail(lookback).copy()
    price_min = float(window['low'].min())
    price_max = float(window['high'].max())
    if price_max <= price_min:
        return {"poc": None, "vah": None, "val": None,
                "lvn_levels": [], "at_poc": False, "vp_bonus": 0}

    bin_edges  = np.linspace(price_min, price_max, bins + 1)
    bin_vols   = np.zeros(bins)
    bin_prices = (bin_edges[:-1] + bin_edges[1:]) / 2

    for _, row in window.iterrows():
        low_i  = np.searchsorted(bin_edges, row['low'],  side='left')  - 1
        high_i = np.searchsorted(bin_edges, row['high'], side='right') - 1
        low_i  = max(0, min(low_i, bins - 1))
        high_i = max(0, min(high_i, bins - 1))
        span   = max(1, high_i - low_i + 1)
        for b in range(low_i, high_i + 1):
            bin_vols[b] += row['volume'] / span

    total_vol  = bin_vols.sum()
    poc_idx    = int(np.argmax(bin_vols))
    poc        = round(float(bin_prices[poc_idx]), 4)

    # Value Area: 70% of total volume
    sorted_idx = np.argsort(-bin_vols)
    cumvol     = 0
    va_indices = []
    for idx in sorted_idx:
        cumvol += bin_vols[idx]
        va_indices.append(idx)
        if cumvol >= 0.70 * total_vol:
            break

    vah = round(float(bin_prices[max(va_indices)]), 4)
    val = round(float(bin_prices[min(va_indices)]), 4)

    # LVN: bins with < 20% of average volume
    avg_vol    = total_vol / bins
    lvn_levels = [round(float(bin_prices[i]), 4)
                  for i in range(bins) if bin_vols[i] < 0.2 * avg_vol]

    current_price = float(df['close'].iloc[-1])
    at_poc        = abs(current_price - poc) / poc < 0.002

    return {
        "poc": poc, "vah": vah, "val": val,
        "lvn_levels": lvn_levels[:5],
        "at_poc": at_poc,
    }


def calculate_vwap(df, anchor_idx=None):
    """
    Phase 10.6: VWAP and Anchored VWAP.
    anchor_idx: if set, VWAP resets from that candle (Anchored VWAP from swing).
    Returns {vwap, avwap, price_vs_vwap, vwap_deviation}.
    Fixed: safe division for zero-volume assets (Forex).
    """
    if 'volume' not in df.columns or len(df) < 5:
        return {"vwap": None, "avwap": None,
                "price_vs_vwap": "NEUTRAL", "vwap_deviation_pct": 0.0}

    typical = (df['high'] + df['low'] + df['close']) / 3
    vol_sum = df['volume'].sum()
    
    # If entire asset has exactly 0 volume (e.g., Forex on yfinance), gracefully skip
    if vol_sum == 0:
        return {"vwap": None, "avwap": None,
                "price_vs_vwap": "NEUTRAL", "vwap_deviation_pct": 0.0}

    cum_tpv = (typical * df['volume']).cumsum()
    cum_vol = df['volume'].cumsum().replace(0, np.nan)
    vwap_series = cum_tpv / cum_vol
    
    # Safely extract last valid VWAP
    try:
        vwap = round(float(vwap_series.ffill().iloc[-1]), 4)
    except Exception:
        vwap = float(typical.iloc[-1])

    # Anchored VWAP from last significant swing (or provided anchor)
    if anchor_idx is None:
        anchor_idx = max(0, len(df) - min(100, len(df)))
    
    anchor_slice = df.iloc[anchor_idx:]
    anchor_vol_sum = anchor_slice['volume'].sum()

    if len(anchor_slice) >= 2 and anchor_vol_sum > 0:
        typ_a = (anchor_slice['high'] + anchor_slice['low'] + anchor_slice['close']) / 3
        avwap = round(float((typ_a * anchor_slice['volume']).sum() / anchor_vol_sum), 4)
    else:
        avwap = vwap

    current_price = float(df['close'].iloc[-1])
    
    if vwap == 0 or vwap is None:
        return {"vwap": None, "avwap": None,
                "price_vs_vwap": "NEUTRAL", "vwap_deviation_pct": 0.0}

    deviation_pct = round((current_price - vwap) / vwap * 100, 2)

    if abs(deviation_pct) < 0.1:     price_vs_vwap = "AT"
    elif current_price > vwap:       price_vs_vwap = "ABOVE"
    else:                            price_vs_vwap = "BELOW"

    return {
        "vwap": vwap, "avwap": avwap,
        "price_vs_vwap": price_vs_vwap,
        "vwap_deviation_pct": deviation_pct,
    }



def determine_structure_points(df):
    structure = []
    last_high = None
    last_low = None
    swing_indices = df[df['is_swing_high'] | df['is_swing_low']].index
    
    for idx in swing_indices:
        row = df.loc[idx]
        clarity = calculate_swing_clarity(df, idx)
        if row['is_swing_high']:
            label = "H"
            if last_high is not None: label = "HH" if row['high'] > last_high else "LH"
            last_high = row['high']
            structure.append({"type": label, "price": row['high'], "index": int(idx), "confidence": clarity})
        elif row['is_swing_low']:
            label = "L"
            if last_low is not None: label = "LL" if row['low'] < last_low else "HL"
            last_low = row['low']
            structure.append({"type": label, "price": row['low'], "index": int(idx), "confidence": clarity})
    return structure

def determine_market_state(structure):
    if len(structure) < 4: return "UNCLEAR", 0.1
    recent = structure[-4:]
    conf = np.mean([s['confidence'] for s in recent])
    last_high = next((s for s in reversed(recent) if 'H' in s['type']), None)
    last_low = next((s for s in reversed(recent) if 'L' in s['type']), None)
    
    state = "RANGE"
    if last_high and last_low:
        if last_high['type'] == 'HH' and last_low['type'] == 'HL': state = "BULLISH"
        elif last_high['type'] == 'LH' and last_low['type'] == 'LL': state = "BEARISH"
    return state, conf

def analyze_layer1(df):
    df = identify_swings(df, length=3)
    structure = determine_structure_points(df)
    state, structure_conf = determine_market_state(structure)

    pools = detect_liquidity_pools(structure)
    sweeps = detect_sweeps(df, pools)
    last_sweep = sweeps[-1] if sweeps else None

    # Phase 3.2: Volume Confirmation
    volume_ratio = 1.0
    if 'volume' in df.columns:
        avg_vol = df['volume'].rolling(20).mean().iloc[-1]
        cur_vol = df['volume'].iloc[-1]
        if avg_vol and avg_vol > 0:
            volume_ratio = min(2.0, float(cur_vol / avg_vol))

    # Phase 3.3 / 10.1: BOS vs CHoCH Detection
    struct_event = detect_choch_or_bos(structure, state)
    bos_bonus = 0
    if struct_event:
        if struct_event['event_type'] == 'BOS':
            # BOS in trend direction = trend continuation confirmed
            if (struct_event['direction'] == 'BULLISH' and state == 'BULLISH') or \
               (struct_event['direction'] == 'BEARISH' and state == 'BEARISH'):
                bos_bonus = 6
        # keep backwards-compat choch alias
    choch = detect_choch(structure, state)

    # ATR for downstream TP/SL
    atr = calculate_atr(df)

    # ─ Phase 7.1 + 10.3: ADX Regime Gate + Slope ─
    adx_val, adx_regime, adx_slope_regime = calculate_adx(df)
    adx_slope_bonus = 0
    if adx_regime == "TRENDING":
        if adx_slope_regime == "ACCELERATING":   adx_slope_bonus = +5
        elif adx_slope_regime == "DECELERATING": adx_slope_bonus = -5

    # ─ Phase 7.2: Order Block Detection ─
    order_blocks  = detect_order_blocks(df, structure)
    current_price = float(df['close'].iloc[-1])

    # ─ Phase 10.2: Fibonacci Auto-Draw ─
    fib_data  = calculate_fibonacci_levels(structure, current_price)
    fib_bonus = fib_data['fib_bonus']

    ob_bonus = 0
    for ob in order_blocks:
        aligned = (ob['type'] == 'BULLISH_OB' and state == 'BULLISH') or \
                  (ob['type'] == 'BEARISH_OB' and state == 'BEARISH')
        if aligned:
            if ob.get('active'):  ob_bonus = max(ob_bonus, 10)
            elif ob.get('near'): ob_bonus = max(ob_bonus, 5)

    # ─ Phase 7.3: Fair Value Gap Detection ─
    fvgs = detect_fvgs(df)

    fvg_bonus = 0
    for fvg in fvgs:
        aligned = (fvg['type'] == 'BULLISH_FVG' and state == 'BULLISH') or \
                  (fvg['type'] == 'BEARISH_FVG' and state == 'BEARISH')
        if aligned:
            if fvg.get('inside'):        fvg_bonus = max(fvg_bonus, 8)
            elif fvg.get('approaching'): fvg_bonus = max(fvg_bonus, 4)

    # ─ Phase 7.4: Premium / Discount ─
    pd_zone, pd_pct, sw_high, sw_low = calculate_premium_discount(current_price, structure)

    pd_modifier = 0
    if state == "BULLISH" and pd_zone == "DISCOUNT":   pd_modifier = +5
    elif state == "BEARISH" and pd_zone == "PREMIUM":  pd_modifier = +5
    elif state == "BULLISH" and pd_zone == "PREMIUM":  pd_modifier = -8
    elif state == "BEARISH" and pd_zone == "DISCOUNT": pd_modifier = -8

    # ─ Phase 8.3: RSI Divergence ─
    rsi_divergence = detect_rsi_divergence(df, structure)
    rsi_bonus      = 0
    if rsi_divergence:
        div_aligns = (
            (rsi_divergence['type'] == 'BULLISH_DIVERGENCE' and state == 'BULLISH') or
            (rsi_divergence['type'] == 'BEARISH_DIVERGENCE' and state == 'BEARISH')
        )
        at_zone = ob_bonus > 0 or fvg_bonus > 0
        if div_aligns:
            rsi_bonus = 12 if at_zone else 6

    # ─ Phase 8.4: Rejection Candle Detection ─
    active_zones   = [ob for ob in order_blocks if ob.get('active') or ob.get('near')] + \
                     [fvg for fvg in fvgs if fvg.get('inside') or fvg.get('approaching')]
    rejection      = detect_rejection_candle(df, active_zones)
    rejection_bonus = 0
    if rejection:
        rej_aligns = (
            (rejection['direction'] == 'BULL' and state == 'BULLISH') or
            (rejection['direction'] == 'BEAR' and state == 'BEARISH') or
            rejection['direction'] == 'NEUTRAL'
        )
        if rej_aligns:
            rejection_bonus = 8 if rejection['pattern'] in ('PINBAR', 'ENGULFING') else 4

    # ─ Phase 8.5: ATR Percentile Volatility Filter ─
    atr_pct, atr_vol_regime, atr_vol_mult = calculate_atr_percentile(df)

    # ─ Phase 10.4: StochRSI at Key Zones ─
    stoch_k, stoch_d, stoch_regime = calculate_stoch_rsi(df)
    stoch_bonus = 0
    if (stoch_regime == "OVERSOLD"  and state == "BULLISH" and (ob_bonus > 0 or fvg_bonus > 0)) or \
       (stoch_regime == "OVERBOUGHT" and state == "BEARISH" and (ob_bonus > 0 or fvg_bonus > 0)):
        stoch_bonus = 7

    # ─ Phase 10.5: Volume Profile ─
    vp_data  = calculate_volume_profile(df)
    vp_bonus = 0
    if vp_data['poc']:
        if vp_data['at_poc']:
            vp_bonus = 6  # Price sitting on POC = high probability area
        elif state == "BULLISH" and vp_data['val'] and current_price <= vp_data['val'] * 1.002:
            vp_bonus = 5  # At Value Area Low in bullish trend
        elif state == "BEARISH" and vp_data['vah'] and current_price >= vp_data['vah'] * 0.998:
            vp_bonus = 5  # At Value Area High in bearish trend

    # ─ Phase 10.6: VWAP ─
    vwap_data  = calculate_vwap(df)
    vwap_bonus = 0
    if vwap_data['vwap']:
        pvwap = vwap_data['price_vs_vwap']
        dev   = abs(vwap_data['vwap_deviation_pct'])
        if state == "BULLISH" and pvwap == "BELOW":  vwap_bonus = 4   # Discount to VWAP
        elif state == "BEARISH" and pvwap == "ABOVE": vwap_bonus = 4  # Premium to VWAP
        elif pvwap == "AT":                           vwap_bonus = 3  # VWAP bounce
        elif dev >= 2.0:                              vwap_bonus = 2  # 2σ extension

    # ─ Final Score ─
    score = calculate_layer1_score(
        state, last_sweep, structure_conf, volume_ratio,
        adx_regime=adx_regime, ob_bonus=ob_bonus,
        fvg_bonus=fvg_bonus, pd_modifier=pd_modifier,
        rsi_bonus=rsi_bonus, rejection_bonus=rejection_bonus,
        atr_volatility_mult=atr_vol_mult,
        bos_bonus=bos_bonus, fib_bonus=fib_bonus,
        adx_slope_bonus=adx_slope_bonus,
        stoch_bonus=stoch_bonus,
        vp_bonus=vp_bonus, vwap_bonus=vwap_bonus
    )

    return {
        "structure_bias":       "NEUTRAL" if state == "RANGE" else state,
        "structure_confidence": round(float(structure_conf), 2),
        "liquidity_context": {
            "type":       last_sweep['type'].split('_')[0] + "_SIDE" if last_sweep else "NONE",
            "event":      "SWEEP" if last_sweep else "NONE",
            "confidence": round(float(last_sweep['confidence']), 2) if last_sweep else 0.0
        },
        "volume_ratio":   round(volume_ratio, 2),
        "choch":          choch,
        "struct_event":   struct_event,    # Phase 10.1: full BOS/CHoCH event
        "atr":            round(atr, 6) if atr else None,
        # Phase 7 fields
        "adx":            adx_val,
        "regime":         adx_regime,
        "adx_slope":      adx_slope_regime,      # Phase 10.3
        "order_blocks":   order_blocks,
        "fvgs":           fvgs,
        "pd_zone":        pd_zone,
        "pd_pct":         pd_pct,
        "ob_bonus":       ob_bonus,
        "fvg_bonus":      fvg_bonus,
        "pd_modifier":    pd_modifier,
        # Phase 8 fields
        "rsi_divergence":   rsi_divergence,
        "rsi_bonus":         rsi_bonus,
        "rejection_candle": rejection,
        "rejection_bonus":  rejection_bonus,
        "atr_pct":          atr_pct,
        "atr_vol_regime":   atr_vol_regime,
        # Phase 10 Group A fields
        "bos_bonus":        bos_bonus,
        "fib_data":         fib_data,
        "fib_bonus":        fib_bonus,
        "adx_slope_bonus":  adx_slope_bonus,
        "stoch_k":          stoch_k,
        "stoch_d":          stoch_d,
        "stoch_regime":     stoch_regime,
        "stoch_bonus":      stoch_bonus,
        # Phase 10 Group B fields
        "volume_profile":   vp_data,
        "vp_bonus":         vp_bonus,
        "vwap_data":        vwap_data,
        "vwap_bonus":       vwap_bonus,
        "layer1_score":     score,
        "notes": (
            f"{state} | ADX:{adx_val}({adx_regime}/{adx_slope_regime}) | Vol:{round(volume_ratio,2)}x | "
            f"PD:{pd_zone}({pd_pct}%) | OB:+{ob_bonus} FVG:+{fvg_bonus} | "
            f"RSI:{rsi_divergence['type'] if rsi_divergence else 'None'}(+{rsi_bonus}) | "
            f"Rej:{rejection['pattern'] if rejection else 'None'}(+{rejection_bonus}) | "
            f"ATR:{atr_vol_regime}({atr_pct}pct) | CHoCH:{choch['type'] if choch else 'None'} | "
            f"BOS:+{bos_bonus} Fib:{fib_data['fib_entry_zone']}(+{fib_bonus}) | "
            f"StochRSI:{stoch_regime}(+{stoch_bonus}) VP:+{vp_bonus} VWAP:{vwap_data['price_vs_vwap']}(+{vwap_bonus})"
        ),
        "raw_structure": structure
    }

def main():
    parser = argparse.ArgumentParser(description='Analyze Market Structure & Liquidity v2.')
    parser.add_argument('--input', type=str, required=True, help='Path to CSV file')
    args = parser.parse_args()
    try:
        df = pd.read_csv(args.input)
        result = analyze_layer1(df)
        print(json.dumps(result, indent=2))
    except Exception as e:
        print(json.dumps({"error": str(e)}))
        sys.exit(1)

if __name__ == "__main__":
    main()
