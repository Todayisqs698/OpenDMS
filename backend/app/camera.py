"""摄像头引擎 — 采集 + HUD + 5类独立告警 + 状态推送 + 语音管线"""
import time, logging, threading, cv2, numpy as np

logger = logging.getLogger(__name__)

_running = False
_thread = None
_frame = None
_state = {}
_show_landmarks = True
_lock = threading.Lock()
_audio_pipeline = None  # 音频管线实例


def set_landmarks(show: bool):
    global _show_landmarks
    _show_landmarks = show


def pause_audio():
    """TTS 播报前暂停音频采集，防止啸叫"""
    if _audio_pipeline:
        _audio_pipeline.pause()


def resume_audio():
    """TTS 播报后恢复音频采集"""
    if _audio_pipeline:
        _audio_pipeline.resume()


def _loop(ws_manager):
    global _frame, _state, _audio_pipeline

    from modules.vision.face_tracker import FaceTracker
    from modules.ai.local_decision_engine import decide_locally, check_crowd, check_absence, check_fatigue, check_head_deviation, check_gaze_deviation

    ft = FaceTracker()

    # Gesture detector (geometric classifier, zero model deps)
    gesture_detector = None
    try:
        from modules.vision.hand_gesture import HandGestureDetector
        gesture_detector = HandGestureDetector()
        logger.info(f"Gesture detector ready: {len(gesture_detector.available)} gestures")
    except Exception as e:
        logger.warning(f"Gesture not loaded: {e}")

    # 音频管线（独立线程，不阻塞视觉）
    audio = None
    try:
        from modules.audio.audio_pipeline import AudioPipeline
        audio = AudioPipeline()
        audio.start()
        global _audio_pipeline
        _audio_pipeline = audio
        logger.info("音频管线已启动")
    except Exception as e:
        logger.warning(f"音频管线未加载: {e}")

    cap = cv2.VideoCapture(0)
    if not cap.isOpened():
        logger.error("摄像头不可用")
        return

    logger.info("摄像头引擎启动")
    fps_times = []
    frame_idx = 0  # 帧计数器，用于降频手势检测
    gesture_name = ""      # 保留上一次手势结果
    gesture_action = None

    # ── 5 类告警独立计时器 ──
    # 每类告警各自追踪：上次状态、偏离开始时间、回正时间
    timers = {
        "crowd":    {"last": "normal",  "start": time.time(), "back_at": 0},
        "absence":  {"last": "normal",  "start": time.time(), "back_at": 0},
        "fatigue":  {"last": "normal",  "start": time.time(), "back_at": 0},
        "head":     {"last": "center",  "start": time.time(), "back_at": 0},
        "gaze":     {"last": "center",  "start": time.time(), "back_at": 0},
    }

    def _get_duration(key: str, active: bool, now: float) -> float:
        """通用计时器：活动时累加，回正需持续 1s 才清零（防抖）"""
        t = timers[key]
        if active:
            if t["last"] != "active":
                t["start"] = now
                t["last"] = "active"
            t["back_at"] = 0
            return now - t["start"]
        else:
            if t["last"] == "active":
                t["back_at"] = now
                t["last"] = "normal"
            if t["back_at"] and now - t["back_at"] < 1.0:
                # 回正不足 1 秒，返回之前的持续时间
                return now - t["start"] if t["start"] else 0
            else:
                return 0

    # ── 疲劳追踪 ──
    from collections import deque
    ear_history = deque(maxlen=60)
    blink_history = deque(maxlen=60)
    last_blink_total = ft.blink_count
    fatigue_score = 0
    fatigue_level = "normal"
    perclos_val = 0.0
    fatigue_active = False

    # ── 多人检测计数器 ──
    crowd_face_count = 0
    # 用 face_landmarks 的检测结果：每次 refresh 可能检测到多张脸
    # 当前 FaceTracker 只取第一张脸，所以用 face_ok 判断是否存在人脸
    # 多人检测需要扩展 FaceTracker 支持 num_faces > 1
    # 暂用简单方案：检测到无人脸 = absence，多人暂标记为 0

    while _running:
        ret, img = cap.read()
        if not ret:
            time.sleep(0.01); continue
        img = cv2.flip(img, 1)
        h, w = img.shape[:2]
        now = time.time()
        frame_idx += 1

        # ── BGR→RGB 只转换一次，面部和手势模块共用 ──
        rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)

        # 面部追踪
        ft.refresh(img, rgb=rgb)
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
            closed_frames = sum(1 for e in ear_history if e < ft.ear_threshold * ft.BLINK_RATIO)
            perclos_val = round(closed_frames / max(len(ear_history), 1), 3)
            blink_rate_val = round(sum(blink_history) * 60.0 / max(len(blink_history), 1), 1)
            if perclos_val > 0.15:
                fatigue_score = min(100, int(40 + (perclos_val - 0.15) / 0.1 * 60))
                fatigue_level = "danger"
            elif perclos_val > 0.08:
                fatigue_score = min(100, int(20 + (perclos_val - 0.08) / 0.07 * 20))
                fatigue_level = "warning"
            else:
                fatigue_score = max(0, int(perclos_val / 0.08 * 20))
                fatigue_level = "normal"
            fatigue_active = fatigue_level in ("warning", "danger")
        else:
            ear_history.append(0.3)
            blink_history.append(0)
            blink_rate_val = 0
            fatigue_active = False

        # ── 5 类独立计时 ──
        crowd_dur = _get_duration("crowd", crowd_face_count >= 2, now)
        absence_dur = _get_duration("absence", not face_ok, now)
        fatigue_dur = _get_duration("fatigue", fatigue_active, now)
        head_dur = _get_duration("head", face_ok and gaze != "center" and gaze != "lost", now)
        gaze_dur = _get_duration("gaze", face_ok and gaze != "center" and gaze != "lost", now)

        # ── 5 类独立决策（优先级：crowd > absence > fatigue > head > gaze）──
        result = check_crowd(crowd_dur, crowd_face_count)
        if result.get("action_code") == "normal":
            result = check_absence(absence_dur)
        if result.get("action_code") == "normal":
            result = check_fatigue(fatigue_dur)
        if result.get("action_code") == "normal":
            result = check_head_deviation(gaze if face_ok else "center", head_dur)
        if result.get("action_code") == "normal":
            result = check_gaze_deviation(gaze if face_ok else "center", gaze_dur)

        # 手势仍然独立检测，每 3 帧跑一次（大幅降低开销）
        if gesture_detector and frame_idx % 3 == 0:
            gname, gaction, gconf = gesture_detector.process(img, rgb=rgb)
            if gname:
                gesture_name = gname
            else:
                gesture_name = ""
            if gaction:
                gesture_action = gaction
                logger.info(f"Gesture triggered: {gname} -> {gaction['action_code']}")
            else:
                gesture_action = None
        # 跳过的帧保持上一次的手势结果（gesture_name/gesture_action 已在循环外初始化）

        # ── 语音识别结果（异步，由音频管线独立线程产出）──
        speech_text = ""
        if audio:
            result = audio.get_result()
            if result:
                speech_text = result["text"]
                logger.info(f"语音识别: {speech_text}")

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

        # HUD — 顶部状态栏
        cv2.rectangle(img, (0, 0), (w, 80), (0, 0, 0), -1)
        cv2.putText(img, f"Gaze: {gaze}", (10, 22), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (200, 200, 200), 2)
        cv2.putText(img, f"Action: {result.get('action_code','normal')}", (10, 45), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 255, 255), 1)
        alert_cat = result.get("alert_category", "")
        alert_label = result.get("alert_label", "")
        if alert_cat:
            cv2.putText(img, f"Alert: {alert_label}", (10, 68), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 0, 255), 1)

        if blink:
            cv2.putText(img, "BLINK", (w // 2, 45), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 2)
        if gesture_name:
            cv2.putText(img, f"Gesture: {gesture_name}", (w // 2, 22), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
        if gesture_action:
            cv2.putText(img, f"{gesture_action['icon']} {gesture_action['label']}", (10, h - 70), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)

        # 告警条
        if result.get("alert"):
            cv2.rectangle(img, (0, h - 60), (w, h), (0, 0, 0), -1)
            alert_text = result["alert"]
            # 截断过长文字
            if len(alert_text) > 40:
                alert_text = alert_text[:40] + "..."
            cv2.putText(img, alert_text, (20, h - 25), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)
            if int(now * 4) % 2:
                cv2.rectangle(img, (3, 3), (w - 3, h - 3), (0, 0, 255), 3)

        # FPS
        fps_times.append(now)
        if len(fps_times) > 30: fps_times.pop(0)
        fps = len(fps_times) / (fps_times[-1] - fps_times[0]) if len(fps_times) > 1 else 0
        cv2.putText(img, f"FPS:{fps:.0f}", (w - 80, 45), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (150, 150, 150), 1)

        # 存状态
        with _lock:
            _, jpg = cv2.imencode('.jpg', img, [cv2.IMWRITE_JPEG_QUALITY, 70])
            _frame = jpg.tobytes()
            _state = {
                "gaze": gaze, "gesture": gesture_name,
                "gesture_hint": gesture_action["label"] if gesture_action else "",
                "gesture_action": gesture_action["action_code"] if gesture_action else "",
                "confidence": round(result.get("confidence", 0.8), 2),
                "action_code": result.get("action_code", "normal"),
                "alert": result.get("alert", ""),
                "severity": result.get("severity", "normal"),
                "alert_category": result.get("alert_category", ""),
                "alert_label": result.get("alert_label", ""),
                "duration": round(max(
                    crowd_dur, absence_dur, fatigue_dur, head_dur, gaze_dur
                ), 1),
                "perclos": perclos_val,
                "blink_rate": blink_rate_val,
                "fatigue_score": fatigue_score,
                "fatigue_level": fatigue_level,
                # 各类独立持续时间
                "dur_crowd": round(crowd_dur, 1),
                "dur_absence": round(absence_dur, 1),
                "dur_fatigue": round(fatigue_dur, 1),
                "dur_head": round(head_dur, 1),
                "dur_gaze": round(gaze_dur, 1),
                "speech": speech_text,
            }

    if audio:
        audio.stop()
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
