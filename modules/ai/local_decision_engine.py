"""
本地决策引擎 — 不依赖网络的毫秒级决策

覆盖场景：
- 5 类独立告警：多人 / 离开摄像头 / 疲劳 / 头部偏离 / 视线偏离
- 每类独立计时、独立阈值（2s mild / 3s moderate / 5s severe）
- 手势映射：15+ 手势 → action_code
- 语音关键词：20+ 常见指令 → action_code
- 综合判断：多模态信号融合
"""
import logging

logger = logging.getLogger(__name__)

# ── 手势映射表 ──

GESTURE_MAP = {
    # 空调控制
    "open_ac": "TurnOnAC",
    "close_ac": "TurnOffAC",
    "confirm_ac": "TurnOnAC",

    # 确认/取消类
    "thumbs_up": "confirm",
    "ok_sign": "confirm",
    "thumbs_down": "cancel",
    "peace": "cancel",

    # 功能控制类
    "index_point": "attention",
    "three_fingers": "mode_3",
    "four_fingers": "mode_4",
    "pinch": "zoom_in",
    "swipe_left": "previous_track",
    "swipe_right": "next_track",
    "palm_up": "volume_up",
    "palm_down": "volume_down",

    # 安全相关
    "call_me": "call",
    "rock_on": "mute",
    "stop": "emergency_stop",
}

# ── 语音关键词映射表 ──

SPEECH_KEYWORD_MAP = {
    # 空调
    "开空调": "TurnOnAC", "打开空调": "TurnOnAC", "太热": "TurnOnAC",
    "好热": "TurnOnAC", "外面天气好热": "TurnOnAC",
    "关空调": "TurnOffAC", "关闭空调": "TurnOffAC", "太冷": "TurnOffAC",
    "好冷": "TurnOffAC", "现在好冷": "TurnOffAC",
    "调高温度": "temp_up", "调低温度": "temp_down",

    # 音乐
    "放音乐": "PlayMusic", "播放音乐": "PlayMusic", "来首歌": "PlayMusic",
    "关音乐": "StopMusic", "暂停": "StopMusic", "停下": "StopMusic",
    "下一首": "next_track", "上一首": "previous_track",
    "音量加大": "volume_up", "音量减小": "volume_down",

    # 导航
    "导航": "Navigate", "去": "Navigate", "怎么走": "Navigate",

    # 车窗/灯光
    "开车窗": "window_open", "关车窗": "window_close",
    "开灯": "light_on", "关灯": "light_off",

    # 安全确认
    "我在看路": "NoticeRoad", "注意到了": "NoticeRoad",
    "已注意": "NoticeRoad", "好的": "NoticeRoad",

    # 知识查询（标记为需要RAG）
    "什么意思": "knowledge_qa", "怎么办": "knowledge_qa",
    "故障": "knowledge_qa", "报警": "knowledge_qa",
}

# ── 5 类告警阈值（统一 2/3/5 秒三级） ──

ALERT_CATEGORIES = {
    "crowd": {
        "label": "crowd", "label_zh": "多人", "label_en": "Multiple Faces",
        "alert": "检测到多人，请确认驾驶员身份",
        # 多人极其危险，触发即 severe
        "severities": {
            "mild":     {"threshold": 0.5, "action": "attention_hint"},
            "moderate": {"threshold": 1.0, "action": "distract"},
            "severe":   {"threshold": 2.0, "action": "distract"},
        },
    },
    "absence": {
        "label": "absence", "label_zh": "离开摄像头", "label_en": "Left Camera",
        "alert": "驾驶员离开摄像头范围",
        "severities": {
            "mild":     {"threshold": 2.0, "action": "attention_hint"},
            "moderate": {"threshold": 3.0, "action": "distract"},
            "severe":   {"threshold": 5.0, "action": "distract"},
        },
    },
    "fatigue": {
        "label": "fatigue", "label_zh": "疲劳", "label_en": "Fatigue",
        "alert": "驾驶员疲劳驾驶，请注意休息",
        "severities": {
            "mild":     {"threshold": 2.0, "action": "attention_hint"},
            "moderate": {"threshold": 3.0, "action": "distract"},
            "severe":   {"threshold": 5.0, "action": "distract"},
        },
    },
    "head": {
        "label": "head_deviation", "label_zh": "头部偏离", "label_en": "Head Deviation",
        "alert": "头部偏离前方，请注意",
        "severities": {
            "mild":     {"threshold": 2.0, "action": "attention_hint"},
            "moderate": {"threshold": 3.0, "action": "distract"},
            "severe":   {"threshold": 5.0, "action": "distract"},
        },
    },
    "gaze": {
        "label": "gaze_deviation", "label_zh": "视线偏离", "label_en": "Gaze Deviation",
        "alert": "视线偏离道路，请注意",
        "severities": {
            "mild":     {"threshold": 2.0, "action": "attention_hint"},
            "moderate": {"threshold": 3.0, "action": "distract"},
            "severe":   {"threshold": 5.0, "action": "distract"},
        },
    },
}


