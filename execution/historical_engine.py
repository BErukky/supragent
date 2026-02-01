import pandas as pd
import numpy as np
import argparse
import json
import sys

def normalize(series):
    """
    Normalizes a price series to start at 1.0 (Percentage growth view)
    or Z-score standardization (Mean=0, Std=1).
    Here using simple % change normalization for shape comparison.
    """
    if len(series) == 0:
        return series
    return (series - series.min()) / (series.max() - series.min())

def euclidean_distance(s1, s2):
    """
    Calculates Euclidean distance between two series.
    Lower is better.
    """
    return np.linalg.norm(s1 - s2)

def find_similar_patterns(target_df, history_df, window_size=50, top_k=3):
    """
    Finds historical windows similar to the recent target window.
    """
    if len(target_df) < window_size:
        return []
        
    # Extract just the closing prices for the pattern
    target_pattern = target_df['close'].iloc[-window_size:].values
    target_norm = normalize(target_pattern)
    
    matches = []
    
    # Iterate through history
    # Optimization: This is O(N*M) naive search. For production, use Faiss or similar.
    hist_closes = history_df['close'].values
    hist_dates = history_df['timestamp'].values
    
    # We stop `prediction_window` before end to allow looking ahead
    prediction_window = 24 # look at next 24 candles
    limit = len(hist_closes) - window_size - prediction_window
    
    for i in range(0, limit, 10): # Step 10 to speed up
        candidate = hist_closes[i : i+window_size]
        candidate_norm = normalize(candidate)
        
        dist = euclidean_distance(target_norm, candidate_norm)
        
        matches.append({
            "index": i,
            "dist": dist,
            "date": str(hist_dates[i]),
            "next_returns": (hist_closes[i+window_size+prediction_window] - hist_closes[i+window_size]) / hist_closes[i+window_size]
        })
        
    # Sort by distance (lowest first)
    matches.sort(key=lambda x: x['dist'])
    
    return matches[:top_k]

def analyze_matches(matches):
    if not matches:
        return "UNCLEAR", 0.0
        
    # Count positive vs negative outcomes
    positive = sum(1 for m in matches if m['next_returns'] > 0)
    negative = sum(1 for m in matches if m['next_returns'] < 0)
    
    avg_return = sum(m['next_returns'] for m in matches) / len(matches)
    
    if positive > negative:
        return "BULLISH", avg_return
    elif negative > positive:
        return "BEARISH", avg_return
    else:
        return "UNCLEAR", avg_return

def main():
    parser = argparse.ArgumentParser(description='Analyze Historical Similarity.')
    parser.add_argument('--target', type=str, required=True, help='Current market data CSV')
    parser.add_argument('--history', type=str, help='Historical DB CSV (optional, defaults to target if not provided)')
    args = parser.parse_args()
    
    try:
        # Load Data
        target_df = pd.read_csv(args.target)
        history_df = pd.read_csv(args.history) if args.history else target_df
        
        # Run Analysis
        # Using a smaller window for testing if data is small
        window = 20 if len(target_df) < 100 else 50
        
        matches = find_similar_patterns(target_df, history_df, window_size=window)
        bias, avg_ret = analyze_matches(matches)
        
        result = {
            "historical_bias": bias,
            "avg_future_return_pct": round(avg_ret * 100, 2),
            "match_count": len(matches),
            "top_match_dates": [m['date'] for m in matches],
            "similarity_scores": [round(1/(1+m['dist']), 2) for m in matches] # Convert dist to score 0-1
        }
        
        print(json.dumps(result, indent=2))
        
    except Exception as e:
        print(json.dumps({"error": str(e)}))
        sys.exit(1)

if __name__ == "__main__":
    main()
