import pandas as pd
import numpy as np
import argparse
import json
import sys
import os

def normalize(series):
    if len(series) == 0: return series
    if series.max() == series.min(): return np.zeros(len(series))
    return (series - series.min()) / (series.max() - series.min())

def find_similar_patterns(target_df, history_df, window_size=50, top_k=5):
    if len(target_df) < window_size: return []
    
    target_pattern = target_df['close'].iloc[-window_size:].values
    target_norm = normalize(target_pattern)
    
    matches = []
    hist_closes = history_df['close'].values
    hist_timestamps = history_df['timestamp'].values
    prediction_window = 24
    limit = len(hist_closes) - window_size - prediction_window
    
    for i in range(0, limit, 5): # Step 5 for better resolution
        candidate = hist_closes[i : i+window_size]
        candidate_norm = normalize(candidate)
        dist = np.linalg.norm(target_norm - candidate_norm)
        
        # Convert distance to similarity probability
        # Similarity = exponential decay of distance (e^-d)
        prob = np.exp(-dist)
        
        matches.append({
            "index": i,
            "probability": float(prob),
            "next_returns": (hist_closes[i+window_size+prediction_window] - hist_closes[i+window_size]) / hist_closes[i+window_size]
        })
        
    matches.sort(key=lambda x: x['probability'], reverse=True)
    return matches[:top_k]

def analyze_probabilistic_bias(matches):
    if not matches: return "UNCLEAR", 0.0, 0.0
    
    # Weight returns by their similarity probability
    weighted_sum = sum(m['next_returns'] * m['probability'] for m in matches)
    total_prob = sum(m['probability'] for m in matches)
    avg_weighted_return = weighted_sum / total_prob if total_prob > 0 else 0
    
    # Confidence is average probability of top matches
    confidence = total_prob / len(matches) if matches else 0
    
    # False Positive Check: If probability is high but returns are mixed
    variance = np.var([m['next_returns'] for m in matches])
    false_positive_risk = float(variance > 0.005) # Logic: high variance in outcomes = unstable analog
    
    bias = "UNCLEAR"
    if avg_weighted_return > 0.002: bias = "BULLISH"
    elif avg_weighted_return < -0.002: bias = "BEARISH"
    
    return bias, float(avg_weighted_return), float(confidence), false_positive_risk

def main():
    parser = argparse.ArgumentParser(description='Analyze Historical Similarity v2.')
    parser.add_argument('--target', type=str, required=True, help='Current market data CSV')
    parser.add_argument('--history', type=str, help='Historical DB CSV')
    args = parser.parse_args()
    
    try:
        target_df = pd.read_csv(args.target)
        history_df = pd.read_csv(args.history) if args.history else target_df
        
        window = 30 if len(target_df) < 100 else 50
        matches = find_similar_patterns(target_df, history_df, window_size=window)
        bias, ret, conf, fp_risk = analyze_probabilistic_bias(matches)
        
        # Layer 3 score out of 20
        l3_score = round(20 * conf * (1.0 - (0.5 if fp_risk else 0.0)), 2)

        result = {
            "historical_bias": bias,
            "avg_weighted_return": round(ret * 100, 4),
            "match_confidence": round(conf, 2),
            "false_positive_risk": fp_risk,
            "layer3_score": l3_score,
            "reasoning": f"Probabilistic Similarity: {round(conf*100,1)}%. Result: {bias} (FP Risk: {fp_risk})"
        }
        print(json.dumps(result, indent=2))
        
    except Exception as e:
        print(json.dumps({"error": str(e)}))
        sys.exit(1)

if __name__ == "__main__":
    main()
