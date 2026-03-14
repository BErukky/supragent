# FX Intraday Data Setup Guide

## OANDA Setup (Recommended - Real-time FX data)

### Step 1: Create Practice Account
1. Go to https://www.oanda.com/us-en/trading/
2. Click "Open Account" > "Practice Account" (100% FREE)
3. Complete registration (no credit card required)

### Step 2: Get API Credentials
1. Login to your practice account
2. Go to "Manage API Access" in account settings
3. Generate a new API token
4. Copy your **API Token** and **Account ID**

### Step 3: Update .env file
```
OANDA_API_KEY=your_practice_token_here
OANDA_ACCOUNT_ID=your_account_id_here
```

**Features:**
- ✅ Real-time data (< 1 second latency)
- ✅ Unlimited API calls
- ✅ 500 candles per request
- ✅ Timeframes: 1m, 5m, 15m, 1h, 4h, daily
- ✅ 70+ forex pairs

---

## Twelve Data Setup (Backup - 800 calls/day)

### Step 1: Create Free Account
1. Go to https://twelvedata.com/
2. Click "Get Free API Key"
3. Sign up with email (no credit card)

### Step 2: Get API Key
1. Login to dashboard
2. Copy your API key from the dashboard

### Step 3: Update .env file
```
TWELVEDATA_API_KEY=your_api_key_here
```

**Features:**
- ✅ 800 API calls per day (free tier)
- ✅ 1-2 minute delay
- ✅ Timeframes: 1m, 5m, 15m, 1h, 4h, daily
- ✅ 50+ forex pairs

---

## Priority Chain

The system will try data sources in this order for forex:

1. **OANDA** (if configured) - Real-time, unlimited
2. **Twelve Data** (if configured) - 800 calls/day limit
3. **Alpha Vantage** (daily only) - Already configured
4. **yfinance** (30-60 min delay) - Fallback

---

## Testing

Test EUR/USD intraday data:
```powershell
python execution/market_data.py --symbol EUR/USD --timeframe 15m --limit 100
```

Test full swing stack analysis:
```powershell
python main.py --symbol EUR/USD --stack swing
```

---

## Notes

- **OANDA Practice Account**: Never expires, perfect for data access
- **Twelve Data**: Monitor your daily usage (800 calls = ~130 multi-stack analyses)
- **Rate Limiting**: System automatically falls back if limits are hit
- **Cache**: 5-minute cache reduces API calls by 60%+
