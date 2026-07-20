import os
import requests
import time
import logging

# ===========================
# CONFIGURATION
# ===========================

BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)

print("✅ NSE AI BOT STARTED")


# ===========================
# TELEGRAM FUNCTION
# ===========================

def send_telegram(message):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"

    data = {
        "chat_id": CHAT_ID,
        "text": message
    }

    try:
        requests.post(url, data=data, timeout=20)
        print("✅ Telegram Message Sent")
    except Exception as e:
        print(e)


# ===========================
# MAIN LOOP
# ===========================

if __name__ == "__main__":

    send_telegram("🚀 NSE AI BOT Started Successfully")

    while True:
        print("Bot Running...")
        time.sleep(60)
