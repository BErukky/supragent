import requests
import time
import os
import sys
import subprocess
import json

# Setup Environment
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
ALLOWED_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

if not BOT_TOKEN:
    print("Error: Missing TELEGRAM_BOT_TOKEN in .env")
    sys.exit(1)

BASE_URL = f"https://api.telegram.org/bot{BOT_TOKEN}"

def send_message(chat_id, text):
    url = f"{BASE_URL}/sendMessage"
    payload = {"chat_id": chat_id, "text": text, "parse_mode": "Markdown"}
    try:
        requests.post(url, json=payload, timeout=5)
    except Exception as e:
        print(f"Failed to send message: {e}", file=sys.stderr)

def process_command(chat_id, command, args):
    print(f"Processing command: {command} from {chat_id}", file=sys.stderr)
    
    if str(chat_id) != str(ALLOWED_CHAT_ID):
        send_message(chat_id, "⛔ Authorization Failed. You are not the owner of this bot.")
        return

    if command == "/start" or command == "/help":
        msg = (
            "🤖 *Super Signals Bot Interface*\n\n"
            "Available Commands:\n"
            "• `/scan` - Run full market scan (Top 10)\n"
            "• `/analyze <SYMBOL>` - Analyze specific coin (e.g. `/analyze BTC/USD`)\n"
            "• `/help` - Show this menu"
        )
        send_message(chat_id, msg)

    elif command == "/scan":
        send_message(chat_id, "🔍 *Starting Market Scan...* (This may take ~30s)")
        try:
            # Run market_scanner.py
            # Note: market_scanner.py already sends Telegram Alerts on hits.
            # We just capture stdout for a summary.
            result = subprocess.run(
                [sys.executable, "execution/market_scanner.py"],
                capture_output=True, text=True
            )
            
            # Check output for "No high-confidence" message
            if "No high-confidence setups found" in result.stdout:
                send_message(chat_id, "📉 *Scan Complete*: No actionable setups found. Market is defensive.")
            else:
                 send_message(chat_id, "✅ *Scan Complete*. Check above for alerts.")
                 
        except Exception as e:
            send_message(chat_id, f"❌ Scan Error: {str(e)}")

    elif command == "/analyze":
        if not args:
            send_message(chat_id, "⚠️ Usage: `/analyze SYMBOL` (e.g. `/analyze BTC/USD`)")
            return
            
        symbol = args[0].upper()
        send_message(chat_id, f"🔬 *Analyzing {symbol}...*")
        
        try:
            # Run main.py for single symbol
            # We need to parse the JSON output from report_engine if main.py prints it
            # But main.py output format is designed for console reading.
            # Let's run it and capture the summary.
            
            result = subprocess.run(
                [sys.executable, "main.py", "--symbol", symbol],
                capture_output=True, text=True
            )
            
            output = result.stdout
            
            # Extract key info if possible, or just send a summary based on exit code
            if result.returncode == 0:
                # Naive parsing for "SIGNAL:" line
                signal = "UNKNOWN"
                conf = "0"
                for line in output.split("\n"):
                    if "SIGNAL:" in line:
                        signal = line.split("SIGNAL:", 1)[1].strip()
                    if "Confidence:" in line: # From report text
                         conf = line.split("Confidence:", 1)[1].strip()
                
                # Check for Governance Warnings structure in stdout
                is_wait = "WAIT" in signal
                
                msg = f"📊 *Report for {symbol}*\n\n*Signal:* {signal}\n\nCheck console logs for details."
                if is_wait:
                     msg += "\n⚠️ *Governance Active*: Trade blocked due to risk/structure."
                     
                send_message(chat_id, msg)
            else:
                send_message(chat_id, f"❌ Analysis Failed. Check logs.\n`{result.stderr[:100]}`")

        except Exception as e:
             send_message(chat_id, f"❌ Execution Error: {str(e)}")

    else:
        send_message(chat_id, "❓ Unknown command. Try `/help`.")

def main_loop():
    print(f"Telegram Listener Online. Waiting for commands from {ALLOWED_CHAT_ID}...", file=sys.stderr)
    offset = 0
    
    while True:
        try:
            url = f"{BASE_URL}/getUpdates?timeout=30&offset={offset}"
            resp = requests.get(url, timeout=35)
            data = resp.json()
            
            if data.get("ok"):
                for update in data.get("result", []):
                    offset = update["update_id"] + 1
                    
                    if "message" in update and "text" in update["message"]:
                        chat_id = update["message"]["chat"]["id"]
                        text = update["message"]["text"].strip()
                        
                        if text.startswith("/"):
                            parts = text.split()
                            command = parts[0]
                            args = parts[1:]
                            process_command(chat_id, command, args)
                            
            time.sleep(1)
            
        except Exception as e:
            print(f"Poll Error: {e}", file=sys.stderr)
            time.sleep(5)

if __name__ == "__main__":
    main_loop()
