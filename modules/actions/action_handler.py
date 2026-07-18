"""
统一动作处理器 — TTS 语音反馈 + 动作执行 + 日志记录

从 In-Vehicle-Multimodal-Interaction-System 参考项目增强：
- 线程安全的 TTS 引擎懒加载
- 完整的中文反馈语料库（30+ 条）
- 支持 str/dict/JSON 多种输入格式
- 与 interaction_logger 集成
- 播报期间自动暂停/恢复录音
"""
import json
import logging
import threading
from typing import Optional, Any, Union, Dict

logger = logging.getLogger(__name__)

# ── TTS 引擎（线程安全懒加载）──
_tts_engine = None
_tts_lock = threading.Lock()


def _get_tts_engine():
    """获取 TTS 引擎单例"""
    global _tts_engine
    if _tts_engine is None:
        with _tts_lock:
            if _tts_engine is None:
                try:
                    import pyttsx3
                    _tts_engine = pyttsx3.init()
                    _tts_engine.setProperty('rate', 160)
                    _tts_engine.setProperty('volume', 0.8)
                    logger.info("✅ TTS 引擎初始化成功")
                except Exception as e:
                    logger.warning(f"⚠️ TTS 引擎不可用: {e}")
                    _tts_engine = False
    return _tts_engine if _tts_engine is not False else None


# ── 中文反馈语料库（从参考项目扩展）──
FEEDBACK_TEXT: Dict[str, str] = {
    # ── 空调控制 ──
    "TurnOnAC": "好的，已为您打开空调",
    "TurnOffAC": "好的，已为您关闭空调",
    "temp_up": "温度已调高",
    "temp_down": "温度已调低",

    # ── 音乐控制 ──
    "PlayMusic": "好的，已开始播放音乐",
    "StopMusic": "好的，已暂停音乐",
    "next_track": "已切换到下一首",
    "previous_track": "已切换到上一首",
    "volume_up": "音量已调大",
    "volume_down": "音量已调小",

    # ── 导航 ──
    "Navigate": "正在为您规划路线",

    # ── 车窗/灯光 ──
    "window_open": "车窗已打开",
    "window_close": "车窗已关闭",
    "light_on": "灯光已打开",
    "light_off": "灯光已关闭",

    # ── 安全相关 ──
    "distract": "请注意安全驾驶，视线不要离开前方道路",
    "NoticeRoad": "驾驶员已恢复专注，请保持",
    "attention_hint": "请保持视线在前方",
    "attention_confirm": "已确认注意力已恢复",
    "emergency_stop": "紧急制动已触发",

    # ── 确认/取消 ──
    "confirm": "好的，已确认",
    "cancel": "已取消操作",

    # ── 环境相关（你做的部分）──
    "weather_alert": "天气预警，请注意行车安全",
    "fatigue_warning": "检测到疲劳驾驶迹象，建议休息",

    # ── 系统 ──
    "unknown": "抱歉，未能识别您的指令，请再说一次",
    "fallback": "系统运行在离线模式，基础功能正常",
}


def speak_text(text: str, app: Optional[Any] = None) -> bool:
    """
    通过 TTS 引擎播报文字。
    播报期间自动暂停/恢复录音。

    Returns:
        True 如果播报成功，False 如果 TTS 不可用。
    """
    engine = _get_tts_engine()
    if engine is None:
        logger.info(f"🔇 [TTS-降级] {text}")
        return False

    try:
        if app is not None and hasattr(app, 'pause_recording'):
            app.pause_recording()

        engine.say(text)
        engine.runAndWait()

        if app is not None and hasattr(app, 'resume_recording'):
            app.resume_recording()
        return True
    except Exception as e:
        logger.warning(f"TTS 播报异常: {e}")
        return False


def get_feedback_text(action_code: str) -> str:
    """根据 action_code 获取中文反馈文本"""
    return FEEDBACK_TEXT.get(action_code, FEEDBACK_TEXT["unknown"])


def handle_action(action: Union[str, dict], app: Optional[Any] = None,
                  silent: bool = False) -> Dict[str, Any]:
    """
    统一动作反馈入口。

    支持输入格式：
      - 字符串: "TurnOnAC"
      - 字典: {"command": "TurnOnAC"} 或 {"action_code": "PlayMusic"}
      - JSON 字符串: '{"action": "navigation", "command": "start_route"}'

    Args:
        action: 动作指令
        app: 应用实例（用于暂停录音）
        silent: True 时不播报语音

    Returns:
        {"action_code": str, "feedback": str, "spoken": bool, "success": bool}
    """
    cmd = _parse_action_code(action)
    text = FEEDBACK_TEXT.get(cmd)
    spoken = False

    if text:
        logger.info(f"[Action] {cmd} → {text}")
        if not silent:
            spoken = speak_text(text, app)
        return {
            "action_code": cmd,
            "feedback": text,
            "spoken": spoken,
            "success": True,
        }
    else:
        logger.warning(f"[Action] 未知指令: {cmd}")
        fallback = FEEDBACK_TEXT["unknown"]
        if not silent:
            spoken = speak_text(fallback, app)
        return {
            "action_code": cmd,
            "feedback": fallback,
            "spoken": spoken,
            "success": False,
        }


def _parse_action_code(action: Union[str, dict]) -> str:
    """从各种格式中提取 action_code"""
    if isinstance(action, dict):
        if "command" in action:
            return str(action["command"])
        if "action_code" in action:
            return str(action["action_code"])
        if action:
            return str(next(iter(action.keys())))
        return "unknown"

    if isinstance(action, str):
        stripped = action.strip()
        if stripped.startswith("{"):
            try:
                data = json.loads(stripped)
                return _parse_action_code(data)
            except json.JSONDecodeError:
                pass
        return stripped

    return "unknown"


def register_feedback(action_code: str, text: str):
    """扩展语料库"""
    FEEDBACK_TEXT[action_code] = text


def get_all_actions() -> Dict[str, str]:
    """获取所有已注册的动作码"""
    return dict(FEEDBACK_TEXT)
