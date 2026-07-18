"""
本地决策引擎 — 不依赖网络的毫秒级决策

覆盖场景：
- 眼动分析：偏离检测 + 严重度分级
- 手势映射：15+ 手势 → action_code
- 语音关键词：20+ 常见指令 → action_code
- 综合判断：多模态信号融合
"""
import logging

logger = logging.getLogger(__name__)

# ── 手势映射表 ──

GESTURE_MAP = {
    # 确认/取消类
    "Thumbs Up": "confirm",
    "OK": "confirm",
    "Thumbs Down": "cancel",
    "Close": "cancel",
    "Peace": "cancel",

    # 功能控制类
    "Open": "PlayMusic",
    "Point": "TurnOnAC",
    "Fist": "StopMusic",
    "Palm": "Navigate",
    "Swipe Left": "previous_track",
    "Swipe Right": "next_track",
    "Swipe Up": "volume_up",
    "Swipe Down": "volume_down",

    # 安全相关
    "Wave": "attention_confirm",  # 挥手确认注意力恢复
    "Stop": "emergency_stop",    # 紧急停止
}

# ── 语音关键词映射表 ──

SPEECH_KEYWORD_MAP = {
    # 空调
    "开空调": "TurnOnAC", "打开空调": "TurnOnAC", "太热": "TurnOnAC",
    "关空调": "TurnOffAC", "关闭空调": "TurnOffAC", "太冷": "TurnOffAC",
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

# ── 眼动分析参数 ──

GAZE_SEVERITY = {
    "mild": {"threshold": 2.0, "action": "attention_hint", "alert": "请保持视线在前方"},
    "moderate": {"threshold": 3.0, "action": "distract", "alert": "视线偏离道路，请注意"},
    "severe": {"threshold": 5.0, "action": "distract", "alert": "严重分心！请立即注视前方"},
}


def decide_locally(context: dict) -> dict:
    """
    本地推理主入口 — 根据触发类型分发。

    Args:
        context: {"trigger": "gaze"|"gesture"|"speech"|"multi",
                  "data": {...trigger-specific data...}}

    Returns:
        {"action_code": "...", "confidence": 0.95, "source": "local",
         "alert": "..." (仅告警场景)}
    """
    trigger = context.get("trigger", "")
    data = context.get("data", {})

    if trigger == "gaze":
        return _handle_gaze(data)
    elif trigger == "gesture":
        return _handle_gesture(data)
    elif trigger == "speech":
        return _handle_speech(data)
    elif trigger == "multi":
        return _handle_multi(data)

    return {"action_code": "unknown", "confidence": 0.0, "source": "local"}


# ── 各模态处理 ──

def _handle_gaze(data: dict) -> dict:
    """眼动分析：偏离方向 + 持续时间 → 严重度分级"""
    state = data.get("state", "center")
    duration = float(data.get("duration", 0))

    if state == "center":
        return {"action_code": "normal", "confidence": 0.95, "source": "local"}

    # 偏离不足 2 秒：仅标记方向，不告警
    if duration < 2.0:
        return {"action_code": "normal", "confidence": 0.8, "source": "local"}

    # 按严重度分级
    matched = "mild"
    for level, params in sorted(GAZE_SEVERITY.items(),
                                 key=lambda x: x[1]["threshold"]):
        if duration >= params["threshold"]:
            matched = level
        else:
            break

    params = GAZE_SEVERITY[matched]
    return {
        "action_code": params["action"],
        "confidence": min(0.8 + duration * 0.03, 0.98),
        "source": "local",
        "alert": f"{params['alert']}（{duration:.0f}秒）",
        "severity": matched,
    }


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
    - 眼动偏离 + 任何手势/语音 → 眼动优先（安全问题）
    - 手势 + 语音不一致 → 语音优先（更明确）
    - 只有手势 → 手势为准
    """
    gaze = data.get("gaze", {})
    gesture = data.get("gesture", {})
    speech = data.get("speech", {})

    # 安全优先：眼动偏离 → 忽略其他模态
    gaze_state = gaze.get("state", "center")
    if gaze_state != "center" and gaze.get("duration", 0) > 2:
        return _handle_gaze(gaze)

    # 语音优先
    speech_text = speech.get("text", "")
    if speech_text:
        return _handle_speech(speech)

    # 手势兜底
    gesture_name = gesture.get("gesture", "")
    if gesture_name:
        return _handle_gesture(gesture)

    return {"action_code": "unknown", "confidence": 0.0, "source": "local"}
