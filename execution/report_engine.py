import argparse
import json
import sys
import os
from datetime import datetime
from telegram_bot import send_telegram_alert

def aggregate_v2_confidence(str_res, hist_res, news_res):
    """
    Super Signals v2.1 Aggregation Model — Phase 8.1 enhanced.
    Phase 8.1: Hard floor gates applied BEFORE score aggregation.
      Gate 1: L1 < 10  → no structural basis → force WAIT
      Gate 2: L1+L2 < 25 → weak confluence → force WAIT
      Gate 3: ADX RANGING on LTF → choppy market → force WAIT
    Final Score = 10 + L1 + L2 + L3 + L4, scaled by (1 − news_penalty/100).
    """
    # Extract granular scores
    l1_score     = str_res.get("details", {}).get("ltf_layer1", {}).get("layer1_score", 0)
    l2_score     = str_res.get("layer2_score", 0)
    l3_score     = hist_res.get("layer3_score", 0)
    l4_score     = news_res.get("layer4_score", 0)
    ltf_l1       = str_res.get("details", {}).get("ltf_layer1", {})
    adx_regime   = ltf_l1.get("regime", "TRENDING")

    # ─ Phase 8.1: Hard Floor Gates ────────────────────────────────────
    if l1_score < 10:
        return 0.0, "WAIT / NO_TRADE (Structural Floor)"
    if l1_score + l2_score < 25:
        return 0.0, "WAIT / NO_TRADE (Confluence Floor)"
    if adx_regime == "RANGING":
        return 0.0, "WAIT / NO_TRADE (Ranging Regime — ADX Gate)"

    # FIX 1.4: Cross-validate L3 historical bias vs structural bias
    structural_bias = str_res.get("final_signal", "WAIT / NO_TRADE")
    hist_bias       = hist_res.get("historical_bias", "UNCLEAR")
    if hist_bias != "UNCLEAR":
        bias_conflict = (
            ("LONG"  in structural_bias and hist_bias == "BEARISH") or
            ("SHORT" in structural_bias and hist_bias == "BULLISH")
        )
        if bias_conflict:
            l3_score = -l3_score   # Penalise conflicting history

    base_confidence  = 10.0 + l1_score + l2_score + l3_score + l4_score
    penalty          = news_res.get("final_penalty", 0)
    risk_state       = news_res.get("risk_state", "NORMAL")
    event_scope      = news_res.get("highest_scope", "unknown")
    source_trust     = news_res.get("max_trust", 0.0)

    final_confidence = base_confidence * (1 - penalty / 100.0)

    bias   = str_res.get("final_signal", "WAIT / NO_TRADE")
    action = "WAIT / NO_TRADE"

    if event_scope == "protocol" and source_trust >= 0.8:
        risk_state = "CRITICAL"
        news_res["risk_state"] = "CRITICAL"

    if risk_state == "CRITICAL":
        action = "WAIT / LOCKED (CRITICAL NEWS)"
    elif risk_state == "WAIT_VERIFICATION":
        action = "WAIT / VERIFYING NEWS"
    elif final_confidence >= 70:
        if "LONG"  in bias: action = "LONG_BIAS"
        elif "SHORT" in bias: action = "SHORT_BIAS"

    if risk_state == "CAUTION" and "WAIT" not in action:
        action += " (CAUTION)"

    return round(final_confidence, 2), action

def calculate_pips(symbol, entry, stop_loss, take_profits):
    """
    Calculates pip values based on asset type.
    Forex: 0.0001 = 1 pip (except JPY pairs: 0.01 = 1 pip)
    Gold/Silver: 0.1 = 1 pip
    Crypto: 1.0 = 1 pip
    """
    symbol_upper = symbol.upper()
    
    # Determine pip size
    if 'JPY' in symbol_upper:
        pip_size = 0.01
    elif any(x in symbol_upper for x in ['XAU', 'XAG', 'GOLD', 'SILVER']):
        pip_size = 0.1
    elif any(x in symbol_upper for x in ['BTC', 'ETH', 'CRYPTO']):
        pip_size = 1.0
    elif '/' in symbol and any(x in symbol_upper for x in ['USD', 'EUR', 'GBP', 'CHF', 'AUD', 'NZD', 'CAD']):
        pip_size = 0.0001
    else:
        pip_size = 0.01  # Default
    
    risk_pips = abs(entry - stop_loss) / pip_size
    reward_pips = [abs(entry - tp) / pip_size for tp in take_profits]
    
    return {
        "risk_pips": round(risk_pips, 1),
        "reward_pips": [round(r, 1) for r in reward_pips],
        "pip_size": pip_size
    }


