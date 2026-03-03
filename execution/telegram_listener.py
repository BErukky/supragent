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

import threading

def process_command(chat_id, command, args):
    """
    Handles command execution. Now designed to be run in a separate thread.
    """
    print(f"Processing command: {command} from {chat_id}", file=sys.stderr)
    
    # Normalize command (Handle cases like /analyzeBTC/USD)
    cmd_clean = command.lower()
    if "/analyze" in cmd_clean and len(cmd_clean) > 8:
        args = [command[8:]] + args
        command = "/analyze"
    
    if str(chat_id) != str(ALLOWED_CHAT_ID):
        send_message(chat_id, "⛔ Authorization Failed. You are not the owner of this bot.")
        return

    if command == "/start" or command == "/help":
        msg = (
            "🤖 *Super Signals Bot Interface*\n\n"
            "Available Commands:\n"
            "• `/scan` - Full Market Scan (Top 10 + News)\n"
            "• `/scan_tech` - Pure Technical Scan (Ignore News)\n"
            "• `/analyze <SYMBOL>` - Deep analysis of a coin\n"
            "• `/help` - Show this menu"
        )
        send_message(chat_id, msg)

    elif command == "/scan" or command == "/scan_tech":
        no_news = (command == "/scan_tech")
        send_message(chat_id, f"🔍 *Starting {'Technical ' if no_news else 'Full '}Market Scan...*")
        try:
            # We use a longer timeout for the scanner as it analyzes many assets
            cmd = [sys.executable, "execution/market_scanner.py"]
            if no_news: cmd.append("--no_news")
            
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
            
            # Check output for "No high-confidence" message
            if "No high-confidence setups found" in result.stdout:
                send_message(chat_id, "📉 *Scan Complete*: No actionable setups found. Market is defensive.")
            else:
                 send_message(chat_id, "✅ *Scan Complete*. Check above for alerts.")
                 
        except subprocess.TimeoutExpired:
            send_message(chat_id, "⌛ *Scan Timeout*: The market scan took too long. Check logs for partial results.")
        except Exception as e:
            send_message(chat_id, f"❌ Scan Error: {str(e)}")

    elif command == "/analyze":
        if not args:
            send_message(chat_id, "⚠️ Usage: `/analyze SYMBOL` (e.g. `/analyze BTC/USD`)")
            return
            
        symbol = args[0].upper().replace(" ", "")
        send_message(chat_id, f"🔬 *Analyzing {symbol}...*")
        
        try:
            result = subprocess.run(
                [sys.executable, "main.py", "--symbol", symbol],
                capture_output=True, text=True, timeout=180
            )
            
            output = result.stdout
            if result.returncode == 0:
                signal = "UNKNOWN"
                for line in output.split("\n"):
                    if "SIGNAL:" in line:
                        signal = line.split("SIGNAL:", 1)[1].strip()
                
                is_wait = "WAIT" in signal
                msg = f"📊 *Report for {symbol}*\n\n*Signal:* {signal}\n\nAnalysis complete."
                if is_wait:
                     msg += "\n⚠️ *Governance Active*: Trade blocked due to risk/structure."
                send_message(chat_id, msg)
            else:
                send_message(chat_id, f"❌ Analysis Failed for {symbol}.\n`{result.stderr[:200]}`")

        except subprocess.TimeoutExpired:
            send_message(chat_id, f"⌛ *Analysis Timeout*: {symbol} analysis exceeded 3 minutes. This usually happens when the server is overwhelmed. Please try again in a moment.")
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
            resp = requests.get(url, timeout=45)
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
                            # Run processing in a separate thread to keep the poll loop alive
                            threading.Thread(target=process_command, args=(chat_id, command, args), daemon=True).start()
                            
            time.sleep(1)
            
        except Exception as e:
            print(f"Poll Error: {e}", file=sys.stderr)
            time.sleep(5)

if __name__ == "__main__":
    main_loop()
