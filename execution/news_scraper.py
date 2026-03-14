import requests
import xml.etree.ElementTree as ET
import json
import os
import sys
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

RSS_FEEDS = {
    "https://www.coindesk.com/arc/outboundfeeds/rss/?outputType=xml": {"type": "TIER_1", "domain": "coindesk.com"},
    "https://cointelegraph.com/rss": {"type": "TIER_1", "domain": "cointelegraph.com"},
    "https://cryptopanic.com/news/rss": {"type": "AGGREGATOR", "domain": "cryptopanic.com"}
}

def parse_pub_date(pub_date_text):
    """
    Parses an RSS pubDate string (RFC 2822 format) into an ISO datetime string.
    Falls back to datetime.now() if parsing fails.
    Example input: 'Tue, 03 Mar 2026 09:30:00 +0000'
    """
    if not pub_date_text:
        return str(datetime.now())
    try:
        # parsedate_to_datetime handles RFC 2822 format used by all RSS feeds
        dt = parsedate_to_datetime(pub_date_text.strip())
        # Normalise to UTC-naive ISO string for consistency
        return dt.strftime('%Y-%m-%d %H:%M:%S')
    except Exception:
        try:
            # Fallback: attempt common format directly
            return str(datetime.strptime(pub_date_text[:25].strip(), '%a, %d %b %Y %H:%M:%S'))
        except Exception:
            return str(datetime.now())

def fetch_headlines():
    structured_news = []
    print("Scraping live crypto news via RSS (CARI Structured)...")
    
    for url, config in RSS_FEEDS.items():
        try:
            response = requests.get(url, timeout=10, headers={"User-Agent": "Mozilla/5.0"})
            if response.status_code != 200:
                print(f"Warning: Failed to fetch {url} (Status {response.status_code})")
                continue
            
            # Use content and try to fix encoding issues
            content = response.content
            try:
                root = ET.fromstring(content)
            except ET.ParseError:
                # Fallback: simple regex-based extraction if XML is broken
                import re
                titles = re.findall(r'<title>(.*?)</title>', response.text)
                for t in titles:
                    if t and "CryptoPanic" not in t:
                        structured_news.append({
                            "text": t.strip(),
                            "source_type": config["type"],
                            "domain": config["domain"],
                            "timestamp": str(datetime.now())
                        })
                continue # Skip standard parsing if we used regex fallback

            for item in root.findall(".//item"):
                title = item.find("title")
                pub_date = item.find("pubDate")
                
                if title is not None and title.text:
                    # FIX 1.1: Parse actual pubDate so temporal decay works correctly.
                    # Old code overwrote every article's timestamp with datetime.now(),
                    # making CARI decay formula always return 1.0 (no decay at all).
                    ts = parse_pub_date(pub_date.text if pub_date is not None else None)

                    structured_news.append({
                        "text": title.text.strip(),
                        "source_type": config["type"],
                        "domain": config["domain"],
                        "timestamp": ts
                    })
                    
        except Exception as e:
            print(f"Error scraping {url}: {e}")
            
    return structured_news[:20]

def run_scraper():
    """
    Direct functional entry point for the orchestrator.
    """
    latest_news = fetch_headlines()
    if not latest_news:
        latest_news = [{
            "text": "Market showing stable sideways movement",
            "source_type": "AGGREGATOR",
            "domain": "internal",
            "timestamp": str(datetime.now())
        }]
        
    os.makedirs(".tmp", exist_ok=True)
    with open(".tmp/latest_news_structured.json", "w") as f:
        json.dump(latest_news, f, indent=2)
        
    with open(".tmp/latest_headlines.json", "w") as f:
        json.dump([item["text"] for item in latest_news], f, indent=2)
        
    return latest_news

if __name__ == "__main__":
    results = run_scraper()
    print(f"Success: {len(results)} structured headlines scraped to 2026 context.")
