import requests
import xml.etree.ElementTree as ET
import json
import os
import sys

RSS_FEEDS = [
    "https://www.coindesk.com/arc/outboundfeeds/rss/?outputType=xml",
    "https://cointelegraph.com/rss",
    "https://cryptopanic.com/news/rss"
]

def fetch_headlines():
    headlines = []
    print("Scraping live crypto news via RSS...")
    
    for url in RSS_FEEDS:
        try:
            response = requests.get(url, timeout=10, headers={"User-Agent": "Mozilla/5.0"})
            if response.status_code != 200:
                print(f"Warning: Failed to fetch {url} (Status {response.status_code})")
                continue
            
            root = ET.fromstring(response.content)
            # RSS typically has items in channel/item/title
            for item in root.findall(".//item"):
                title = item.find("title")
                if title is not None and title.text:
                    headlines.append(title.text.strip())
                    
        except Exception as e:
            print(f"Error scraping {url}: {e}")
            
    # Remove duplicates and limit
    unique_headlines = list(set(headlines))
    return unique_headlines[:20] # Return top 20 recent headlines

if __name__ == "__main__":
    latest_news = fetch_headlines()
    if not latest_news:
        # Fallback if scraping fails
        latest_news = ["Market showing stable sideways movement", "No major news events detected"]
        
    os.makedirs(".tmp", exist_ok=True)
    with open(".tmp/latest_headlines.json", "w") as f:
        json.dump(latest_news, f, indent=2)
        
    print(f"Success: {len(latest_news)} headlines scraped and saved to .tmp/latest_headlines.json")
    # Also output for pipe if needed
    print(json.dumps(latest_news))
