"""Gửi cảnh báo ảnh lên Telegram (chạy nền – không block main loop)."""

import threading
import requests
from config import TG_TOKEN, TG_CHAT_ID

_URL = f"https://api.telegram.org/bot{TG_TOKEN}/sendPhoto"


def _send(photo_path: str, caption: str):
    try:
        with open(photo_path, "rb") as f:
            resp = requests.post(_URL, files={"photo": f},
                                 data={"chat_id": TG_CHAT_ID, "caption": caption},
                                 timeout=10)
        if resp.status_code != 200:
            print(f"[Telegram] Lỗi {resp.status_code}: {resp.text}")
    except Exception as e:
        print(f"[Telegram] Gửi thất bại: {e}")


def send_alert(photo_path: str, caption: str = "🚨 Cảnh báo vi phạm an toàn!"):
    """Gửi ảnh cảnh báo Telegram trong thread riêng (non-blocking)."""
    threading.Thread(target=_send, args=(photo_path, caption), daemon=True).start()
