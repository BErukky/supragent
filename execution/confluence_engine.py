import argparse
import sys
import pandas as pd
import json
import os

# Ensure we can import structure_engine from the same directory
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
try:
    from structure_engine import analyze_layer1
except ImportError:
    from execution.structure_engine import analyze_layer1

def get_layer1_analysis(csv_path):
    """
    Helper to pipeline the Layer 1 analysis for a single file.
    """
    try:
        df = pd.read_csv(csv_path)
        return analyze_layer1(df)
    except Exception as e:
        print(f"Error processing {csv_path}: {e}")
        return None

def main():
    parser = argparse.ArgumentParser(description='Analyze Multi-Timeframe Confluence.')
    parser.add_argument('--htf', type=str, required=True, help='Path to HTF CSV')
    parser.add_argument('--ltf', type=str, required=True, help='Path to LTF CSV')
    args = parser.parse_args()

    # 1. Analyze HTF
    htf_analysis = get_layer1_analysis(args.htf)
    if not htf_analysis: sys.exit(1)
    htf_state = htf_analysis['structure_bias']
    
    # 2. Analyze LTF
    ltf_analysis = get_layer1_analysis(args.ltf)
    if not ltf_analysis: sys.exit(1)
    ltf_state = ltf_analysis['structure_bias']
    
    # 3. Apply Confluence Logic
    bias = "NO_TRADE"
    confidence = "LOW"
    reasoning = ""
    
    # Logic Matrix
    if htf_state == "BULLISH":
        if ltf_state == "BULLISH":
            bias = "LONG_BIAS"
            confidence = "HIGH"
            reasoning = "Full Alignment: HTF Bullish & LTF Bullish."
        elif ltf_state == "NEUTRAL" or ltf_state == "RANGE":
            bias = "LONG_BIAS"
            confidence = "MEDIUM"
            reasoning = "HTF Bullish, but LTF is ranging. Wait for LTF breakout."
        elif ltf_state == "BEARISH":
            bias = "NO_TRADE"
            confidence = "LOW"
            reasoning = "Conflict: HTF Bullish but LTF is Bearish (Pullback active)."
            
    elif htf_state == "BEARISH":
        if ltf_state == "BEARISH":
            bias = "SHORT_BIAS"
            confidence = "HIGH"
            reasoning = "Full Alignment: HTF Bearish & LTF Bearish."
        elif ltf_state == "NEUTRAL" or ltf_state == "RANGE":
            bias = "SHORT_BIAS"
            confidence = "MEDIUM"
            reasoning = "HTF Bearish, but LTF is ranging."
        elif ltf_state == "BULLISH":
            bias = "NO_TRADE"
            confidence = "LOW"
            reasoning = "Conflict: HTF Bearish but LTF is Bullish (Pullback active)."
            
    else: # HTF is RANGE or UNCLEAR
        bias = "NO_TRADE"
        confidence = "LOW"
        reasoning = "HTF is Ranging/Unclear. No trade direction."

    # Output
    result = {
        "final_signal": bias,
        "confidence": confidence,
        "reasoning": reasoning,
        "details": {
            "htf_layer1": htf_analysis,
            "ltf_layer1": ltf_analysis,
            # Maintain these for backwards compatibility with Report Engine if needed
            "htf_state": htf_state,
            "ltf_state": ltf_state,
            "raw_ltf_structure": ltf_analysis['raw_structure'],
            "raw_htf_structure": htf_analysis['raw_structure']
        }
    }
    
    print(json.dumps(result, indent=2))

if __name__ == "__main__":
    main()
