import sys
import os

def print_setup_guide():
    print("\n" + "="*50)
    print("🤖 SUPER SIGNALS: INTERACTIVE BOT SETUP")
    print("="*50)
    print("\nTo enable the buttons and commands in your Telegram App:")
    print("\n1. Open Telegram and go to @BotFather")
    print("2. Type command: /mybots")
    print("3. Select your bot.")
    print("4. Click 'Edit Bot' -> 'Edit Commands'.")
    print("5. Paste the following list:\n")
    print("-" * 30)
    print("scan - Run a full market scan (Top 10 Assets)")
    print("analyze - Analyze a specific coin (Usage: /analyze BTC/USD)")
    print("help - Show available commands")
    print("-" * 30)
    print("\n6. Done! Your bot now has a menu.")
    print("\n" + "="*50)
    print("🚀 NEXT STEP: START THE LISTENER")
    print("Run this command to keep the bot online:")
    print("python execution/telegram_listener.py")
    print("="*50 + "\n")

if __name__ == "__main__":
    print_setup_guide()
