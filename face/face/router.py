import os, time, json, asyncio
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, StreamingResponse
from pydantic import BaseModel
from config import UI_DIR

router = APIRouter()

SETTINGS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "settings.json")


# ── Helpers ────────────────────────────────────────────────────────────────
def _save_settings(data: dict):
    try:
        with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4)
    except Exception as e:
        print("Lỗi lưu settings:", e)


# ── Pydantic models ────────────────────────────────────────────────────────
class ConfigBody(BaseModel):
    confirm_frames:   int
    dist_threshold:   int
    mask_cooldown:    int
    dist_cooldown:    int
    telegram_token:   str
    telegram_chat_id: str


# ── HTML ───────────────────────────────────────────────────────────────────
@router.get("/", response_class=HTMLResponse)
async def get_index():
    path = os.path.join(UI_DIR, "index.html")
    return HTMLResponse(open(path, encoding="utf-8").read())


# ── Stream ─────────────────────────────────────────────────────────────────
@router.get("/api/stream")
async def video_stream():
    import main
    return StreamingResponse(
        main.video_generator(),
        media_type="multipart/x-mixed-replace; boundary=frame",
    )


# ── SSE Alerts ─────────────────────────────────────────────────────────────
@router.get("/api/alerts")
async def sse_alerts(request: Request):
    import main

    async def generator():
        q = asyncio.Queue()
        main.sse_clients.append(q)
        try:
            while not await request.is_disconnected():
                yield f"data: {await q.get()}\n\n"
        finally:
            if q in main.sse_clients:
                main.sse_clients.remove(q)

    return StreamingResponse(generator(), media_type="text/event-stream")


# ── History ────────────────────────────────────────────────────────────────
@router.get("/api/history")
async def get_history():
    import main
    records = []
    if not os.path.exists(main.OUTPUT_DIR):
        return {"status": "ok", "data": []}

    for fname in os.listdir(main.OUTPUT_DIR):
        if not fname.endswith(".jpg"):
            continue
        if not (fname.startswith("mask_") or fname.startswith("dist_")):
            continue
        try:
            # fname: mask_{tid}_{ts}.jpg hoặc dist_{tid}_{ts}.jpg
            parts = fname.replace(".jpg", "").split("_")
            vtype = parts[0]          # mask | dist
            tid = int(parts[1])
            ts  = int(parts[2])
            dt  = time.localtime(ts)
            records.append({
                "id":       fname,
                "track_id": tid,
                "timestamp": ts,
                "date":     time.strftime("%Y-%m-%d", dt),
                "time":     time.strftime("%H:%M:%S", dt),
                "vtype":    "no_mask" if vtype == "mask" else "distance",
                "img_url":  f"/alerts/{fname}",
            })
        except Exception:
            continue

    records.sort(key=lambda r: r["timestamp"], reverse=True)
    return {"status": "ok", "data": records}


# ── Config ─────────────────────────────────────────────────────────────────
@router.get("/api/config")
async def get_config():
    import main
    return {
        "status":           "ok",
        "confirm_frames":   main.state.get("confirm_frames",   5),
        "dist_threshold":   main.state.get("dist_threshold",   120),
        "mask_cooldown":    main.state.get("mask_cooldown",    30),
        "dist_cooldown":    main.state.get("dist_cooldown",    20),
        "telegram_token":   main.state.get("telegram_token",   ""),
        "telegram_chat_id": main.state.get("telegram_chat_id", ""),
    }


@router.post("/api/config")
async def set_config(body: ConfigBody):
    import main
    main.state["confirm_frames"]   = max(1, body.confirm_frames)
    main.state["dist_threshold"]   = max(10, body.dist_threshold)
    main.state["mask_cooldown"]    = max(1, body.mask_cooldown)
    main.state["dist_cooldown"]    = max(1, body.dist_cooldown)
    main.state["telegram_token"]   = body.telegram_token.strip()
    main.state["telegram_chat_id"] = body.telegram_chat_id.strip()

    _save_settings({
        "confirm_frames":   main.state["confirm_frames"],
        "dist_threshold":   main.state["dist_threshold"],
        "mask_cooldown":    main.state["mask_cooldown"],
        "dist_cooldown":    main.state["dist_cooldown"],
        "telegram_token":   main.state["telegram_token"],
        "telegram_chat_id": main.state["telegram_chat_id"],
    })
    return {"status": "ok"}


# ── Test Telegram ──────────────────────────────────────────────────────────
@router.post("/api/test-telegram")
async def test_telegram():
    import main, telegram_utils
    token   = main.state.get("telegram_token", "").strip()
    chat_id = main.state.get("telegram_chat_id", "").strip()
    if not token or not chat_id:
        return {"status": "error", "message": "Chưa cấu hình Token hoặc Chat ID"}
    try:
        msg = "🔔 FaceSafe Monitor: Kết nối Telegram thành công! ✅"
        await asyncio.to_thread(telegram_utils.send_telegram_text, token, chat_id, msg)
        return {"status": "ok"}
    except Exception as e:
        return {"status": "error", "message": str(e)}
