import argparse
import sys
import pandas as pd
import json
import os
import numpy as np

# Ensure we can import structure_engine from the same directory
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
try:
    from structure_engine import analyze_layer1
except ImportError:
    from execution.structure_engine import analyze_layer1

def calculate_trend_coherence(htf_state, ltf_state, htf_conf, ltf_conf):
    """
    Measures 'Coherence' as a numeric value (0.0-1.0).
    1.0 = Perfect trend alignment.
    0.0 = Direct trend opposition.
    """
    coherence = 0.0
    
    # Define directional values
    states = {"BULLISH": 1, "BEARISH": -1, "NEUTRAL": 0, "RANGE": 0, "UNCLEAR": 0}
    h_val = states.get(htf_state, 0)
    l_val = states.get(ltf_state, 0)
    
    # Perfect alignment (1/1 or -1/-1)
    if h_val == l_val and h_val != 0:
        coherence = 1.0
    # Pullback / Counter-trend (1/-1 or -1/1)
    elif h_val != 0 and l_val != 0 and h_val != l_val:
        coherence = 0.2
    # Ranging/Neutral (Alignment with 0)
    elif h_val == 0 or l_val == 0:
        if h_val == l_val: # both 0
            coherence = 0.5
        else: # One is 0, one is trending
            coherence = 0.7 
            
    # Factor in the confidence of each layer
    total_conf = (htf_conf + ltf_conf) / 2.0
    return round(float(coherence * total_conf), 2)

def get_layer1_analysis(csv_path):
    try:
        df = pd.read_csv(csv_path)
        return analyze_layer1(df)
    except Exception as e:
        print(f"Error processing {csv_path}: {e}")
        return None

def run_confluence_analysis(htf_csv, ltf_csv):
    """
    Direct functional entry point for the orchestrator.
    """
    # 1. Analyze HTF
    htf_analysis = get_layer1_analysis(htf_csv)
    if not htf_analysis: return None
    htf_state = htf_analysis['structure_bias']
    htf_conf = htf_analysis['structure_confidence']
    
    # 2. Analyze LTF
    ltf_analysis = get_layer1_analysis(ltf_csv)
    if not ltf_analysis: return None
    ltf_state = ltf_analysis['structure_bias']
    ltf_conf = ltf_analysis['structure_confidence']
    
    # 3. Calculate Coherence
    coherence_score = calculate_trend_coherence(htf_state, ltf_state, htf_conf, ltf_conf)
    
    # 4. Final Logic
    bias = "WAIT / NO_TRADE"
    if htf_state == "BULLISH" and ltf_state == "BULLISH":
        bias = "LONG_BIAS"
    elif htf_state == "BEARISH" and ltf_state == "BEARISH":
        bias = "SHORT_BIAS"
    elif htf_state == "BULLISH" and ltf_state in ["NEUTRAL", "RANGE"]:
        bias = "WAIT / LONG_RECOVERY"
    elif htf_state == "BEARISH" and ltf_state in ["NEUTRAL", "RANGE"]:
        bias = "WAIT / SHORT_RECOVERY"

    l2_score = round(30 * coherence_score, 2)

    return {
        "final_signal": bias,
        "coherence_score": coherence_score,
        "layer2_score": l2_score,
        "reasoning": f"Trend Coherence: {round(coherence_score*100, 1)}%. HTF({htf_state}) LTF({ltf_state})",
        "details": {
            "htf_layer1": htf_analysis,
            "ltf_layer1": ltf_analysis,
            "raw_ltf_structure": ltf_analysis['raw_structure']
        }
    }

def main():
    parser = argparse.ArgumentParser(description='Analyze Multi-Timeframe Confluence v2.')
    parser.add_argument('--htf', type=str, required=True, help='Path to HTF CSV')
    parser.add_argument('--ltf', type=str, required=True, help='Path to LTF CSV')
    args = parser.parse_args()

    result = run_confluence_analysis(args.htf, args.ltf)
    if result:
        print(json.dumps(result, indent=2))
    else:
        sys.exit(1)

if __name__ == "__main__":
    main()
