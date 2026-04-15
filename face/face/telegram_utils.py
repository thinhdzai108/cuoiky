import os, time
import requests


def send_alert_photo(photo_path: str, token: str, chat_id: str, caption: str) -> bool:
    """Gửi ảnh bằng chứng qua Telegram."""
    if not token or not chat_id or not os.path.exists(photo_path):
        return False
    url = f"https://api.telegram.org/bot{token}/sendPhoto"
    try:
        with open(photo_path, "rb") as f:
            r = requests.post(url, files={"photo": f},
                              data={"chat_id": chat_id, "caption": caption}, timeout=15)
            r.raise_for_status()
        return True
    except Exception as e:
        print(f"❌ Telegram photo error: {e}")
        return False


def send_telegram_text(token: str, chat_id: str, text: str) -> bool:
    """Gửi tin nhắn văn bản qua Telegram."""
    if not token or not chat_id:
        return False
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    try:
        r = requests.post(url, data={"chat_id": chat_id, "text": text}, timeout=10)
        r.raise_for_status()
        return True
    except Exception as e:
        print(f"❌ Telegram text error: {e}")
        return False


def send_formatted_violation_alert(photo_path: str, token: str, chat_id: str,
                                   track_id: int, vtype: str) -> bool:
    """Gửi cảnh báo vi phạm có định dạng đẹp (mask / distance)."""
    t = time.strftime("%H:%M:%S %d/%m/%Y")
    if vtype == "no_mask":
        title   = "😷 CẢNH BÁO: KHÔNG ĐEO KHẨU TRANG"
        detail  = "Đối tượng không đeo khẩu trang đúng cách"
    else:
        title   = "📏 CẢNH BÁO: VI PHẠM KHOẢNG CÁCH"
        detail  = "Khoảng cách xã hội không đảm bảo"

    caption = (
        f"{title}\n"
        + "─" * 28 + "\n"
        f"👤 Track ID : #{track_id}\n"
        f"⚠️  Loại    : {detail}\n"
        f"⏱  Thời gian: {t}\n"
        f"📍 Hệ thống : FaceSafe Monitor"
    )
    return send_alert_photo(photo_path, token, chat_id, caption)
