"""
面部追踪器 — 3 级降级策略

Level 1: MediaPipe Face Landmarker（468 点 + 虹膜 + blendshapes）
Level 2: OpenCV Haar Cascade（人脸框 + 粗略视线估算）
Level 3: noop（无检测，返回默认值，系统不崩溃）
"""
import logging
import cv2
import numpy as np
import os

logger = logging.getLogger(__name__)

# 模型路径
_MODEL_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "face_landmarker_v2_with_blendshapes.task"
)


class FaceTracker:
    """面部追踪 — 3 级降级：MediaPipe → OpenCV Haar → noop"""

    def __init__(self):
        self._mode = "noop"
        self.face_landmarks = None
        self._img_h = 0
        self._img_w = 0
        self._timestamp = 0

        # ── Level 1: MediaPipe ──
        try:
            import mediapipe as mp
            from mediapipe.tasks import python as mp_tasks
            from mediapipe.tasks.python import vision

            if not os.path.exists(_MODEL_PATH):
                raise FileNotFoundError(f"模型文件不存在: {_MODEL_PATH}")

            options = vision.FaceLandmarkerOptions(
                base_options=mp_tasks.BaseOptions(model_asset_path=_MODEL_PATH),
                running_mode=vision.RunningMode.VIDEO,
                num_faces=1,
                output_face_blendshapes=True,
            )
            self._mp = mp
            self._landmarker = vision.FaceLandmarker.create_from_options(options)
            self._mode = "mediapipe"
            logger.info("FaceTracker: MediaPipe 模式（468 点 + 虹膜）")
            return
        except Exception as e:
            logger.warning(f"FaceTracker: MediaPipe 不可用: {e}")

        # ── Level 2: OpenCV Haar Cascade ──
        try:
            haar_path = os.path.join(
                cv2.data.haarcascades, 'haarcascade_frontalface_default.xml')
            self._haar = cv2.CascadeClassifier(haar_path)
            if self._haar.empty():
                raise RuntimeError("Haar Cascade 加载失败")
            self._mode = "opencv"
            self._haar_gaze_history = []
            logger.info("FaceTracker: OpenCV Haar 模式（人脸框 + 粗略视线）")
            return
        except Exception as e:
            logger.warning(f"FaceTracker: OpenCV Haar 不可用: {e}")

        # ── Level 3: noop ──
        self._mode = "noop"
        logger.warning("FaceTracker: noop 模式（无面部检测，系统降级运行）")

    @property
    def mode(self) -> str:
        """当前运行模式: mediapipe / opencv / noop"""
        return self._mode

    def refresh(self, frame, rgb=None):
        """处理一帧，更新面部状态。"""
        self._img_h, self._img_w = frame.shape[:2]
        self._timestamp += 1

        if self._mode == "mediapipe":
            self._refresh_mediapipe(frame, rgb)
        elif self._mode == "opencv":
            self._refresh_opencv(frame)
        else:
            self.face_landmarks = None

    def _refresh_mediapipe(self, frame, rgb=None):
        """Level 1: MediaPipe 468 点检测"""
        if rgb is None:
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        mp_image = self._mp.Image(image_format=self._mp.ImageFormat.SRGB, data=rgb)
        result = self._landmarker.detect_for_video(mp_image, self._timestamp)
        if result.face_landmarks:
            self.face_landmarks = result.face_landmarks[0]
        else:
            self.face_landmarks = None

    def _refresh_opencv(self, frame):
        """Level 2: OpenCV Haar Cascade — 人脸框 + 粗略视线估算"""
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        faces = self._haar.detectMultiScale(gray, scaleFactor=1.3, minNeighbors=5, minSize=(60, 60))

        if len(faces) > 0:
            # 取最大的人脸
            x, y, w, h = max(faces, key=lambda f: f[2] * f[3])
            cx = x + w / 2
            frame_cx = self._img_w / 2

            # 粗略估算：人脸中心偏左→视线左，偏右→视线右
            offset = (cx - frame_cx) / max(frame_cx, 1)

            # 人脸框宽高比估算 pitch（低头时脸框变短）
            aspect = h / max(w, 1)
            pitch_est = (aspect - 1.2) * 30  # 粗略映射

            if offset < -0.15:
                h_raw = "left"
            elif offset > 0.15:
                h_raw = "right"
            else:
                h_raw = "center"

            if pitch_est > 8:
                v_raw = "down"
            elif pitch_est < -8:
                v_raw = "up"
            else:
                v_raw = "center"

            # 组合
            if h_raw == "center" and v_raw == "center":
                raw = "center"
            elif h_raw == "center":
                raw = v_raw
            elif v_raw == "center":
                raw = h_raw
            else:
                raw = f"{v_raw}_{h_raw}"

            # 平滑
            self._haar_gaze_history.append(raw)
            if len(self._haar_gaze_history) > 5:
                self._haar_gaze_history.pop(0)
            recent = self._haar_gaze_history[-3:]
            best = max(set(recent), key=recent.count) if recent else raw
            self._haar_gaze = best

            # 标记为检测到（用非 None 占位）
            self.face_landmarks = []
            self._haar_pitch = round(pitch_est, 1)
            self._haar_yaw = round(offset * 45, 1)  # 粗略映射到角度
        else:
            self.face_landmarks = None
            self._haar_gaze = "center"

    def is_face_detected(self) -> bool:
        return self.face_landmarks is not None

    @property
    def pupils_located(self) -> bool:
        return self._mode == "mediapipe" and self.face_landmarks is not None

    # ── 眼动（仅 MediaPipe 模式有效）──

    def horizontal_ratio(self) -> float:
        """视线水平比例 -1(左) ~ 0(中) ~ 1(右)"""
        if not self.face_landmarks or self._mode != "mediapipe":
            return 0.0
        lm = self.face_landmarks
        left_corner = lm[33].x
        right_corner = lm[133].x
        iris = lm[468].x
        eye_width = right_corner - left_corner
        if eye_width == 0:
            return 0.0
        return (iris - left_corner) / eye_width - 0.5

    def vertical_ratio(self) -> float:
        """视线垂直比例 -1(上) ~ 0(中) ~ 1(下)"""
        if not self.face_landmarks or self._mode != "mediapipe":
            return 0.0
        lm = self.face_landmarks
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
        avg = (left_ratio + right_ratio) / 2.0
        return avg - 0.5

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

    # ── 眨眼追踪（仅 MediaPipe 模式有效）──

    _blink_count = 0
    _blink_closed = False
    _ear_history = []
    _ear_baseline = None
    _baseline_samples = []

    BLINK_RATIO = 0.55
    CALIBRATION_FRAMES = 60

    def is_blinking(self) -> bool:
        """自适应眨眼检测 — 基于个人 EAR 基线"""
        if self._mode != "mediapipe" or not self.face_landmarks:
            return self._blink_closed

        lm = self.face_landmarks
        left_ear = abs(lm[159].y - lm[145].y) / max(abs(lm[33].x - lm[133].x), 0.001)
        right_ear = abs(lm[386].y - lm[374].y) / max(abs(lm[362].x - lm[263].x), 0.001)
        ear = (left_ear + right_ear) / 2.0

        self._ear_history.append(ear)
        if len(self._ear_history) > 5:
            self._ear_history.pop(0)

        if self._ear_baseline is None:
            self._baseline_samples.append(ear)
            if len(self._baseline_samples) >= self.CALIBRATION_FRAMES:
                sorted_vals = sorted(self._baseline_samples)
                self._ear_baseline = sorted_vals[len(sorted_vals) // 2]
            return False

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
        """返回头部姿态角度 {pitch, yaw, roll}"""
        if self._mode == "mediapipe":
            return self._head_pose_mediapipe()
        elif self._mode == "opencv":
            return {"pitch": getattr(self, "_haar_pitch", 0),
                    "yaw": getattr(self, "_haar_yaw", 0), "roll": 0}
        else:
            return {"pitch": 0, "yaw": 0, "roll": 0}

    def _head_pose_mediapipe(self) -> dict:
        """MediaPipe PnP 头部姿态"""
        if not self.face_landmarks:
            return {"pitch": 0, "yaw": 0, "roll": 0}

        lm = self.face_landmarks
        img_points = np.array([
            [lm[1].x * self._img_w, lm[1].y * self._img_h],
            [lm[152].x * self._img_w, lm[152].y * self._img_h],
            [lm[33].x * self._img_w, lm[33].y * self._img_h],
            [lm[263].x * self._img_w, lm[263].y * self._img_h],
            [lm[61].x * self._img_w, lm[61].y * self._img_h],
            [lm[291].x * self._img_w, lm[291].y * self._img_h],
        ], dtype=np.float32)

        model_points = np.array([
            [0.0, 0.0, 0.0],
            [0.0, -63.6, -12.5],
            [-43.3, 32.7, -26.0],
            [43.3, 32.7, -26.0],
            [-30.0, -20.0, -20.0],
            [30.0, -20.0, -20.0],
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

    # ── 视线状态 ──

    _gaze_history = []

    @property
    def gaze_state(self) -> str:
        if self._mode == "mediapipe":
            return self._gaze_state_mediapipe()
        elif self._mode == "opencv":
            return getattr(self, "_haar_gaze", "center")
        else:
            return "center"

    def _gaze_state_mediapipe(self) -> str:
        """MediaPipe: 头部姿态 + 虹膜位置 → 9 种视线状态"""
        if not self.face_landmarks:
            return "center"

        head = self._head_pose_mediapipe()
        yaw = head.get("yaw", 0)
        pitch = head.get("pitch", 0)

        # 水平: yaw 优先，虹膜辅助
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

        # 垂直: pitch 优先，虹膜辅助
        if pitch < -8:
            v_raw = "up"
        elif pitch > 8:
            v_raw = "down"
        else:
            vr = self.vertical_ratio()
            if vr < -0.12:
                v_raw = "up"
            elif vr > 0.12:
                v_raw = "down"
            else:
                v_raw = "center"

        # 组合
        if h_raw == "center" and v_raw == "center":
            raw = "center"
        elif h_raw == "center":
            raw = v_raw
        elif v_raw == "center":
            raw = h_raw
        else:
            raw = f"{v_raw}_{h_raw}"

        # 平滑
        self._gaze_history.append(raw)
        if len(self._gaze_history) > 8:
            self._gaze_history.pop(0)
        recent = self._gaze_history[-5:]
        best = max(set(recent), key=recent.count)
        if recent.count(best) >= 3:
            return best
        return "center"
