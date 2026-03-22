import os
import sys
from dotenv import load_dotenv, find_dotenv

# Add execution to path
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'execution'))
sys.path.append(os.path.dirname(__file__))

try:
    from nlp_engine import generate_nlp_summary
    print("[OK] Imported nlp_engine")
except ImportError as e:
    print(f"[FAIL] Failed to import nlp_engine: {e}")
    sys.exit(1)

def verify():
    print(f"Searching for .env via find_dotenv: {find_dotenv()}")
    load_dotenv(find_dotenv())
    
    keys_to_check = ["GROQ_API_KEY", "GROQ_AI_KEY", "GROQAPIKEY"]
    found_any = False
    for k in keys_to_check:
        val = os.environ.get(k)
        if val:
            print(f"[OK] Found {k}: {val[:6]}...{val[-4:]}")
            found_any = True
        else:
            print(f"[INFO] {k} not set")
            
    if not found_any:
        print("[FAIL] No Groq API keys found in environment!")
        
    mock_report = {
        "SYMBOL": "BTC/USD",
        "FINAL_SIGNAL": "LONG / BUY",
        "CONFIDENCE": 85,
        "REASONING": {
            "l2_confluence": "HTF(BULLISH) 4H(BULLISH) LTF(BULLISH). (+15pts)",
            "l3_history": "History is BULLISH (+10pts)",
            "l4_news": "Sentiment is positive (+5pts)"
        },
        "GOVERNANCE_ALERTS": [],
        "RISK_ADVISORY": {
            "ENTRY_TYPE": "MARKET",
            "ENTRY_PRICE": 70000.0,
            "STOP_LOSS": 69000.0,
            "TAKE_PROFIT": [73000.0],
            "RR_RATIO": 3.0
        }
    }
    
    print("\nAttempting to generate NLP summary...")
    summary = generate_nlp_summary(mock_report, "BTC/USD")
    print(f"Result: {summary}")
    
    if "NLP Engine Offline" in summary:
        print("[FAIL] Verification FAILED: NLP Engine reports offline.")
    elif "NLP Generation Failed" in summary:
        print("[WARN] Verification PARTIAL: Key found but API call failed (check internet/credits).")
    else:
        print("[OK] Verification SUCCESS: NLP Engine returned a summary.")

if __name__ == "__main__":
    verify()
