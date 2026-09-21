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
import traceback
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
_RATE_LIMITS = {"analyze": 30, "scan": 300, "scalp": 120, "mtf": 120, "default": 5}
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

# ─── Signal persistence ──────────────────────────────────────────────────────
_SIGNALS_LOG = os.path.join(os.path.dirname(__file__), '..', '.tmp', 'signals_log.json')

def _persist_signal(chat_id, symbol: str, report: dict, stack: str):
    """Appends the signal (with its SIGNAL_ID and full report) to the durable signals log."""
    entry = {
        "signal_id": report.get("SIGNAL_ID"),
        "chat_id":   str(chat_id),
        "symbol":    symbol,
        "stack":     stack,
        "signal":    report.get("FINAL_SIGNAL"),
        "confidence":report.get("CONFIDENCE"),
        "report":    report,
        "ts":        report.get("TIMESTAMP", datetime.now().strftime("%Y-%m-%d %H:%M")),
        "created_at": time.time(),
    }
    try:
        os.makedirs(os.path.dirname(_SIGNALS_LOG), exist_ok=True)
        existing = []
        if os.path.exists(_SIGNALS_LOG):
            with open(_SIGNALS_LOG, "r") as f:
                existing = json.load(f)
        existing.append(entry)
        if len(existing) > 50:
            existing = existing[-50:]
        with open(_SIGNALS_LOG, "w") as f:
            json.dump(existing, f, indent=2)
    except Exception as e:
        log("WARN", "signal_persist_failed", error=str(e))


def _get_persisted_signal(signal_id: str = None, symbol: str = None, chat_id: str = None) -> dict | None:
    """Finds a signal in .tmp/signals_log.json by signal_id or most recent symbol."""
    try:
        if os.path.exists(_SIGNALS_LOG):
            with open(_SIGNALS_LOG, "r") as f:
                logs = json.load(f)
            if signal_id:
                for entry in reversed(logs):
                    if entry.get("signal_id") == signal_id:
                        return entry
            if symbol:
                sym_clean = symbol.upper().replace(" ", "")
                for entry in reversed(logs):
                    if entry.get("symbol", "").upper().replace(" ", "") == sym_clean:
                        if not chat_id or str(entry.get("chat_id")) == str(chat_id):
                            return entry
            if chat_id:
                for entry in reversed(logs):
                    if str(entry.get("chat_id")) == str(chat_id):
                        return entry
    except Exception as e:
        log("WARN", "get_persisted_signal_failed", error=str(e))
    return None


# ─── Last signal cache for inline trade registration ──────────────────────────
_LAST_SIGNAL: dict = {}   # {chat_id: {symbol, report, stack, ts}}


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



def answer_callback(callback_id, text=None):
    try:
        payload = {"callback_query_id": callback_id}
        if text:
            payload["text"] = text
        requests.post(f"{BASE_URL}/answerCallbackQuery", json=payload, timeout=5)
    except Exception as e:
        log("WARN", "answer_callback_failed", error=str(e))


RECENT_SYMBOLS_FILE = os.path.join(os.path.dirname(__file__), '..', '.tmp', 'recent_symbols.json')
_RECENT_SYMBOLS_LOCK = threading.RLock()
DEFAULT_SYMBOLS = ["XAU/USD", "BTC/USD", "GBP/USD", "EUR/USD", "ETH/USD"]

def _load_recent_symbols(chat_id) -> list:
    """Returns list of 3-5 recent symbols for chat_id, or defaults if none."""
    cid_str = str(chat_id)
    with _RECENT_SYMBOLS_LOCK:
        try:
            if os.path.exists(RECENT_SYMBOLS_FILE):
                with open(RECENT_SYMBOLS_FILE, "r") as f:
                    data = json.load(f)
                    user_list = data.get(cid_str, [])
                    if user_list:
                        combined = []
                        for s in user_list + DEFAULT_SYMBOLS:
                            s_norm = normalize_user_symbol(s)
                            if s_norm and s_norm not in combined:
                                combined.append(s_norm)
                        return combined[:5]
        except Exception:
            pass
    return DEFAULT_SYMBOLS[:4]


