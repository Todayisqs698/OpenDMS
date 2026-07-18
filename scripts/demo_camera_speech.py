"""
EdgeGuard 实时演示 — 摄像头 + 语音 + AI 决策
运行: python demo_camera_speech.py

流程: 摄像头拍照 → 输入语音文本 → AI决策 → 输出结果
"""
import sys, time, cv2

print("=" * 50)
print("EdgeGuard 实时演示")
print("=" * 50)

# 摄像头
cap = cv2.VideoCapture(0)
if cap.isOpened():
    ret, frame = cap.read()
    h, w = frame.shape[:2] if ret else (0, 0)
    print(f"摄像头: {w}x{h}")
else:
    print("摄像头: 未检测到")
    cap = None

# AI 链路
from modules.ai.edge_cloud_router import get_router
from modules.ai.local_decision_engine import decide_locally
from modules.ai.langgraph_orchestrator import Orchestrator
from modules.ai.deepseek_client import MultimodalInput

router = get_router()
orchestrator = Orchestrator()
print("AI链路: 就绪")
print("=" * 50)

# 预设测试场景
scenarios = [
    ("打开空调", "speech", "center", 0, ""),
    ("我要导航去公司", "speech", "center", 0, ""),
    ("", "gaze", "left", 4.0, ""),
    ("播放音乐", "speech", "right", 5.0, ""),
    ("", "gesture", "center", 0, "Thumbs Up"),
]

print("\n预设场景:")
for i, (text, trigger, gaze, dur, gesture) in enumerate(scenarios, 1):
    desc = text or (f"视线{gaze} {dur}秒" if trigger == "gaze" else f"手势 {gesture}")
    print(f"  [{i}] {desc}")

print("\n输入数字 1-5 选场景，或直接输入语音文本，q 退出")

while True:
    cmd = input("\n> ").strip()
    if cmd.lower() == 'q':
        break

    if cmd in ('1','2','3','4','5'):
        text, trigger, gaze, dur, gesture = scenarios[int(cmd)-1]
    elif cmd:
        text, trigger, gaze, dur, gesture = cmd, "speech", "center", 0, ""
    else:
        continue

    # 拍照
    if cap:
        ret, frame = cap.read()
        timestamp = time.strftime("%H:%M:%S")

    # AI 决策
    multimodal_input = MultimodalInput(
        gaze_data={"state": gaze, "duration": dur},
        gesture_data={"gesture": gesture, "confidence": 0.9 if gesture else 0},
        speech_data={"text": text, "intent": "command" if text else ""},
        timestamp=time.time(), duration=0.1,
        context={"type": "user_input", "trigger": trigger},
    )

    route = router.route({"trigger": trigger, "text": text, "type": "user_input"})
    result = decide_locally({"trigger": trigger, "data": {
        "state": gaze, "duration": dur,
        "gesture": gesture, "confidence": 0.9,
        "text": text
    }})

    print(f"  路由: {route}")
    print(f"  动作: {result.get('action_code', '?')}")
    if result.get('alert'):
        print(f"  告警: {result['alert']}")

print("\n演示结束")
if cap: cap.release()
