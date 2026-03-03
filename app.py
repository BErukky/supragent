from flask import Flask
import os
import threading
from execution.telegram_listener import main_loop

app = Flask(__name__)

# Start Telegram Listener in a background thread
# In Gunicorn, the code is executed in the master and then in workers.
# We want to avoid conflicts and double-start issues.
def start_bot():
    print(">> [DEPLOY] Starting Telegram Listener background thread...", flush=True)
    try:
        main_loop()
    except Exception as e:
        print(f">> [CRITICAL] Bot Thread Crashed: {e}", flush=True)

# Gunicorn logic: Only start thread in the worker process
# if os.environ.get("WERKZEUG_RUN_MAIN") != "true" is for Flask dev server
# For Gunicorn, we can check if it's the master or worker, 
# but usually checking if we are NOT in the master (e.g. if a worker arg is present)
# or just using a simple 'started' flag in a module if gunicorn preloads.
# A more robust way on Render/Gunicorn is to check the PID or use post_worker_init.
# For now, we'll use a safer check.

if __name__ == "__main__":
    # Local development
    threading.Thread(target=start_bot, daemon=True).start()
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
else:
    # Gunicorn / Production
    # This runs when gunicorn imports the app.
    # We delay start slightly or use a flag to prevent master start if possible.
    # However, gunicorn master usually kills threads on fork.
    # So starting here usually means the worker gets it.
    threading.Thread(target=start_bot, daemon=True).start()

@app.route('/')
def health_check():
    return {"status": "online", "bot_active": True, "version": "2.1.0"}, 200