def _record_recent_symbol(chat_id, symbol: str):
    """Records symbol in user's recent list (most recent first, max 5)."""
    if not symbol or not chat_id:
        return
    cid_str = str(chat_id)
    sym_normalized = normalize_user_symbol(symbol.upper().strip())
    with _RECENT_SYMBOLS_LOCK:
        try:
            os.makedirs(os.path.dirname(RECENT_SYMBOLS_FILE), exist_ok=True)
            data = {}
            if os.path.exists(RECENT_SYMBOLS_FILE):
                with open(RECENT_SYMBOLS_FILE, "r") as f:
                    data = json.load(f)
            current = [normalize_user_symbol(s) for s in data.get(cid_str, [])]
            new_list = [sym_normalized] + [s for s in current if s != sym_normalized]
            data[cid_str] = new_list[:5]
            with open(RECENT_SYMBOLS_FILE, "w") as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            log("WARN", "record_recent_symbol_failed", error=str(e))


def _symbol_suggestion_keyboard(command_name: str, chat_id):
    """
    Builds an inline keyboard with buttons for recent/default symbols.
    command_name: e.g. 'analyze', 'scalp', 'mtf'
    """
    symbols = _load_recent_symbols(chat_id)
    keyboard = []
    row = []
    for sym in symbols:
        row.append({
            "text": sym,
            "callback_data": f"symcmd:{command_name}:{sym}"
        })
        if len(row) == 2:
            keyboard.append(row)
            row = []
    if row:
        keyboard.append(row)
    return {"inline_keyboard": keyboard}


def register_bot_commands():
    """Registers bot commands with Telegram via setMyCommands API for native autocomplete."""
    commands = [
        {"command": "analyze",    "description": "Full confluence analysis (e.g. /analyze XAU/USD)"},
        {"command": "scalp",      "description": "Multi-timeframe AI scalp analysis (/scalp BTC/USD)"},
        {"command": "mtf",        "description": "Single timeframe analysis (/mtf BTC/USD 1D)"},
        {"command": "scan",       "description": "Scan watchlist for top setups"},
        {"command": "scan_tech",  "description": "Fast technical scan (no news)"},
        {"command": "trades",     "description": "View active open trades & live P&L"},
        {"command": "took",       "description": "Record entry on last generated signal"},
        {"command": "close",      "description": "Close an open trade (/close SYMBOL PRICE)"},
        {"command": "history",    "description": "View recent closed trade history"},
        {"command": "stats",      "description": "View win rate, avg R:R & net P&L"},
        {"command": "settings",   "description": "View current risk & balance settings"},
        {"command": "setbalance", "description": "Set account balance (/setbalance 100)"},
        {"command": "setrisk",    "description": "Set risk % per trade (/setrisk 2)"},
        {"command": "setdrawdown","description": "Set daily drawdown limit % (/setdrawdown 50)"},
        {"command": "resetday",   "description": "Reset daily drawdown counter"},
        {"command": "help",       "description": "Show help and command guide"}
    ]
    try:
        r = requests.post(f"{BASE_URL}/setMyCommands", json={"commands": commands}, timeout=10)
        if r.status_code == 200 and r.json().get("ok"):
            log("INFO", "bot_commands_registered", count=len(commands))
        else:
            log("WARN", "set_commands_failed", response=r.text)
    except Exception as e:
        log("WARN", "set_commands_exception", error=str(e))


