"""
FaceSafe Monitor — main.py
PHÁT HIỆN HÀNH VI KHÔNG ĐEO KHẨU TRANG HOẶC VI PHẠM KHOẢNG CÁCH
Ứng dụng Deep Learning (YOLOv8) để giám sát tuân thủ quy định an toàn.

Architecture:
  Python: detect → render label lên frame → stream MJPEG
  Web   : hiển thị video stream + alert log (UI only)
"""
import os, time, json, asyncio, threading
import cv2 as cv
import numpy as np
from PIL import ImageFont, ImageDraw, Image
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from ultralytics import YOLO

import router
import telegram_utils
from config import (
    CAMERA_SOURCE, PERSON_MODEL_PATH, MASK_MODEL_PATH,
    OUTPUT_DIR, UI_DIR,
    CONFIRM_FRAMES, DISTANCE_THRESHOLD, MASK_COOLDOWN, DIST_COOLDOWN,
    TELEGRAM_TOKEN, TELEGRAM_CHAT_ID, COLOR, PIXELS_PER_METER,
)

os.makedirs(OUTPUT_DIR, exist_ok=True)


# ── App ────────────────────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    print("\n" + "=" * 50)
    print("  FaceSafe Monitor  ->  http://localhost:8001")
    print("=" * 50 + "\n")
    yield

app = FastAPI(title="FaceSafe", lifespan=lifespan)
app.mount("/ui", StaticFiles(directory=UI_DIR), name="ui")
app.mount("/alerts", StaticFiles(directory=OUTPUT_DIR),  name="alerts")
app.include_router(router.router)


# ── YOLO models ────────────────────────────────────────────────────────────
person_model = YOLO(PERSON_MODEL_PATH)
mask_model   = YOLO(MASK_MODEL_PATH)
model_lock   = threading.Lock()
PERSON_CLS   = [k for k, v in person_model.names.items() if v == "person"] or [0]


# ── PIL Font (tiếng Việt) ──────────────────────────────────────────────────
_FONT_PATH = r"C:\Windows\Fonts\arial.ttf"
try:
    _FONT_LBL  = ImageFont.truetype(_FONT_PATH, 16)  # label trên box
    _FONT_DIST = ImageFont.truetype(_FONT_PATH, 14)  # label khoảng cách
except Exception:
    _FONT_LBL  = ImageFont.load_default()
    _FONT_DIST = ImageFont.load_default()


# ── Shared state ───────────────────────────────────────────────────────────
state: dict = {
    "confirm_frames":   CONFIRM_FRAMES,
    "dist_threshold":   DISTANCE_THRESHOLD,
    "mask_cooldown":    MASK_COOLDOWN,
    "dist_cooldown":    DIST_COOLDOWN,
    "telegram_token":   TELEGRAM_TOKEN,
    "telegram_chat_id": TELEGRAM_CHAT_ID,
    "mask_streaks":    {},    # tid → int
    "dist_streaks":    {},    # tid → int
    "mask_last_alert": {},    # tid → float   (per-person cooldown)
    "dist_last_alert": {},    # tid → float
    "mask_global_ts":  0.0,   # float  (global cooldown – chống spam khi tracker đổi ID)
    "dist_global_ts":  0.0,   # float
}

if os.path.exists(router.SETTINGS_FILE):
    try:
        with open(router.SETTINGS_FILE, "r", encoding="utf-8") as f:
            cfg = json.load(f)
            for k in ("confirm_frames", "dist_threshold", "mask_cooldown",
                      "dist_cooldown", "telegram_token", "telegram_chat_id"):
                if k in cfg:
                    state[k] = cfg[k]
    except Exception as e:
        print("Loi doc settings.json:", e)

sse_clients: list[asyncio.Queue] = []


# ── SSE push ─────────────────────────────────────────────────────
def _emit(data: dict):
    """Push SSE event từ bất kỳ thread nào."""
    payload = json.dumps(data, ensure_ascii=False)
    for q in list(sse_clients):
        try:   q.put_nowait(payload)
        except: pass


