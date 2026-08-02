import os
import sys
import time
import traceback

root = os.path.abspath(os.path.dirname(__file__))
sys.path.insert(0, root)
sys.path.insert(0, os.path.join(root, 'execution'))

import telegram_listener
import market_scanner

# Patch message functions to print and avoid sending Telegram messages during local reproduction.
telegram_listener.send_message = lambda chat_id, text, reply_markup=None: print(f'[TELEGRAM] {text}')
market_scanner.send_telegram_alert = lambda message: print(f'[ALERT] {message}')

print('=== Running /scalp BTC/USD simulation ===')
try:
    telegram_listener._handle_scalp(123456, ['BTC/USD'])
    # Give the background thread some time to complete.
    time.sleep(30)
except Exception:
    traceback.print_exc()

print('\n=== Running /scan simulation ===')
try:
    market_scanner.main()
except Exception:
    traceback.print_exc()
