import argparse
import json
import sys

# Simple internal database of keywords
# In production, load this from a config file
KEYWORDS = {
    "CRITICAL_RISK": {
        "hack": -10,
        "insolvent": -10,
        "bankruptcy": -10,
        "sec lawsuit": -8,
        "ban": -8
    },
    "NEGATIVE": {
        "inflation": -3,
        "rate hike": -3,
        "dump": -2,
        "fear": -2,
        "liquidation": -2
    },
    "POSITIVE": {
        "etf approval": 8,
        "partnership": 4,
        "adoption": 3,
        "bullish": 2,
        "all time high": 3
    }
}

def analyze_sentiment(headlines):
    """
    Analyzes a list of headlines against the keyword database.
    """
    total_score = 0
    flagged = []
    trade_permitted = True
    
    queries = [h.lower() for h in headlines]
    
    for headline in queries:
        # Check Critical
        for word, score in KEYWORDS["CRITICAL_RISK"].items():
            if word in headline:
                total_score += score
                flagged.append(word)
                trade_permitted = False
                
        # Check Negative
        for word, score in KEYWORDS["NEGATIVE"].items():
            if word in headline:
                total_score += score
                
        # Check Positive
        for word, score in KEYWORDS["POSITIVE"].items():
            if word in headline:
                total_score += score

    # Determine Risk Level based on Score
    risk_level = "LOW"
    if not trade_permitted:
        risk_level = "CRITICAL"
    elif total_score < -5:
        risk_level = "HIGH"
    elif total_score < 0:
        risk_level = "MEDIUM"
        
    return {
        "risk_level": risk_level,
        "sentiment_score": total_score,
        "permits_trade": trade_permitted,
        "flagged_keywords": list(set(flagged))
    }

def main():
    parser = argparse.ArgumentParser(description='Analyze News Risk.')
    parser.add_argument('--input', type=str, help='Path to JSON file with headlines list')
    # Or allow direct text input for testing
    parser.add_argument('--text', type=str, nargs='+', help='Direct headline input')
    
    args = parser.parse_args()
    
    headlines = []
    
    try:
        if args.input:
            with open(args.input, 'r') as f:
                data = json.load(f)
                headlines = data if isinstance(data, list) else data.get("headlines", [])
        
        if args.text:
            headlines.extend(args.text)
            
        if not headlines:
            print(json.dumps({"error": "No headlines provided"}))
            sys.exit(1)
            
        result = analyze_sentiment(headlines)
        print(json.dumps(result, indent=2))
        
    except Exception as e:
        print(json.dumps({"error": str(e)}))
        sys.exit(1)

if __name__ == "__main__":
    main()