def smart_round(price: float) -> float:
    """
    Price-magnitude-aware rounding.
    >= $100  → 2 dp   (BTC: 69,143.08, Gold: 2,943.50)
    >= $10   → 3 dp   (USD/JPY: 149.236)
    >= $1    → 5 dp   (EUR/USD: 1.16328)
    < $1     → 6 dp   (XRP: 0.512340)
    """
    if price >= 100:    return round(price, 2)
    if price >= 10:     return round(price, 3)
    if price >= 1:      return round(price, 5)
    return round(price, 6)


def pip_cost_per_lot(symbol: str, price: float = 1.0) -> float:
    """
    USD value of 1 pip for 1 standard lot.
    Forex USD-quoted: $10/pip | JPY pairs: $6.7/pip approx
    Gold: $100/pip | Silver: $50/pip | Crypto/other: 0
    """
    s = symbol.upper()
    if "XAU" in s or "GOLD" in s:   return 100.0
    if "XAG" in s or "SILVER" in s: return 50.0
    if "JPY" in s:                   return round(1000 / price, 2) if price else 6.7
    if any(x in s for x in ["EUR", "GBP", "AUD", "NZD", "CAD", "CHF", "USD"]):
        if "/" in s:                 return 10.0
    return 0.0   # crypto / unknown


def calculate_lot_size(symbol: str, position_units: float, risk_pips: float,
                       risk_amount_usd: float, price: float = 1.0) -> dict:
    """
    Converts position units into standard forex lot notation.
    Returns lot_label, standard_lots, micro_lots, pip_value, implied_risk.
    For crypto returns units-only (no lot concept).
    """
    s = symbol.upper()
    is_crypto = any(x in s for x in ["BTC", "ETH", "SOL", "XRP", "BNB", "DOGE", "ADA", "AVAX"])

    if is_crypto:
        return {"lot_label": f"{position_units} units", "standard_lots": 0,
                "micro_lots": 0, "pip_value": 0, "implied_risk": 0, "is_forex": False}

    CONTRACT_SIZE = 100_000                           # standard forex lot
    if "XAU" in s or "GOLD" in s:   CONTRACT_SIZE = 100
    if "XAG" in s or "SILVER" in s: CONTRACT_SIZE = 1_000

    std_lots  = position_units / CONTRACT_SIZE
    micro     = int(round(std_lots * 100))
    advised   = round(std_lots, 2)
    pip_value = pip_cost_per_lot(symbol, price)
    implied_risk = round(advised * risk_pips * pip_value, 2) if pip_value else 0

    return {
        "lot_label":     f"{advised} lots  ({micro} micro)",
        "standard_lots":  advised,
        "micro_lots":     micro,
        "pip_value":      pip_value,
        "implied_risk":   implied_risk,
        "is_forex":       True,
    }


