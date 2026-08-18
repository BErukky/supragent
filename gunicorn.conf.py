# gunicorn.conf.py — Render production config
#
# Default Gunicorn timeout is 30s. Analysis commands (/analyze, /scalp, /mtf)
# take 30-120s on Render free tier. Without this, Gunicorn kills the worker
# mid-analysis — the bot appears live but commands silently die.

# Worker timeout: 300s (5 min) — covers the slowest /mtf deep analysis
timeout = 300

# Single worker — free tier has limited RAM; multiple workers cause OOM kills
workers = 1

# Use a threaded worker so Flask can handle the keep-alive ping while the
# bot thread is blocked on a long analysis
worker_class = "gthread"
threads = 4

# Bind to Render's PORT env var
bind = "0.0.0.0:" + __import__("os").environ.get("PORT", "5000")

# Log to stderr so Render captures it
accesslog = "-"
errorlog  = "-"
loglevel  = "info"
