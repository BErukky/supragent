# Ensure we can import from the parent directory (root)
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))
try:
    from main import run_full_analysis
    import market_scanner
except ImportError:
    # Fallback to direct imports if run from root
    from main import run_full_analysis
    import execution.market_scanner as market_scanner

def send_message(chat_id, text):
    # Truncate if too long for Telegram (4096 chars)
    if len(text) > 4000:
        text = text[:3900] + "\n... (Report Truncated)"
        
    url = f"{BASE_URL}/sendMessage"
    payload = {"chat_id": chat_id, "text": text, "parse_mode": "Markdown"}
    try:
        requests.post(url, json=payload, timeout=5)
    except Exception as e:
        print(f"Failed to send message: {e}", file=sys.stderr)

def process_command(chat_id, command, args):
    """
    Handles command execution via direct function calls.
    """
    print(f"Processing command: {command} from {chat_id}", file=sys.stderr)
    
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
        
        # Call market_scanner directly in a thread-safe way (it handles its own Telegram updates)
        try:
            # We mock sys.argv for the scanner parser
            old_argv = sys.argv
            sys.argv = ["market_scanner.py"]
            if no_news: sys.argv.append("--no_news")
            
            market_scanner.main()
            
            sys.argv = old_argv
            send_message(chat_id, "✅ *Scan Complete*. All alerts sent.")
        except Exception as e:
            send_message(chat_id, f"❌ Scan Error: {str(e)}")

    elif command == "/analyze":
        if not args:
            send_message(chat_id, "⚠️ Usage: `/analyze SYMBOL` (e.g. `/analyze BTC/USD`)")
            return
            
        symbol = args[0].upper().replace(" ", "")
        send_message(chat_id, f"🔬 *Analyzing {symbol}...*")
        
        try:
            # Call engine directly
            report = run_full_analysis(symbol)
            
            if report and "error" not in report:
                report_msg = format_institutional_report(symbol, report)
                send_message(chat_id, report_msg)
            else:
                send_message(chat_id, f"❌ Analysis Failed for {symbol}.\n`{report.get('error', 'Unknown Error')}`")

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