def _severity_for(category: str, duration: float) -> tuple:
    """
    根据告警类别和持续时间，返回 (severity_level, params_dict)。
    未达到 mild 阈值返回 (None, None)。
    """
    cat = ALERT_CATEGORIES[category]
    matched_level = None
    matched_params = None
    for level in ("mild", "moderate", "severe"):
        params = cat["severities"][level]
        if duration >= params["threshold"]:
            matched_level = level
            matched_params = params
        else:
            break
    return matched_level, matched_params


def _build_alert(category: str, severity: str, duration: float) -> dict:
    """构建标准告警返回结构"""
    cat = ALERT_CATEGORIES[category]
    params = cat["severities"][severity]
    return {
        "action_code": params["action"],
        "confidence": min(0.8 + duration * 0.03, 0.98),
        "source": "local",
        "alert": f"{cat['alert']}（{duration:.0f}秒）",
        "severity": severity,
        "alert_category": category,
        "alert_label": cat["label"],
    }


# ── 5 类告警入口函数 ──

def check_crowd(duration: float, face_count: int = 0) -> dict:
    """多人检测"""
    if face_count < 2:
        return {"action_code": "normal", "confidence": 0.95, "source": "local",
                "alert_category": "crowd", "alert_label": "多人"}
    level, params = _severity_for("crowd", duration)
    if level is None:
        return {"action_code": "normal", "confidence": 0.8, "source": "local",
                "alert_category": "crowd", "alert_label": "多人"}
    return _build_alert("crowd", level, duration)


def check_absence(duration: float) -> dict:
    """离开摄像头检测（无人脸）"""
    level, params = _severity_for("absence", duration)
    if level is None:
        return {"action_code": "normal", "confidence": 0.8, "source": "local",
                "alert_category": "absence", "alert_label": "离开摄像头"}
    return _build_alert("absence", level, duration)


def check_fatigue(duration: float) -> dict:
    """疲劳检测（由 camera.py 计算 PERCLOS 后调用）"""
    level, params = _severity_for("fatigue", duration)
    if level is None:
        return {"action_code": "normal", "confidence": 0.8, "source": "local",
                "alert_category": "fatigue", "alert_label": "疲劳"}
    return _build_alert("fatigue", level, duration)


def check_head_deviation(state: str, duration: float) -> dict:
    """
    头部偏离检测。
    仅当头部姿态明显偏转（含 left/right/up/down）时触发。
    纯虹膜移动（gaze_state 不含 head_yaw 偏转）不算头部偏离。
    """
    if state == "center":
        return {"action_code": "normal", "confidence": 0.95, "source": "local",
                "alert_category": "head", "alert_label": "头部偏离"}

    # 判断是否为头部偏转（所有非 center 都算）
    level, params = _severity_for("head", duration)
    if level is None:
        return {"action_code": "normal", "confidence": 0.8, "source": "local",
                "alert_category": "head", "alert_label": "头部偏离"}
    cat = ALERT_CATEGORIES["head"]
    direction_text = {"left": "左偏", "right": "右偏", "up": "上仰", "down": "下俯"}
    dir_label = direction_text.get(state, state)
    return {
        "action_code": params["action"],
        "confidence": min(0.8 + duration * 0.03, 0.98),
        "source": "local",
        "alert": f"头部{dir_label}，{cat['alert']}（{duration:.0f}秒）",
        "severity": level,
        "alert_category": "head",
        "alert_label": cat["label"],
        "head_direction": state,
    }


