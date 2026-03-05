import argparse
import pandas as pd
import os
import sys
import ccxt

def fetch_data(symbol, timeframe, limit):
    """
    Fetches OHLCV data. Tries yfinance first (high reliability), fallbacks to Kraken.
    """
    print(f"Fetching {limit} candles for {symbol} on {timeframe} timeframe...")
    
    # Standardize symbol for yfinance if it's a known crypto
    yf_symbol = symbol.replace('/', '-')
    if 'BTC' in yf_symbol:
        yf_symbol = 'BTC-USD'
    elif 'ETH' in yf_symbol:
        yf_symbol = 'ETH-USD'

    try:
        import yfinance as yf
        print(f"Attempting live fetch via yfinance: {yf_symbol}")
        
        # Map CCXT timeframes to yfinance intervals
        interval_map = {'1h': '1h', '15m': '15m', '4h': '1h', '1d': '1d'}
        interval = interval_map.get(timeframe, '1h')
        
        # Fetch a bit more than needed to ensure we have the 'limit'
        data = yf.download(yf_symbol, period='5d', interval=interval, progress=False)
        
        if data.empty:
            raise Exception("yfinance returned empty dataframe")

        # Standardize columns to match CCXT output
        df = data.reset_index()
        # yfinance columns are sometimes multi-indexed or mixed case
        df.columns = [c[0].lower() if isinstance(c, tuple) else c.lower() for c in df.columns]
        
        # Determine timestamp column
        ts_col = 'datetime' if 'datetime' in df.columns else 'date'
        df['timestamp'] = pd.to_datetime(df[ts_col]).astype('int64') // 10**6
        
        # Extract OHLCV
        df = df[['timestamp', 'open', 'high', 'low', 'close', 'volume']]
        df = df.tail(limit)

        os.makedirs('.tmp', exist_ok=True)
        safe_symbol = symbol.replace('/', '_')
        filename = f".tmp/{safe_symbol}_{timeframe}.csv"
        
        df.to_csv(filename, index=False)
        print(f"Success: REAL-TIME data saved to {filename}")
        return filename

    except Exception as e:
        print(f"yfinance failed: {e}. Trying Kraken fallback...")
        try:
            exchange = ccxt.kraken()
            ohlcv = exchange.fetch_ohlcv(symbol, timeframe, limit=limit)
            df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
            
            os.makedirs('.tmp', exist_ok=True)
            safe_symbol = symbol.replace('/', '_')
            filename = f".tmp/{safe_symbol}_{timeframe}.csv"
            df.to_csv(filename, index=False)
            print(f"Success: REAL-TIME data fetched via Kraken.")
            return filename
        except Exception as e2:
            print(f"FATAL: All live data sources failed. Error: {e2}")
            sys.exit(1)

def main():
    parser = argparse.ArgumentParser(description='Fetch OHLCV market data.')
    parser.add_argument('--symbol', type=str, default='BTC/USD', help='Trading symbol')
    parser.add_argument('--timeframe', type=str, default='1h', help='Timeframe')
    parser.add_argument('--limit', type=int, default=100, help='Limit')
    
    args = parser.parse_args()
    fetch_data(args.symbol, args.timeframe, args.limit)

if __name__ == "__main__":
    main()
