"""
疲劳趋势预测器 — PERCLOS + 眨眼频率 + 多维状态向量 + 滑动窗口趋势分析

接口规范：
  batch_predict(eye_frames) -> {"fatigue_score": 0-100, "level": "normal/warning/danger", ...}
  FatiguePredictor.update(perclos, blink_rate, ...) -> 趋势预测结果

7 维状态向量：
  1. PERCLOS          — 闭眼时长占比 (0~1)
  2. 眨眼频率          — 每分钟眨眼次数
  3. 平均睁眼时长      — 秒
  4. 头部 yaw 方差     — 偏转抖动程度
  5. 头部 pitch 方差  — 点头频率
  6. 视线偏移频率      — 视线离开前方次数
  7. 告警响应延迟      — 秒（模拟值，无实测时用 -1 占位）

滑动窗口：默认 60 帧（假设 1 帧/秒），计算线性回归斜率判断趋势。
"""
import logging
import math
from collections import deque
from typing import Optional

logger = logging.getLogger(__name__)

# ── 阈值常量 ──
EAR_THRESHOLD = 0.26          # 闭眼判定阈值
FATIGUE_SCORE_WARN = 40       # 注意力下降阈值
FATIGUE_SCORE_DANGER = 70     # 重度疲劳阈值
MIN_FRAMES_FOR_TREND = 10     # 趋势分析最少帧数


def _linear_regression_slope(values: list[float]) -> float:
    """简单一元线性回归斜率，返回趋势方向。"""
    n = len(values)
    if n < 2:
        return 0.0
    x_mean = (n - 1) / 2
    y_mean = sum(values) / n
    numerator = sum((i - x_mean) * (v - y_mean) for i, v in enumerate(values))
    denominator = sum((i - x_mean) ** 2 for i in range(n))
    if denominator == 0:
        return 0.0
    return numerator / denominator


def _extract_features(eye_frames: list[dict]) -> dict:
    """从眼动帧序列提取 7 维状态向量。"""
    if not eye_frames:
        return {
            "perclos": 0.0, "blink_rate": 12.0, "avg_eye_open": 0.35,
            "yaw_var": 0.0, "pitch_var": 0.0, "gaze_off_freq": 0,
            "alert_delay": -1.0,
        }

    total = len(eye_frames)
    close_count = 0
    blink_times = 0
    ear_values = []
    yaw_values = []
    pitch_values = []
    gaze_off_count = 0
    last_ear_low = False

    for frame in eye_frames:
        ear = frame.get("ear", 0.5)
        ear_values.append(ear)

        if ear < EAR_THRESHOLD:
            close_count += 1
            if not last_ear_low:
                blink_times += 1
                last_ear_low = True
        else:
            last_ear_low = False

        yaw_values.append(frame.get("yaw", 0))
        pitch_values.append(frame.get("pitch", 0))

        gaze = frame.get("gaze", "center")
        if gaze != "center":
            gaze_off_count += 1

    # 方差计算
    def _variance(vals: list[float]) -> float:
        if len(vals) < 2:
            return 0.0
        m = sum(vals) / len(vals)
        return sum((v - m) ** 2 for v in vals) / len(vals)

    perclos = round(close_count / total, 3)
    # 假设窗口为 60 秒，1 帧/秒，换算成每分钟眨眼次数
    blink_rate = round(blink_times * (60.0 / max(total, 1)), 1)
    avg_eye_open = round(sum(ear_values) / total, 3)

    return {
        "perclos": perclos,
        "blink_rate": blink_rate,
        "avg_eye_open": avg_eye_open,
        "yaw_var": round(_variance(yaw_values), 2),
        "pitch_var": round(_variance(pitch_values), 2),
        "gaze_off_freq": gaze_off_count,
        "alert_delay": -1.0,  # 无实测时占位
    }


