"""
自动演示脚本 — 无人操作，自动跑完全部场景并录屏
运行: python demo_auto.py
"""
import sys, time, cv2
sys.path.insert(0, ".")

from modules.vision.face_tracker import FaceTracker
from modules.ai.local_decision_engine import decide_locally
from modules.ai.edge_cloud_router import get_router
from modules.ai.langgraph_orchestrator import Orchestrator
from modules.ai.deepseek_client import MultimodalInput

tracker = FaceTracker()
router = get_router()
orchestrator = Orchestrator()
cap = cv2.VideoCapture(0)
if not cap.isOpened():
    print("摄像头不可用")
    exit(1)

print("=" * 60)
print("  EdgeGuard 自动演示 — 全部场景一键跑完")
print("=" * 60)

scenarios = [
    {"name": "正常驾驶", "speech": "", "desc": "视线在前，无异常"},
    {"name": "语音开空调", "speech": "打开空调", "desc": "语音指令 → TurnOnAC"},
    {"name": "视线偏离(左)", "speech": "", "desc": "往左看3秒 → attention_hint"},
    {"name": "语音导航", "speech": "导航去公司", "desc": "语音指令 → Navigate"},
    {"name": "分心+语音冲突", "speech": "播放音乐", "desc": "视线偏离+语音 → 安全优先"},
    {"name": "恢复正常", "speech": "我在看路", "desc": "确认恢复 → normal"},
]

h, w = 480, 640
writer = None
SAVE_VIDEO = False  # 需要录屏时改成 True

for i, scenario in enumerate(scenarios):
    print(f"\n[{i+1}/{len(scenarios)}] {scenario['name']}: {scenario['desc']}")

    # 拍 10 帧，模拟持续状态
    for _ in range(10):
        ret, frame = cap.read()
        if not ret:
            continue
        frame = cv2.flip(frame, 1)

        tracker.refresh(frame)
        gaze = tracker.gaze_state
        blinking = tracker.is_blinking()
        head = tracker.head_pose()

        # AI 决策
        result = decide_locally({
            "trigger": "speech" if scenario["speech"] else "gaze",
            "data": {
                "state": gaze, "duration": 3.0 if gaze != "center" else 0,
                "gesture": "", "confidence": 0, "text": scenario["speech"]
            }
        })

        # HUD
        cv2.rectangle(frame, (0, 0), (w, 80), (0, 0, 0), -1)
        cv2.putText(frame, f"[{i+1}/{len(scenarios)}] {scenario['name']}",
                    (10, 25), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
        cv2.putText(frame, f"语音: {scenario['speech'] or '无'}",
                    (10, 50), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (200, 200, 200), 1)
        cv2.putText(frame, f"视线: {gaze} | 动作: {result.get('action_code')}",
                    (10, 70), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 1)

        # 告警
        if result.get("alert"):
            cv2.rectangle(frame, (5, 5), (w - 5, h - 5), (0, 0, 255), 4)
            cv2.putText(frame, result["alert"], (50, h // 2),
                        cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 0, 255), 3)

        cv2.imshow("EdgeGuard Auto Demo", frame)

        # 录制（可选）
        if SAVE_VIDEO:
            if writer is None:
                fourcc = cv2.VideoWriter_fourcc(*'mp4v')
                writer = cv2.VideoWriter('demo_output.mp4', fourcc, 20, (w, h))
            writer.write(frame)

        if cv2.waitKey(30) & 0xFF == ord('q'):
            break

    # 每步打印结果
    ret, frame = cap.read()
    if ret:
        tracker.refresh(frame)
        result = decide_locally({
            "trigger": "speech" if scenario["speech"] else "gaze",
            "data": {"state": tracker.gaze_state, "duration": 0,
                     "gesture": "", "confidence": 0, "text": scenario["speech"]}
        })
    print(f"  => {result.get('action_code')} {result.get('alert', '')}")

    time.sleep(0.5)

cap.release()
if writer:
    writer.release()
cv2.destroyAllWindows()
print("\n演示完成，视频保存为 demo_output.mp4")