# ── Alert dispatch ─────────────────────────────────────────────────────────
def dispatch_alert(img_path: str, track_id: int, vtype: str):
    """Gửi cảnh báo qua Telegram + SSE alert log."""
    ts       = time.localtime()
    date_str = time.strftime("%d/%m/%Y", ts)
    time_str = time.strftime("%H:%M:%S", ts)
    label    = "Không đeo khẩu trang" if vtype == "no_mask" else "Vi phạm khoảng cách"

    def _run():
        telegram_utils.send_formatted_violation_alert(
            img_path, state["telegram_token"], state["telegram_chat_id"],
            track_id, vtype,
        )
        _emit({
            "type":    "alert",
            "id":      track_id,
            "time":    f"{date_str} {time_str}",
            "msg":     label,
            "vtype":   vtype,
            "img_url": f"/alerts/{os.path.basename(img_path)}",
        })

    threading.Thread(target=_run, daemon=True).start()


# ── Status dispatch ────────────────────────────────────────────────────────
def dispatch_status(count: int, mask_v: int, dist_v: int):
    """Cập nhật số liệu realtime cho dashboard."""
    _emit({"type": "status", "count": count, "mask_v": mask_v, "dist_v": dist_v})


# ── Helpers ────────────────────────────────────────────────────────────────
def _foot(bbox) -> tuple:
    x1, y1, x2, y2 = bbox
    return (x1 + x2) // 2, y2


def _iou_head(px1, py1, px2, py2, mx1, my1, mx2, my2) -> float:
    """Tỉ lệ mask-box nằm trong vùng đầu người (top 50% bbox)."""
    head_y2 = py1 + int((py2 - py1) * 0.5)
    ix1 = max(px1, mx1); iy1 = max(py1, my1)
    ix2 = min(px2, mx2); iy2 = min(head_y2, my2)
    if ix2 <= ix1 or iy2 <= iy1:
        return 0.0
    return ((ix2 - ix1) * (iy2 - iy1)) / max((mx2 - mx1) * (my2 - my1), 1)


def _match_mask(person_bbox, mask_boxes: list, mask_cls_names: list) -> str:
    """
    Ghép mask detection vào vùng đầu người.
    Trả về: 'mask' | 'no_mask' | 'unknown'
    """
    _lmap    = {"mask": "mask", "no-mask": "no_mask", "no_mask": "no_mask"}
    best     = "unknown"
    best_iou = 0.25     # overlap tối thiểu 25%
    px1, py1, px2, py2 = person_bbox
    for (mx1, my1, mx2, my2), cls_name in zip(mask_boxes, mask_cls_names):
        iou = _iou_head(px1, py1, px2, py2, mx1, my1, mx2, my2)
        if iou > best_iou:
            best_iou = iou
            best     = _lmap.get(str(cls_name), "unknown")
    return best


# ── Render toàn bộ frame (PIL — 1 lần convert/frame) ──────────────────────
def _bgr2rgb(c) -> tuple:
    return (c[2], c[1], c[0])


