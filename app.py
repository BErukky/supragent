from flask import Flask, jsonify
import os
import sys
import time
import threading
import logging
import json
import requests
from datetime import datetime

# ─────────────────────────────────────────────────────────────────────────────
# Phase 5.3: Structured JSON Logger (shared with telegram_listener.py)
# ─────────────────────────────────────────────────────────────────────────────
logging.basicConfig(format="%(message)s", level=logging.INFO, stream=sys.stderr)

def log(level: str, event: str, **kwargs):
    entry = {"ts": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"), "level": level, "event": event}
    entry.update(kwargs)
    logging.info(json.dumps(entry))


# ─────────────────────────────────────────────────────────────────────────────
# Phase 5.2: Thread Crash Recovery Supervisor
#
# Problem before this fix:
#   The Telegram listener ran in a plain daemon thread. If it crashed (network
#   timeout, malformed RSS, unhandled exception), the thread died silently.
#   Flask's health check at GET / still returned HTTP 200, so Render/Heroku
#   thought the app was healthy — but the bot was completely dead.
#
# Fix:
#   A supervisor loop wraps main_loop() and restarts it after any crash with
#   exponential back-off (10s → 20s → 40s, capped at 120s). This means the
#   bot self-heals from transient failures without any manual intervention.
# ─────────────────────────────────────────────────────────────────────────────

# Shared state for health check endpoint
_bot_state = {
    "status":       "starting",   # starting | online | restarting | crashed
    "restarts":     0,
    "last_restart": None,
    "uptime_start": datetime.now().isoformat(),
}

def supervised_bot():
    """
    Supervisor that keeps the Telegram listener running even after crashes.
    Uses exponential back-off: 10s, 20s, 40s, 80s, capped at 120s.
    """
    from execution.telegram_listener import main_loop

    backoff = 10   # seconds
    _bot_state["status"] = "online"

    while True:
        try:
            log("INFO", "bot_thread_start", restart_count=_bot_state["restarts"])
            main_loop()
            # main_loop() is an infinite loop — if it returns, something is wrong
            log("WARN", "bot_thread_exited_normally")
        except Exception as e:
            _bot_state["status"]       = "restarting"
            _bot_state["restarts"]    += 1
            _bot_state["last_restart"] = datetime.now().isoformat()
            log("ERROR", "bot_thread_crashed",
                error=str(e),
                restart_count=_bot_state["restarts"],
                next_retry_secs=backoff)

        # Wait before restarting, with exponential back-off
        time.sleep(backoff)
        backoff = min(backoff * 2, 120)   # cap at 2 minutes
        _bot_state["status"] = "online"


# ─────────────────────────────────────────────────────────────────────────────
# Flask Application
# ─────────────────────────────────────────────────────────────────────────────
app = Flask(__name__)


# DEBUG ENDPOINT — remove or add auth before any public/multi-user deployment.
# Exposes raw trade and signal data over an unauthenticated HTTP route.
# Fine for solo Render testing; not suitable for production.
@app.route("/debug/files")
def debug_files():
    import os, json
    def _read(path):
        if os.path.exists(path):
            try:
                with open(path, "r") as f:
                    return json.load(f)
            except Exception as e:
                return {"error": str(e)}
        return None
    return jsonify({
        "trades":      _read(".tmp/trades.json"),
        "signals_log": _read(".tmp/signals_log.json"),
    }), 200


@app.route("/")
def health_check():
    """
    Enhanced health check — now reports bot supervisor status so monitoring
    tools (UptimeRobot, Render health checks) can distinguish between
    'Flask is alive' and 'bot thread is actually running'.
    """
    uptime_secs = (datetime.now() - datetime.fromisoformat(_bot_state["uptime_start"])).seconds
    return jsonify({
        "status":         "online",
        "bot_status":     _bot_state["status"],
        "bot_restarts":   _bot_state["restarts"],
        "last_restart":   _bot_state["last_restart"],
        "uptime_seconds": uptime_secs,
        "version":        "2.1.0"
    }), 200


@app.route("/ping")
def ping():
    """Lightweight keep-alive endpoint — faster than / for external pingers."""
    return "pong", 200


def _self_ping_loop():
    """
    Pings own public Render URL every 10 minutes to prevent free-tier sleep.
    RENDER_EXTERNAL_URL is set automatically by Render on all services.
    Falls back to localhost if not on Render (local dev).
    """
    time.sleep(60)  # wait for gunicorn to fully start first
    public_url = os.environ.get("RENDER_EXTERNAL_URL", "").rstrip("/")
    port       = int(os.environ.get("PORT", 5000))
    url        = f"{public_url}/ping" if public_url else f"http://localhost:{port}/ping"
    log("INFO", "keepalive_started", target=url)
    while True:
        try:
            r = requests.get(url, timeout=10)
            log("INFO", "keepalive_ping", status=r.status_code, target=url)
        except Exception as e:
            log("WARN", "keepalive_ping_failed", error=str(e))
        time.sleep(600)  # every 10 minutes


def _start_supervisor():
    """Starts the supervised bot thread and self-ping keep-alive."""
    t = threading.Thread(target=supervised_bot, name="BotSupervisor", daemon=True)
    t.start()
    p = threading.Thread(target=_self_ping_loop, name="KeepAlive", daemon=True)
    p.start()
    log("INFO", "supervisor_started", thread=t.name)


# Start the supervisor in both local dev and production (Gunicorn)
if __name__ == "__main__":
    # Local development
    _start_supervisor()
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
else:
    # Gunicorn / Production — runs when gunicorn imports the app module
    _start_supervisor()
