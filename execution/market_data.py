import argparse
import pandas as pd
import os
import sys
import ccxt
import time
import json
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Session cache for data consistency
_DATA_CACHE = {}
_CACHE_TTL = 300  # 5 minutes
_TMP_CLEANED = False  # D2: Only clean once per process lifetime

def get_cached_data(cache_key):
    """Returns cached data if still valid."""
    if cache_key in _DATA_CACHE:
        cached = _DATA_CACHE[cache_key]
        if time.time() - cached['timestamp'] < _CACHE_TTL:
            print(f"  Using cached data ({int(time.time() - cached['timestamp'])}s old)")
            return cached['data']
    return None

def set_cached_data(cache_key, df):
    """Stores data in cache."""
    _DATA_CACHE[cache_key] = {'data': df.copy(), 'timestamp': time.time()}

def _cleanup_tmp(max_age_hours=24):
    """
    D2: Deletes .tmp/*.csv files older than max_age_hours on startup.
    Prevents indefinite accumulation of stale data files.
    """
    global _TMP_CLEANED
    if _TMP_CLEANED:
        return
    _TMP_CLEANED = True
    cutoff = time.time() - (max_age_hours * 3600)
    try:
        for fname in os.listdir('.tmp'):
            if fname.endswith('.csv'):
                fpath = os.path.join('.tmp', fname)
                if os.path.getmtime(fpath) < cutoff:
                    os.remove(fpath)
    except Exception:
        pass  # Non-blocking — never fail the analysis over a cleanup error

def validate_ohlc(df):
    """Validates OHLC data quality."""
    if len(df) < 50:
        return False, "Insufficient rows"
    if df['close'].std() < df['close'].mean() * 0.001:
        return False, "Flat data (no price movement)"
    if df[['open','high','low','close']].isna().any().any():
        return False, "Contains NaN values"
    if not (df['high'] >= df['low']).all():
        return False, "Invalid OHLC logic"
    if not (df['high'] >= df['open']).all() or not (df['high'] >= df['close']).all():
        return False, "High < Open/Close"
    if not (df['low'] <= df['open']).all() or not (df['low'] <= df['close']).all():
        return False, "Low > Open/Close"
    return True, "Valid"

def fetch_via_ccxt(symbol, timeframe, limit):
    """Fetches data from CCXT exchanges (Binance/Bybit/Kraken)."""
    exchanges = [
        ('binance', ccxt.binance()),
        ('bybit', ccxt.bybit()),
        ('kraken', ccxt.kraken())
    ]
    
    for exchange_name, exchange in exchanges:
        try:
            print(f"  Trying {exchange_name}...")
            ohlcv = exchange.fetch_ohlcv(symbol, timeframe, limit=limit)
            if not ohlcv or len(ohlcv) < 10:
                continue
            
            df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
            valid, msg = validate_ohlc(df)
            if valid:
                print(f"  Success: {exchange_name} returned {len(df)} candles")
                return df
            else:
                print(f"  {exchange_name} data invalid: {msg}")
        except Exception as e:
            print(f"  {exchange_name} failed: {e}")
    
    return None


def fetch_via_twelvedata(symbol, timeframe, limit):
    """Fetches forex data from Twelve Data (backup for intraday FX)."""
    api_key = os.environ.get('TWELVEDATA_API_KEY')
    if not api_key:
        return None
    
    try:
        from_curr, to_curr = symbol.split('/')
        pair = f"{from_curr}/{to_curr}"
        
        # Twelve Data interval mapping
        interval_map = {'1m': '1min', '5m': '5min', '15m': '15min', '1h': '1h', '4h': '4h', '1d': '1day'}
        interval = interval_map.get(timeframe)
        if not interval:
            return None
        
        import requests
        url = f"https://api.twelvedata.com/time_series"
        params = {
            'symbol': pair,
            'interval': interval,
            'outputsize': limit,
            'apikey': api_key,
            'format': 'JSON'
        }
        
        print(f"  Trying Twelve Data: {pair} ({interval})")
        resp = requests.get(url, params=params, timeout=10)
        
        if resp.status_code == 200:
            data = resp.json()
            if 'values' in data:
                values = data['values']
                df = pd.DataFrame([{
                    'timestamp': int(pd.to_datetime(v['datetime']).timestamp() * 1000),
                    'open': float(v['open']),
                    'high': float(v['high']),
                    'low': float(v['low']),
                    'close': float(v['close']),
                    'volume': 0  # Forex doesn't have volume
                } for v in values])
                df = df.sort_values('timestamp').reset_index(drop=True)
                
                valid, msg = validate_ohlc(df)
                if valid:
                    print(f"  Success: Twelve Data returned {len(df)} candles")
                    return df
                else:
                    print(f"  Twelve Data invalid: {msg}")
    except Exception as e:
        print(f"  Twelve Data failed: {e}")
    
    return None

