"""
EdgeGuard：边缘智能驾驶安全多模态交互系统
主入口 — 摄像头采集 + 面部追踪 + 手势识别 + AI 决策 + WebSocket 推流

启动方式：
    # 1. 先启后端
    cd backend && uvicorn main:app --host 0.0.0.0 --port 8000

    # 2. 再启前端
    cd frontend && npm run dev

    # 3. 启动摄像头 AI 引擎
    python app.py              # 需要摄像头
    python app.py --dry-run    # 干跑模式（不需要硬件，仅测试AI链路）
"""
import sys
import os
import time
import logging

# 修复 Windows GBK 编码问题
if sys.platform == 'win32' and hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(message)s")
logger = logging.getLogger(__name__)

# ── AI 决策层（始终可用）──
from modules.ai.edge_cloud_router import get_router
from modules.ai.langgraph_orchestrator import Orchestrator
from modules.ai.local_decision_engine import decide_locally
from modules.ai.fallback_handler import handle_fallback

# multimodal_collector 在 Windows 下可能因 emoji 打印报错，容错导入
try:
    from modules.ai.multimodal_collector import multimodal_collector
    _collector_ok = True
except Exception as e:
    logger.warning(f"multimodal_collector 加载失败(不影响AI链路): {e}")
    multimodal_collector = None
    _collector_ok = False

# ── 感知层（懒加载，硬件不可用时跳过）──
_perception_available = False
_recorder = None
_gesture_recognizer = None
_head_pose_detector = None
_gaze_tracker = None
_camera_manager = None


def _init_perception():
    """尝试加载感知层，失败则标记不可用"""
    global _perception_available, _recorder, _gesture_recognizer
    global _head_pose_detector, _gaze_tracker, _camera_manager

    try:
        from modules.vision.face_tracker import FaceTracker
        _gaze_tracker = FaceTracker()
        logger.info("  FaceTracker (MediaPipe) 就绪")
    except Exception as e:
        logger.warning(f"  FaceTracker 不可用: {e}")
        _gaze_tracker = None

    try:
        from modules.audio.recorder import Recorder
        _recorder = Recorder()
        logger.info("  录音器就绪")
    except Exception as e:
        logger.warning(f"  录音器不可用: {e}")
        _recorder = None

    try:
        from modules.vision.gesture.gesture_recognizer import GestureRecognizer
        _gesture_recognizer = GestureRecognizer()
        logger.info("  手势识别器就绪")
    except Exception as e:
        logger.warning(f"  手势识别器不可用: {e}")
        _gesture_recognizer = None

    _head_pose_detector = None  # 头部姿态由 FaceTracker 提供
    _camera_manager = None
    _perception_available = True
    return True


