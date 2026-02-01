import pandas as pd
import numpy as np
import argparse
import os
from datetime import datetime, timedelta

def generate_random_walk(start_price=50000, periods=100, volatility=0.01):
    """
    Generates synthetic OHLCV data using a random walk.
    """
    data = []
    current_price = start_price
    
    start_time = datetime.now() - timedelta(hours=periods)
    
    for i in range(periods):
        timestamp = start_time + timedelta(hours=i)
        
        # Random percent change
        change = np.random.normal(0, volatility)
        close = current_price * (1 + change)
        
        # Derive OHL based on Close
        open_p = current_price
        high = max(open_p, close) * (1 + abs(np.random.normal(0, volatility/2)))
        low = min(open_p, close) * (1 - abs(np.random.normal(0, volatility/2)))
        
        volume = abs(np.random.normal(1000, 500))
        
        data.append([timestamp, open_p, high, low, close, volume])
        
        current_price = close
        
    df = pd.DataFrame(data, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
    return df

def main():
    parser = argparse.ArgumentParser(description='Generate Mock Market Data')
    parser.add_argument('--symbol', type=str, default='BTC_USDT')
    parser.add_argument('--limit', type=int, default=100)
    args = parser.parse_args()
    
    print(f"Generating {args.limit} mock candles for {args.symbol}...")
    
    df = generate_random_walk(periods=args.limit)
    
    # Save to tmp
    os.makedirs('.tmp', exist_ok=True)
    filename = f".tmp/{args.symbol}_1h.csv" # Hardcoded 1h for simplicity
    df.to_csv(filename, index=False)
    
    print(f"Success: Mock data saved to {filename}")

if __name__ == "__main__":
    main()
