import os
import requests
from datetime import datetime

class NotificationManager:
    def __init__(self):
        self.tg_token = os.getenv("TELEGRAM_BOT_TOKEN")
        self.tg_chat_id = os.getenv("TELEGRAM_CHAT_ID")

    def notify(self, title: str, message: str):
        """
        Send a notification via Console and Telegram.
        """
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        formatted_msg = f"[{timestamp}] 🔔 {title}\n{message}\n" + "-"*30
        
        # 1. Console Log
        print(formatted_msg)
        
        # 2. Telegram Notification
        if self.tg_token and self.tg_chat_id:
            try:
                # Telegram message format
                tg_text = f"🔔 *{title}*\n\n{message}"
                url = f"https://api.telegram.org/bot{self.tg_token}/sendMessage"
                payload = {
                    "chat_id": self.tg_chat_id,
                    "text": tg_text,
                    "parse_mode": "Markdown"
                }
                response = requests.post(url, json=payload, timeout=5)
                if response.status_code != 200:
                    print(f"Failed to send Telegram: {response.text}")
            except Exception as e:
                print(f"Error sending Telegram notification: {e}")
