"""
驾驶员状态机 — 四级状态 + 7维状态向量 + 滑动窗口趋势分析

状态流转：
  NORMAL ←→ ATTENTION_DECLINING → DISTRACTED → DANGEROUS
    ↑                                    ↓           ↓
    └──────────── 恢复确认 ───────────────┘           │
    (手势/语音确认后回到NORMAL)                        │
                                                      ↓
                                            (连续dangerous→强制干预)

设计要点：
- 不是单点阈值判断，而是追踪状态向量的变化趋势
- 上升趋势提前预警（attention_declining），不等进入distracted
- 恢复需要确认（手势/语音），避免短暂恢复→再次分心的抖动
"""
from collections import deque
import logging
import time

logger = logging.getLogger(__name__)


class DriverStateMachine:
    """驾驶员状态机 — 四级状态 + 趋势预测"""

    # 状态转移权重（每个维度的恶化对状态转移的贡献）
    WEIGHTS = {
        "perclos": 0.25,         # 闭眼比例 — 最重要
        "blink_rate": 0.15,      # 眨眼频率
        "head_pitch": 0.10,      # 头部俯仰（低头看手机）
        "head_yaw": 0.15,        # 头部偏航（看窗外）
        "gaze_direction": 0.20,  # 视线方向 — 重要
        "gesture_freq": 0.05,    # 手势频率（过高可能焦躁）
        "speech_emotion": 0.10,  # 语音情绪
    }

    # 状态转移阈值
    NORMAL_THRESHOLD = 0.25       # 低于此 → normal
    DECLINING_THRESHOLD = 0.40    # 25-40 → attention_declining
    DISTRACTED_THRESHOLD = 0.65   # 40-65 → distracted
    DANGEROUS_THRESHOLD = 0.65    # 高于此 → dangerous

    # 趋势参数
    WINDOW_SIZE = 30              # 滑动窗口（秒）
    TREND_WINDOW = 10             # 趋势检测：最近10帧

    def __init__(self):
        self.current_state = "normal"
        self.previous_state = "normal"
        self.state_start_time = time.time()
        self.consecutive_warnings = 0

        # 7 维状态向量
        self.state_vector = {
            "perclos": 0.0,
            "blink_rate": 0.0,
            "head_pitch": 0.0,
            "head_yaw": 0.0,
            "gaze_direction": "center",
            "gesture_freq": 0.0,
            "speech_emotion": "neutral",
        }

        # 滑动窗口历史
        self.history: deque = deque(maxlen=self.WINDOW_SIZE)
        self.last_update_time = time.time()

    # ── 公共接口 ──

    def update(self, sensor_data: dict) -> str:
        """
        更新状态向量，计算风险分数，执行状态转移。

        Args:
            sensor_data: 包含任意 7 维数据的字典

        Returns:
            当前状态字符串
        """
        # 更新向量
        for key in self.state_vector:
            if key in sensor_data:
                self.state_vector[key] = sensor_data[key]

        # 记录历史
        now = time.time()
        self.history.append({
            "time": now,
            "vector": self.state_vector.copy(),
        })
        self.last_update_time = now

        # 计算风险分数
        risk_score = self._compute_risk_score()
        trend = self._detect_trend()

        # 状态转移
        self.previous_state = self.current_state
        new_state = self._determine_state(risk_score, trend)
        self._transition(new_state)

        return self.current_state

    def get_state(self) -> str:
        return self.current_state

    def get_vector(self) -> dict:
        return self.state_vector.copy()

    def get_risk_score(self) -> float:
        return self._compute_risk_score()

    def get_trend(self) -> str:
        """返回当前趋势：improving / stable / declining / deteriorating"""
        return self._detect_trend()

    def confirm_recovery(self, method: str = "gesture") -> bool:
        """
        尝试确认恢复：distracted/attention_declining → normal

        只在非 dangerous 状态下允许恢复，dangerous 需要连续多帧正常才自动恢复。
        """
        if self.current_state == "dangerous":
            # dangerous 状态需要连续 5 帧低风险才能恢复
            recent_risks = [
                self._compute_risk_score_from_vector(h["vector"])
                for h in list(self.history)[-5:]
            ]
            if len(recent_risks) >= 5 and all(r < self.NORMAL_THRESHOLD for r in recent_risks):
                self._transition("normal")
                return True
            return False

        if self.current_state in ("distracted", "attention_declining"):
            self._transition("normal")
            logger.info(f"驾驶员通过 {method} 确认恢复注意力")
            return True

        return False

    # ── 内部逻辑 ──

    def _compute_risk_score(self) -> float:
        """从当前状态向量计算加权风险分数 (0.0 ~ 1.0)"""
        return self._compute_risk_score_from_vector(self.state_vector)

    def _compute_risk_score_from_vector(self, vector: dict) -> float:
        """从指定向量计算风险分数"""
        score = 0.0

        # PERCLOS (0~1 直接贡献)
        score += vector.get("perclos", 0) * self.WEIGHTS["perclos"]

        # 眨眼频率（正常 ~15次/分，>25异常，>30严重）
        blink = vector.get("blink_rate", 15)
        blink_factor = max(0, (blink - 15) / 15)  # 15→0, 30→1
        score += min(blink_factor, 1.0) * self.WEIGHTS["blink_rate"]

        # 头部俯仰（>20° 可能低头看手机）
        pitch = abs(vector.get("head_pitch", 0))
        score += min(pitch / 30, 1.0) * self.WEIGHTS["head_pitch"]

        # 头部偏航（>25° 看窗外）
        yaw = abs(vector.get("head_yaw", 0))
        score += min(yaw / 35, 1.0) * self.WEIGHTS["head_yaw"]

        # 视线方向
        gaze = vector.get("gaze_direction", "center")
        if gaze != "center":
            # 视线偏离越久分数越高（由上层传入 duration 信息）
            score += 0.8 * self.WEIGHTS["gaze_direction"]

        # 手势频率（异常高频可能焦躁）
        gesture_freq = vector.get("gesture_freq", 0)
        score += min(gesture_freq / 10, 1.0) * self.WEIGHTS["gesture_freq"]

        # 语音情绪
        emotion = vector.get("speech_emotion", "neutral")
        emotion_map = {"neutral": 0.0, "positive": 0.0, "questioning": 0.1, "negative": 0.3, "angry": 0.5}
        score += emotion_map.get(emotion, 0) * self.WEIGHTS["speech_emotion"]

        return round(min(score, 1.0), 3)

    def _detect_trend(self) -> str:
        """
        从滑动窗口检测风险变化趋势。

        Returns:
            "improving" — 风险在下降
            "stable" — 变化不大
            "declining" — 风险在上升（预警）
            "deteriorating" — 风险快速上升（严重）
        """
        if len(self.history) < self.TREND_WINDOW:
            return "stable"

        recent = list(self.history)[-self.TREND_WINDOW:]
        first_score = self._compute_risk_score_from_vector(recent[0]["vector"])
        last_score = self._compute_risk_score_from_vector(recent[-1]["vector"])

        delta = last_score - first_score

        if delta > 0.15:
            return "deteriorating"
        elif delta > 0.05:
            return "declining"
        elif delta < -0.05:
            return "improving"
        else:
            return "stable"

    def _determine_state(self, risk_score: float, trend: str) -> str:
        """根据风险分数和趋势决定新状态"""
        # 趋势加成
        trend_bonus = {"deteriorating": 0.15, "declining": 0.05,
                       "stable": 0, "improving": -0.05}

        adjusted = risk_score + trend_bonus.get(trend, 0)

        if adjusted >= self.DANGEROUS_THRESHOLD:
            return "dangerous"
        elif adjusted >= self.DISTRACTED_THRESHOLD:
            return "distracted"
        elif adjusted >= self.DECLINING_THRESHOLD:
            return "attention_declining"
        else:
            return "normal"

    def _transition(self, new_state: str):
        """执行状态转移，记录日志"""
        if new_state == self.current_state:
            return

        old = self.current_state
        self.current_state = new_state
        self.state_start_time = time.time()

        # 上升告警
        severity_order = {"normal": 0, "attention_declining": 1, "distracted": 2, "dangerous": 3}
        if severity_order.get(new_state, 0) > severity_order.get(old, 0):
            self.consecutive_warnings += 1
            logger.warning(
                f"⚠️ 状态恶化: {old} → {new_state} "
                f"(风险分: {self._compute_risk_score():.2f}, 趋势: {self._detect_trend()})"
            )
        else:
            if self.consecutive_warnings > 0:
                logger.info(f"✅ 状态恢复: {old} → {new_state}")
            self.consecutive_warnings = 0