def calculate_v2_risk(action, str_data, news_penalty, external_data=None, symbol="UNKNOWN"):
    """
    Phase 11: Precision Execution Engine (High R:R).
    Transitioned from wide ATR stops at Market to Limit orders at specific
    discount zones (FVG/OB/Fib/VWAP) with micro-invalidation stops.
    """
    if "LOCKED" in action:
        return None

    if external_data is None:
        external_data = {}

    details = str_data.get("details", {})
    ltf_l1 = details.get("ltf_layer1", {})
    ltf_struct = details.get("raw_ltf_structure", [])
    if not ltf_struct: 
        return None

    last_price = float(ltf_struct[-1]['price'])
    atr = ltf_l1.get("atr", 0) or (last_price * 0.005)

    is_long = "LONG" in action

    # 1. IDENTIFY SNIPER ENTRY ZONE (Limit Order)
    # -------------------------------------------------------------------------
    # Priority: 1. FVG, 2. OB, 3. 0.705 Fib, 4. VWAP
    entry_candidates = []

    # FVG
    for fvg in ltf_l1.get("fvgs", []):
        if (is_long and fvg['type'] == 'BULLISH') or (not is_long and fvg['type'] == 'BEARISH'):
            entry_candidates.append({"type": "FVG", "price": fvg['top'] if is_long else fvg['bottom'], "inval": fvg['bottom'] if is_long else fvg['top']})

    # Order Block
    if not entry_candidates:
        for ob in ltf_l1.get("order_blocks", []):
            if (is_long and ob['type'] == 'BULLISH') or (not is_long and ob['type'] == 'BEARISH'):
                entry_candidates.append({"type": "OB", "price": ob['top'] if is_long else ob['bottom'], "inval": ob['bottom'] if is_long else ob['top']})

    # 0.705 Fib OTE (Optimal Trade Entry)
    if not entry_candidates and ltf_l1.get("fib_levels"):
        fib = ltf_l1["fib_levels"].get("0.705")
        fib_inval = ltf_l1["fib_levels"].get("1.0")
        if fib and fib_inval:
            entry_candidates.append({"type": "FIB_0.705", "price": fib, "inval": fib_inval})

    # VWAP / AVWAP fallback
    if not entry_candidates and ltf_l1.get("vwap"):
        vwap = ltf_l1.get("avwap") or ltf_l1.get("vwap")
        if vwap:
            # For VWAP, invalidation is a standard 1.0 ATR deviation
            inval = vwap - atr if is_long else vwap + atr
            entry_candidates.append({"type": "VWAP", "price": vwap, "inval": inval})

    # Absolute fallback (Current Price with ATR stop)
    if not entry_candidates:
        inval = last_price - (1.5 * atr) if is_long else last_price + (1.5 * atr)
        entry_candidates.append({"type": "MARKET_FALLBACK", "price": last_price, "inval": inval})

    best_entry = entry_candidates[0]
    entry_price = float(best_entry["price"])
    invalidation_price = float(best_entry["inval"])


    # 2. MICRO-INVALIDATION (Sniper Stop Loss)
    # -------------------------------------------------------------------------
    # Stop Loss is precisely 0.2*ATR past the invalidation point of the zone
    buffer = 0.2 * atr
    if is_long:
        sl_price = invalidation_price - buffer
    else:
        sl_price = invalidation_price + buffer

    # If the entry zone is somehow worse than current price (price already ran away),
    # pull the entry up/down to current price so we don't issue impossible limits
    if (is_long and entry_price > last_price) or (not is_long and entry_price < last_price):
        entry_price = last_price

    # Fallback to absolute minimum risk if math gets tangled
    min_dist = last_price * 0.001 
    if abs(entry_price - sl_price) < min_dist:
        sl_price = entry_price - min_dist if is_long else entry_price + min_dist

    risk_dist = abs(entry_price - sl_price)


    # 3. ASYMMETRIC TAKE PROFIT TARGETS
    # -------------------------------------------------------------------------
    # News risk tightens TP targets aggressively (squeezes to secure gains)
    risk_multi = max(0.4, 1.0 - (news_penalty / 200.0))
    tps = []

    # Try to use Fib Extensions first (Phase 10.2 structure)
    fibs = ltf_l1.get("fib_levels", {})
    if fibs and "0.0" in fibs and "1.618" in fibs:
        base_tp1 = fibs.get("0.0")     # The 0.0 line is the swing high/low (1.0 extension logic)
        base_tp2 = fibs.get("1.618")   # Primary target
        base_tp3 = fibs.get("2.618")   # Runner
        
        # Apply squeeze multiplier to the distance from entry
        if is_long:
            tp1 = entry_price + max(0, (base_tp1 - entry_price) * risk_multi)
            tp2 = entry_price + max(0, (base_tp2 - entry_price) * risk_multi)
            tp3 = entry_price + max(0, (base_tp3 - entry_price) * risk_multi)
        else:
            tp1 = entry_price - max(0, (entry_price - base_tp1) * risk_multi)
            tp2 = entry_price - max(0, (entry_price - base_tp2) * risk_multi)
            tp3 = entry_price - max(0, (entry_price - base_tp3) * risk_multi)
        tps = [round(tp1, 2), round(tp2, 2), round(tp3, 2)]
    else:
        # Fallback R-mults if Fibs aren't drawn (3R, 6R, 10R)
        mults = [3.0, 6.0, 10.0]
        for m in mults:
            if is_long:
                tps.append(round(entry_price + (risk_dist * m * risk_multi), 2))
            else:
                tps.append(round(entry_price - (risk_dist * m * risk_multi), 2))

    # Phase 11.3 Runner Override: CME Gap
    # If a CME gap exists in our direction, override TP3 to target it
    cme_gap = external_data.get("cme_gap", {}).get("nearest_gap")
    if cme_gap:
        gap_mid = (cme_gap['gap_high'] + cme_gap['gap_low']) / 2
        if (is_long and gap_mid > tps[1]) or (not is_long and gap_mid < tps[1]):
            tps[2] = round(gap_mid, 2)
    
    # Calculate pips and risk %
    pip_data = calculate_pips(symbol, entry_price, sl_price, tps)
    risk_pct = round((risk_dist / entry_price) * 100, 3) if entry_price > 0 else 0.0

    # Position Sizing — reads live settings from bot_settings (bot commands override .env)
    try:
        import sys as _sys
        _sys.path.insert(0, os.path.dirname(__file__))
        from bot_settings import load_settings as _load_settings
        _s = _load_settings()
        account_balance  = _s["account_balance"]
        risk_pct_input   = _s["risk_per_trade_pct"]
    except Exception:
        account_balance  = float(os.environ.get("ACCOUNT_BALANCE", 60))
        risk_pct_input   = float(os.environ.get("RISK_PER_TRADE", 20))

    try:
        risk_amount_usd  = round(account_balance * (risk_pct_input / 100), 4)

        min_risk_dist = entry_price * 0.0005
        effective_risk_dist = max(risk_dist, min_risk_dist)

        pos_units = round(risk_amount_usd / effective_risk_dist, 6) if effective_risk_dist > 0 else 0.0
        pos_size_usd = round(pos_units * entry_price, 2)
        
        lot_data = calculate_lot_size(symbol, pos_units, pip_data["risk_pips"], risk_amount_usd, entry_price)

        # TP Profit: USD gain if position closes at each TP level
        tp_profit_usd = []
        tp_rr_actual  = []
        for tp in tps:
            gain = round(abs(tp - entry_price) * pos_units, 2)
            rr   = round(gain / risk_amount_usd, 2) if risk_amount_usd > 0 else 0.0
            tp_profit_usd.append(gain)
            tp_rr_actual.append(rr)

    except Exception:
        risk_pct_input = 20.0
        risk_amount_usd = 0.0
        pos_units = 0.0
        pos_size_usd = 0.0
        tp_profit_usd = []
        tp_rr_actual  = []
        lot_data      = {}

    return {
        "ENTRY_PRICE":        smart_round(entry_price),
        "ENTRY_TYPE":         f"LIMIT ({best_entry['type']})" if best_entry['type'] != "MARKET_FALLBACK" else "MARKET",
        "STOP_LOSS":          smart_round(sl_price),
        "TAKE_PROFIT":        [smart_round(tp) for tp in tps],
        "RISK_OFFSET":        round(risk_multi, 2),
        "RISK_PCT":           risk_pct,
        "METHOD":             f"PRECISION_{best_entry['type']}",
        "ATR_VALUE":          round(atr, 4),
        "RISK_PIPS":          pip_data["risk_pips"],
        "REWARD_PIPS":        pip_data["reward_pips"],
        # Position sizing
        "ACCOUNT_BALANCE":     account_balance,
        "RISK_PER_TRADE_PCT":  risk_pct_input,
        "RISK_AMOUNT_USD":     risk_amount_usd,
        "POSITION_SIZE_UNITS": pos_units,
        "POSITION_SIZE_USD":   pos_size_usd,
        "TP_PROFIT_USD":       tp_profit_usd,
        "TP_RR_ACTUAL":        tp_rr_actual,
        "LOT_SIZE_DATA":       lot_data,
    }