def _took_trade_keyboard(symbol: str = "", signal_id: str = ""):
    """Inline keyboard shown below every signal."""
    took_data = f"took:{symbol}:{signal_id}" if symbol and signal_id else "took_trade"
    skip_data = f"skip:{symbol}:{signal_id}" if symbol and signal_id else "skip_trade"
    return {
        "inline_keyboard": [[
            {"text": "✅ Took This Trade", "callback_data": took_data},
            {"text": "❌ Skip",            "callback_data": skip_data},
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

    if "LOCKED" in sig.upper():
        msg += "  ⛔ _Trade Locked — Setup withheld due to critical risk_\n"
    elif risk.get("ENTRY_PRICE"):
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
        "  `/mtf (pair) (tf)`          Single-TF analysis (D1/H4/H1/M15/M5/M1)\n"
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




def normalize_user_symbol(sym: str) -> str:
    """
    Cleans up user symbol input and normalises common variations/typos:
    - XAG/USA -> XAG/USD, XAU/USA -> XAU/USD
    - BTCUSDT -> BTC/USD, ETHUSDT -> ETH/USD
    - EURUSD  -> EUR/USD, GBPJPY  -> GBP/JPY
    """
    if not sym:
        return sym
    s = sym.upper().strip().replace(" ", "")
    if s.endswith("/USA"):
        s = s[:-4] + "/USD"
    elif s.endswith("USA") and "/" not in s and len(s) > 3:
        s = s[:-3] + "/USD"
    elif s.endswith("/USDT"):
        s = s[:-5] + "/USD"
    elif s.endswith("USDT") and "/" not in s and len(s) > 4:
        s = s[:-4] + "/USD"
    elif "/" not in s and len(s) == 6:
        s = s[:3] + "/" + s[3:]
    return s


def _handle_analyze(chat_id, args):
    VALID_STACKS = list(TF_STACKS.keys())
    if not args:
        send_message(chat_id,
            "🔍 *Select a symbol to analyze:*\n"
            "Tap a recent symbol below or type `/analyze SYMBOL`",
            reply_markup=_symbol_suggestion_keyboard("analyze", chat_id))
        return

    wait = check_rate_limit(chat_id, "analyze")
    if wait:
        send_message(chat_id, f"⏳ Please wait *{wait}s* before another `/analyze`.")
        return

    symbol    = normalize_user_symbol(args[0])
    _record_recent_symbol(chat_id, symbol)
    stack_arg = args[1].lower() if len(args) > 1 else "intraday"
    if stack_arg not in VALID_STACKS:
        send_message(chat_id, f"⚠️ Unknown stack `{stack_arg}`. Valid: `{', '.join(VALID_STACKS)}`")
        return

    # Drawdown gate
    blocked, reason = is_drawdown_limit_hit()
    if blocked:
        send_message(chat_id, reason)
        return

    send_message(chat_id, f"⏳ Analyzing {symbol}...")

    # Weekend FX Gate
    if is_fx_pair(symbol) and is_weekend():
        msg = (
            "⚪ *Forex Market Closed*\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "No analysis during weekends. FX analysis resumes on Monday."
        )
        send_message(chat_id, msg)
        return

    def _run_analysis_work():
        try:
            # Single-pass analysis with in-flight smart news evaluation
            report = run_full_analysis(symbol, stack_name=stack_arg, smart_news=True, use_nlp=False)
            if not report or "error" in report:
                send_message(chat_id, f"⚠️ Analysis failed for `{symbol}`. Please try again.")
                return

            # Always generate NLP
            report["NLP_SUMMARY"] = generate_nlp_summary(report, symbol)

            panel = format_signal_panel(symbol, report, stack_label=stack_arg.upper())
            _LAST_SIGNAL[chat_id] = {
                "symbol": symbol, "report": report,
                "stack": stack_arg, "ts": time.time()
            }
            _persist_signal(chat_id, symbol, report, stack_arg)
            is_locked = "LOCKED" in (report.get("FINAL_SIGNAL") or "").upper()
            send_message(chat_id, panel, reply_markup=None if is_locked else _took_trade_keyboard(symbol, report.get("SIGNAL_ID", "")))
            log("INFO", "analyze_complete", chat_id=chat_id, symbol=symbol,
                signal=report.get("FINAL_SIGNAL"), conf=report.get("CONFIDENCE"),
                signal_id=report.get("SIGNAL_ID"))

        except Exception as e:
            err_msg = str(e)
            if "All data sources failed" in err_msg:
                send_message(chat_id, f"⚠️ Could not find market data for `{symbol}`.\nPlease verify the symbol ticker (e.g. `XAG/USD` for Silver, `XAU/USD` for Gold, `BTC/USD`, `EUR/USD`).")
            else:
                send_message(chat_id, f"⚠️ Analysis failed for `{symbol}`. Please try again.")
            log("ERROR", "analyze_exception", chat_id=chat_id, symbol=symbol, error=err_msg)

    threading.Thread(target=_run_analysis_work, daemon=True).start()


# ─── /mtf timeframe alias map ────────────────────────────────────────────────
# Accepts user-friendly input (D1, 1D, H4, 4H, H1, 1H, M15, 15M, M5, 5M, M1, 1M)
# and normalises to the internal format used by fetch_data / run_full_analysis.
_TF_ALIASES = {
    "d1": "1d", "1d": "1d",
    "h4": "4h", "4h": "4h",
    "h1": "1h", "1h": "1h",
    "m15": "15m", "15m": "15m",
    "m5": "5m",  "5m": "5m",
    "m1": "1m",  "1m": "1m",
}
_VALID_TF_DISPLAY = "D1, H4, H1, M15, M5, M1"

# Map each single TF to the best matching named stack so run_full_analysis
# uses a sensible HTF/LTF pairing internally.
_TF_TO_STACK = {
    "1d":  "swing",
    "4h":  "intraday",
    "1h":  "scalp",
    "15m": "scalp_fast",
    "5m":  "scalp_fast",
    "1m":  "scalp_ultra",
}


def _handle_mtf(chat_id, args):
    if not args:
        send_message(chat_id,
            "⏱️ *Select a symbol for MTF analysis:*\n"
            "Tap a symbol below (defaults to 1H) or type `/mtf SYMBOL TIMEFRAME`",
            reply_markup=_symbol_suggestion_keyboard("mtf", chat_id))
        return

    if len(args) == 1:
        args = [args[0], "1h"]

    symbol   = normalize_user_symbol(args[0])
    tf_input = args[1].lower().replace(" ", "")
    tf       = _TF_ALIASES.get(tf_input)

    if not tf:
        send_message(chat_id,
            f"⚠️ Unknown timeframe `{args[1].upper()}`.\n"
            f"Valid options: `{_VALID_TF_DISPLAY}`")
        return

    wait = check_rate_limit(chat_id, "mtf")
    if wait:
        send_message(chat_id, f"⏳ MTF cooldown: *{wait}s* remaining.")
        return

    _record_recent_symbol(chat_id, symbol)

    if is_fx_pair(symbol) and is_weekend():
        send_message(chat_id, "⚪ *Forex Market Closed* — MTF analysis resumes Monday.")
        return

    blocked, reason = is_drawdown_limit_hit()
    if blocked:
        send_message(chat_id, reason)
        return

    send_message(chat_id, f"⏳ Analyzing {symbol} on {args[1].upper()}...")

    stack = _TF_TO_STACK[tf]

    def _run_mtf_work():
        try:
            # Single-pass analysis with in-flight smart news evaluation
            report = run_full_analysis(symbol, stack_name=stack, smart_news=True, use_nlp=False)
            if not report or "error" in report:
                send_message(chat_id, f"⚠️ Analysis failed for `{symbol}`. Please try again.")
                return

            report["NLP_SUMMARY"] = generate_nlp_summary(report, symbol)

            stack_label = f"{args[1].upper()} [{stack}]"
            panel = format_signal_panel(symbol, report, stack_label=stack_label)
            _LAST_SIGNAL[chat_id] = {
                "symbol": symbol, "report": report,
                "stack": stack, "ts": time.time()
            }
            _persist_signal(chat_id, symbol, report, stack)
            is_locked = "LOCKED" in (report.get("FINAL_SIGNAL") or "").upper()
            send_message(chat_id, panel, reply_markup=None if is_locked else _took_trade_keyboard(symbol, report.get("SIGNAL_ID", "")))
            log("INFO", "mtf_complete", chat_id=chat_id, symbol=symbol,
                tf=tf, stack=stack, signal=report.get("FINAL_SIGNAL"),
                conf=report.get("CONFIDENCE"), signal_id=report.get("SIGNAL_ID"))

        except Exception as e:
            err_msg = str(e)
            if "All data sources failed" in err_msg:
                send_message(chat_id, f"⚠️ Could not find market data for `{symbol}`.\nPlease verify the symbol ticker (e.g. `XAG/USD` for Silver, `XAU/USD` for Gold, `BTC/USD`, `EUR/USD`).")
            else:
                send_message(chat_id, f"⚠️ Analysis failed for `{symbol}`. Please try again.")
            log("ERROR", "mtf_exception", chat_id=chat_id, symbol=symbol, tf=tf, error=err_msg)

    threading.Thread(target=_run_mtf_work, daemon=True).start()


def _handle_scalp(chat_id, args):
    if not args:
        send_message(chat_id,
            "⚡ *Select a symbol for scalp analysis:*\n"
            "Tap a recent symbol below or type `/scalp SYMBOL`",
            reply_markup=_symbol_suggestion_keyboard("scalp", chat_id))
        return

    wait = check_rate_limit(chat_id, "scalp")
    if wait:
        send_message(chat_id, f"⏳ Scalp cooldown: *{wait}s* remaining.")
        return

    symbol = normalize_user_symbol(args[0])
    _record_recent_symbol(chat_id, symbol)

    blocked, reason = is_drawdown_limit_hit()
    if blocked:
        send_message(chat_id, reason)
        return

    send_message(chat_id, f"⏳ Scalp analysis for {symbol} is running...")

    # Weekend FX Gate
    if is_fx_pair(symbol) and is_weekend():
        msg = (
            "⚪ *Forex Market Closed*\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "No analysis during weekends. FX analysis resumes on Monday."
        )
        send_message(chat_id, msg)
        return

    def _run_scalp_work():
        try:
            # Use smart news: run without first, AI ranks, then decide on news per confidence
            result = run_multi_stack_analysis(symbol, use_nlp=False, no_news=True)

            if "error" in result or not result.get("top_setups"):
                send_message(chat_id, f"⚠️ Analysis failed for `{symbol}`. Please try again.")
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
            _persist_signal(chat_id, symbol, best_report, best.get("stack", ""))
            is_locked = "LOCKED" in (best_report.get("FINAL_SIGNAL") or "").upper()
            send_message(chat_id, panel, reply_markup=None if is_locked else _took_trade_keyboard(symbol, best_report.get("SIGNAL_ID", "")))
            log("INFO", "scalp_complete", chat_id=chat_id, symbol=symbol, stack=best_stack,
                signal_id=best_report.get("SIGNAL_ID"))

        except BaseException as e:
            tb_text = traceback.format_exc()
            print(tb_text, file=sys.stderr)
            err_msg = str(e)
            if "All data sources failed" in err_msg:
                send_message(chat_id, f"⚠️ Could not find market data for `{symbol}`.\nPlease verify the symbol ticker (e.g. `XAG/USD` for Silver, `XAU/USD` for Gold, `BTC/USD`, `EUR/USD`).")
            else:
                send_message(chat_id, f"⚠️ Scalp analysis failed for `{symbol}`. Please try again.")
            log("ERROR", "scalp_exception", chat_id=chat_id, symbol=symbol, error=repr(e), traceback=tb_text)

    threading.Thread(target=_run_scalp_work, daemon=True).start()


def _handle_took_trade(chat_id, symbol: str = None, signal_id: str = None):
    """Registers the signal as a taken trade (by signal_id from callback, symbol, or last signal)."""
    entry = None
    if signal_id:
        entry = _get_persisted_signal(signal_id=signal_id)
    elif symbol:
        entry = _get_persisted_signal(symbol=symbol, chat_id=str(chat_id))
    
    if not entry and not signal_id and not symbol:
        entry = _get_persisted_signal(chat_id=str(chat_id))

    report = None
    trade_symbol = symbol

    if entry:
        report = entry.get("report")
        trade_symbol = entry.get("symbol", symbol)
        # Check expiration (10 min)
        created_at = entry.get("created_at", 0)
        if created_at and (time.time() - created_at) > 600:
            send_message(chat_id, "⚠️ Signal has expired (signals expire after 10 min). Run `/analyze` again for fresh levels.")
            return

    # Fallback to memory cache only if not found in signals log
    if not report:
        cached = _LAST_SIGNAL.get(chat_id)
        if cached and (time.time() - cached.get("ts", 0)) <= 600:
            if not symbol or cached.get("symbol", "").upper() == symbol.upper():
                report = cached.get("report")
                trade_symbol = cached.get("symbol")

    if not report:
        send_message(chat_id, "⚠️ No recent signal found (last signal expires after 10 min). Run `/analyze` first.")
        return

    risk = (report.get("RISK_ADVISORY") or {})

    if "LOCKED" in (report.get("FINAL_SIGNAL") or "").upper():
        send_message(chat_id, "⛔ *Trade Locked*: Cannot register trade. Orders are blocked due to critical risk.")
        return

    if not risk.get("ENTRY_PRICE"):
        send_message(chat_id, "⚠️ No valid trade setup in this signal (WAIT signal).")
        return

    direction = "LONG" if any(w in (report.get("FINAL_SIGNAL") or "").upper() for w in ["LONG", "BUY", "BULL"]) else "SHORT"
    trade = register_trade(
        symbol      = trade_symbol,
        direction   = direction,
        entry       = risk["ENTRY_PRICE"],
        sl          = risk["STOP_LOSS"],
        tps         = risk.get("TAKE_PROFIT", []),
        size_units  = risk.get("POSITION_SIZE_UNITS", 0),
        risk_usd    = risk.get("RISK_AMOUNT_USD", 0),
        tp_profits  = risk.get("TP_PROFIT_USD", []),
        chat_id     = str(chat_id),
        signal_id   = report.get("SIGNAL_ID") or signal_id,
    )

    s = load_settings()
    send_message(chat_id,
        f"✅ *Trade Registered — {trade_symbol}*\n"
        f"  Direction: `{direction}`\n"
        f"  Entry:     `{risk['ENTRY_PRICE']}`\n"
        f"  SL:        `{risk['STOP_LOSS']}`\n"
        f"  Size:      `{risk.get('POSITION_SIZE_UNITS', 0)} units`\n"
        f"  Risk:      `${risk.get('RISK_AMOUNT_USD', 0)}` ({s['risk_per_trade_pct']}% of ${s['account_balance']})\n\n"
        f"📡 _Monitoring price every {s.get('monitor_interval', 300)//60} min..._"
    )
    log("INFO", "trade_registered", chat_id=chat_id, symbol=trade_symbol, direction=direction, signal_id=signal_id)


def _handle_close(chat_id, args):
    if len(args) < 2:
        send_message(chat_id, "⚠️ Usage: `/close SYMBOL PRICE`\ne.g. `/close BTC/USD 71000`")
        return
    symbol     = args[0].upper()
    try:
        exit_price = float(args[1])
    except ValueError:
        send_message(chat_id, "⚠️ Invalid exit price.")
        return

    open_trades = get_open_trades(chat_id=str(chat_id))
    match = next((t for t in open_trades if t["symbol"] == symbol), None)
    if not match:
        send_message(chat_id, f"⚠️ No open trade found for `{symbol}` under your account.")
        return

    result = close_trade(match["id"], exit_price, chat_id=str(chat_id))
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

    elif cmd == "/mtf":
        threading.Thread(target=_handle_mtf, args=(chat_id, args), daemon=True).start()

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

        def _run_scan_work():
            try:
                market_scanner.main(stack=stack_arg, no_news=no_news)
                send_message(chat_id, "✅ *Scan complete.* All alerts sent.")
            except BaseException as e:
                tb_text = traceback.format_exc()
                print(tb_text, file=sys.stderr)
                send_message(chat_id, "⚠️ Scan analysis failed — check logs")
                log("ERROR", "scan_exception", chat_id=chat_id, error=repr(e), traceback=tb_text)

        threading.Thread(target=_run_scan_work, daemon=True).start()

    # ── Trade tracker commands ─────────────────────────────────────────────────
    elif cmd == "/took":
        # Allow /took BTC/USD (optional, uses last signal if no symbol given)
        target_sym = args[0].upper().replace(" ", "") if args else None
        threading.Thread(target=_handle_took_trade, args=(chat_id, target_sym), daemon=True).start()

    elif cmd == "/trades":
        send_message(chat_id, format_open_trades(chat_id=str(chat_id)))

    elif cmd == "/close":
        _handle_close(chat_id, args)

    elif cmd == "/history":
        send_message(chat_id, format_history(chat_id=str(chat_id)))

    elif cmd == "/stats":
        send_message(chat_id, format_stats(chat_id=str(chat_id)))

    else:
        send_message(chat_id, "❓ Unknown command. Send `/start` to see all commands.")


def handle_callback(query):
    """Handles inline button presses (Took Trade / Skip / Symbol Selection)."""
    try:
        chat_id     = query.get("message", {}).get("chat", {}).get("id") or query.get("from", {}).get("id")
        callback_id = query.get("id")
        data        = query.get("data", "")

        log("INFO", "callback_received", chat_id=chat_id, data=data)
        if callback_id:
            answer_callback(callback_id)

        if not chat_id:
            return

        if data == "took_trade":
            threading.Thread(target=_handle_took_trade, args=(chat_id,), daemon=True).start()
        elif data.startswith("took:"):
            # Format: took:SYMBOL:SIGNAL_ID
            parts = data.split(":", 2)
            sym = parts[1] if len(parts) > 1 else None
            sig_id = parts[2] if len(parts) > 2 else None
            threading.Thread(target=_handle_took_trade, args=(chat_id, sym, sig_id), daemon=True).start()
        elif data == "skip_trade" or data.startswith("skip:"):
            send_message(chat_id, "⏭️ Signal skipped. No trade recorded.")
        elif data.startswith("symcmd:"):
            parts = data.split(":", 2)
            if len(parts) >= 3:
                cmd = parts[1]
                sym = normalize_user_symbol(parts[2])
                if cmd == "analyze":
                    threading.Thread(target=_handle_analyze, args=(chat_id, [sym]), daemon=True).start()
                elif cmd == "scalp":
                    threading.Thread(target=_handle_scalp, args=(chat_id, [sym]), daemon=True).start()
                elif cmd == "mtf":
                    threading.Thread(target=_handle_mtf, args=(chat_id, [sym, "1h"]), daemon=True).start()
    except Exception as e:
        log("ERROR", "handle_callback_error", error=str(e), traceback=traceback.format_exc())


# ─── Main Loop ────────────────────────────────────────────────────────────────

def main_loop():
    # Automatically clear any active webhook to ensure getUpdates long-polling works
    try:
        del_res = requests.post(f"{BASE_URL}/deleteWebhook?drop_pending_updates=False", timeout=10).json()
        log("INFO", "webhook_cleared", result=del_res.get("description", "ok"))
    except Exception as e:
        log("WARN", "webhook_clear_failed", error=str(e))

    # Register native Telegram autocomplete command menu
    register_bot_commands()

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
                    log("DEBUG", "update_received", update_id=update["update_id"])

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
            else:
                err_code = data.get("error_code")
                desc = data.get("description", "Unknown Telegram API error")
                log("WARN", "telegram_poll_error", error_code=err_code, description=desc)
                # If webhook conflict returned, re-attempt deleteWebhook
                if err_code == 409 and "webhook" in desc.lower():
                    requests.post(f"{BASE_URL}/deleteWebhook", timeout=10)
                time.sleep(3)

            time.sleep(0.5)

        except Exception as e:
            log("ERROR", "poll_error", error=str(e))
            time.sleep(5)


if __name__ == "__main__":
    main_loop()
