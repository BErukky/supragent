import pandas as pd
import numpy as np
import argparse
import sys
import json

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

def calculate_layer1_score(state, sweep_event, structure_confidence):
    """
    v2: Weights bias by structural confidence.
    """
    score = 0
    # Structure (Max 15 * Confidence)
    if state in ["BULLISH", "BEARISH"]:
        score += (15 * structure_confidence)
    elif state == "RANGE":
        score += (5 * structure_confidence)
        
    # Liquidity (Max 15 * Sweep Confidence)
    if sweep_event:
        score += (15 * sweep_event.get('confidence', 0.5))
    
    return round(min(30, score), 2)

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
    
    score = calculate_layer1_score(state, last_sweep, structure_conf)
    
    return {
        "structure_bias": "NEUTRAL" if state == "RANGE" else state,
        "structure_confidence": round(float(structure_conf), 2),
        "liquidity_context": {
            "type": last_sweep['type'].split('_')[0] + "_SIDE" if last_sweep else "NONE",
            "event": "SWEEP" if last_sweep else "NONE",
            "confidence": round(float(last_sweep['confidence']), 2) if last_sweep else 0.0
        },
        "layer1_score": score,
        "notes": f"{state} structure (Conf:{round(structure_conf,2)}). Last sweep: {last_sweep['type'] if last_sweep else 'None'}",
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