def _score_features(f: dict) -> float:
    """
    根据多维特征计算疲劳分数 (0-100)。

    权重分配：
      PERCLOS        ×35  （最核心指标）
      眨眼频率异常    ×20  （过低=嗜睡，过高=疲劳性眨眼）
      平均睁眼时长    ×15  （睁眼越小越疲劳）
      头部 yaw 方差   ×10  （偏转抖动）
      头部 pitch 方差  ×10  （点头）
      视线偏移频率    ×10  （注意力涣散）
    """
    score = 0.0

    # 1. PERCLOS: 0~0.08 正常, 0.08~0.15 注意力下降, >0.15 危险
    p = f["perclos"]
    if p > 0.15:
        score += 35
    elif p > 0.08:
        score += 20 + (p - 0.08) / 0.07 * 15
    else:
        score += p / 0.08 * 20

    # 2. 眨眼频率: 正常 10-20/min, <8 嗜睡, >25 疲劳性
    br = f["blink_rate"]
    if br < 8:
        score += 20
    elif br > 25:
        score += 15 + min((br - 25) / 10, 1) * 5
    elif 10 <= br <= 20:
        score += 5
    else:
        score += 10

    # 3. 平均睁眼时长: EAR 越低越疲劳
    aeo = f["avg_eye_open"]
    if aeo < 0.2:
        score += 15
    elif aeo < 0.28:
        score += 8 + (0.28 - aeo) / 0.08 * 7
    else:
        score += 0

    # 4. 头部 yaw 方差: 抖动越大越疲劳
    yv = f["yaw_var"]
    if yv > 50:
        score += 10
    elif yv > 20:
        score += 5 + (yv - 20) / 30 * 5
    else:
        score += 0

    # 5. 头部 pitch 方差: 点头
    pv = f["pitch_var"]
    if pv > 50:
        score += 10
    elif pv > 20:
        score += 5 + (pv - 20) / 30 * 5
    else:
        score += 0

    # 6. 视线偏移频率
    gof = f["gaze_off_freq"]
    total = 60  # 假设 60 帧
    off_ratio = gof / total
    if off_ratio > 0.3:
        score += 10
    elif off_ratio > 0.1:
        score += 5 + (off_ratio - 0.1) / 0.2 * 5
    else:
        score += 0

    return round(min(score, 100), 1)


def batch_predict(eye_frames: list[dict]) -> dict:
    """
    无状态批量预测接口（被 safety_agent 调用）。

    Args:
        eye_frames: [{"ear":0.3, "yaw":5, "pitch":10, "gaze":"center"}, ...]

    Returns:
        {"fatigue_score": 0-100, "level": "normal/warning/danger",
         "features": {...}, "trend": "stable"}
    """
    # 空输入短路：无数据 = 无疲劳
    if not eye_frames:
        return {
            "fatigue_score": 0,
            "level": "normal",
            "features": _extract_features([]),
            "trend": "stable",
        }

    features = _extract_features(eye_frames)
    score = _score_features(features)

    if score >= FATIGUE_SCORE_DANGER:
        level = "danger"
    elif score >= FATIGUE_SCORE_WARN:
        level = "warning"
    else:
        level = "normal"

    return {
        "fatigue_score": score,
        "level": level,
        "features": features,
        "trend": "stable",  # 无状态模式无法算趋势，默认稳定
    }


