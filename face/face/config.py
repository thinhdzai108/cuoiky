import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# ── Model ────────────────────────────────────────────────
PERSON_MODEL_PATH = os.path.join(BASE_DIR, "yolov8.pt")
MASK_MODEL_PATH   = os.path.join(BASE_DIR, "YOLOv8m_FMD.pt")

# ── Camera ───────────────────────────────────────────────
CAMERA_SOURCE = 0

# ── Thư mục ──────────────────────────────────────────────
OUTPUT_DIR  = os.path.join(BASE_DIR, "alerts")
UI_DIR  = os.path.join(BASE_DIR, "UI")

# ── Vi phạm ──────────────────────────────────────────────
CONFIRM_FRAMES      = 5     # frame liên tiếp để xác nhận vi phạm
DISTANCE_THRESHOLD  = 120   # pixel khoảng cách chân < ngưỡng → vi phạm
MASK_COOLDOWN       = 30    # giây cooldown cảnh báo khẩu trang
DIST_COOLDOWN       = 20    # giây cooldown cảnh báo khoảng cách

# ── Telegram ─────────────────────────────────────────────
TELEGRAM_TOKEN   = ""
TELEGRAM_CHAT_ID = ""

# ── Màu BGR cho OpenCV ───────────────────────────────────
COLOR = {
    "mask":     (  0, 210,   0),   # Xanh lá tươi – đeo khẩu trang
    "no_mask":  (  0,   0, 220),   # Đỏ           – không đeo / vi phạm
    "distance": (  0,   0, 200),   # Đỏ đậm       – vi phạm khoảng cách
    "unknown":  (120, 120, 120),   # Xám           – chưa xác định
}

# ── Quy đổi pixel → mét (tuỳ camera, điều chỉnh cho phù hợp) ──────────────
PIXELS_PER_METER = 150   # 150 px ≈ 1 mét (chỉnh theo góc camera thực tế)
