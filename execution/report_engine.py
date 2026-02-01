import argparse
import json
import sys
from datetime import datetime

def calculate_score(structure_data, history_data, news_data):
    """
    Calculates final confidence score (0-100) and incorporates Confidence Governance.
    """
    score = 50 # Start Neutral (0 confidence distance)
    reasons = []
    gov_notes = []
    
    # 1. Base Structure & Layer 1 Scoring (Max +/- 30)
    details = structure_data.get("details", {})
    ltf_l1 = details.get("ltf_layer1", {})
    l1_score = ltf_l1.get("layer1_score", 0)
    structure_signal = structure_data.get("final_signal", "NO_TRADE")
    
    if structure_signal == "LONG_BIAS":
        score += l1_score
        reasons.append(f"Layer 1: {ltf_l1.get('notes')} (+{l1_score})")
    elif structure_signal == "SHORT_BIAS":
        score -= l1_score
        reasons.append(f"Layer 1: {ltf_l1.get('notes')} (-{l1_score})")
    else:
        reasons.append("Structure: No clear bias (Neutral)")
            
    # 2. History Scoring (Max +/- 10)
    hist_bias = history_data.get("historical_bias", "UNCLEAR")
    if hist_bias == "BULLISH":
        score += 10
        reasons.append("History: Past analogs ended Bullish (+10)")
    elif hist_bias == "BEARISH":
        score -= 10
        reasons.append("History: Past analogs ended Bearish (-10)")
        
    # --- CONFIDENCE GOVERNANCE PHASE ---
    
    # A. News Override Rules
    news_impact = news_data.get("risk_level", "NONE")
    if news_impact == "HIGH" or news_impact == "CRITICAL":
        gov_notes.append("[!] News: High-impact event imminent (Risk Override)")
        return 50, "WAIT / NO_TRADE", reasons + gov_notes
    
    if news_impact == "MEDIUM":
        # Moderate confidence by 20 points
        if score > 50: score = max(50, score - 20)
        elif score < 50: score = min(50, score + 20)
        gov_notes.append("[!] News: Risk context detected (confidence moderated)")

    # B. Historical Assimilation Sanity Check
    # If historical return is low or bias is unclear despite structure alignment
    if hist_bias == "UNCLEAR" and structure_signal != "NO_TRADE":
        if score > 50: score = max(50, score - 15)
        elif score < 50: score = min(50, score + 15)
        gov_notes.append("[~] History: Similar structures showed instability")

    # 3. Sentiment Adjustment (Layer 4) - Max +/- 10
    news_score = news_data.get("sentiment_score", 0)
    if news_score > 5:
        score += 10 # This is "earned" sentiment
        reasons.append("News: Positive Sentiment (+10)")
    elif news_score < -5:
        score -= 10
        reasons.append("News: Negative Sentiment (-10)")

    # Final Clamp
    score = max(0, min(100, score))
    
    # Final Decision Thresholds
    final_action = "WAIT / NO_TRADE"
    if score >= 75:
        final_action = "LONG_BIAS"
    elif score <= 25:
        final_action = "SHORT_BIAS"
    else:
        final_action = "WAIT / NO_TRADE"
        if not gov_notes:
            gov_notes.append("[!] Confidence below trust threshold (75) -> WAIT")
        
    return score, final_action, reasons + gov_notes

def calculate_risk_levels(action, structure_data):
    """
    Calculates TP and SL based on LTF structure points.
    """
    if action == "NO_TRADE" or action == "WAIT / NO_TRADE":
        return None

    details = structure_data.get("details", {})
    ltf_struct = details.get("raw_ltf_structure", [])
    
    if not ltf_struct:
        return {"note": "No structure data for risk calc"}
        
    last_struct_price = ltf_struct[-1]['price']
    
    sl_price = 0.0
    tp_targets = []
    
    # Simple Logic:
    # Buffer is arbitrarily 0.5% for this demo
    buffer = last_struct_price * 0.005 

    if action == "LONG_BIAS":
        # SL = Below last swing low (search backwards for a 'L' type)
        swing_low = next((s for s in reversed(ltf_struct) if 'L' in s['type']), None)
        if swing_low:
             sl_price = swing_low['price'] - buffer
        else:
             sl_price = last_struct_price * 0.95 # Fallback 5%
        
        # TP = Next swing high (if above current?). For now, simplified 1.5R projection
        risk = abs(last_struct_price - sl_price)
        tp1 = last_struct_price + risk
        tp2 = last_struct_price + (risk * 2)
        tp_targets = [round(tp1, 2), round(tp2, 2)]

    elif action == "SHORT_BIAS":
        # SL = Above last swing high (search backwards for a 'H' type)
        swing_high = next((s for s in reversed(ltf_struct) if 'H' in s['type']), None)
        if swing_high:
             sl_price = swing_high['price'] + buffer
        else:
             sl_price = last_struct_price * 1.05 # Fallback 5%
             
        # TP
        risk = abs(sl_price - last_struct_price)
        tp1 = last_struct_price - risk
        tp2 = last_struct_price - (risk * 2)
        tp_targets = [round(tp1, 2), round(tp2, 2)]
        
    return {
        "STOP_LOSS": round(sl_price, 2),
        "TAKE_PROFIT": tp_targets,
        "BUFFER_USED": round(buffer, 2)
    }

def main():
    parser = argparse.ArgumentParser(description='Generate Final Report.')
    parser.add_argument('--structure', type=str, required=True, help='JSON file from confluence engine')
    parser.add_argument('--history', type=str, required=True, help='JSON file from historical engine')
    parser.add_argument('--news', type=str, required=True, help='JSON file from news engine')
    args = parser.parse_args()
    
    try:
        # Load Inputs
        with open(args.structure, 'r') as f: str_data = json.load(f)
        with open(args.history, 'r') as f: hist_data = json.load(f)
        with open(args.news, 'r') as f: news_data = json.load(f)
        
        score, action, reasons = calculate_score(str_data, hist_data, news_data)
        
        # Calculate Risk
        risk_advisory = calculate_risk_levels(action, str_data)
        
        report = {
            "TIMESTAMP": str(datetime.now()),
            "FINAL_SIGNAL": action,
            "CONFIDENCE_SCORE": score,
            "RISK_LEVEL": news_data.get("risk_level", "UNKNOWN"),
            "RISK_ADVISORY": risk_advisory,
            "REASONING": reasons,
            "INPUT_SUMMARY": {
                "structure": str_data.get("final_signal"),
                "history": hist_data.get("historical_bias"),
                "news_sentiment": news_data.get("sentiment_score")
            }
        }
        
        print(json.dumps(report, indent=2))
        
    except Exception as e:
        print(json.dumps({"error": str(e)}))
        sys.exit(1)

if __name__ == "__main__":
    main()