def check_gaze_deviation(state: str, duration: float) -> dict:
    """
    视线偏离检测（纯虹膜移动）。
    仅当 gaze_state 不为 center 且不是头部主导的偏转时触发。
    """
    if state == "center":
        return {"action_code": "normal", "confidence": 0.95, "source": "local",
                "alert_category": "gaze", "alert_label": "视线偏离"}

    level, params = _severity_for("gaze", duration)
    if level is None:
        return {"action_code": "normal", "confidence": 0.8, "source": "local",
                "alert_category": "gaze", "alert_label": "视线偏离"}
    cat = ALERT_CATEGORIES["gaze"]
    dir_map = {
        "left": "左偏", "right": "右偏", "up": "上偏", "down": "下偏",
        "up_left": "左上偏", "up_right": "右上偏",
        "down_left": "左下偏", "down_right": "右下偏",
    }
    dir_label = dir_map.get(state, state)
    return {
        "action_code": params["action"],
        "confidence": min(0.8 + duration * 0.03, 0.98),
        "source": "local",
        "alert": f"视线{dir_label}，{cat['alert']}（{duration:.0f}秒）",
        "severity": level,
        "alert_category": "gaze",
        "alert_label": cat["label"],
        "gaze_direction": state,
    }


def decide_locally(context: dict) -> dict:
    """
    本地推理主入口 — 根据触发类型分发。

    Args:
        context: {"trigger": "gaze"|"gesture"|"speech"|"multi"|"fatigue"|"absence"|"crowd",
                  "data": {...trigger-specific data...}}

    Returns:
        {"action_code": "...", "confidence": 0.95, "source": "local",
         "alert": "...", "severity": "...", "alert_category": "...", "alert_label": "..."}
    """
    trigger = context.get("trigger", "")
    data = context.get("data", {})

    if trigger == "crowd":
        return check_crowd(data.get("duration", 0), data.get("face_count", 0))
    elif trigger == "absence":
        return check_absence(data.get("duration", 0))
    elif trigger == "fatigue":
        return check_fatigue(data.get("duration", 0))
    elif trigger == "head":
        return check_head_deviation(data.get("state", "center"), data.get("duration", 0))
    elif trigger == "gaze":
        return check_gaze_deviation(data.get("state", "center"), data.get("duration", 0))
    elif trigger == "gesture":
        return _handle_gesture(data)
    elif trigger == "speech":
        return _handle_speech(data)
    elif trigger == "multi":
        return _handle_multi(data)

    return {"action_code": "unknown", "confidence": 0.0, "source": "local"}


# ── 各模态处理 ──

def _handle_gesture(data: dict) -> dict:
    """手势识别：手势名 → action_code"""
    gesture = data.get("gesture", "")
    confidence = float(data.get("confidence", 0.0))

    if confidence < 0.6:
        return {"action_code": "unknown", "confidence": confidence, "source": "local"}

    action = GESTURE_MAP.get(gesture, "unknown")
    return {
        "action_code": action,
        "confidence": confidence,
        "source": "local",
    }


def _handle_speech(data: dict) -> dict:
    """语音关键词匹配"""
    text = data.get("text", "").strip()
    if not text:
        return {"action_code": "unknown", "confidence": 0.0, "source": "local"}

    # 精确匹配
    for keyword, action in SPEECH_KEYWORD_MAP.items():
        if keyword in text:
            return {
                "action_code": action,
                "confidence": 0.85 if len(keyword) >= 3 else 0.7,
                "source": "local",
            }

    # 未匹配 → 需要云端理解
    return {
        "action_code": "semantic_query",
        "confidence": 0.5,
        "source": "local",
        "hint": "local_keyword_miss",
    }


def _handle_multi(data: dict) -> dict:
    """
    多模态综合判断。

    规则：
    - 多人/离开/疲劳 → 最高优先级
    - 眼动偏离 + 任何手势/语音 → 眼动优先（安全问题）
    - 手势 + 语音不一致 → 语音优先（更明确）
    - 只有手势 → 手势为准
    """
    gaze = data.get("gaze", {})
    gesture = data.get("gesture", {})
    speech = data.get("speech", {})

    # 安全最高优先：多人/离开/疲劳
    crowd = data.get("crowd", {})
    absence = data.get("absence", {})
    fatigue = data.get("fatigue", {})

    if crowd.get("active"):
        return check_crowd(crowd.get("duration", 0), crowd.get("face_count", 0))
    if absence.get("active"):
        return check_absence(absence.get("duration", 0))
    if fatigue.get("active"):
        return check_fatigue(fatigue.get("duration", 0))

    # 眼动优先
    gaze_state = gaze.get("state", "center")
    if gaze_state != "center" and gaze.get("duration", 0) > 2:
        return check_gaze_deviation(gaze_state, gaze.get("duration", 0))

    # 语音优先
    speech_text = speech.get("text", "")
    if speech_text:
        return _handle_speech(speech)

    # 手势兜底
    gesture_name = gesture.get("gesture", "")
    if gesture_name:
        return _handle_gesture(gesture)

    return {"action_code": "unknown", "confidence": 0.0, "source": "local"}
