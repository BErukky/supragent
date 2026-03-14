import sys
import os
import json
from datetime import datetime, timezone

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from main import run_full_analysis, TF_STACKS
from nlp_engine import generate_nlp_summary

def rank_stacks_with_ai(results, symbol):
    """
    Uses Groq LLM to rank multiple stack analyses and pick the best 1-3 setups.
    """
    from groq import Groq
    
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        # Fallback to simple scoring
        return simple_rank_stacks(results)
    
    # Build compact summary for LLM
    summary = f"Analyzed {len(results)} timeframe stacks for {symbol}:\n\n"
    for i, r in enumerate(results, 1):
        rep = r['report']
        summary += f"{i}. {r['stack'].upper()}: {rep.get('FINAL_SIGNAL', 'N/A')} "
        summary += f"({rep.get('CONFIDENCE', 0)}% conf)\n"
        if rep.get('RISK_ADVISORY'):
            risk = rep['RISK_ADVISORY']
            summary += f"   R:R: {risk.get('RR_RATIO', 'N/A')}:1 | "
            summary += f"Risk: {risk.get('RISK_PIPS', 0)} pips | "
            summary += f"Reward: {risk.get('REWARD_PIPS', [0])[0]} pips\n"
    
    prompt = (
        f"{summary}\n"
        "Rank these setups by quality (1-3 best). Consider:\n"
        "- Confidence level\n"
        "- Signal clarity (not WAIT)\n"
        "- R:R ratio\n"
        "- Pip values\n\n"
        "Return ONLY a JSON array of stack names in order, e.g. [\"intraday\", \"swing\"]"
    )
    
    try:
        client = Groq(api_key=api_key)
        completion = client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1,
            max_tokens=100
        )
        
        response = completion.choices[0].message.content.strip()
        # Extract JSON array
        import re
        match = re.search(r'\[.*?\]', response)
        if match:
            ranked = json.loads(match.group())
            return [r for r in results if r['stack'] in ranked][:3]
    except:
        pass
    
    return simple_rank_stacks(results)

def simple_rank_stacks(results):
    """
    Fallback ranking without AI - scores based on confidence and signal quality.
    """
    scored = []
    for r in results:
        rep = r['report']
        score = 0
        
        # Confidence weight
        conf = rep.get('CONFIDENCE', 0)
        score += conf
        
        # Signal clarity bonus
        signal = rep.get('FINAL_SIGNAL', '')
        if 'WAIT' not in signal and 'LOCKED' not in signal:
            score += 20
        
        # R:R bonus
        risk = rep.get('RISK_ADVISORY')
        if risk:
            rr = risk.get('RR_RATIO', 0)
            if rr >= 3.0:
                score += 15
            elif rr >= 2.0:
                score += 10
        
        scored.append({'stack': r['stack'], 'report': rep, 'score': score})
    
    scored.sort(key=lambda x: x['score'], reverse=True)
    return scored[:3]

def run_multi_stack_analysis(symbol, use_nlp=False, no_news=False):
    """
    Runs analysis on all 6 timeframe stacks and returns the best 1-3 setups.
    """
    print(f"\n{'='*60}")
    print(f"MULTI-STACK ANALYSIS: {symbol}")
    print(f"Analyzing {len(TF_STACKS)} timeframe combinations...")
    print(f"{'='*60}\n")
    
    results = []
    news_cache = None  # Share news across stacks
    
    for i, stack_name in enumerate(TF_STACKS.keys(), 1):
        print(f"[{i}/{len(TF_STACKS)}] Running {stack_name.upper()} stack...")
        try:
            report = run_full_analysis(
                symbol, 
                stack_name=stack_name, 
                no_news=no_news,
                use_nlp=False  # Skip NLP per-stack, do it at the end
            )
            if report and 'error' not in report:
                results.append({'stack': stack_name, 'report': report})
        except Exception as e:
            print(f"  Error: {e}")
    
    if not results:
        return {"error": "All stacks failed"}
    
    # Rank with AI
    print(f"\nRanking setups with AI...")
    top_stacks = rank_stacks_with_ai(results, symbol)
    
    # Generate AI summary if requested
    if use_nlp and top_stacks:
        best = top_stacks[0]['report']
        best['NLP_SUMMARY'] = generate_nlp_summary(best, symbol)
    
    return {
        "symbol": symbol,
        "total_analyzed": len(results),
        "top_setups": top_stacks,
        "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    }

if __name__ == "__main__":
    import argparse
    import pandas as pd
    
    parser = argparse.ArgumentParser(description='Multi-Stack Analyzer')
    parser.add_argument('--symbol', type=str, default='BTC/USD')
    parser.add_argument('--nlp', action='store_true')
    parser.add_argument('--no_news', action='store_true')
    args = parser.parse_args()
    
    result = run_multi_stack_analysis(args.symbol, args.nlp, args.no_news)
    
    if 'error' in result:
        print(f"Error: {result['error']}")
        sys.exit(1)
    
    # Display results
    print(f"\n{'='*60}")
    print(f"TOP {len(result['top_setups'])} SETUPS FOR {result['symbol']}")
    print(f"{'='*60}\n")
    
    for i, setup in enumerate(result['top_setups'], 1):
        rep = setup['report']
        risk = rep.get('RISK_ADVISORY', {})
        
        medal = ["#1", "#2", "#3"][i-1] if i <= 3 else f"#{i}"
        print(f"{medal} {setup['stack'].upper()}")
        print(f"   Signal: {rep.get('FINAL_SIGNAL')} ({rep.get('CONFIDENCE')}% confidence)")
        
        if risk:
            print(f"   Entry: {risk.get('ENTRY_TYPE')} @ {risk.get('ENTRY_PRICE')}")
            print(f"   Stop Loss: {risk.get('STOP_LOSS')} ({risk.get('RISK_PIPS', 0)} pips)")
            print(f"   Take Profit: {risk.get('TAKE_PROFIT', [])[0]} ({risk.get('REWARD_PIPS', [0])[0]} pips)")
            print(f"   R:R: {risk.get('RR_RATIO', 'N/A')}:1")
        print()
    
    if result['top_setups'] and result['top_setups'][0]['report'].get('NLP_SUMMARY'):
        print(f"{'='*60}")
        print("AI ANALYSIS:")
        print(result['top_setups'][0]['report']['NLP_SUMMARY'])
        print(f"{'='*60}\n")
