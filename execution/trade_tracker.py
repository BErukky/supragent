"""
trade_tracker.py — Trade lifecycle manager with background price monitor.
Stores open/closed trades in .tmp/trades.json and .tmp/trade_history.json.
Polls prices every N seconds and fires Telegram TP/SL alerts automatically.
"""
import os
import json
import time
import threading
from datetime import datetime

TRADES_FILE  = ".tmp/trades.json"
HISTORY_FILE = ".tmp/trade_history.json"

_monitor_thread: threading.Thread = None
_bot_send_fn = None   # injected by telegram_listener


# ─── Persistence ────────────────────────────────────────────────────────────

def _load_trades() -> list:
    try:
        if os.path.exists(TRADES_FILE):
            with open(TRADES_FILE, "r") as f:
                return json.load(f)
    except Exception:
        pass
    return []


def _save_trades(trades: list):
    os.makedirs(".tmp", exist_ok=True)
    with open(TRADES_FILE, "w") as f:
        json.dump(trades, f, indent=2)


def _load_history() -> list:
    try:
        if os.path.exists(HISTORY_FILE):
            with open(HISTORY_FILE, "r") as f:
                return json.load(f)
    except Exception:
        pass
    return []


def _save_history(history: list):
    os.makedirs(".tmp", exist_ok=True)
    with open(HISTORY_FILE, "w") as f:
        json.dump(history, f, indent=2)


# ─── Core Operations ─────────────────────────────────────────────────────────

def register_trade(symbol: str, direction: str, entry: float, sl: float,
                   tps: list, size_units: float, risk_usd: float,
                   tp_profits: list = None, chat_id: str = None) -> dict:
    """Registers a new open trade."""
    trade = {
        "id":          f"{symbol.replace('/', '_')}_{int(time.time())}",
        "symbol":      symbol,
        "direction":   direction,       # "LONG" or "SHORT"
        "entry":       entry,
        "sl":          sl,
        "tps":         tps,             # [tp1, tp2, tp3]
        "tp_profits":  tp_profits or [],
        "size_units":  size_units,
        "risk_usd":    risk_usd,
        "tps_hit":     [],              # tracks which TPs already triggered
        "status":      "OPEN",
        "opened_at":   datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC"),
        "chat_id":     chat_id,
    }
    trades = _load_trades()
    trades.append(trade)
    _save_trades(trades)
    return trade


def get_open_trades() -> list:
    return [t for t in _load_trades() if t["status"] == "OPEN"]


def close_trade(trade_id: str, exit_price: float) -> dict:
    """Manually closes a trade at the given price. Returns the closed trade record."""
    from bot_settings import record_trade_close

    trades  = _load_trades()
    history = _load_history()
    result  = None

    for t in trades:
        if t["id"] == trade_id and t["status"] == "OPEN":
            is_long  = t["direction"] == "LONG"
            pnl_usd  = round((exit_price - t["entry"]) * t["size_units"] * (1 if is_long else -1), 4)
            rr       = round(pnl_usd / t["risk_usd"], 2) if t["risk_usd"] > 0 else 0

            t["status"]    = "CLOSED"
            t["exit_price"] = exit_price
            t["pnl_usd"]   = pnl_usd
            t["rr_actual"] = rr
            t["closed_at"] = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")

            history.append(t)
            record_trade_close(pnl_usd)
            result = t
            break

    _save_trades([t for t in trades if t["status"] == "OPEN"])
    _save_history(history)
    return result


def get_stats() -> dict:
    """Returns win rate, avg R, net P&L from closed trade history."""
    history = _load_history()
    if not history:
        return {"total": 0, "wins": 0, "losses": 0, "win_rate": 0, "avg_rr": 0, "net_pnl": 0}

    wins   = [t for t in history if t.get("pnl_usd", 0) > 0]
    losses = [t for t in history if t.get("pnl_usd", 0) <= 0]
    net    = sum(t.get("pnl_usd", 0) for t in history)
    rrs    = [t.get("rr_actual", 0) for t in history if t.get("rr_actual")]

    return {
        "total":    len(history),
        "wins":     len(wins),
        "losses":   len(losses),
        "win_rate": round(len(wins) / len(history) * 100, 1),
        "avg_rr":   round(sum(rrs) / len(rrs), 2) if rrs else 0,
        "net_pnl":  round(net, 4),
    }


# ─── Price Monitor ────────────────────────────────────────────────────────────

def _get_live_price(symbol: str) -> float | None:
    """Fetches the latest close price for a symbol."""
    try:
        import sys
        sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        from execution.market_data import fetch_data
        filename = fetch_data(symbol, "1m", 5)
        if filename:
            import pandas as pd
            df = pd.read_csv(filename)
            return float(df["close"].iloc[-1])
    except Exception:
        pass
    return None