class FatiguePredictor:
    """有状态的趋势预测器，维护滑动窗口。"""

    def __init__(self, window_size: int = 60):
        self.window_size = window_size
        # 滑动窗口存每帧的 fatigue_score
        self._score_history: deque = deque(maxlen=window_size)
        # 也存原始指标，用于详细趋势分析
        self._perclos_history: deque = deque(maxlen=window_size)
        self._blink_rate_history: deque = deque(maxlen=window_size)

    def update(self, perclos: float, blink_rate: float,
               avg_eye_open: float = 0.3, yaw_var: float = 0,
               pitch_var: float = 0, gaze_off_freq: int = 0) -> dict:
        """
        更新滑动窗口并返回趋势预测结果。

        Returns:
            {"perclos", "blink_rate", "fatigue_score", "fatigue_level",
             "trend", "prediction_seconds"}
        """
        self._perclos_history.append(perclos)
        self._blink_rate_history.append(blink_rate)

        # 计算当前帧的疲劳分数
        features = {
            "perclos": perclos, "blink_rate": blink_rate,
            "avg_eye_open": avg_eye_open, "yaw_var": yaw_var,
            "pitch_var": pitch_var, "gaze_off_freq": gaze_off_freq,
            "alert_delay": -1.0,
        }
        score = _score_features(features)
        self._score_history.append(score)

        # 趋势分析：对 score 历史做线性回归
        if len(self._score_history) >= MIN_FRAMES_FOR_TREND:
            slope = _linear_regression_slope(list(self._score_history))
            if slope > 0.5:
                trend = "rising"
            elif slope < -0.5:
                trend = "declining"
            else:
                trend = "stable"
        else:
            trend = "stable"  # 数据不足，默认稳定

        # 等级判定
        if score >= FATIGUE_SCORE_DANGER:
            level = "danger"
        elif score >= FATIGUE_SCORE_WARN:
            level = "warning"
        else:
            level = "normal"

        # 预测：如果趋势上升，估算多久进入危险
        prediction_seconds = 0
        if trend == "rising" and level != "danger":
            slope = _linear_regression_slope(list(self._score_history))
            if slope > 0:
                remaining = FATIGUE_SCORE_DANGER - score
                prediction_seconds = int(remaining / slope)

        return {
            "perclos": perclos,
            "blink_rate": blink_rate,
            "fatigue_score": score,
            "fatigue_level": level,
            "trend": trend,
            "prediction_seconds": prediction_seconds,
        }


# ── 自测 ──
if __name__ == "__main__":
    print("=== FatiguePredictor 自测 ===\n")

    # 测试 1: batch_predict 正常工况
    print("--- 1. batch_predict 正常工况 ---")
    normal_frames = [{"ear": 0.35, "yaw": 2, "pitch": 5, "gaze": "center"}] * 30
    r = batch_predict(normal_frames)
    print(f"  score={r['fatigue_score']}, level={r['level']}")
    assert r["level"] == "normal", f"期望 normal, 实际 {r['level']}"
    print("  ✅ PASS\n")

    # 测试 2: batch_predict 危险工况（高 PERCLOS + 低眨眼率）
    print("--- 2. batch_predict 危险工况 ---")
    danger_frames = [{"ear": 0.18, "yaw": 8, "pitch": 15, "gaze": "left"}] * 30
    r = batch_predict(danger_frames)
    print(f"  score={r['fatigue_score']}, level={r['level']}")
    assert r["level"] == "danger", f"期望 danger, 实际 {r['level']}"
    print("  ✅ PASS\n")

    # 测试 3: batch_predict 空输入
    print("--- 3. batch_predict 空输入 ---")
    r = batch_predict([])
    print(f"  score={r['fatigue_score']}, level={r['level']}")
    assert r["level"] == "normal", f"期望 normal, 实际 {r['level']}"
    assert r["fatigue_score"] == 0, f"期望 0, 实际 {r['fatigue_score']}"
    print("  ✅ PASS\n")

    # 测试 4: FatiguePredictor 有状态趋势 — 上升
    print("--- 4. FatiguePredictor 趋势上升 ---")
    fp = FatiguePredictor(window_size=60)
    # 模拟 60 帧，PERCLOS 从 0.02 逐步上升到 0.18
    for i in range(60):
        perclos = 0.02 + (0.16 * i / 59)
        r = fp.update(perclos=perclos, blink_rate=8)
    print(f"  score={r['fatigue_score']}, level={r['fatigue_level']}, trend={r['trend']}")
    assert r["trend"] == "rising", f"期望 rising, 实际 {r['trend']}"
    print("  ✅ PASS\n")

    # 测试 5: FatiguePredictor 趋势稳定
    print("--- 5. FatiguePredictor 趋势稳定 ---")
    fp2 = FatiguePredictor(window_size=60)
    for i in range(60):
        r = fp2.update(perclos=0.05, blink_rate=15)
    print(f"  score={r['fatigue_score']}, level={r['fatigue_level']}, trend={r['trend']}")
    assert r["trend"] == "stable", f"期望 stable, 实际 {r['trend']}"
    print("  ✅ PASS\n")

    print("=== 全部测试通过 ✅ ===")
