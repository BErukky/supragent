import argparse
import json
import sys
import os
from datetime import datetime
from telegram_bot import send_telegram_alert

def aggregate_v2_confidence(str_res, hist_res, news_res):
    """
    Super Signals 2.0 Aggregation Model:
    Final Score = (L1 * 0.4) + (L2 * 0.3) + (L3 * 0.2) + (L4 * 0.1)
    Then scaled by (1 - RiskPenalty / 100).
    """
    # Extract granular scores
    l1_score = str_res.get("details", {}).get("ltf_layer1", {}).get("layer1_score", 0)
    l2_score = str_res.get("layer2_score", 0)
    l3_score = hist_res.get("layer3_score", 0)
    l4_score = news_res.get("layer4_score", 0)
    
    # Scale each to 0-100 base for calculation
    base_confidence = 10.0 + l1_score + l2_score + l3_score + l4_score
    
    # Apply Proportional Governance (Precision Upgrade 1)
    penalty = news_res.get("final_penalty", 0)
    risk_state = news_res.get("risk_state", "NORMAL")
    event_scope = news_res.get("highest_scope", "unknown")
    source_trust = news_res.get("max_trust", 0.0)
    
    # Proportional scaling instead of direct subtraction
    final_confidence = base_confidence * (1 - penalty / 100.0)
    
    # Determine Action based on 3-State Logic
    bias = str_res.get("final_signal", "WAIT / NO_TRADE")
    action = "WAIT / NO_TRADE"
    
    # --- Precision Lock Rule ---
    # If PROTOCOL risk from TRUSTED source -> Force CRITICAL
    if event_scope == "protocol" and source_trust >= 0.8:
        risk_state = "CRITICAL"
        news_res["risk_state"] = "CRITICAL" # Update for reporting

    # Adaptive Logic
    if risk_state == "CRITICAL":
        action = "WAIT / LOCKED (CRITICAL NEWS)"
    elif risk_state == "WAIT_VERIFICATION":
        action = "WAIT / VERIFYING NEWS"
    elif final_confidence >= 70:
        if "LONG" in bias: action = "LONG_BIAS"
        elif "SHORT" in bias: action = "SHORT_BIAS"
    
    if risk_state == "CAUTION" and "WAIT" not in action:
        action += " (CAUTION)"
        
    return round(final_confidence, 2), action

def calculate_v2_risk(action, str_data, news_penalty):
    """
    Precision Upgrade: Tightens TP/SL based on news penalty.
    Includes fallback buffers for low-confidence states.
    """
    details = str_data.get("details", {})
    ltf_struct = details.get("raw_ltf_structure", [])
    if not ltf_struct: return None
    
    last_price = ltf_struct[-1]['price']
    
    # Logic: More news risk = tighter TP targets
    risk_multi = 1.0 - (news_penalty / 200.0)
    if "WAIT" in action or "LOCKED" in action:
        risk_multi = 1.0
    
    # 1. Structural Calculation
    sl_price = 0.0
    if "LONG" in action:
        sl_node = next((s for s in reversed(ltf_struct) if 'L' in s['type']), None)
        sl_price = sl_node['price'] if sl_node else last_price * 0.99
    else:
        sl_node = next((s for s in reversed(ltf_struct) if 'H' in s['type']), None)
        sl_price = sl_node['price'] if sl_node else last_price * 1.01

    risk = abs(last_price - sl_price)
    
    # 2. Reliability Check & Fallback (Precision Upgrade 2)
    min_buffer = last_price * 0.003
    if risk < min_buffer:
        # Apply Minimal Structural Buffer
        if "LONG" in action:
            sl_price = last_price * 0.997
            tps = [round(last_price * 1.006, 2), round(last_price * 1.012, 2)]
        else:
            sl_price = last_price * 1.003
            tps = [round(last_price * 0.994, 2), round(last_price * 0.988, 2)]
    else:
        # Standard structural targets
        if "LONG" in action:
            tps = [round(last_price + (risk * 1.0 * risk_multi), 2), round(last_price + (risk * 2.0 * risk_multi), 2)]
        else:
            tps = [round(last_price - (risk * 1.0 * risk_multi), 2), round(last_price - (risk * 2.0 * risk_multi), 2)]
        
    return {"STOP_LOSS": round(sl_price, 2), "TAKE_PROFIT": tps, "RISK_OFFSET": round(risk_multi, 2)}

def log_outcome_prediction(symbol, action, confidence, price):
    """
    Stores prediction for the feedback loop.
    """
    log_file = ".tmp/prediction_logs.json"
    entry = {
        "timestamp": str(datetime.now()),
        "symbol": symbol,
        "action": action,
        "confidence": confidence,
        "entry_price": price
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
        risk = calculate_v2_risk(action, str_data, penalty)
        
        # Log for feedback loop
        ltf_struct = str_data.get("details", {}).get("raw_ltf_structure", [])
        last_p = ltf_struct[-1]['price'] if ltf_struct else 0
        log_outcome_prediction(symbol, action, conf, last_p)
        
        # Governance Alerts
        alerts = []
        if penalty > 0:
            alerts.append(f"[!] NEWS: Risk Penalty {penalty} applied.")
        
        if news_data.get("risk_state") == "WAIT_VERIFICATION":
            alerts.append("[!] GOV: Verifying news consensus (Temporary Hold).")

        if hist_data.get("false_positive_risk"):
            alerts.append("[!] HIST: High instability/Analogue variance detected.")

        report = {
            "TIMESTAMP": str(datetime.now()),
            "FINAL_SIGNAL": action,
            "CONFIDENCE": conf,
            "RISK_ADVISORY": risk,
            "GOVERNANCE_ALERTS": alerts,
            "REASONING": {
                "l1_structure": str_data.get("details", {}).get("ltf_layer1", {}).get("notes"),
                "l2_confluence": str_data.get("reasoning"),
                "l3_history": hist_data.get("reasoning"),
                "l4_news": news_data.get("reasoning")
            }
        }
        
        # --- TELEGRAM INTEGRATION ---
        # The telegram_listener.py now handles the primary reporting.
        if conf >= 85 and "WAIT" not in action:
            msg = f"🚀 *SUPER SIGNAL ALERT* 🚀\n\n*Symbol:* {symbol}\n*Signal:* {action}\n*Confidence:* {conf}/100\n\n*Price:* {last_p}"
            if risk:
                msg += f"\n*TP:* {risk.get('TAKE_PROFIT')[0]}\n*SL:* {risk.get('STOP_LOSS')}"
            send_telegram_alert(msg)
            
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
