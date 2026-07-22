"""
MediaPipe 面部追踪器 — 替代 dlib

使用 MediaPipe Face Landmarker Tasks API（兼容 0.10.30+）。
"""
import cv2
import mediapipe as mp
import numpy as np
import os

# MediaPipe 0.10.30+ 使用 tasks API
from mediapipe.tasks import python as mp_tasks
from mediapipe.tasks.python import vision

_BaseOptions = mp_tasks.BaseOptions
_FaceLandmarker = vision.FaceLandmarker
_FaceLandmarkerOptions = vision.FaceLandmarkerOptions
_RunningMode = vision.RunningMode

# 模型路径
_MODEL_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "face_landmarker_v2_with_blendshapes.task"
)


class FaceTracker:
    """MediaPipe 面部追踪 — 眼动 + 头部姿态"""

    def __init__(self):
        if not os.path.exists(_MODEL_PATH):
            raise FileNotFoundError(
                f"面部模型文件不存在: {_MODEL_PATH}\n"
                "下载: wget https://storage.googleapis.com/mediapipe-models/"
                "face_landmarker/face_landmarker/float16/latest/"
                "face_landmarker.task"
            )

        options = _FaceLandmarkerOptions(
            base_options=_BaseOptions(model_asset_path=_MODEL_PATH),
            running_mode=_RunningMode.VIDEO,
            num_faces=1,
            output_face_blendshapes=True,
        )
        self.landmarker = _FaceLandmarker.create_from_options(options)
        self.face_landmarks = None
        self._img_h = 0
        self._img_w = 0
        self._timestamp = 0

    def refresh(self, frame, rgb=None):
        """处理一帧，更新面部关键点。可传入预转换的 rgb 以节省一次 cvtColor。"""
        self._img_h, self._img_w = frame.shape[:2]
        self._timestamp += 1
        if rgb is None:
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
        result = self.landmarker.detect_for_video(mp_image, self._timestamp)
        if result.face_landmarks:
            self.face_landmarks = result.face_landmarks[0]
        else:
            self.face_landmarks = None

    def is_face_detected(self) -> bool:
        return self.face_landmarks is not None

    @property
    def pupils_located(self) -> bool:
        return self.face_landmarks is not None

    # ── 眼动 ──

    def horizontal_ratio(self) -> float:
        """视线水平比例 -1(左) ~ 0(中) ~ 1(右)"""
        if not self.face_landmarks:
            return 0.0
        lm = self.face_landmarks
        # 左眼角 33, 右眼角 133, 左虹膜 468
        left_corner = lm[33].x
        right_corner = lm[133].x
        iris = lm[468].x
        eye_width = right_corner - left_corner
        if eye_width == 0:
            return 0.0
        return (iris - left_corner) / eye_width - 0.5

    def vertical_ratio(self) -> float:
        """视线垂直比例 -1(上) ~ 0(中) ~ 1(下)"""
        if not self.face_landmarks:
            return 0.0
        lm = self.face_landmarks
        # 左眼上眼睑 159, 下眼睑 145, 虹膜 468
        # 右眼上眼睑 386, 下眼睑 374, 虹膜 473
        left_top = lm[159].y
        left_bottom = lm[145].y
        left_iris = lm[468].y
        right_top = lm[386].y
        right_bottom = lm[374].y
        right_iris = lm[473].y

        left_eye_h = left_bottom - left_top
        right_eye_h = right_bottom - right_top
        left_ratio = (left_iris - left_top) / left_eye_h if left_eye_h > 0.001 else 0.5
        right_ratio = (right_iris - right_top) / right_eye_h if right_eye_h > 0.001 else 0.5
        # 双眼平均，0.5=居中，<0.5=偏上，>0.5=偏下
        avg = (left_ratio + right_ratio) / 2.0
        return avg - 0.5  # 映射到 -1(上) ~ 0(中) ~ 1(下)

    def is_center(self) -> bool:
        return abs(self.horizontal_ratio()) < 0.08 and abs(self.vertical_ratio()) < 0.1

    def is_right(self) -> bool:
        return self.horizontal_ratio() > 0.08

    def is_left(self) -> bool:
        return self.horizontal_ratio() < -0.08

    def is_up(self) -> bool:
        return self.vertical_ratio() < -0.1

    def is_down(self) -> bool:
        return self.vertical_ratio() > 0.1

    # 眨眼追踪 — 自适应基线
    _blink_count = 0
    _blink_closed = False
    _ear_history = []
    _ear_baseline = None           # 用户睁眼时的 EAR 基线
    _baseline_samples = []

    BLINK_RATIO = 0.55             # 低于基线 55% = 闭眼
    CALIBRATION_FRAMES = 60        # 前 60 帧搜集基线

    def is_blinking(self) -> bool:
        """自适应眨眼检测 — 基于个人 EAR 基线"""
        if not self.face_landmarks:
            return self._blink_closed

        lm = self.face_landmarks
        left_ear = abs(lm[159].y - lm[145].y) / max(abs(lm[33].x - lm[133].x), 0.001)
        right_ear = abs(lm[386].y - lm[374].y) / max(abs(lm[362].x - lm[263].x), 0.001)
        ear = (left_ear + right_ear) / 2.0

        self._ear_history.append(ear)
        if len(self._ear_history) > 5:
            self._ear_history.pop(0)

        # 前 60 帧搜集睁眼基线（取中位数，排除闭眼异常值）
        if self._ear_baseline is None:
            self._baseline_samples.append(ear)
            if len(self._baseline_samples) >= self.CALIBRATION_FRAMES:
                # 取中位数（抗异常值干扰）
                sorted_vals = sorted(self._baseline_samples)
                self._ear_baseline = sorted_vals[len(sorted_vals) // 2]
            return False  # 校准中，不判断

        # 低于基线 40% = 闭眼
        threshold = self._ear_baseline * self.BLINK_RATIO
        closed = ear < threshold

        if closed and not self._blink_closed:
            self._blink_closed = True
            self._blink_count += 1
        elif not closed and self._blink_closed:
            self._blink_closed = False

        return self._blink_closed

    @property
    def perclos(self) -> float:
        return 1.0 if self._blink_closed else 0.0

    @property
    def blink_count(self) -> int:
        return self._blink_count

    @property
    def ear(self) -> float:
        if self._ear_history:
            return round(sum(self._ear_history) / len(self._ear_history), 4)
        return 0.0

    @property
    def ear_threshold(self) -> float:
        if self._ear_baseline:
            return round(self._ear_baseline * self.BLINK_RATIO, 4)
        return 0.0

    # ── 头部姿态 ──

    def head_pose(self) -> dict:
        """返回头部姿态角度"""
        if not self.face_landmarks:
            return {"pitch": 0, "yaw": 0, "roll": 0}

        lm = self.face_landmarks
        # 6 点：鼻尖、下巴、左右眼角、左右嘴角
        img_points = np.array([
            [lm[1].x * self._img_w, lm[1].y * self._img_h],      # 鼻尖
            [lm[152].x * self._img_w, lm[152].y * self._img_h],   # 下巴
            [lm[33].x * self._img_w, lm[33].y * self._img_h],     # 左眼角
            [lm[263].x * self._img_w, lm[263].y * self._img_h],   # 右眼角
            [lm[61].x * self._img_w, lm[61].y * self._img_h],     # 左嘴角
            [lm[291].x * self._img_w, lm[291].y * self._img_h],   # 右嘴角
        ], dtype=np.float32)

        model_points = np.array([
            [0.0, 0.0, 0.0],           # 鼻尖
            [0.0, -63.6, -12.5],       # 下巴
            [-43.3, 32.7, -26.0],      # 左眼角
            [43.3, 32.7, -26.0],       # 右眼角
            [-30.0, -20.0, -20.0],     # 左嘴角
            [30.0, -20.0, -20.0],      # 右嘴角
        ], dtype=np.float32)

        focal = self._img_w
        center = (self._img_w / 2, self._img_h / 2)
        cam_matrix = np.array([[focal, 0, center[0]],
                                [0, focal, center[1]],
                                [0, 0, 1]], dtype=np.float32)

        success, rvec, _ = cv2.solvePnP(
            model_points, img_points, cam_matrix, np.zeros((4, 1)),
            flags=cv2.SOLVEPNP_ITERATIVE
        )

        if not success:
            return {"pitch": 0, "yaw": 0, "roll": 0}

        rmat, _ = cv2.Rodrigues(rvec)
        sy = np.sqrt(rmat[0, 0] ** 2 + rmat[1, 0] ** 2)
        pitch = np.degrees(np.arctan2(-rmat[2, 0], sy))
        yaw = np.degrees(np.arctan2(rmat[1, 0], rmat[0, 0]))
        roll = np.degrees(np.arctan2(rmat[2, 1], rmat[2, 2]))

        return {"pitch": round(pitch, 1), "yaw": round(yaw, 1), "roll": round(roll, 1)}

    _gaze_history = []  # 平滑防抖

    @property
    def gaze_state(self) -> str:
        if not self.face_landmarks:
            return "center"

        # 头部姿态
        head = self.head_pose()
        yaw = head.get("yaw", 0)
        pitch = head.get("pitch", 0)

        # ── 水平方向: 头部 yaw 优先，虹膜位置辅助 ──
        if yaw > 10:
            h_raw = "right"
        elif yaw < -10:
            h_raw = "left"
        else:
            ratio = self.horizontal_ratio()
            if ratio > 0.13:
                h_raw = "right"
            elif ratio < -0.13:
                h_raw = "left"
            else:
                h_raw = "center"

        # ── 垂直方向: 头部 pitch 优先，虹膜垂直位置辅助 ──
        if pitch < -8:           # 抬头
            v_raw = "up"
        elif pitch > 8:         # 低头
            v_raw = "down"
        else:
            vr = self.vertical_ratio()
            if vr < -0.12:       # 虹膜偏上
                v_raw = "up"
            elif vr > 0.12:      # 虹膜偏下
                v_raw = "down"
            else:
                v_raw = "center"

        # ── 组合：水平 + 垂直 → 9 种状态 ──
        if h_raw == "center" and v_raw == "center":
            raw = "center"
        elif h_raw == "center":
            raw = v_raw           # up / down
        elif v_raw == "center":
            raw = h_raw           # left / right
        else:
            raw = f"{v_raw}_{h_raw}"  # up_left, up_right, down_left, down_right

        # 平滑：最近 5 帧中占多数的状态
        self._gaze_history.append(raw)
        if len(self._gaze_history) > 8:
            self._gaze_history.pop(0)
        # 取最近 5 帧中频率最高的状态
        recent = self._gaze_history[-5:]
        best = max(set(recent), key=recent.count)
        if recent.count(best) >= 3:
            return best
        return "center"
