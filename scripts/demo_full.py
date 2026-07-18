"""
EdgeGuard 实时驾驶监控 — 摄像头持续运行，自动告警
运行: python demo_full.py
按 Q 退出
"""
import sys, time, cv2
sys.path.insert(0, ".")

from modules.vision.face_tracker import FaceTracker
from modules.ai.local_decision_engine import decide_locally

tracker = FaceTracker()
cap = cv2.VideoCapture(0)
if not cap.isOpened():
    print("摄像头不可用")
    exit(1)

print("EdgeGuard 实时监控运行中... 按 Q 退出")
print("试试: 往左看/往右看/闭眼/低头")

last_gaze = "center"
gaze_start = time.time()
alert_text = ""
alert_color = (0, 255, 0)
fps_times = []

while True:
    ret, frame = cap.read()
    if not ret:
        continue

    frame = cv2.flip(frame, 1)  # 镜像
    h, w = frame.shape[:2]
    tracker.refresh(frame)

    # 视线追踪
    gaze = tracker.gaze_state
    now = time.time()
    if gaze != last_gaze:
        gaze_start = now
        last_gaze = gaze
    gaze_dur = now - gaze_start if gaze != "center" else 0

    # AI 决策
    result = decide_locally({
        "trigger": "gaze",
        "data": {"state": gaze, "duration": gaze_dur}
    })

    action = result.get("action_code", "normal")
    alert = result.get("alert", "")
    blinking = tracker.is_blinking()
    face = tracker.is_face_detected()

    # 告警状态
    if not face:
        alert_text = "未检测到面部"
        alert_color = (0, 165, 255)  # 橙
    elif action == "distract":
        alert_text = f"分心! {alert} (已{gaze_dur:.0f}秒)"
        alert_color = (0, 0, 255)  # 红
    elif action == "attention_hint":
        alert_text = f"注意: {alert}"
        alert_color = (0, 200, 255)  # 黄
    elif blinking:
        alert_text = f"检测到闭眼 (第{tracker.blink_count}次)"
        alert_color = (0, 255, 255)  # 青
    else:
        alert_text = "正常"
        alert_color = (0, 255, 0)  # 绿

    # FPS
    fps_times.append(time.time())
    if len(fps_times) > 30:
        fps_times.pop(0)
    fps = len(fps_times) / (fps_times[-1] - fps_times[0]) if len(fps_times) > 1 else 0

    # 绘制 HUD
    # 顶栏
    cv2.rectangle(frame, (0, 0), (w, 60), (0, 0, 0), -1)
    cv2.putText(frame, f"EdgeGuard", (10, 25),
                cv2.FONT_HERSHEY_SIMPLEX, 0.7, (200, 200, 200), 2)
    cv2.putText(frame, f"FPS: {fps:.0f}", (w - 100, 25),
                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (150, 150, 150), 1)

    # 状态信息
    cv2.putText(frame, f"视线: {gaze} ({gaze_dur:.1f}s)", (10, 55),
                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (200, 200, 200), 1)
    ear_val = tracker.ear
    ear_color = (0, 0, 255) if blinking else (200, 200, 200)
    if tracker._ear_baseline is None:
        calib_progress = min(len(tracker._baseline_samples), tracker.CALIBRATION_FRAMES)
        ear_text = f"校准中 {calib_progress}/{tracker.CALIBRATION_FRAMES} EAR: {ear_val:.3f}"
    else:
        ear_text = f"眨眼: {tracker.blink_count}  EAR: {ear_val:.3f} 阈值: {tracker.ear_threshold:.3f}"
    cv2.putText(frame, ear_text, (w // 2 - 100, 55),
                cv2.FONT_HERSHEY_SIMPLEX, 0.5, ear_color, 1)

    # 告警条（底部）
    alert_y = h - 50
    cv2.rectangle(frame, (0, h - 80), (w, h), (0, 0, 0), -1)
    cv2.putText(frame, alert_text, (20, h - 30),
                cv2.FONT_HERSHEY_SIMPLEX, 1.0, alert_color, 3)

    # 告警闪烁（红色边框）
    if action == "distract":
        flash = int(time.time() * 3) % 2
        if flash:
            cv2.rectangle(frame, (5, 5), (w - 5, h - 5), (0, 0, 255), 5)

    cv2.imshow("EdgeGuard", frame)

    key = cv2.waitKey(1) & 0xFF
    if key == ord('q'):
        break

cap.release()
cv2.destroyAllWindows()
print("EdgeGuard 已退出")
