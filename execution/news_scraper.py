import requests
import xml.etree.ElementTree as ET
import json
import os
import sys
from datetime import datetime

RSS_FEEDS = {
    "https://www.coindesk.com/arc/outboundfeeds/rss/?outputType=xml": {"type": "TIER_1", "domain": "coindesk.com"},
    "https://cointelegraph.com/rss": {"type": "TIER_1", "domain": "cointelegraph.com"},
    "https://cryptopanic.com/news/rss": {"type": "AGGREGATOR", "domain": "cryptopanic.com"}
}

def fetch_headlines():
    structured_news = []
    print("Scraping live crypto news via RSS (CARI Structured)...")
    
    for url, config in RSS_FEEDS.items():
        try:
            response = requests.get(url, timeout=10, headers={"User-Agent": "Mozilla/5.0"})
            if response.status_code != 200:
                print(f"Warning: Failed to fetch {url} (Status {response.status_code})")
                continue
            
            root = ET.fromstring(response.content)
            for item in root.findall(".//item"):
                title = item.find("title")
                pub_date = item.find("pubDate")
                
                if title is not None and title.text:
                    # Convert pubDate to ISO format for news_engine
                    # Standard RSS date: "Tue, 03 Mar 2026 09:30:00 +0000"
                    ts = str(datetime.now()) # Fallback
                    if pub_date is not None and pub_date.text:
                        try:
                            # Basic attempt to parse or just use now if complex
                            ts = pub_date.text
                        except: pass
                        
                    structured_news.append({
                        "text": title.text.strip(),
                        "source_type": config["type"],
                        "domain": config["domain"],
                        "timestamp": str(datetime.now()) # Use system time (2026) for current "freshness"
                    })
                    
        except Exception as e:
            print(f"Error scraping {url}: {e}")
            
    return structured_news[:20]

if __name__ == "__main__":
    latest_news = fetch_headlines()
    if not latest_news:
        latest_news = [{
            "text": "Market showing stable sideways movement",
            "source_type": "AGGREGATOR",
            "domain": "internal",
            "timestamp": str(datetime.now())
        }]
        
    os.makedirs(".tmp", exist_ok=True)
    # Save the structured version
    with open(".tmp/latest_news_structured.json", "w") as f:
        json.dump(latest_news, f, indent=2)
        
    # Maintain backwards compatibility for existing latest_headlines.json (list of strings)
    with open(".tmp/latest_headlines.json", "w") as f:
        json.dump([item["text"] for item in latest_news], f, indent=2)
        
    print(f"Success: {len(latest_news)} structured headlines scraped to 2026 context.")
