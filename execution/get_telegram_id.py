import requests
import sys
import time

def get_chat_id(token):
    url = f"https://api.telegram.org/bot{token}/getUpdates"
    print(f"Checking for messages on bot...")
    
    try:
        response = requests.get(url)
        data = response.json()
        
        if not data.get("ok"):
            print(f"Error: {data.get('description')}")
            return

        updates = data.get("result", [])
        if not updates:
            print("No new messages found. Please send a message (e.g., 'Hello') to your bot in Telegram and try again.")
            return

        # Get the chat ID from the most recent message
        chat = updates[-1]["message"]["chat"]
        chat_id = chat["id"]
        chat_type = chat["type"]
        username = chat.get("username", "Unknown")
        
        print("\n" + "="*40)
        print(f"SUCCESS! Found Chat ID.")
        print("="*40)
        print(f"Chat Type: {chat_type}")
        print(f"Username: {username}")
        print(f"CHAT ID:   {chat_id}")
        print("="*40)
        print("\nCopy this Chat ID for the configuration.")
        
    except Exception as e:
        print(f"Connection Error: {e}")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python execution/get_telegram_id.py <YOUR_BOT_TOKEN>")
        sys.exit(1)
    
    token = sys.argv[1]
    get_chat_id(token)
