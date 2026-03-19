import os
import requests
from dotenv import load_dotenv

def test_api_keys():
    print("Loading environment variables from .env...")
    load_dotenv()
    
    groq_key = os.environ.get("GROQ_API_KEY")
    alpha_key = os.environ.get("ALPHAVANTAGE_API_KEY")
    twelve_key = os.environ.get("TWELVEDATA_API_KEY")
    bot_token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    
    print("\n--- Testing GROQ API ---")
    if groq_key:
        headers = {
            "Authorization": f"Bearer {groq_key}",
            "Content-Type": "application/json"
        }
        payload = {
            "model": "llama-3.1-8b-instant",
            "messages": [{"role": "user", "content": "Say 'hello world' in one sentence."}]
        }
        try:
            res = requests.post("https://api.groq.com/openai/v1/chat/completions", headers=headers, json=payload)
            if res.status_code == 200:
                print("[SUCCESS] GROQ API works!")
            else:
                print(f"[FAIL] GROQ API Failed ({res.status_code}): {res.text[:200]}")
        except Exception as e:
            print(f"[ERROR] GROQ API Connection error: {e}")
    else:
        print("[FAIL] GROQ_API_KEY not found in .env")

    print("\n--- Testing Alpha Vantage API ---")
    if alpha_key:
        url = f"https://www.alphavantage.co/query?function=FX_DAILY&from_symbol=EUR&to_symbol=USD&apikey={alpha_key}"
        try:
            res = requests.get(url)
            data = res.json()
            if "Time Series FX (Daily)" in data or "Meta Data" in data:
                print("[SUCCESS] Alpha Vantage API works!")
            elif "Information" in data and "rate limit" in data["Information"].lower():
                 print("[WARN] Alpha Vantage API Rate limited, but key seems valid.")
            else:
                print(f"[FAIL] Alpha Vantage API Failed: {str(data)[:200]}")
        except Exception as e:
            print(f"[ERROR] Alpha Vantage API Connection error: {e}")
    else:
        print("[FAIL] ALPHAVANTAGE_API_KEY not found in .env")

    print("\n--- Testing Twelve Data API ---")
    if twelve_key:
        url = f"https://api.twelvedata.com/time_series?symbol=EUR/USD&interval=1min&apikey={twelve_key}"
        try:
            res = requests.get(url)
            data = res.json()
            if "meta" in data and "values" in data:
                print("[SUCCESS] Twelve Data API works!")
            else:
                print(f"[FAIL] Twelve Data API Failed: {str(data)[:200]}")
        except Exception as e:
            print(f"[ERROR] Twelve Data API Connection error: {e}")
    else:
         print("[FAIL] TWELVEDATA_API_KEY not found in .env")

    print("\n--- Testing Telegram Integration ---")
    if bot_token and chat_id:
        url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        payload = {
            "chat_id": chat_id,
            "text": "🚀 *Super Signals Configuration Successful!*\n\nAll systems are now connected and ready for analysis.",
            "parse_mode": "Markdown"
        }
        try:
            res = requests.post(url, json=payload)
            if res.status_code == 200:
                print("[SUCCESS] Telegram Message Sent!")
            else:
                print(f"[FAIL] Telegram Failed ({res.status_code}): {res.text[:200]}")
        except Exception as e:
            print(f"[ERROR] Telegram Connection error: {e}")
    else:
        print("[FAIL] Telegram credentials missing in .env")

if __name__ == "__main__":
    test_api_keys()
