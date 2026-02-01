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

def detect_liquidity_pools(structure, variance=0.001):
    """
    Detects clusters of equal highs/lows (Liquidity Pools).
    """
    pools = []
    
    highs = [s for s in structure if 'H' in s['type']]
    lows = [s for s in structure if 'L' in s['type']]
    
    # Check for Equal Highs (BSL)
    for i in range(len(highs)):
        for j in range(i + 1, len(highs)):
            if abs(highs[i]['price'] - highs[j]['price']) / highs[i]['price'] <= variance:
                pools.append({"type": "BUY_SIDE", "level": max(highs[i]['price'], highs[j]['price']), "indices": [highs[i]['index'], highs[j]['index']]})
                
    # Check for Equal Lows (SSL)
    for i in range(len(lows)):
        for j in range(i + 1, len(lows)):
            if abs(lows[i]['price'] - lows[j]['price']) / lows[i]['price'] <= variance:
                pools.append({"type": "SELL_SIDE", "level": min(lows[i]['price'], lows[j]['price']), "indices": [lows[i]['index'], lows[j]['index']]})
                
    return pools

def detect_sweeps(df, pools):
    """
    Detects if price breached a pool and reclaimed.
    """
    active_sweeps = []
    
    for i in range(len(df)):
        current_high = df['high'].iloc[i]
        current_low = df['low'].iloc[i]
        current_close = df['close'].iloc[i]
        
        for pool in pools:
            if pool['type'] == "BUY_SIDE":
                # Wick above pool, but close below pool
                if current_high > pool['level'] and current_close < pool['level']:
                    active_sweeps.append({"type": "BUY_SIDE_SWEEP", "index": i, "level": pool['level']})
            elif pool['type'] == "SELL_SIDE":
                # Wick below pool, but close above pool
                if current_low < pool['level'] and current_close > pool['level']:
                    active_sweeps.append({"type": "SELL_SIDE_SWEEP", "index": i, "level": pool['level']})
                    
    return active_sweeps

def calculate_layer1_score(state, sweep_event):
    """
    Calculates score from 0-30 based on structure and sweeps.
    """
    score = 0
    
    # Base Structure Score (Max 15)
    if state == "BULLISH" or state == "BEARISH":
        score += 15
    elif state == "RANGE":
        score += 5
    else:
        score += 0
        
    # Liquidity Modifiers (Max ±15)
    if sweep_event:
        if "SWEEP" in sweep_event['type']:
            # Assume sweep against trend is good. For now, simple +10 if any sweep.
            score += 10
            # If we had CHoCH logic here, we'd add +15.
    
    return min(30, score)

def determine_structure_points(df):
    structure = []
    last_high = None
    last_low = None
    swing_indices = df[df['is_swing_high'] | df['is_swing_low']].index
    
    for idx in swing_indices:
        row = df.loc[idx]
        if row['is_swing_high']:
            label = "H"
            if last_high is not None:
                label = "HH" if row['high'] > last_high else "LH"
            last_high = row['high']
            structure.append({"type": label, "price": row['high'], "timestamp": str(row['timestamp']), "index": int(idx)})
        elif row['is_swing_low']:
            label = "L"
            if last_low is not None:
                label = "LL" if row['low'] < last_low else "HL"
            last_low = row['low']
            structure.append({"type": label, "price": row['low'], "timestamp": str(row['timestamp']), "index": int(idx)})
    return structure

def determine_market_state(structure):
    if len(structure) < 4: return "UNCLEAR"
    recent = structure[-4:]
    last_high = next((s for s in reversed(recent) if 'H' in s['type']), None)
    last_low = next((s for s in reversed(recent) if 'L' in s['type']), None)
    
    if last_high and last_low:
        if last_high['type'] == 'HH' and last_low['type'] == 'HL': return "BULLISH"
        if last_high['type'] == 'LH' and last_low['type'] == 'LL': return "BEARISH"
    return "RANGE"

def analyze_layer1(df):
    """
    High-level entry point for Layer 1 analysis.
    """
    df = identify_swings(df, length=3)
    structure = determine_structure_points(df)
    state = determine_market_state(structure)
    
    # Liquidity Logic
    pools = detect_liquidity_pools(structure)
    sweeps = detect_sweeps(df, pools)
    
    last_sweep = sweeps[-1] if sweeps else None
    score = calculate_layer1_score(state, last_sweep)
    
    return {
        "structure_bias": "NEUTRAL" if state == "RANGE" else state,
        "structure_state": "RANGE" if state == "RANGE" else "TREND",
        "liquidity_context": {
            "type": last_sweep['type'].split('_')[0] + "_SIDE" if last_sweep else "NONE",
            "event": "SWEEP" if last_sweep else "NONE",
            "level": last_sweep['level'] if last_sweep else None
        },
        "layer1_score": score,
        "notes": f"{state} structure. Last sweep: {last_sweep['type'] if last_sweep else 'None'}",
        "raw_structure": structure # Useful for confluence/risk
    }

def main():
    parser = argparse.ArgumentParser(description='Analyze Market Structure & Liquidity.')
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
