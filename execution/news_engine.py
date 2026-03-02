import argparse
import json
import sys

# Simple internal database of keywords with historical reaction scores
# Score = Emotional Sentiment | Penalty = System Risk Overlay
KEYWORDS = {
    "CRITICAL_RISK": {
        "hack": {"score": -20, "penalty": 100},
        "insolvent": {"score": -20, "penalty": 100},
        "bankruptcy": {"score": -20, "penalty": 100},
        "sec lawsuit": {"score": -10, "penalty": 60},
        "crypto ban": {"score": -15, "penalty": 100},
        "trading halt": {"score": -10, "penalty": 80},
        "exploit": {"score": -15, "penalty": 90}
    },
    "NEGATIVE": {
        "inflation": {"score": -5, "penalty": 20},
        "rate hike": {"score": -5, "penalty": 30},
        "market dump": {"score": -5, "penalty": 30},
        "liquidation": {"score": -4, "penalty": 25},
        "bearish": {"score": -3, "penalty": 10}
    },
    "POSITIVE": {
        "etf approval": {"score": 15, "penalty": 0},
        "partnership": {"score": 5, "penalty": 0},
        "adoption": {"score": 5, "penalty": 0},
        "bullish": {"score": 5, "penalty": 0},
        "all time high": {"score": 8, "penalty": 0},
        "breakout": {"score": 5, "penalty": 0}
    }
}

def analyze_news_v2(headlines):
    total_sentiment = 0
    total_penalty = 0
    flagged = []
    
    queries = [h.lower() for h in headlines]
    
    for headline in queries:
        for category, words in KEYWORDS.items():
            for word, config in words.items():
                if word in headline:
                    total_sentiment += config['score']
                    total_penalty += config['penalty']
                    flagged.append(word)
                    
    # Clamp penalty
    total_penalty = min(100, total_penalty)
    
    # Determine Risk Level
    risk_level = "LOW"
    if total_penalty >= 80: risk_level = "CRITICAL"
    elif total_penalty >= 40: risk_level = "HIGH"
    elif total_penalty >= 20: risk_level = "MEDIUM"
    
    # Layer 4 score starts at 10 (Neutral) and moves by sentiment
    # Governance will use 'penalty' to subtract from total confidence
    l4_score = round(max(0, min(10, 5 + (total_sentiment / 2.0))), 2)

    return {
        "risk_level": risk_level,
        "sentiment_score": round(float(total_sentiment), 2),
        "risk_penalty": int(total_penalty),
        "permits_trade": total_penalty < 80,
        "layer4_score": l4_score,
        "flagged_keywords": list(set(flagged)),
        "reasoning": f"Sentiment: {total_sentiment}. Risk Penalty: {total_penalty}. Level: {risk_level}"
    }

def main():
    parser = argparse.ArgumentParser(description='Analyze News Risk v2.')
    parser.add_argument('--input', type=str, help='Path to JSON file with headlines list')
    parser.add_argument('--text', type=str, nargs='+', help='Direct headline input')
    args = parser.parse_args()
    
    headlines = []
    try:
        if args.input:
            with open(args.input, 'r') as f:
                data = json.load(f)
                headlines = data if isinstance(data, list) else data.get("headlines", [])
        if args.text: headlines.extend(args.text)
        if not headlines:
            print(json.dumps({"error": "No headlines provided"}))
            sys.exit(1)
            
        result = analyze_news_v2(headlines)
        print(json.dumps(result, indent=2))
    except Exception as e:
        print(json.dumps({"error": str(e)}))
        sys.exit(1)

if __name__ == "__main__":
    main()
