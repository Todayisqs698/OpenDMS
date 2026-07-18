"""摄像头引擎 — 采集 + HUD + 状态推送"""
import time, logging, threading, cv2, numpy as np

logger = logging.getLogger(__name__)

_running = False
_thread = None
_frame = None
_state = {}
_show_landmarks = True
_lock = threading.Lock()


def set_landmarks(show: bool):
    global _show_landmarks
    _show_landmarks = show


def _loop(ws_manager):
    global _frame, _state

    from modules.vision.face_tracker import FaceTracker
    from modules.ai.local_decision_engine import decide_locally

    ft = FaceTracker()

    cap = cv2.VideoCapture(0)
    if not cap.isOpened():
        logger.error("摄像头不可用")
        return

    logger.info("摄像头引擎启动")
    last_gaze, gaze_start = "center", time.time()
    back_to_center_at = 0
    fps_times = []

    # ── 疲劳追踪 ──
    from collections import deque
    ear_history = deque(maxlen=60)     # 最近60帧EAR
    blink_history = deque(maxlen=60)   # 最近60帧眨眼计数增量
    last_blink_total = ft.blink_count
    fatigue_score = 0
    fatigue_level = "normal"
    perclos_val = 0.0

    while _running:
        ret, img = cap.read()
        if not ret:
            time.sleep(0.01); continue
        img = cv2.flip(img, 1)
        h, w = img.shape[:2]
        now = time.time()

        # 面部追踪
        ft.refresh(img)
        face_ok = ft.is_face_detected()
        gaze = ft.gaze_state if face_ok else "lost"
        blink = ft.is_blinking() if face_ok else False

        # ── 疲劳指标计算（每帧更新）──
        if face_ok:
            ear_history.append(ft.ear)
            blink_now = ft.blink_count
            blink_delta = max(0, blink_now - last_blink_total)
            blink_history.append(blink_delta)
            last_blink_total = blink_now
            # PERCLOS：60帧中闭眼占比
            closed_frames = sum(1 for e in ear_history if e < ft.ear_threshold * ft.BLINK_RATIO)
            perclos_val = round(closed_frames / max(len(ear_history), 1), 3)
            # 眨眼频率（次/分钟）
            blink_total = sum(blink_history)
            blink_rate_val = round(blink_total * 60.0 / max(len(blink_history), 1), 1)
            # 疲劳评分（简化版）
            if perclos_val > 0.15:
                fatigue_score = min(100, int(40 + (perclos_val - 0.15) / 0.1 * 60))
                fatigue_level = "danger"
            elif perclos_val > 0.08:
                fatigue_score = min(100, int(20 + (perclos_val - 0.08) / 0.07 * 20))
                fatigue_level = "warning"
            else:
                fatigue_score = max(0, int(perclos_val / 0.08 * 20))
                fatigue_level = "normal"
        else:
            ear_history.append(0.3)
            blink_history.append(0)

        # 计时稳定：回正需持续1秒才清零，避免抖动重置
        if gaze != last_gaze:
            gaze_start = now
            last_gaze = gaze
        if gaze == "center":
            back_to_center_at = 0 if gaze != last_gaze else (back_to_center_at or now)
            if now - back_to_center_at < 1.0:
                dur = 0  # 还不够1秒，保持之前的状态
            else:
                dur = 0
        else:
            back_to_center_at = 0
            dur = now - gaze_start

        # AI 决策
        result = decide_locally({
            "trigger": "gaze",
            "data": {"state": gaze, "duration": dur,
                     "gesture": "", "confidence": 0.0, "text": ""}
        })

        # ── 面部关键点（眼睛+鼻子，可开关）──
        if _show_landmarks and face_ok and ft.face_landmarks:
            lm = ft.face_landmarks
            for idx in [33, 133, 362, 263]:
                px, py = int(lm[idx].x * w), int(lm[idx].y * h)
                cv2.circle(img, (px, py), 3, (0, 255, 0), -1)
            px, py = int(lm[1].x * w), int(lm[1].y * h)
            cv2.circle(img, (px, py), 4, (0, 255, 255), -1)
            for idx in [468, 473]:
                px, py = int(lm[idx].x * w), int(lm[idx].y * h)
                cv2.circle(img, (px, py), 2, (255, 0, 255), -1)

        # HUD
        cv2.rectangle(img, (0, 0), (w, 60), (0, 0, 0), -1)
        cv2.putText(img, f"Gaze: {gaze}", (10, 25), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (200, 200, 200), 2)
        cv2.putText(img, f"Action: {result.get('action_code','normal')}", (10, 50), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 255), 1)
        if blink:
            cv2.putText(img, "BLINK", (w // 2, 50), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 2)

        # 告警条
        if result.get("alert"):
            cv2.rectangle(img, (0, h - 60), (w, h), (0, 0, 0), -1)
            cv2.putText(img, result["alert"], (20, h - 25), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)
            if int(now * 4) % 2:
                cv2.rectangle(img, (3, 3), (w - 3, h - 3), (0, 0, 255), 3)

        # FPS
        fps_times.append(now)
        if len(fps_times) > 30: fps_times.pop(0)
        fps = len(fps_times) / (fps_times[-1] - fps_times[0]) if len(fps_times) > 1 else 0
        cv2.putText(img, f"FPS:{fps:.0f}", (w - 80, 50), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (150, 150, 150), 1)

        # 存状态
        with _lock:
            _, jpg = cv2.imencode('.jpg', img, [cv2.IMWRITE_JPEG_QUALITY, 70])
            _frame = jpg.tobytes()
            blink_rate_val = round(sum(blink_history) * 60.0 / max(len(blink_history), 1), 1)
            _state = {
                "gaze": gaze, "gesture": "",
                "gesture_hint": "",
                "confidence": round(result.get("confidence", 0.8), 2),
                "action_code": result.get("action_code", "normal"),
                "alert": result.get("alert", ""), "severity": result.get("severity", "normal"),
                "duration": round(dur, 1),
                "perclos": perclos_val,
                "blink_rate": blink_rate_val,
                "fatigue_score": fatigue_score,
                "fatigue_level": fatigue_level,
            }

    cap.release()


def start(ws):
    global _running, _thread
    if _running: return
    _running = True
    _thread = threading.Thread(target=_loop, args=(ws,), daemon=True)
    _thread.start()


def stop():
    global _running
    _running = False


def get_frame():
    with _lock:
        return _frame


def get_state():
    with _lock:
        return dict(_state) if _state else None
