"""
bot_settings.py — Persistent bot configuration layer.
Settings are stored in .tmp/bot_settings.json and override .env values.
Falls back to .env / defaults if the file doesn't exist.
"""
import os
import json
from datetime import date
from dotenv import load_dotenv

load_dotenv()

SETTINGS_FILE = ".tmp/bot_settings.json"

DEFAULTS = {
    "account_balance":      60.0,
    "risk_per_trade_pct":   20.0,   # % of balance per trade
    "daily_drawdown_limit": 50.0,   # % of starting balance — pauses bot if hit
    "monitor_interval":     300,    # seconds between price checks for open trades
    "daily_start_balance":  None,   # set on first trade of the day
    "daily_realized_pnl":   0.0,    # sum of closed trade P&L today
    "daily_date":           None,   # YYYY-MM-DD — resets counters when date changes
}


def _load_raw() -> dict:
    try:
        os.makedirs(".tmp", exist_ok=True)
        if os.path.exists(SETTINGS_FILE):
            with open(SETTINGS_FILE, "r") as f:
                return json.load(f)
    except Exception:
        pass
    return {}


def _save_raw(data: dict):
    os.makedirs(".tmp", exist_ok=True)
    with open(SETTINGS_FILE, "w") as f:
        json.dump(data, f, indent=2)


def load_settings() -> dict:
    """Returns merged settings: file > env > defaults."""
    raw = _load_raw()
    settings = dict(DEFAULTS)

    # Apply .env overrides
    if os.environ.get("ACCOUNT_BALANCE"):
        settings["account_balance"] = float(os.environ["ACCOUNT_BALANCE"])
    if os.environ.get("RISK_PER_TRADE"):
        settings["risk_per_trade_pct"] = float(os.environ["RISK_PER_TRADE"])
    if os.environ.get("DAILY_DRAWDOWN_LIMIT"):
        settings["daily_drawdown_limit"] = float(os.environ["DAILY_DRAWDOWN_LIMIT"])

    # File values win over env
    settings.update(raw)

    # Auto-reset daily counters if date changed
    today = str(date.today())
    if settings.get("daily_date") != today:
        settings["daily_date"] = today
        settings["daily_start_balance"] = settings["account_balance"]
        settings["daily_realized_pnl"] = 0.0
        _save_raw(settings)

    return settings


def save_setting(key: str, value) -> dict:
    """Updates a single setting and returns the full settings dict."""
    raw = _load_raw()
    raw[key] = value
    _save_raw(raw)
    return load_settings()


def record_trade_close(pnl_usd: float):
    """
    Called when a trade closes. Updates balance and daily P&L.
    Returns updated settings dict including whether drawdown limit is hit.
    """
    s = load_settings()
    new_balance = round(s["account_balance"] + pnl_usd, 4)
    new_daily   = round(s["daily_realized_pnl"] + pnl_usd, 4)

    raw = _load_raw()
    raw["account_balance"]     = new_balance
    raw["daily_realized_pnl"]  = new_daily
    if raw.get("daily_start_balance") is None:
        raw["daily_start_balance"] = s["account_balance"]
    _save_raw(raw)
    return load_settings()


def is_drawdown_limit_hit() -> tuple[bool, str]:
    """
    Returns (True, reason_str) if daily drawdown gate is active.
    """
    s = load_settings()
    start = s.get("daily_start_balance") or s["account_balance"]
    if start <= 0:
        return False, ""
    loss_pct = ((start - s["account_balance"]) / start) * 100
    limit    = s["daily_drawdown_limit"]
    if loss_pct >= limit:
        return True, (
            f"🛑 *Daily Drawdown Limit Hit*\n"
            f"Started today at `${start}` — now at `${s['account_balance']}`\n"
            f"Loss: `{round(loss_pct, 1)}%` exceeds your `{limit}%` daily limit.\n"
            f"Trading paused. Use /resetday to override."
        )
    return False, ""


def format_settings_panel() -> str:
    """Returns a Telegram-formatted settings summary."""
    s = load_settings()
    bal   = s["account_balance"]
    risk  = s["risk_per_trade_pct"]
    dd    = s["daily_drawdown_limit"]
    dpnl  = s["daily_realized_pnl"]
    risk_usd = round(bal * risk / 100, 2)
    dd_usd   = round(bal * dd / 100, 2)
    pnl_emoji = "🟢" if dpnl >= 0 else "🔴"

    return (
        "⚙️ *CURRENT SETTINGS*\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"💰 *Balance:*       `${bal}`\n"
        f"⚡ *Risk/Trade:*    `{risk}%`  (${risk_usd} per trade)\n"
        f"🛑 *Daily Limit:*   `{dd}%`  (max ${dd_usd} loss/day)\n"
        f"{pnl_emoji} *Today's P&L:*   `${dpnl}`\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "Use /setbalance, /setrisk, /setdrawdown to adjust."
    )