def log_outcome_prediction(symbol, action, confidence, entry_price, snapshot_close):
    """
    Stores prediction for the feedback loop.
    FIX 2.1: Now records snapshot_close (the actual live close at analysis time)
    separately from entry_price (last structure point). Previously only entry_price
    was logged and 'current price' was read from a stale CSV that had been overwritten,
    making performance_analyzer.py produce meaningless drift numbers.
    """
    log_file = ".tmp/prediction_logs.json"
    entry = {
        "timestamp": str(datetime.now()),
        "symbol": symbol,
        "action": action,
        "confidence": confidence,
        "entry_price": entry_price,
        "snapshot_close": snapshot_close,  # Actual market close at time of signal
        "outcome_checked": False           # Set to True by performance_analyzer after evaluation
    }
    logs = []
    if os.path.exists(log_file):
        try:
            with open(log_file, 'r') as f: logs = json.load(f)
        except: pass
    logs.append(entry)
    with open(log_file, 'w') as f: json.dump(logs, f, indent=2)

def generate_report(symbol, str_data, hist_data, news_data):
    """
    Direct functional entry point for the orchestrator.
    """
    try:
        conf, action = aggregate_v2_confidence(str_data, hist_data, news_data)
        penalty = news_data.get("final_penalty", 0)
        risk    = calculate_v2_risk(action, str_data, penalty, symbol=symbol)

        # ─ Phase 11.4: Precision R:R Validation Gate ──────────────────────────
        # Before issuing any LONG/SHORT, check that the trade is worth taking.
        # With sniper limit entries, R:R must be >= 1.5:1 (Lenient mode)
        rr_ratio  = 0.0
        rr_gate   = "N/A"
        rr_bonus  = 0
        if risk and "WAIT" not in action and "LOCKED" not in action:
            entry_p = risk.get("ENTRY_PRICE", 0)
            sl_dist = abs(entry_p - risk["STOP_LOSS"])
            tp_list = risk.get("TAKE_PROFIT", [])
            tp1_dist = abs(tp_list[0] - entry_p) if tp_list else 0
            
            if sl_dist > 0:
                rr_ratio = round(tp1_dist / sl_dist, 2)
                
            if rr_ratio < 1.5:
                action   = "WAIT / NO_TRADE (R:R < 1.5)"
                rr_gate  = "FAIL"
            elif rr_ratio >= 3.0:
                conf    = round(min(100, conf + 5), 2)  # Exceptional R:R bonus
                rr_gate = "PASS+"
            else:
                rr_gate = "PASS"
                
            if risk:
                risk["RR_RATIO"] = rr_ratio
                risk["RR_GATE"]  = rr_gate

        # Feedback loop logging
        ltf_struct    = str_data.get("details", {}).get("raw_ltf_structure", [])
        last_p        = ltf_struct[-1]['price'] if ltf_struct else 0
        snapshot_close = last_p
        log_outcome_prediction(symbol, action, conf, last_p, snapshot_close)

        # Governance Alerts
        alerts = []
        if penalty > 0:
            alerts.append(f"[!] NEWS: Risk Penalty {penalty} applied.")
        if news_data.get("risk_state") == "WAIT_VERIFICATION":
            alerts.append("[!] GOV: Verifying news consensus (Temporary Hold).")
        if hist_data.get("false_positive_risk"):
            alerts.append("[!] HIST: High instability/Analogue variance detected.")

        # CHoCH alert
        ltf_l1 = str_data.get("details", {}).get("ltf_layer1", {})
        choch  = ltf_l1.get("choch")
        if choch:
            alerts.append(f"[!] CHOCH: {choch['type']} detected at {choch['level']} — {choch['note']}")

        # Phase 8.1 / 8.2 gate alerts
        if "Structural Floor" in action:
            alerts.append("[!] GATE: L1 score below structural minimum (< 10).")
        if "Confluence Floor" in action:
            alerts.append("[!] GATE: L1+L2 below confluence minimum (< 25).")
        if "Ranging Regime" in action:
            alerts.append("[!] GATE: ADX regime RANGING — choppy market, no trade.")
        if rr_gate == "FAIL":
            alerts.append(f"[!] R:R GATE: Ratio {rr_ratio}:1 below 1.5 minimum — signal downgraded.")
        if rr_gate == "PASS+":
            alerts.append(f"[OK] R:R BONUS: Exceptional {rr_ratio}:1 ratio -- +5 confidence applied.")

        report = {
            "TIMESTAMP":         str(datetime.now()),
            "FINAL_SIGNAL":      action,
            "CONFIDENCE":        conf,
            "RISK_ADVISORY":     risk,
            "GOVERNANCE_ALERTS": alerts,
            "REASONING": {
                "l1_structure":  ltf_l1.get("notes"),
                "l2_confluence": str_data.get("reasoning"),
                "l3_history":    hist_data.get("reasoning"),
                "l4_news":       news_data.get("reasoning")
            }
        }

        if conf >= 85 and "WAIT" not in action:
            msg = (
                f"SUPER SIGNAL ALERT\n\n*Symbol:* {symbol}\n"
                f"*Signal:* {action}\n*Confidence:* {conf}/100\n*Price:* {last_p}"
            )
            if risk:
                msg += f"\n*TP:* {risk.get('TAKE_PROFIT')[0]}\n*SL:* {risk.get('STOP_LOSS')}"
            try:
                send_telegram_alert(msg)
            except Exception:
                pass

        return report
    except Exception as e:
        return {"error": str(e)}

def main():
    parser = argparse.ArgumentParser(description='Super Signals 2.0 Report Engine.')
    parser.add_argument('--structure', type=str, required=True)
    parser.add_argument('--history', type=str, required=True)
    parser.add_argument('--news', type=str, required=True)
    parser.add_argument('--symbol', type=str, default="UNKNOWN")
    args = parser.parse_args()
    
    try:
        with open(args.structure, 'r') as f: str_data = json.load(f)
        with open(args.history, 'r') as f: hist_data = json.load(f)
        with open(args.news, 'r') as f: news_data = json.load(f)
        
        result = generate_report(args.symbol, str_data, hist_data, news_data)
        print(json.dumps(result, indent=2))
        
    except Exception as e:
        print(json.dumps({"error": str(e)}))
        sys.exit(1)

if __name__ == "__main__":
    main()
