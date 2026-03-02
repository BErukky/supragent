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
    Then minus News Penalties.
    """
    # Extract granular scores
    l1_score = str_res.get("details", {}).get("ltf_layer1", {}).get("layer1_score", 0)
    l2_score = str_res.get("layer2_score", 0)
    l3_score = hist_res.get("layer3_score", 0)
    l4_score = news_res.get("layer4_score", 0)
    
    # Scale each to 0-100 base for calculation
    # L1 Max 30, L2 Max 30, L3 Max 20, L4 Max 10. Total Max = 90 + base offset 10 = 100
    base_confidence = 10.0 + l1_score + l2_score + l3_score + l4_score
    
    # Apply Governance Penalties from News (Layer 4)
    penalty = news_res.get("risk_penalty", 0)
    final_confidence = max(0, base_confidence - penalty)
    
    # Determine Action
    bias = str_res.get("final_signal", "WAIT / NO_TRADE")
    action = "WAIT / NO_TRADE"
    
    # Governance: Selective Action
    if final_confidence >= 75:
        if "LONG" in bias: action = "LONG_BIAS"
        elif "SHORT" in bias: action = "SHORT_BIAS"
    
    # If News is Critical, force Wait
    if not news_res.get("permits_trade", True):
        action = "WAIT / NO_TRADE"
        
    return round(final_confidence, 2), action

def calculate_v2_risk(action, str_data, news_penalty):
    """
    Tightens TP/SL based on news penalty.
    """
    if "NO_TRADE" in action or "WAIT" in action: return None
    
    details = str_data.get("details", {})
    ltf_struct = details.get("raw_ltf_structure", [])
    if not ltf_struct: return None
    
    last_price = ltf_struct[-1]['price']
    
    # Logic: More news risk = tighter TP targets (locking in profit early)
    risk_multi = 1.0 - (news_penalty / 200.0) # Reduce multi if penalty > 0
    
    # Find SL
    sl_price = 0.0
    if action == "LONG_BIAS":
        sl_node = next((s for s in reversed(ltf_struct) if 'L' in s['type']), None)
        sl_price = sl_node['price'] if sl_node else last_price * 0.98
        risk = abs(last_price - sl_price)
        tps = [round(last_price + (risk * 1.0 * risk_multi), 2), round(last_price + (risk * 2.0 * risk_multi), 2)]
    else:
        sl_node = next((s for s in reversed(ltf_struct) if 'H' in s['type']), None)
        sl_price = sl_node['price'] if sl_node else last_price * 1.02
        risk = abs(sl_price - last_price)
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
        
        conf, action = aggregate_v2_confidence(str_data, hist_data, news_data)
        risk = calculate_v2_risk(action, str_data, news_data.get("risk_penalty", 0))
        
        # Log for feedback loop
        ltf_struct = str_data.get("details", {}).get("raw_ltf_structure", [])
        last_p = ltf_struct[-1]['price'] if ltf_struct else 0
        log_outcome_prediction(args.symbol, action, conf, last_p)
        
        # Governance Alerts
        alerts = []
        if news_data.get("risk_penalty", 0) > 0:
            alerts.append(f"[!] NEWS: Risk Penalty {news_data['risk_penalty']} applied.")
            if news_data.get("flagged_keywords"):
                alerts.append(f"    Flagged: {', '.join(news_data['flagged_keywords'])}")
        
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
        # Trigger Alert if High Confidence OR Critical Risk
        if conf >= 75:
            msg = f"🚀 *SUPER SIGNAL ALERT* 🚀\n\n*Symbol:* {args.symbol}\n*Signal:* {action}\n*Confidence:* {conf}/100\n\n*Reasoning:*\nL1: {report['REASONING']['l1_structure']}\nL2: {report['REASONING']['l2_confluence']}\n\n*Price:* {last_p}"
            if risk:
                msg += f"\n\n*TP:* {risk.get('TAKE_PROFIT')}\n*SL:* {risk.get('STOP_LOSS')}"
            send_telegram_alert(msg)
            
        elif news_data.get("risk_penalty", 0) >= 80:
            msg = f"⚠️ *GOVERNANCE WARNING* ⚠️\n\n*Symbol:* {args.symbol}\n*Status:* WAIT / LOCKED\n\n*Reason:* Critical News Risk Detected.\n*Penalty:* -{news_data['risk_penalty']}\n*Headlines:* {news_data.get('flagged_keywords')}"
            send_telegram_alert(msg)
        # ----------------------------

        print(json.dumps(report, indent=2))
        
    except Exception as e:
        print(json.dumps({"error": str(e)}))
        sys.exit(1)

if __name__ == "__main__":
    main()
