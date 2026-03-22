"""
telegram_listener.py — Super Signals v2.1 Bot
Phase 14: Bot intelligence, trade tracker, detailed panel, smart news, always-on NLP.
"""
import requests
import time
import os
import sys
import json
import threading
import logging
from datetime import datetime

sys.path.append(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, os.path.dirname(__file__))

try:
    from main import run_full_analysis, TF_STACKS, SYMBOL_YF_MAP
    import market_scanner
    from multi_stack_analyzer import run_multi_stack_analysis
    from nlp_engine import generate_nlp_summary
    from bot_settings import (
        load_settings, save_setting, format_settings_panel,
        is_drawdown_limit_hit, record_trade_close
    )
    from trade_tracker import (
        register_trade, get_open_trades, close_trade, start_monitor,
        format_open_trades, format_stats, format_history
    )
except ImportError as e:
    print(f"Import error: {e}")
    sys.exit(1)

# ─── Logging ──────────────────────────────────────────────────────────────────
logging.basicConfig(format="%(message)s", level=logging.INFO, stream=sys.stderr)

def log(level: str, event: str, **kwargs):
    entry = {"ts": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"), "level": level, "event": event}
    entry.update(kwargs)
    logging.info(json.dumps(entry))

# ─── Rate Limiting ────────────────────────────────────────────────────────────
_COOLDOWNS: dict = {}
_RATE_LIMITS = {"analyze": 30, "scan": 300, "scalp": 120, "default": 5}
_COOLDOWN_LOCK = threading.Lock()

def check_rate_limit(chat_id: int, command_group: str) -> int:
    limit = _RATE_LIMITS.get(command_group, _RATE_LIMITS["default"])
    now = datetime.now()
    with _COOLDOWN_LOCK:
        last = _COOLDOWNS.get(chat_id, {}).get(command_group)
        if last and (now - last).total_seconds() < limit:
            return int(limit - (now - last).total_seconds())
        _COOLDOWNS.setdefault(chat_id, {})[command_group] = now
    return 0

# ─── Environment ──────────────────────────────────────────────────────────────
from dotenv import load_dotenv, find_dotenv

load_dotenv(find_dotenv())
BOT_TOKEN       = os.getenv("TELEGRAM_BOT_TOKEN")
ALLOWED_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

if not BOT_TOKEN:
    log("CRITICAL", "missing_env", var="TELEGRAM_BOT_TOKEN")
    sys.exit(1)

BASE_URL = f"https://api.telegram.org/bot{BOT_TOKEN}"

# ─── Helpers ──────────────────────────────────────────────────────────────────

def is_fx_pair(symbol: str) -> bool:
    """True if symbol is a Forex pair (ends with =X in yfinance)."""
    yf_ticker = SYMBOL_YF_MAP.get(symbol, "")
    return yf_ticker.endswith("=X")

def is_weekend() -> bool:
    """True if today is Saturday (5) or Sunday (6)."""
    return datetime.now().weekday() >= 5

# ─── Last signal cache for inline trade registration ──────────────────────────
_LAST_SIGNAL: dict = {}   # {chat_id: {symbol, report}}


# ─── Telegram API helpers ─────────────────────────────────────────────────────

def send_message(chat_id, text, reply_markup=None):
    if len(text) > 4000:
        text = text[:3900] + "\n... (truncated)"
    payload = {"chat_id": chat_id, "text": text, "parse_mode": "Markdown"}
    if reply_markup:
        payload["reply_markup"] = json.dumps(reply_markup)
    try:
        r = requests.post(f"{BASE_URL}/sendMessage", json=payload, timeout=10)
        # Telegram returns 400 if Markdown is malformed — retry as plain text
        if r.status_code == 400:
            payload.pop("parse_mode", None)
            requests.post(f"{BASE_URL}/sendMessage", json=payload, timeout=10)
    except Exception as e:
        log("ERROR", "send_message_failed", chat_id=chat_id, error=str(e))


def _safe(s: str) -> str:
    """Strip backticks and special Markdown chars from raw engine output strings."""
    if not s:
        return "N/A"
    # Remove backticks, asterisks, underscores that could break Markdown
    for ch in ["`", "*", "_", "[", "]"]:
        s = s.replace(ch, "")
    return s[:200]  # cap length too



def answer_callback(callback_id, text="✅"):
    try:
        requests.post(f"{BASE_URL}/answerCallbackQuery",
                      json={"callback_query_id": callback_id, "text": text}, timeout=5)
    except Exception:
        pass


def _took_trade_keyboard():
    """Inline keyboard shown below every signal."""
    return {
        "inline_keyboard": [[
            {"text": "✅ Took This Trade", "callback_data": "took_trade"},
            {"text": "❌ Skip",            "callback_data": "skip_trade"},
        ]]
    }


# ─── Signal Panel Formatter ───────────────────────────────────────────────────

def _conf_bar(score: float, width: int = 8) -> str:
    """Renders a simple ASCII progress bar."""
    filled = round((score / 100) * width)
    return "[" + "=" * filled + "-" * (width - filled) + "]"


def format_signal_panel(symbol: str, data: dict, stack_label: str = "") -> str:
    """
    Builds the detailed 4-section Telegram signal panel.
    Sections: Market Context | Confidence | Trade Setup | AI Analysis
    """
    sig     = data.get("FINAL_SIGNAL", "UNKNOWN")
    conf    = data.get("CONFIDENCE", 0)
    risk    = data.get("RISK_ADVISORY", {}) or {}
    reasons = data.get("REASONING", {}) or {}
    alerts  = data.get("GOVERNANCE_ALERTS", []) or []
    ts      = data.get("TIMESTAMP", datetime.now().strftime("%Y-%m-%d %H:%M"))[:16]

    sig_emoji = (
        "🟢" if "LONG"  in sig and "WAIT" not in sig else
        "🔴" if "SHORT" in sig and "WAIT" not in sig else
        "⚪"
    )

    # ── Header ────────────────────────────────────────────────────────────
    msg = (
        f"🧠 *SUPER SIGNALS v2.1 — {symbol}*\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
    )

    # ── Section 1: Market Context ─────────────────────────────────────────
    l2  = _safe(reasons.get("l2_confluence", ""))
    l3  = _safe(reasons.get("l3_history",    ""))
    l4  = _safe(reasons.get("l4_news",       ""))

    # Parse bias from l2 string e.g. "HTF(BEARISH) 4H(BULLISH) LTF(NEUTRAL)"
    bias_str = ""
    for chunk in l2.split(".")[0].split("|") if "|" in l2 else l2.split():
        if "(" in chunk:
            bias_str += chunk.strip() + " "
    session_str = ""
    if "Session:" in l2:
        session_str = l2.split("Session:")[1].split("(")[0].strip()
    seasonal = data.get("NLP_SUMMARY", "")   # may include seasonal in reasoning if set
    seasonal_raw = reasons.get("seasonality", "")

    msg += (
        f"📊 *MARKET CONTEXT*\n"
        f"  Bias:    `{bias_str.strip() or 'Multi-TF conflict'}`\n"
        f"  Session: `{session_str or 'N/A'}`\n"
    )
    if stack_label:
        msg += f"  Stack:   `{stack_label}`\n"
    msg += "\n"

    # ── Section 2: Confidence Breakdown ───────────────────────────────────
    def _extract_score(s: str) -> int:
        import re
        m = re.search(r'(\d+\.?\d*)%', s)
        return round(float(m.group(1))) if m else 0

    l2_score = _extract_score(l2)
    l3_score = _extract_score(l3)
    l4_score = _extract_score(l4) if l4 and "Skipped" not in l4 else 0

    msg += (
        f"📐 *CONFIDENCE:  {conf}/100*\n"
        f"  Structure  {_conf_bar(l2_score)} {l2_score}%\n"
        f"  History    {_conf_bar(l3_score)} {l3_score}%\n"
        f"  News/Macro {_conf_bar(l4_score)} {l4_score}%\n"
        "\n"
    )

    # ── Section 3: Trade Setup ────────────────────────────────────────────
    msg += f"💰 *TRADE SETUP — {sig_emoji} {sig}*\n"

    if risk.get("ENTRY_PRICE"):
        sl         = risk.get("STOP_LOSS", "N/A")
        tp_targets = risk.get("TAKE_PROFIT", [])
        tp_usd     = risk.get("TP_PROFIT_USD", [])
        tp_rr      = risk.get("TP_RR_ACTUAL", [])
        risk_usd   = risk.get("RISK_AMOUNT_USD", "?")
        risk_pct   = risk.get("RISK_PER_TRADE_PCT", 20)
        acct       = risk.get("ACCOUNT_BALANCE", 60)
        units      = risk.get("POSITION_SIZE_UNITS", 0)
        pos_usd    = risk.get("POSITION_SIZE_USD", 0)
        rr         = risk.get("RR_RATIO")
        rr_gate    = risk.get("RR_GATE", "")

        msg += (
            f"  Entry:    `{risk.get('ENTRY_TYPE')} @ {risk.get('ENTRY_PRICE')}`\n"
            f"  SL:       `{sl}` — ${risk_usd} risk ({risk_pct}% of ${acct})\n"
        )

        for i, tp in enumerate(tp_targets):
            profit = tp_usd[i] if i < len(tp_usd) else "?"
            rr_i   = tp_rr[i]  if i < len(tp_rr)  else "?"
            msg += f"  TP{i+1}:      `{tp}` — +${profit} ({rr_i}x R)\n"

        if rr:
            msg += f"  R:R:      `{rr}:1` [{rr_gate}]\n"
        
        # New Phase 14 Position Sizing Data
        lot_data = risk.get("LOT_SIZE_DATA", {})
        if lot_data:
            msg += f"\n  📦 *POSITION SIZING*\n"
            msg += f"  Advised:  `{lot_data.get('lot_label', '?')}`\n"
            msg += f"  Units:    `{units}` (${pos_usd} notional)\n"
            if lot_data.get("is_forex"):
                msg += f"  Pip Cost: `${lot_data.get('pip_value', 0)}/pip`\n"
        else:
            msg += f"  Position: `{units} units` (${pos_usd} notional)\n"
    else:
        msg += "  _No actionable entry — see reasoning below_\n"

    if alerts:
        msg += "\n⚠️ *ALERTS:*\n"
        for a in alerts:
            msg += f"   • {a}\n"

    msg += "\n"

    # ── Section 4: AI Analysis ────────────────────────────────────────────
    nlp = data.get("NLP_SUMMARY")
    if nlp:
        msg += f"🤖 *AI ANALYSIS*\n_{nlp}_\n\n"
    else:
        msg += f"🧩 *REASONING*\n"
        msg += f"  `[L1/L2]` {l2}\n"
        msg += f"  `[L3]`    {l3}\n"
        if l4 and "Skipped" not in l4:
            msg += f"  `[L4]`    {l4}\n"

    msg += f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n_{ts}_"
    return msg


# ─── Smart News Decision ──────────────────────────────────────────────────────

def _should_run_news(pre_conf: float, l2_str: str = "") -> bool:
    """
    Returns True if news is worth fetching given the current confluence score.
    Saves API credits on clear signals; adds context on borderline ones.
    """
    if pre_conf >= 70:          return False   # already strong
    if pre_conf < 45:           return False   # too weak to salvage
    if "KILL_ZONE" in l2_str:   return True    # high-impact session
    if "LONDON"    in l2_str:   return True
    if "NEW_YORK"  in l2_str:   return True
    return True  # borderline 45–69: always run news


# ─── Command Handlers ────────────────────────────────────────────────────────

def _handle_start(chat_id):
    s = load_settings()
    bal      = s["account_balance"]
    risk     = s["risk_per_trade_pct"]
    dd       = s["daily_drawdown_limit"]
    risk_usd = round(bal * risk / 100, 2)
    dd_usd   = round(bal * dd / 100, 2)

    # Show "Not set" if user hasn't customised balance yet
    bal_str  = f"Not set — use /setbalance" if bal == 60.0 and not _settings_file_exists() else f"${bal}"

    msg = (
        "🚀 *SUPER SIGNALS v2.1*\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "📋 *ANALYSIS COMMANDS*\n"
        "  `/analyze (pair)`          Full analysis\n"
        "  `/analyze (pair) swing`    Swing stack\n"
        "  `/scalp (pair)`            AI multi-stack scalp\n"
        "  `/scan`                    Scan top 10 assets\n\n"
        "💼 *TRADE TRACKER*\n"
        "  `/trades`                  Open trades + live P&L\n"
        "  `/history`                 Closed trade log\n"
        "  `/stats`                   Win rate, avg R, net profit\n"
        "  `/close (pair) (price)`    Manual close\n\n"
        "⚙️ *CONFIG COMMANDS*\n"
        "  `/settings`                View current config\n"
        "  `/setbalance (amount)`     Set account balance\n"
        "  `/setrisk (pct)`           Set risk % per trade\n"
        "  `/setdrawdown (pct)`       Set daily loss limit\n"
        "  `/resetday`                Re-enable after drawdown\n\n"
        f"📊 *YOUR CONFIG*\n"
        f"  Balance:     `{bal_str}`\n"
        f"  Risk/Trade:  `{risk}%`  (${risk_usd} per trade)\n"
        f"  Daily Limit: `{dd}%`   (${dd_usd} — auto-resets each day)\n\n"
        "📡 *Status:* Online  |  v2.1  |  Groq NLP Active\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    )
    send_message(chat_id, msg)


def _settings_file_exists() -> bool:
    """True if user has ever saved a setting (i.e. bot_settings.json exists)."""
    return os.path.exists(os.path.join(os.path.dirname(__file__), '..', '.tmp', 'bot_settings.json'))




def _handle_analyze(chat_id, args):
    wait = check_rate_limit(chat_id, "analyze")
    if wait:
        send_message(chat_id, f"⏳ Please wait *{wait}s* before another `/analyze`.")
        return

    VALID_STACKS = list(TF_STACKS.keys())
    if not args:
        send_message(chat_id, "⚠️ Usage: `/analyze SYMBOL [stack]`\ne.g. `/analyze BTC/USD` or `/analyze BTC/USD swing`")
        return

    symbol    = args[0].upper().replace(" ", "")
    stack_arg = args[1].lower() if len(args) > 1 else "intraday"
    if stack_arg not in VALID_STACKS:
        send_message(chat_id, f"⚠️ Unknown stack `{stack_arg}`. Valid: `{', '.join(VALID_STACKS)}`")
        return

    # Drawdown gate
    blocked, reason = is_drawdown_limit_hit()
    if blocked:
        send_message(chat_id, reason)
        return

    send_message(chat_id, f"🔬 *Analyzing {symbol}* `[{stack_arg}]`...")

    # Weekend FX Gate
    if is_fx_pair(symbol) and is_weekend():
        msg = (
            "⚪ *Forex Market Closed*\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "No analysis during weekends. FX analysis resumes on Monday."
        )
        send_message(chat_id, msg)
        return

    try:
        # Phase 1: Fast tech pass (no news) to decide if news worth running
        pre_report = run_full_analysis(symbol, stack_name=stack_arg, no_news=True, use_nlp=False)
        pre_conf   = (pre_report or {}).get("CONFIDENCE", 0)
        l2_str     = ((pre_report or {}).get("REASONING") or {}).get("l2_confluence", "")
        run_news   = _should_run_news(pre_conf, l2_str)

        # Phase 2: Full analysis (with or without news)
        report = run_full_analysis(symbol, stack_name=stack_arg, no_news=not run_news, use_nlp=False)
        if not report or "error" in report:
            send_message(chat_id, f"❌ Analysis failed for {symbol}.")
            return

        # Always generate NLP
        report["NLP_SUMMARY"] = generate_nlp_summary(report, symbol)

        panel = format_signal_panel(symbol, report, stack_label=stack_arg.upper())
        _LAST_SIGNAL[chat_id] = {
            "symbol": symbol, "report": report,
            "stack": stack_arg, "ts": time.time()
        }
        send_message(chat_id, panel, reply_markup=_took_trade_keyboard())
        log("INFO", "analyze_complete", chat_id=chat_id, symbol=symbol,
            signal=report.get("FINAL_SIGNAL"), conf=report.get("CONFIDENCE"), news=run_news)

    except Exception as e:
        send_message(chat_id, f"❌ Execution Error: `{str(e)}`")
        log("ERROR", "analyze_exception", chat_id=chat_id, symbol=symbol, error=str(e))


def _handle_scalp(chat_id, args):
    wait = check_rate_limit(chat_id, "scalp")
    if wait:
        send_message(chat_id, f"⏳ Scalp cooldown: *{wait}s* remaining.")
        return

    if not args:
        send_message(chat_id, "⚠️ Usage: `/scalp SYMBOL`\ne.g. `/scalp BTC/USD`")
        return

    symbol = args[0].upper().replace(" ", "")

    blocked, reason = is_drawdown_limit_hit()
    if blocked:
        send_message(chat_id, reason)
        return

    send_message(chat_id, f"⚡ *AI Multi-Stack Scalp Analysis: {symbol}*\nRunning all scalp timeframes...")

    # Weekend FX Gate
    if is_fx_pair(symbol) and is_weekend():
        msg = (
            "⚪ *Forex Market Closed*\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "No analysis during weekends. FX analysis resumes on Monday."
        )
        send_message(chat_id, msg)
        return

    try:
        # Use smart news: run without first, AI ranks, then decide on news per confidence
        result = run_multi_stack_analysis(symbol, use_nlp=False, no_news=True)

        if "error" in result or not result.get("top_setups"):
            send_message(chat_id, f"❌ No valid setups found for {symbol}.")
            return

        best        = result["top_setups"][0]
        best_stack  = best.get("stack", "?").upper()
        best_report = best["report"]

        # Smart news on the best setup
        pre_conf = best_report.get("CONFIDENCE", 0)
        l2_str   = (best_report.get("REASONING") or {}).get("l2_confluence", "")
        if _should_run_news(pre_conf, l2_str):
            best_report = run_full_analysis(symbol, stack_name=best.get("stack"), no_news=False, use_nlp=False) or best_report

        # Always generate NLP
        best_report["NLP_SUMMARY"] = generate_nlp_summary(best_report, symbol)

        label = f"{best_stack} [AI #{1} of {result['total_analyzed']} stacks]"
        panel = format_signal_panel(symbol, best_report, stack_label=label)
        _LAST_SIGNAL[chat_id] = {
            "symbol": symbol, "report": best_report,
            "stack": best.get("stack"), "ts": time.time()
        }
        send_message(chat_id, panel, reply_markup=_took_trade_keyboard())
        log("INFO", "scalp_complete", chat_id=chat_id, symbol=symbol, stack=best_stack)

    except Exception as e:
        send_message(chat_id, f"❌ Scalp Error: `{str(e)}`")
        log("ERROR", "scalp_exception", chat_id=chat_id, symbol=symbol, error=str(e))


def _handle_took_trade(chat_id):
    """Registers the last signal as a taken trade."""
    cached = _LAST_SIGNAL.get(chat_id)
    if not cached or (time.time() - cached["ts"]) > 600:
        send_message(chat_id, "⚠️ No recent signal found (last signal expires after 10 min). Run `/analyze` first.")
        return

    symbol  = cached["symbol"]
    report  = cached["report"]
    risk    = (report.get("RISK_ADVISORY") or {})

    if not risk.get("ENTRY_PRICE"):
        send_message(chat_id, "⚠️ No valid trade setup in the last signal (WAIT signal).")
        return

    direction = "LONG" if "LONG" in report.get("FINAL_SIGNAL", "") else "SHORT"
    trade = register_trade(
        symbol      = symbol,
        direction   = direction,
        entry       = risk["ENTRY_PRICE"],
        sl          = risk["STOP_LOSS"],
        tps         = risk.get("TAKE_PROFIT", []),
        size_units  = risk.get("POSITION_SIZE_UNITS", 0),
        risk_usd    = risk.get("RISK_AMOUNT_USD", 0),
        tp_profits  = risk.get("TP_PROFIT_USD", []),
        chat_id     = str(chat_id),
    )

    s = load_settings()
    send_message(chat_id,
        f"✅ *Trade Registered — {symbol}*\n"
        f"  Direction: `{direction}`\n"
        f"  Entry:     `{risk['ENTRY_PRICE']}`\n"
        f"  SL:        `{risk['STOP_LOSS']}`\n"
        f"  Size:      `{risk.get('POSITION_SIZE_UNITS', 0)} units`\n"
        f"  Risk:      `${risk.get('RISK_AMOUNT_USD', 0)}` ({s['risk_per_trade_pct']}% of ${s['account_balance']})\n\n"
        f"📡 _Monitoring price every {s.get('monitor_interval', 300)//60} min..._"
    )
    log("INFO", "trade_registered", chat_id=chat_id, symbol=symbol, direction=direction)


def _handle_close(chat_id, args):
    if len(args) < 2:
        send_message(chat_id, "⚠️ Usage: `/close SYMBOL PRICE`\ne.g. `/close BTC/USD 71000`")
        return
    symbol     = args[0].upper()
    exit_price = float(args[1])

    open_trades = get_open_trades()
    match = next((t for t in open_trades if t["symbol"] == symbol), None)
    if not match:
        send_message(chat_id, f"⚠️ No open trade found for `{symbol}`.")
        return

    result = close_trade(match["id"], exit_price)
    if not result:
        send_message(chat_id, "❌ Failed to close trade.")
        return

    pnl   = result["pnl_usd"]
    rr    = result["rr_actual"]
    emoji = "🟢" if pnl > 0 else "🔴"
    s     = load_settings()

    send_message(chat_id,
        f"{emoji} *Trade Closed — {symbol}*\n"
        f"  Exit:    `{exit_price}`\n"
        f"  P&L:     `${pnl:+.4f}` ({rr:+.2f}x R)\n"
        f"  Balance: `${s['account_balance']}`\n"
        f"  Today:   `${s['daily_realized_pnl']:+.4f}`"
    )


def process_command(chat_id, command, args):
    log("INFO", "command_received", chat_id=chat_id, command=command, args=args)
    cmd = command.lower().split("@")[0]  # strip @botname if present

    # ── Config commands ────────────────────────────────────────────────────────
    if cmd == "/start" or cmd == "/help":
        _handle_start(chat_id)

    elif cmd == "/settings":
        send_message(chat_id, format_settings_panel())

    elif cmd == "/setbalance":
        if not args:
            send_message(chat_id, "⚠️ Usage: `/setbalance 80`")
            return
        try:
            val = float(args[0])
            save_setting("account_balance", val)
            risk_usd = round(val * load_settings()["risk_per_trade_pct"] / 100, 2)
            send_message(chat_id, f"✅ Balance set to `${val}`. Risk per trade: `${risk_usd}`.")
        except ValueError:
            send_message(chat_id, "⚠️ Invalid number.")

    elif cmd == "/setrisk":
        if not args:
            send_message(chat_id, "⚠️ Usage: `/setrisk 20`")
            return
        try:
            val = float(args[0])
            if val <= 0 or val > 100:
                raise ValueError
            save_setting("risk_per_trade_pct", val)
            bal = load_settings()["account_balance"]
            send_message(chat_id, f"✅ Risk set to `{val}%` (${round(bal*val/100, 2)} per trade).")
        except ValueError:
            send_message(chat_id, "⚠️ Risk must be between 1 and 100.")

    elif cmd == "/setdrawdown":
        if not args:
            send_message(chat_id, "⚠️ Usage: `/setdrawdown 50`")
            return
        try:
            val = float(args[0])
            save_setting("daily_drawdown_limit", val)
            bal = load_settings()["account_balance"]
            send_message(chat_id, f"✅ Daily drawdown limit set to `{val}%` (${round(bal*val/100, 2)} max loss/day).")
        except ValueError:
            send_message(chat_id, "⚠️ Invalid number.")

    elif cmd == "/resetday":
        save_setting("daily_realized_pnl", 0.0)
        save_setting("daily_start_balance", load_settings()["account_balance"])
        send_message(chat_id, "✅ Daily drawdown counter reset. Trading re-enabled.")

    # ── Analysis commands ──────────────────────────────────────────────────────
    elif cmd == "/analyze":
        # Allow inline symbol e.g. /analyzeBTC/USD
        if not args and len(command) > 8:
            args = [command[8:]]
        threading.Thread(target=_handle_analyze, args=(chat_id, args), daemon=True).start()

    elif cmd == "/scalp":
        threading.Thread(target=_handle_scalp, args=(chat_id, args), daemon=True).start()

    elif cmd in ("/scan", "/scan_tech"):
        wait = check_rate_limit(chat_id, "scan")
        if wait:
            send_message(chat_id, f"⏳ Scan cooldown: *{wait}s* remaining.")
            return
        no_news   = (cmd == "/scan_tech")
        stack_arg = args[0].lower() if args else "intraday"
        send_message(chat_id, f"🔍 *Market Scan* `[{stack_arg}]` starting...")
        try:
            market_scanner.main()
            send_message(chat_id, "✅ *Scan complete.* All alerts sent.")
        except Exception as e:
            send_message(chat_id, f"❌ Scan error: `{str(e)}`")

    # ── Trade tracker commands ─────────────────────────────────────────────────
    elif cmd == "/took":
        # Allow /took BTC/USD (optional, uses last signal if no symbol given)
        _handle_took_trade(chat_id)

    elif cmd == "/trades":
        send_message(chat_id, format_open_trades())

    elif cmd == "/close":
        _handle_close(chat_id, args)

    elif cmd == "/history":
        send_message(chat_id, format_history())

    elif cmd == "/stats":
        send_message(chat_id, format_stats())

    else:
        send_message(chat_id, "❓ Unknown command. Send `/start` to see all commands.")


def handle_callback(query):
    """Handles inline button presses (Took Trade / Skip)."""
    chat_id     = query["message"]["chat"]["id"]
    callback_id = query["id"]
    data        = query.get("data", "")

    answer_callback(callback_id)

    if data == "took_trade":
        threading.Thread(target=_handle_took_trade, args=(chat_id,), daemon=True).start()
    elif data == "skip_trade":
        send_message(chat_id, "⏭️ Signal skipped. No trade recorded.")


# ─── Main Loop ────────────────────────────────────────────────────────────────

def main_loop():
    # Start background trade price monitor
    monitor_interval = int(os.environ.get("MONITOR_INTERVAL", 300))
    start_monitor(send_fn=lambda cid, txt: send_message(cid, txt), interval=monitor_interval)

    log("INFO", "bot_online", allowed_chat=ALLOWED_CHAT_ID)
    offset = 0

    while True:
        try:
            url  = f"{BASE_URL}/getUpdates?timeout=30&offset={offset}"
            resp = requests.get(url, timeout=45)
            data = resp.json()

            if data.get("ok"):
                for update in data.get("result", []):
                    offset = update["update_id"] + 1

                    # Text commands
                    if "message" in update and "text" in update["message"]:
                        chat_id = update["message"]["chat"]["id"]
                        text    = update["message"]["text"].strip()
                        if text.startswith("/"):
                            parts   = text.split()
                            command = parts[0]
                            args    = parts[1:]
                            threading.Thread(
                                target=process_command,
                                args=(chat_id, command, args),
                                daemon=True
                            ).start()

                    # Inline button presses
                    elif "callback_query" in update:
                        threading.Thread(
                            target=handle_callback,
                            args=(update["callback_query"],),
                            daemon=True
                        ).start()

            time.sleep(1)

        except Exception as e:
            log("ERROR", "poll_error", error=str(e))
            time.sleep(5)


if __name__ == "__main__":
    main_loop()
