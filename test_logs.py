import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from app import app
from bot_controller import manager

with app.app_context():
    bot = manager.get_bot(1)
    if bot:
        for log in bot.logs[-20:]:
            print(f"[{log['time']}] {log['message']}")
    else:
        print("Bot 1 not running in memory.")
