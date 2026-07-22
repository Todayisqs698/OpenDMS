"""
手势识别器 — MediaPipe Hand Landmarker (Tasks API) + 几何分类器

兼容 mediapipe 0.10.30+。15+ 手势 → action_code 映射。
"""
import os
import logging
import cv2
import mediapipe as mp
from mediapipe.tasks import python as mp_tasks
from mediapipe.tasks.python import vision

logger = logging.getLogger(__name__)

_BaseOptions = mp_tasks.BaseOptions
_HandLandmarker = vision.HandLandmarker
_HandLandmarkerOptions = vision.HandLandmarkerOptions
_RunningMode = vision.RunningMode

_MODEL_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "hand_landmarker.task"
)


class HandGestureDetector:
    """MediaPipe Hand Landmarker (Tasks API) + 15+ 几何手势分类"""

    def __init__(self, max_hands=1, det_conf=0.7, track_conf=0.5):
        if not os.path.exists(_MODEL_PATH):
            raise FileNotFoundError(
                f"手势模型文件不存在: {_MODEL_PATH}"
            )

        options = _HandLandmarkerOptions(
            base_options=_BaseOptions(model_asset_path=_MODEL_PATH),
            running_mode=_RunningMode.VIDEO,
            num_hands=max_hands,
            min_hand_detection_confidence=det_conf,
            min_tracking_confidence=track_conf,
        )
        self.landmarker = _HandLandmarker.create_from_options(options)
        self._timestamp = 0

        from modules.vision.gesture_classifier import GestureClassifier, GestureStabilizer
        self.classifier = GestureClassifier()
        self.stabilizer = GestureStabilizer(hold_frames=10)
        self.available = self.classifier.get_available_gestures()
        logger.info(f"几何手势分类器就绪: {len(self.available)} 种手势")

    def process(self, frame, rgb=None):
        """
        处理一帧，返回 (gesture_name | None, action_info | None, confidence)。

        action_info = {"gesture": ..., "action_code": ..., "label": ..., "icon": ...}

        可传入预转换的 rgb 以节省一次 cvtColor。
        """
        self._timestamp += 1

        if rgb is None:
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

        mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
        result = self.landmarker.detect_for_video(mp_image, self._timestamp)

        if not result.hand_landmarks:
            self.stabilizer.update(None)
            return None, None, 0.0

        # 取第一只手，提取归一化坐标 [(x, y), ...]
        hand_lm = result.hand_landmarks[0]
        pts = [(lm.x, lm.y) for lm in hand_lm]

        gesture_name, confidence, action_code, label, icon = self.classifier.classify(pts)

        # 稳定性滤波
        action = self.stabilizer.update(gesture_name)

        if gesture_name and action:
            return gesture_name, action, float(confidence)

        return gesture_name, None, float(confidence) if gesture_name else 0.0

    def close(self):
        try:
            self.landmarker.close()
        except Exception:
            pass