def fetch_via_alphavantage(symbol, timeframe, limit):
    """Fetches forex data from Alpha Vantage (free tier: daily only)."""
    api_key = os.environ.get('ALPHAVANTAGE_API_KEY')
    if not api_key or api_key == 'demo':
        return None
    
    try:
        from_curr, to_curr = symbol.split('/')
        
        # Free tier only supports daily data
        if timeframe != '1d':
            print(f"  Alpha Vantage: Intraday is premium-only, skipping")
            return None
        
        import requests
        url = f"https://www.alphavantage.co/query?function=FX_DAILY&from_symbol={from_curr}&to_symbol={to_curr}&apikey={api_key}&outputsize=full&datatype=csv"
        
        print(f"  Trying Alpha Vantage: {from_curr}/{to_curr} (daily)")
        resp = requests.get(url, timeout=10)
        
        if resp.status_code == 200 and 'timestamp' in resp.text:
            df = pd.read_csv(pd.io.common.StringIO(resp.text))
            df.columns = df.columns.str.lower()
            df['timestamp'] = (pd.to_datetime(df['timestamp']).astype('int64') // 10**6).astype(int)
            df = df[['timestamp', 'open', 'high', 'low', 'close']]
            df['volume'] = 0  # Forex doesn't have volume
            df = df.tail(limit)
            
            valid, msg = validate_ohlc(df)
            if valid:
                print(f"  Success: Alpha Vantage returned {len(df)} daily candles")
                return df
            else:
                print(f"  Alpha Vantage data invalid: {msg}")
    except Exception as e:
        print(f"  Alpha Vantage failed: {e}")
    
    return None

def fetch_via_yfinance(symbol, timeframe, limit):
    """Fetches data from yfinance (commodities/stocks)."""
    SYMBOL_MAP = {
        "BTC/USD": "BTC-USD", "ETH/USD": "ETH-USD", "SOL/USD": "SOL-USD",
        "XRP/USD": "XRP-USD", "ADA/USD": "ADA-USD", "DOGE/USD": "DOGE-USD",
        "XAU/USD": "GC=F", "XAG/USD": "SI=F", "OIL/USD": "CL=F",
        "EUR/USD": "EURUSD=X", "GBP/USD": "GBPUSD=X", "USD/JPY": "USDJPY=X",
        "SP500": "^GSPC", "NASDAQ": "^IXIC", "DOW": "^DJI"
    }
    yf_symbol = SYMBOL_MAP.get(symbol.upper(), symbol.replace('/', '-'))
    
    try:
        import yfinance as yf
        print(f"  Trying yfinance: {yf_symbol}")
        
        interval_map = {'1m': '1m', '5m': '5m', '15m': '15m', '1h': '1h', '4h': '1h', '1d': '1d'}
        interval = interval_map.get(timeframe, '1h')
        
        data = yf.download(yf_symbol, period='5d', interval=interval, progress=False)
        
        if data.empty:
            return None
        
        df = data.reset_index()
        df.columns = [c[0].lower() if isinstance(c, tuple) else c.lower() for c in df.columns]
        
        ts_col = 'datetime' if 'datetime' in df.columns else 'date'
        df['timestamp'] = (pd.to_datetime(df[ts_col]).astype('int64') // 10**6).astype(int)
        df = df[['timestamp', 'open', 'high', 'low', 'close', 'volume']].tail(limit)
        
        valid, msg = validate_ohlc(df)
        if valid:
            print(f"  Success: yfinance returned {len(df)} candles")
            return df
        else:
            print(f"  yfinance data invalid: {msg}")
    except Exception as e:
        print(f"  yfinance failed: {e}")
    
    return None

def fetch_data(symbol, timeframe, limit):
    """
    Smart fallback chain with caching and validation.
    Priority: Cache > CCXT > Twelve Data > Alpha Vantage > yfinance
    D2: Cleans stale .tmp/ CSVs on first call per process.
    """
    _cleanup_tmp()  # D2: Remove CSVs older than 24h once per run
    print(f"Fetching {limit} candles for {symbol} on {timeframe} timeframe...")
    
    # Check cache first
    cache_key = f"{symbol}_{timeframe}_{limit}"
    cached_df = get_cached_data(cache_key)
    if cached_df is not None:
        os.makedirs('.tmp', exist_ok=True)
        safe_symbol = symbol.replace('/', '_')
        filename = f".tmp/{safe_symbol}_{timeframe}.csv"
        cached_df.to_csv(filename, index=False)
        return filename
    
    # Determine asset type
    is_crypto = any(x in symbol.upper() for x in ['BTC', 'ETH', 'SOL', 'XRP', 'ADA', 'DOGE', 'DOT', 'MATIC', 'LTC', 'LINK', 'AVAX'])
    is_forex = '/' in symbol and any(x in symbol.upper() for x in ['USD', 'EUR', 'GBP', 'JPY', 'CHF', 'AUD', 'NZD', 'CAD'])
    
    df = None
    
    # Try CCXT for crypto
    if is_crypto:
        df = fetch_via_ccxt(symbol, timeframe, limit)
    
    # Try Twelve Data for forex (primary)
    if df is None and is_forex:
        df = fetch_via_twelvedata(symbol, timeframe, limit)
    
    # Try Alpha Vantage for forex daily
    if df is None and is_forex:
        df = fetch_via_alphavantage(symbol, timeframe, limit)
    
    # Try yfinance as final fallback
    if df is None:
        df = fetch_via_yfinance(symbol, timeframe, limit)
    
    # Final validation
    if df is None:
        print(f"FATAL: All data sources failed for {symbol}")
        sys.exit(1)
    
    # Cache the result
    set_cached_data(cache_key, df)
    
    # Save to file
    os.makedirs('.tmp', exist_ok=True)
    safe_symbol = symbol.replace('/', '_')
    filename = f".tmp/{safe_symbol}_{timeframe}.csv"
    df.to_csv(filename, index=False)
    print(f"Success: Data saved to {filename}")
    
    return filename

def main():
    parser = argparse.ArgumentParser(description='Fetch OHLCV market data.')
    parser.add_argument('--symbol', type=str, default='BTC/USD', help='Trading symbol')
    parser.add_argument('--timeframe', type=str, default='1h', help='Timeframe')
    parser.add_argument('--limit', type=int, default=100, help='Limit')
    
    args = parser.parse_args()
    fetch_data(args.symbol, args.timeframe, args.limit)

if __name__ == "__main__":
    main()