class EdgeGuardApp:
    """EdgeGuard 主应用 — 边缘-云端混合多模态 AI 系统"""

    def __init__(self, dry_run: bool = False):
        self.dry_run = dry_run
        self.running = False

        # AI 决策层
        self.router = get_router()
        self.orchestrator = Orchestrator()

        # 统计
        self.stats = {
            "start_time": time.time(),
            "ai_requests": 0,
            "local_decisions": 0,
            "cloud_decisions": 0,
            "hybrid_decisions": 0,
            "fallback_count": 0,
        }

        # 语音实时转写（由 _speech_thread 持续更新）
        self._speech_text = ""
        self._speech_thread = None
        self._speech_available = False

        # 设置多模态回调
        if multimodal_collector:
            multimodal_collector.set_callback(self.on_multimodal_event)

        if not dry_run:
            _init_perception()

        logger.info("=" * 50)
        logger.info("EdgeGuard 初始化完成")
        logger.info(f"  感知层: {'可用' if _perception_available else '不可用（纯AI模式）'}")
        logger.info(f"  决策层: LangGraph 三 Agent + 边缘-云端混合路由")
        logger.info(f"  离线模式: {'已激活' if self.router.is_offline() else '正常'}")
        logger.info("=" * 50)

    def on_multimodal_event(self, multimodal_input):
        """多模态事件回调 → 路由 → 编排 → 响应"""
        self.stats["ai_requests"] += 1

        # Step 1: 边缘-云端路由
        route = self.router.route({
            "trigger": multimodal_input.context.get("trigger", ""),
            "type": multimodal_input.context.get("type", ""),
        })

        if route == "local":
            self.stats["local_decisions"] += 1
            result = decide_locally({
                "trigger": multimodal_input.context.get("trigger", ""),
                "data": {
                    "state": multimodal_input.gaze_data.get("state"),
                    "duration": multimodal_input.gaze_data.get("duration", 0),
                    "gesture": multimodal_input.gesture_data.get("gesture"),
                    "confidence": multimodal_input.gesture_data.get("confidence"),
                    "text": multimodal_input.speech_data.get("text"),
                }
            })
        elif route == "hybrid":
            self.stats["hybrid_decisions"] += 1
            result = self.orchestrator.process(multimodal_input)
        else:  # cloud
            self.stats["cloud_decisions"] += 1
            if self.router.is_offline():
                self.stats["fallback_count"] += 1
                result = handle_fallback({"action_code": ""})
            else:
                result = self.orchestrator.process(multimodal_input)

        self._handle_result(result)

    def _init_speech_thread(self):
        """初始化并启动语音实时转写线程"""
        if _recorder is None:
            logger.warning("  录音器不可用，语音转写未启动")
            self._speech_available = False
            return

        try:
            from modules.audio.speech_recognizer import transcribe
            self._speech_transcribe = transcribe
            self._speech_available = True
        except Exception as e:
            logger.warning(f"  Whisper 语音识别器不可用: {e}")
            self._speech_available = False
            return

        import threading
        self._speech_thread = threading.Thread(
            target=self._speech_loop, daemon=True, name="speech-transcribe"
        )
        self._speech_thread.start()
        logger.info("  语音实时转写线程已启动（Whisper）")

    def _speech_loop(self):
        """语音采集 + 转写后台线程"""
        try:
            for chunk in _recorder.record_stream():
                if not self.running:
                    break
                wav_bytes = chunk.get("wav")
                if not wav_bytes:
                    continue
                try:
                    text = self._speech_transcribe(wav_bytes)
                    text = text.strip()
                    if text:
                        self._speech_text = text
                        logger.info(f"  🎤 语音转写: {text}")
                except Exception as e:
                    logger.warning(f"  语音转写失败: {e}")
        except Exception as e:
            logger.warning(f"  语音采集线程异常退出: {e}")

    def _handle_result(self, result: dict):
        """处理决策结果"""
        action = result.get("action_code", "unknown")
        text = result.get("recommendation_text", "")
        source = result.get("source", "unknown")

        if action == "distract":
            logger.warning(f" [{source}] 安全告警: {text}")
        elif action == "NoticeRoad":
            logger.info(f" [{source}] 注意力已恢复")
        elif action != "unknown":
            logger.info(f" [{source}] 执行: {action} — {text}")

    def run_dry(self):
        """干跑模式：测试 AI 决策链路，不需要摄像头"""
        from modules.ai.deepseek_client import MultimodalInput

        logger.info("干跑模式启动 — 测试 AI 链路...")

        test_scenarios = [
            {
                "name": "分心检测",
                "input": MultimodalInput(
                    gaze_data={"state": "left", "duration": 4.0, "deviation_level": "severe"},
                    gesture_data={"gesture": "", "confidence": 0},
                    speech_data={"text": "", "intent": "", "emotion": "neutral"},
                    timestamp=time.time(), duration=0.1,
                    context={"type": "distraction_detected", "trigger": "gaze"},
                ),
            },
            {
                "name": "语音指令",
                "input": MultimodalInput(
                    gaze_data={"state": "center", "duration": 0, "deviation_level": "normal"},
                    gesture_data={"gesture": "", "confidence": 0},
                    speech_data={"text": "打开空调", "intent": "command", "emotion": "neutral"},
                    timestamp=time.time(), duration=0.1,
                    context={"type": "user_input", "trigger": "speech"},
                ),
            },
            {
                "name": "手势指令",
                "input": MultimodalInput(
                    gaze_data={"state": "center", "duration": 0, "deviation_level": "normal"},
                    gesture_data={"gesture": "Thumbs Up", "confidence": 0.9, "intent": "确认"},
                    speech_data={"text": "", "intent": "", "emotion": "neutral"},
                    timestamp=time.time(), duration=0.1,
                    context={"type": "user_input", "trigger": "gesture"},
                ),
            },
            {
                "name": "分心+语音冲突",
                "input": MultimodalInput(
                    gaze_data={"state": "right", "duration": 5.0, "deviation_level": "severe"},
                    gesture_data={"gesture": "", "confidence": 0},
                    speech_data={"text": "播放音乐", "intent": "command", "emotion": "neutral"},
                    timestamp=time.time(), duration=0.1,
                    context={"type": "distraction_detected", "trigger": "gaze"},
                ),
            },
        ]

        for scenario in test_scenarios:
            logger.info(f"--- 场景: {scenario['name']} ---")
            self.on_multimodal_event(scenario["input"])
            logger.info("")

        logger.info(f"统计: 总请求={self.stats['ai_requests']}, "
                    f"本地={self.stats['local_decisions']}, "
                    f"混合={self.stats['hybrid_decisions']}, "
                    f"云端={self.stats['cloud_decisions']}")

    def run(self):
        """正常模式：摄像头 + 眼动追踪 + 手势识别 → WebSocket 实时推送前端"""
        if not _perception_available:
            logger.error("感知层不可用，无法启动正常模式。请使用 python app.py --dry-run")
            return

        import cv2
        import urllib.request
        import json

        # ── 1. 确认后端已启动 ──
        try:
            req = urllib.request.Request("http://127.0.0.1:8000/api/health")
            urllib.request.urlopen(req, timeout=2)
        except Exception:
            logger.error("后端未启动！请先在 backend/ 目录运行:")
            logger.error("  uvicorn main:app --host 0.0.0.0 --port 8000")
            return
        logger.info("后端连接确认 :8000")

        # ── 2. 启动摄像头 + 感知器 ──
        cap = cv2.VideoCapture(0)
        if not cap.isOpened():
            logger.error("摄像头不可用")
            return

        # 面部追踪
        face_tracker = _gaze_tracker  # 全局已初始化

        # 手势识别：MediaPipe Tasks API + 几何规则（零 ML 依赖）
        gesture_available = False
        gesture_detector = None
        try:
            from modules.vision.hand_gesture import HandGestureDetector
            gesture_detector = HandGestureDetector()
            gesture_available = True
            logger.info("手势识别器就绪（几何规则）")
        except Exception as e:
            logger.warning(f"手势识别未加载: {e}")

        # ── 2.5 启动语音实时转写线程 ──
        self._init_speech_thread()

        # ── 3. 主循环 ──
        self.running = True
        last_gaze = "center"
        gaze_start = time.time()
        frame_count = 0

        logger.info("EdgeGuard 实时监控运行中...")
        logger.info("  前端: http://localhost:5173")
        logger.info("  按 Ctrl+C 退出")

        try:
            while self.running:
                ret, frame = cap.read()
                if not ret:
                    time.sleep(0.01)
                    continue

                frame = cv2.flip(frame, 1)
                h, w = frame.shape[:2]
                frame_count += 1

                # ── 面部追踪 ──
                face_tracker.refresh(frame)
                face = face_tracker.is_face_detected()
                gaze = face_tracker.gaze_state
                blinking = face_tracker.is_blinking()
                now = time.time()

                if gaze != last_gaze:
                    gaze_start = now
                    last_gaze = gaze
                gaze_dur = now - gaze_start if gaze != "center" else 0

                # ── 手势识别（每 3 帧一次）──
                gesture_name = ""
                gesture_conf = 0.0
                if gesture_available and frame_count % 3 == 0:
                    rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                    gname, gconf = gesture_detector.process(rgb)
                    if gname:
                        gesture_name = gname
                        gesture_conf = gconf

                # ── AI 决策 ──
                trigger = "gaze"
                if gesture_name:
                    trigger = "multi"

                # 读取语音转写结果（由后台线程持续更新）
                speech_text = self._speech_text
                if speech_text:
                    trigger = "speech"
                    # 用完即清，避免重复触发
                    self._speech_text = ""

                result = decide_locally({
                    "trigger": trigger,
                    "data": {
                        "state": gaze, "duration": gaze_dur,
                        "gesture": gesture_name, "confidence": gesture_conf,
                        "text": speech_text
                    }
                })

                # ── 推送前端（通过 API，自动 WebSocket 广播）──
                if frame_count % 6 == 0:  # 每 6 帧推一次，减少压力
                    try:
                        payload = json.dumps({
                            "trigger": trigger,
                            "gaze_state": gaze,
                            "gaze_duration": round(gaze_dur, 1),
                            "gesture": gesture_name,
                            "gesture_confidence": round(gesture_conf, 2),
                            "speech_text": speech_text,
                            "context_type": "camera_stream"
                        }).encode("utf-8")
                        req = urllib.request.Request(
                            "http://127.0.0.1:8000/api/analyze",
                            data=payload,
                            headers={"Content-Type": "application/json; charset=utf-8"}
                        )
                        urllib.request.urlopen(req, timeout=2)
                    except Exception:
                        pass  # 后端没启动时静默跳过

                # ── HUD 绘制 ──
                # 顶栏
                cv2.rectangle(frame, (0, 0), (w, 65), (0, 0, 0), -1)
                cv2.putText(frame, "EdgeGuard Live", (10, 25),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.7, (200, 200, 200), 2)

                fps = 1.0 / max(now - getattr(self, '_last_frame_time', now - 0.1), 0.001)
                self._last_frame_time = now
                cv2.putText(frame, f"FPS: {fps:.0f}", (w - 100, 25),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.5, (150, 150, 150), 1)

                # 状态
                cv2.putText(frame, f"Gaze: {gaze} ({gaze_dur:.1f}s)", (10, 50),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.5, (200, 200, 200), 1)

                gesture_text = f"Gesture: {gesture_name}" if gesture_name else "Gesture: --"
                cv2.putText(frame, gesture_text, (w // 2, 50),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.5,
                            (0, 255, 0) if gesture_name else (150, 150, 150), 1)

                cv2.putText(frame, f"Action: {result.get('action_code', 'normal')}", (10, 65),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 255), 1)

                # 告警条
                if result.get("alert"):
                    alert_y = h - 60
                    cv2.rectangle(frame, (0, h - 80), (w, h), (0, 0, 0), -1)
                    cv2.putText(frame, result["alert"], (20, h - 30),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 255), 2)
                    # 红色闪烁边框
                    if int(time.time() * 4) % 2:
                        cv2.rectangle(frame, (3, 3), (w - 3, h - 3), (0, 0, 255), 3)

                cv2.imshow("EdgeGuard Camera", frame)

                key = cv2.waitKey(1) & 0xFF
                if key == ord('q') or key == 27:  # Q 或 ESC 退出
                    break

        except KeyboardInterrupt:
            pass
        finally:
            cap.release()
            if gesture_detector:
                gesture_detector.close()
            cv2.destroyAllWindows()
            self.running = False
            logger.info("EdgeGuard 已关闭")


if __name__ == "__main__":
    dry = "--dry-run" in sys.argv
    app = EdgeGuardApp(dry_run=dry)

    if dry:
        app.run_dry()
    else:
        app.run()
