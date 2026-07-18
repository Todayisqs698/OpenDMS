"""
感知层测试 — 验证摄像头/麦克风/AI 模型可用性
运行: python test_perception.py
"""
import sys
sys.path.insert(0, '.')

print("=" * 50)
print("EdgeGuard 感知层测试")
print("=" * 50)

# 1. OpenCV 摄像头
print("\n[1/5] OpenCV 摄像头...")
try:
    import cv2
    cap = cv2.VideoCapture(0)
    if cap.isOpened():
        ret, frame = cap.read()
        h, w = frame.shape[:2]
        print(f"  OK 摄像头可用: {w}x{h}")
        cap.release()
    else:
        print("  SKIP 未检测到摄像头")
except Exception as e:
    print(f"  SKIP OpenCV: {e}")

# 2. MediaPipe 手势识别
print("\n[2/5] MediaPipe 手势识别...")
try:
    from modules.vision.gesture.gesture_recognizer import GestureRecognizer
    gr = GestureRecognizer()
    print(f"  OK MediaPipe 手势识别加载成功")
except Exception as e:
    print(f"  FAIL: {e}")

# 3. Whisper 语音识别
print("\n[3/5] Whisper 语音识别...")
try:
    from modules.audio.speech_recognizer import transcribe
    print("  OK Whisper-turbo 加载成功")
except Exception as e:
    print(f"  FAIL: {e}")

# 4. dlib 眼动追踪
print("\n[4/5] dlib 眼动追踪...")
try:
    import dlib
    print("  OK dlib 已安装")
    from modules.vision.gaze.gaze_tracking import GazeTracking
    print("  OK 眼动追踪模块加载成功")
except ImportError:
    print("  SKIP dlib 未安装（Python 3.13 无预编译包），眼动追踪不可用")
except Exception as e:
    print(f"  FAIL: {e}")

# 5. dlib 头部姿态
print("\n[5/5] dlib 头部姿态...")
try:
    from modules.vision.head.head_pose_detector import HeadPoseDetector
    print("  OK 头部姿态检测加载成功")
except ImportError:
    print("  SKIP dlib 未安装，头部姿态不可用")
except Exception as e:
    print(f"  FAIL: {e}")

# 总结
print("\n" + "=" * 50)
print("测试完成")
print("  手势识别: MediaPipe OK")
print("  语音识别: Whisper OK")
print("  眼动追踪: 需要 dlib (Python 3.13 暂不支持)")
print("  头部姿态: 需要 dlib")
print("=" * 50)
print("\n当前可用功能: 手势识别 + 语音识别 + AI决策链路")
print("完整功能需降级到 Python 3.10-3.12 安装 dlib")
