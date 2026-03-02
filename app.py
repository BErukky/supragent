from flask import Flask
import os
import threading
from execution.telegram_listener import main_loop

app = Flask(__name__)

# Start Telegram Listener in a background thread
def start_bot():
    print("Starting Telegram Listener thread...")
    main_loop()

# We start the thread only once
if os.environ.get("WERKZEUG_RUN_MAIN") != "true": # Prevent double-start in dev mode
    threading.Thread(target=start_bot, daemon=True).start()

@app.route('/')
def health_check():
    return {"status": "online", "system": "Super Signals v2.0", "bot_active": True, "version": "2.0.1"}, 200

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
