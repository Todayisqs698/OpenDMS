"""
离线降级处理 — 云端不可用时自动切换

设计原则：
- 安全功能永不降级（分心检测/疲劳预警本地运行，不受影响）
- 交互功能模板兜底（语音指令用关键词匹配，手势用本地分类器）
- 知识问答优雅降级（返回预设常见问题答案，并提示离线状态）
- 网络恢复自动切回
"""
import logging

logger = logging.getLogger(__name__)

# ── 离线模板响应库 ──

OFFLINE_TEMPLATES = {
    # 常见操作指令
    "TurnOnAC": "空调已开启（离线模式）",
    "TurnOffAC": "空调已关闭（离线模式）",
    "PlayMusic": "音乐播放中（离线模式）",
    "StopMusic": "音乐已暂停（离线模式）",
    "Navigate": "导航功能需要网络连接，当前为离线模式",

    # 安全相关（本地运行，不走这里）
    "distract": "检测到分心驾驶，请注视前方道路",
    "NoticeRoad": "注意力已恢复，请保持专注",

    # 知识问答
    "knowledge_qa": "当前为离线模式，复杂问题请在网络恢复后重试。常见故障灯说明：\n"
                    "- 黄色感叹号：胎压异常\n"
                    "- 红色机油灯：机油压力过低\n"
                    "- 黄色发动机灯：发动机系统故障\n"
                    "- 红色电池灯：充电系统故障",

    # 默认
    "unknown": "系统运行在离线模式，语音和手势指令可正常使用",
    "fallback": "离线模式：安全功能正常，网络功能暂不可用",
}

# 离线模式下的语音关键词→动作映射（比在线版更精简）
OFFLINE_SPEECH_MAP = {
    "开空调": "TurnOnAC", "打开空调": "TurnOnAC",
    "关空调": "TurnOffAC", "关闭空调": "TurnOffAC",
    "放音乐": "PlayMusic", "播放音乐": "PlayMusic",
    "关音乐": "StopMusic", "暂停": "StopMusic",
    "导航": "Navigate", "去": "Navigate",
}


def handle_fallback(context: dict) -> dict:
    """
    离线降级处理。

    Args:
        context: {"action_code": "...", "trigger": "...", "text": "...", ...}

    Returns:
        {"action_code": "...", "recommendation_text": "...", "source": "fallback", "offline": True}
    """
    logger.warning("离线降级模式已激活")

    action = context.get("action_code", "unknown")
    text = context.get("text", "")

    # 尝试语音关键词匹配
    if not action or action == "unknown":
        action = _match_speech(text)

    # 取模板回复
    recommendation = OFFLINE_TEMPLATES.get(
        action,
        OFFLINE_TEMPLATES["fallback"]
    )

    return {
        "action_code": action,
        "recommendation_text": recommendation,
        "source": "fallback",
        "offline": True,
        "confidence": 0.7 if action in OFFLINE_TEMPLATES else 0.3,
    }


def get_offline_response(action_code: str) -> str:
    """获取指定动作的离线回复文本"""
    return OFFLINE_TEMPLATES.get(action_code, OFFLINE_TEMPLATES["unknown"])


def _match_speech(text: str) -> str:
    """离线语音关键词匹配"""
    if not text:
        return "unknown"
    for keyword, action in OFFLINE_SPEECH_MAP.items():
        if keyword in text:
            return action
    return "unknown"