def _check_trades(send_fn):
    """Called periodically — checks all open trades for TP/SL hits."""
    from bot_settings import record_trade_close, load_settings

    trades  = _load_trades()
    history = _load_history()
    updated = False

    for t in trades:
        if t["status"] != "OPEN":
            continue

        price = _get_live_price(t["symbol"])
        if price is None:
            continue

        is_long = t["direction"] == "LONG"
        chat_id = t.get("chat_id")

        # ── Check SL ─────────────────────────────────────────────────────
        sl_hit = (is_long and price <= t["sl"]) or (not is_long and price >= t["sl"])
        if sl_hit:
            pnl = round(-abs(t["risk_usd"]), 4)
            t["status"]     = "CLOSED"
            t["exit_price"] = t["sl"]
            t["pnl_usd"]    = pnl
            t["rr_actual"]  = -1.0
            t["closed_at"]  = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
            history.append(t)
            s = record_trade_close(pnl)
            updated = True

            if send_fn and chat_id:
                send_fn(chat_id, (
                    f"🛑 *STOPPED OUT — {t['symbol']}*\n"
                    f"  Price hit SL: `{t['sl']}`\n"
                    f"  Loss:    `−${abs(pnl)}`  (−1.0x R)\n"
                    f"  Balance: `${round(s['account_balance'] - pnl, 2)}` → `${s['account_balance']}`\n"
                    f"  Today's P&L: `${s['daily_realized_pnl']}`"
                ))
            continue

        # ── Check TPs ────────────────────────────────────────────────────
        for i, tp in enumerate(t["tps"]):
            if i in t["tps_hit"]:
                continue
            tp_hit = (is_long and price >= tp) or (not is_long and price <= tp)
            if tp_hit:
                profit = t["tp_profits"][i] if i < len(t.get("tp_profits", [])) else \
                         round(abs(tp - t["entry"]) * t["size_units"], 4)
                rr     = round(profit / t["risk_usd"], 2) if t["risk_usd"] > 0 else 0
                t["tps_hit"].append(i)
                updated = True

                # Partial close — record P&L for TP1/TP2, full close at TP3
                if i == len(t["tps"]) - 1:
                    t["status"]     = "CLOSED"
                    t["exit_price"] = tp
                    t["pnl_usd"]    = profit
                    t["rr_actual"]  = rr
                    t["closed_at"]  = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
                    history.append(t)
                    record_trade_close(profit)
                else:
                    record_trade_close(profit)

                s = load_settings()
                next_tp = t["tps"][i + 1] if i + 1 < len(t["tps"]) else None

                if send_fn and chat_id:
                    msg = (
                        f"🎯 *TP{i+1} HIT — {t['symbol']}*\n"
                        f"  Reached: `{tp}` ✓\n"
                        f"  Profit:  `+${profit}`  (+{rr}x R)\n"
                        f"  Balance: `${s['account_balance']}`\n"
                    )
                    if next_tp:
                        msg += f"  TP{i+2} still active at `{next_tp}`"
                    else:
                        msg += "  🏁 Trade fully closed."
                    send_fn(chat_id, msg)

    _save_trades([t for t in trades if t["status"] == "OPEN"])
    if updated:
        _save_history(history)


def _monitor_loop(send_fn, interval: int):
    """Background thread — runs forever, checks trades every `interval` seconds."""
    while True:
        try:
            _check_trades(send_fn)
        except Exception:
            pass
        time.sleep(interval)


def start_monitor(send_fn, interval: int = 300):
    """
    Starts the background price monitor thread (idempotent — only starts once).
    send_fn(chat_id, text) must send a Telegram message.
    """
    global _monitor_thread, _bot_send_fn
    _bot_send_fn = send_fn
    if _monitor_thread and _monitor_thread.is_alive():
        return
    _monitor_thread = threading.Thread(
        target=_monitor_loop, args=(send_fn, interval), daemon=True
    )
    _monitor_thread.start()


# ─── Formatters ───────────────────────────────────────────────────────────────

def format_open_trades() -> str:
    from execution.market_data import fetch_data
    trades = get_open_trades()
    if not trades:
        return "📭 *No open trades.*"

    lines = ["📊 *OPEN TRADES*\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━"]
    for t in trades:
        price = _get_live_price(t["symbol"]) or "?"
        if isinstance(price, float):
            is_long   = t["direction"] == "LONG"
            unreal    = round((price - t["entry"]) * t["size_units"] * (1 if is_long else -1), 4)
            unreal_rr = round(unreal / t["risk_usd"], 2) if t["risk_usd"] > 0 else 0
            p_str = f"+${unreal}" if unreal >= 0 else f"-${abs(unreal)}"
            rr_str = f"({unreal_rr:+.2f}x R)"
        else:
            p_str, rr_str = "?", ""

        tps_remaining = [t["tps"][i] for i in range(len(t["tps"])) if i not in t.get("tps_hit", [])]
        lines.append(
            f"• *{t['symbol']}* {t['direction']}\n"
            f"  Entry: `{t['entry']}` | SL: `{t['sl']}`\n"
            f"  TPs left: `{'  |  '.join(map(str, tps_remaining))}`\n"
            f"  Live: `{price}` → Unrealised: `{p_str}` {rr_str}"
        )
    return "\n".join(lines)


def format_stats() -> str:
    s = get_stats()
    if s["total"] == 0:
        return "📭 *No completed trades yet.*"
    pnl_emoji = "🟢" if s["net_pnl"] >= 0 else "🔴"
    return (
        "📈 *TRADING STATS*\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"  Trades:    `{s['total']}` ({s['wins']}W / {s['losses']}L)\n"
        f"  Win Rate:  `{s['win_rate']}%`\n"
        f"  Avg R:R:   `{s['avg_rr']}x`\n"
        f"{pnl_emoji} Net P&L:   `${s['net_pnl']}`\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    )


def format_history() -> str:
    history = _load_history()
    if not history:
        return "📭 *No trade history yet.*"
    lines = ["📋 *TRADE HISTORY*\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━"]
    for t in history[-10:]:   # last 10
        pnl = t.get("pnl_usd", 0)
        emoji = "🟢" if pnl > 0 else "🔴"
        lines.append(
            f"{emoji} *{t['symbol']}* {t['direction']}  "
            f"`${pnl:+.4f}` ({t.get('rr_actual', '?')}x R) "
            f"— {t.get('closed_at', '?')}"
        )
    return "\n".join(lines)
