import os
import requests
import sys

# Try to load .env manually if python-dotenv is not installed
def load_env():
    env_path = ".env"
    if os.path.exists(env_path):
        with open(env_path, "r") as f:
            for line in f:
                if "=" in line:
                    key, value = line.strip().split("=", 1)
                    os.environ[key] = value

load_env()
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

def send_telegram_alert(message):
    """
    Sends a formatted message to the configured Telegram Chat.
    """
    if not BOT_TOKEN or not CHAT_ID:
        print("[!] Telegram Credentials missing in .env")
        return False

    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": CHAT_ID,
        "text": message,
        "parse_mode": "Markdown"
    }
    
    try:
        response = requests.post(url, json=payload, timeout=5)
        if response.status_code == 200:
            print(">> Telegram Alert Sent.", file=sys.stderr)
            return True
        else:
            print(f"[!] Telegram Error: {response.text}", file=sys.stderr)
            return False
            
    except Exception as e:
        print(f"[!] Connection Failed: {e}", file=sys.stderr)
        return False

if __name__ == "__main__":
    # Test Block
    msg = "*Super Signals Test*\nSystem online. 🚀"
    send_telegram_alert(msg)
