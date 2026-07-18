"""
手势识别器 — MediaPipe HandLandmarker (Tasks API) + TFLite 分类器
兼容 MediaPipe 0.10.35。
"""
import os, time, csv, copy, itertools, logging, numpy as np

logger = logging.getLogger(__name__)

_MODEL_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "hand_landmarker.task")
_KEYPOINT_MODEL = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "gesture", "models", "avazahedi", "keypoint_classifier.tflite")
_KEYPOINT_LABELS = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                 "gesture", "models", "avazahedi", "keypoint_classifier_label.csv")


# ── 关键点预处理（与参考项目一致）──

def _calc_landmark_list(w, h, landmarks):
    return [[min(int(lm.x * w), w - 1), min(int(lm.y * h), h - 1)] for lm in landmarks]


def _pre_process_landmark(landmark_list):
    temp = copy.deepcopy(landmark_list)
    base_x, base_y = temp[0][0], temp[0][1]
    for i in range(len(temp)):
        temp[i][0] -= base_x
        temp[i][1] -= base_y
    temp = list(itertools.chain.from_iterable(temp))
    max_val = max(list(map(abs, temp)))
    def normalize_(n):
        return n / max_val if max_val != 0 else 0
    return list(map(normalize_, temp))


def _load_labels():
    with open(_KEYPOINT_LABELS, encoding='utf-8-sig') as f:
        return [row[0] for row in csv.reader(f)]


class HandGestureDetector:
    """MediaPipe HandLandmarker + TFLite KeyPointClassifier"""

    def __init__(self):
        if not os.path.exists(_MODEL_PATH):
            raise FileNotFoundError(f"手部模型不存在: {_MODEL_PATH}")
        if not os.path.exists(_KEYPOINT_MODEL):
            raise FileNotFoundError(f"分类模型不存在: {_KEYPOINT_MODEL}")

        # HandLandmarker (Tasks API)
        from mediapipe.tasks import python as mp_tasks
        from mediapipe.tasks.python import vision

        options = vision.HandLandmarkerOptions(
            base_options=mp_tasks.BaseOptions(model_asset_path=_MODEL_PATH),
            running_mode=vision.RunningMode.VIDEO,
            num_hands=1,
        )
        self.landmarker = vision.HandLandmarker.create_from_options(options)

        # TFLite KeyPointClassifier
        from modules.vision.gesture.keypoint_classifier import KeyPointClassifier
        self.classifier = KeyPointClassifier(model_path=_KEYPOINT_MODEL)
        self.labels = _load_labels()
        logger.info(f"手势分类器就绪: {len(self.labels)} 类")

        self._timestamp = 0
        self._last_gesture = None
        self._stable_count = 0

    def process(self, frame):
        """返回 (gesture_name | None, confidence)"""
        import mediapipe as mp

        self._timestamp += 1
        h, w = frame.shape[:2]
        mp_img = mp.Image(image_format=mp.ImageFormat.SRGB, data=frame)
        result = self.landmarker.detect_for_video(mp_img, self._timestamp)

        if not result.hand_landmarks:
            self._stable_count = 0
            return None, 0.0

        # 用第一只手
        hand_lm = result.hand_landmarks[0]
        landmark_list = _calc_landmark_list(w, h, hand_lm)
        preprocessed = _pre_process_landmark(landmark_list)
        gesture_id, confidence = self.classifier(preprocessed)

        if 0 <= gesture_id < len(self.labels):
            gesture = self.labels[gesture_id]
        else:
            return None, 0.0

        # 防抖：连续 2 帧确认
        if gesture == self._last_gesture:
            self._stable_count += 1
        else:
            self._last_gesture = gesture
            self._stable_count = 1

        if self._stable_count >= 2 and gesture:
            return gesture, float(confidence)

        return None, 0.0

    def close(self):
        pass