def _render_frame(frame_bgr: np.ndarray,
                  persons: list,
                  mask_statuses: dict,
                  dist_viol: set,
                  dist_pairs: list):
    """
    Python vẽ TẤT CẢ annotations:
      - Bounding box màu (OpenCV, nhanh)
      - Đường kết nối cặp vi phạm KC (OpenCV)
      - Label tiếng Việt trên đầu box, nền fill màu (PIL, 1 lần)
      - Label khoảng cách X.Xm tại midpoint cặp vi phạm (PIL)
    """
    # ── 1. OpenCV: box + line (không cần font) ────────────────────────────
    for bbox, tid in persons:
        x1, y1, x2, y2 = bbox
        ms    = mask_statuses.get(tid, "unknown")
        is_nv = ms == "no_mask" or tid in dist_viol
        c     = COLOR["no_mask"] if is_nv else (
                    COLOR["mask"] if ms == "mask" else COLOR["unknown"])
        cv.rectangle(frame_bgr, (x1, y1), (x2, y2), c, 2)

    for ba, bb, _ in dist_pairs:
        cv.line(frame_bgr, _foot(ba), _foot(bb), COLOR["distance"], 2)

    # ── 2. PIL: tất cả text labels (1 lần convert) ───────────────────────
    pil  = Image.fromarray(cv.cvtColor(frame_bgr, cv.COLOR_BGR2RGB))
    draw = ImageDraw.Draw(pil)

    # Label trên từng người
    for bbox, tid in persons:
        x1, y1, x2, y2 = bbox
        ms    = mask_statuses.get(tid, "unknown")
        is_nv = ms == "no_mask" or tid in dist_viol

        # Chọn màu + text
        if ms == "no_mask":
            text  = "Không Đeo Khẩu Trang - Vi Phạm"
            color = COLOR["no_mask"]
        elif ms == "mask" and tid in dist_viol:
            text  = "Đeo Khẩu Trang - Vi Phạm KC"
            color = COLOR["no_mask"]
        elif ms == "mask":
            text  = "Đeo Khẩu Trang"
            color = COLOR["mask"]
        else:
            text  = "Đang nhận diện..."
            color = COLOR["unknown"]

        rgb = _bgr2rgb(color)

        # Đo kích thước text để vẽ background
        tb  = draw.textbbox((0, 0), text, font=_FONT_LBL)
        tw, th = tb[2] - tb[0], tb[3] - tb[1]

        # Vị trí: label nằm sát phía trên đỉnh box
        lx = x1
        ly = max(0, y1 - th - 4)

        draw.rectangle((lx, ly, lx + tw + 6, ly + th + 4), fill=rgb)
        draw.text((lx + 3, ly + 2), text, font=_FONT_LBL, fill=(255, 255, 255))

    # Label khoảng cách tại midpoint giữa 2 người vi phạm
    for ba, bb, dist_px in dist_pairs:
        fa = _foot(ba)
        fb = _foot(bb)
        mx = (fa[0] + fb[0]) // 2
        my = (fa[1] + fb[1]) // 2

        dist_m = dist_px / PIXELS_PER_METER
        line1  = f"{dist_m:.1f}m - Vi Phạm"
        line2  = "Khoảng Cách"

        tb1 = draw.textbbox((0, 0), line1, font=_FONT_DIST)
        tb2 = draw.textbbox((0, 0), line2, font=_FONT_DIST)
        bw  = max(tb1[2] - tb1[0], tb2[2] - tb2[0]) + 10
        bh  = (tb1[3] - tb1[1]) + (tb2[3] - tb2[1]) + 10

        draw.rectangle((mx - 3, my - 3, mx + bw, my + bh),
                        fill=_bgr2rgb(COLOR["distance"]))
        draw.text((mx + 2, my + 1),      line1, font=_FONT_DIST, fill=(255, 255, 255))
        draw.text((mx + 2, my + bh//2),  line2, font=_FONT_DIST, fill=(255, 255, 255))

    # Convert ngược về BGR (1 lần duy nhất)
    frame_bgr[:] = cv.cvtColor(np.array(pil), cv.COLOR_RGB2BGR)


# ── Video generator ────────────────────────────────────────────────────────
FRAME_W, FRAME_H = 640, 480

def video_generator():
    cap = cv.VideoCapture(CAMERA_SOURCE, cv.CAP_DSHOW)
    if not cap.isOpened():
        print(f"[ERROR] Khong mo duoc camera {CAMERA_SOURCE}")
        return
    cap.set(cv.CAP_PROP_FRAME_WIDTH,  FRAME_W)
    cap.set(cv.CAP_PROP_FRAME_HEIGHT, FRAME_H)
    cap.set(cv.CAP_PROP_FPS, 30)
    target_delay = 1.0 / 25   # giới hạn 25fps để giảm tải PIL

    while True:
        t0 = time.time()
        ok, frame = cap.read()
        if not ok:
            time.sleep(0.05)
            continue

        disp = frame.copy()
        now  = time.time()

        # ── Detect & Track ────────────────────────────────────────────────
        with model_lock:
            p_res = person_model.track(
                frame, persist=True, verbose=False,
                classes=PERSON_CLS, tracker="bytetrack.yaml",
            )
            m_res = mask_model(frame, verbose=False)

        active_ids:    list[int] = []
        persons:       list      = []
        dist_viol:     set[int]  = set()
        dist_pairs:    list      = []   # [(bbox_a, bbox_b, dist_px)]
        mask_statuses: dict      = {}
        mask_v_count   = 0
        dist_v_count   = 0

        if p_res[0].boxes is not None and p_res[0].boxes.id is not None:
            boxes      = p_res[0].boxes.xyxy.cpu().numpy()
            ids        = p_res[0].boxes.id.int().cpu().tolist()
            active_ids = ids

            # Parse mask detections một lần ngoài loop
            mask_boxes_list, mask_cls_list = [], []
            if m_res[0].boxes is not None:
                for mb in m_res[0].boxes:
                    mask_boxes_list.append(tuple(map(int, mb.xyxy[0])))
                    mask_cls_list.append(m_res[0].names[int(mb.cls[0])])

            # Thu thập persons + ghép mask status
            for box, tid in zip(boxes, ids):
                bbox = tuple(map(int, box))
                persons.append((bbox, tid))
                mask_statuses[tid] = _match_mask(bbox, mask_boxes_list, mask_cls_list)

            # Tính khoảng cách giữa các cặp (dựa vào foot point)
            for i in range(len(persons)):
                for j in range(i + 1, len(persons)):
                    ba, ia = persons[i]
                    bb, ib = persons[j]
                    d = float(np.linalg.norm(
                        np.array(_foot(ba)) - np.array(_foot(bb))
                    ))
                    if d < state["dist_threshold"]:
                        dist_viol.update([ia, ib])
                        dist_pairs.append((ba, bb, d))

            # ── Logic vi phạm & cảnh báo ──────────────────────────────────
            for bbox, tid in persons:
                ms = mask_statuses[tid]

                # 1. Khẩu trang
                if ms == "no_mask":
                    state["mask_streaks"][tid] = state["mask_streaks"].get(tid, 0) + 1
                    mask_v_count += 1
                else:
                    state["mask_streaks"][tid] = 0

                # Fire khi: streak đủ + per-tid cooldown + global cooldown
                # Global cooldown chặn spam khi tracker đổi ID cho cùng 1 người
                if (state["mask_streaks"].get(tid, 0) >= state["confirm_frames"]
                        and now - state["mask_last_alert"].get(tid, 0) >= state["mask_cooldown"]
                        and now - state["mask_global_ts"]               >= state["mask_cooldown"]):
                    state["mask_last_alert"][tid] = now
                    state["mask_global_ts"]        = now
                    path = os.path.join(OUTPUT_DIR, f"mask_{tid}_{int(now)}.jpg")
                    cv.imwrite(path, frame)
                    print(f"[{time.strftime('%H:%M:%S')}] KHAU TRANG  ID={tid}")
                    dispatch_alert(path, tid, "no_mask")

                # 2. Khoảng cách
                if tid in dist_viol:
                    state["dist_streaks"][tid] = state["dist_streaks"].get(tid, 0) + 1
                    dist_v_count += 1
                else:
                    state["dist_streaks"][tid] = 0

                if (state["dist_streaks"].get(tid, 0) >= state["confirm_frames"]
                        and now - state["dist_last_alert"].get(tid, 0) >= state["dist_cooldown"]
                        and now - state["dist_global_ts"]               >= state["dist_cooldown"]):
                    state["dist_last_alert"][tid] = now
                    state["dist_global_ts"]        = now
                    path = os.path.join(OUTPUT_DIR, f"dist_{tid}_{int(now)}.jpg")
                    cv.imwrite(path, frame)
                    print(f"[{time.strftime('%H:%M:%S')}] KHOANG CACH  ID={tid}")
                    dispatch_alert(path, tid, "distance")


            # ── Python vẽ tất cả lên frame (1 lần PIL convert) ───────────
            _render_frame(disp, persons, mask_statuses, dist_viol, dist_pairs)

        # ── Dọn track IDs đã mất ─────────────────────────────────────────
        for tid in (set(state["mask_streaks"]) - set(active_ids)):
            state["mask_streaks"].pop(tid, None)
            state["mask_last_alert"].pop(tid, None)
            state["dist_streaks"].pop(tid, None)
            state["dist_last_alert"].pop(tid, None)

        # ── Encode & stream ───────────────────────────────────────────────
        _, buf = cv.imencode(".jpg", disp, [cv.IMWRITE_JPEG_QUALITY, 85])
        yield b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + buf.tobytes() + b"\r\n"

        dispatch_status(len(active_ids), mask_v_count, dist_v_count)

        elapsed = time.time() - t0
        time.sleep(max(0.0, target_delay - elapsed))


# ── Entry point ────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)
