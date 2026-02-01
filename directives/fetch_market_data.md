# Directive: Fetch Market Data

## Goal

Fetch historical OHLCV (Open, High, Low, Close, Volume) data for specified crypto assets from public exchanges (Binance via CCXT) and save it to a CSV file for analysis.

## Inputs

- `--symbol`: The trading pair (e.g., `BTC/USDT`, `ETH/USDT`). Default: `BTC/USDT`.
- `--timeframe`: The time interval (e.g., `1h`, `15m`, `4h`). Default: `1h`.
- `--limit`: Number of candles to fetch. Default: `100`.

## Tools / Scripts

- `execution/market_data.py`

## Outputs

- CSV file in `.tmp/` directory.
- Filename format: `.tmp/{symbol}_{timeframe}.csv` (slashes in symbol replaced by underscores).
- CSV columns: `timestamp,open,high,low,close,volume`

## Edge Cases / Constraints

- Rate limits: The script should handle or avoid exchange rate limits.
- Connectivity: Handle network errors gracefully.
- Invalid Symbol/Timeframe: Return a clear error message.
