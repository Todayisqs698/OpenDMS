"""
交互 Agent — 手势 + 语音意图理解（兼容层）
============================================
此文件为 langgraph_orchestrator 的兼容层，所有逻辑委托到
modules.ai.interaction_agent 模块。

接口规范（保持与 orchestrator 兼容）：
  输入: {"gesture": {"gesture": "Thumbs Up", "confidence": 0.9, "intent": "..."},
         "speech": {"text": "打开空调", "intent": "command", "emotion": "neutral"}}
  输出: {"action_code": "TurnOnAC",
         "recommendation_text": "空调已开启",
         "confidence": 0.92,
         "source": "gesture/speech/hybrid"}
"""

import logging

logger = logging.getLogger(__name__)


class InteractionAgent:
    """
    交互 Agent — 兼容层

    委托到 modules.ai.interaction_agent.InteractionAgent，
    保持与 langgraph_orchestrator 完全兼容。
    """

    # 手势 → action_code 映射表（保持向后兼容）
    GESTURE_MAP = {
        "Thumbs Up": "confirm",
        "Thumbs Down": "cancel",
        "Open": "PlayMusic",
        "Close": "StopMusic",
        "Point": "TurnOnAC",
    }

    def __init__(self):
        self._agent = None
        self._init_agent()
        self.knowledge_base = None

    def _init_agent(self):
        """延迟加载核心交互智能体"""
        try:
            from modules.ai.interaction_agent import get_interaction_agent
            self._agent = get_interaction_agent()
            logger.info("InteractionAgent 核心模块已加载")
        except Exception as e:
            logger.warning(f"核心 InteractionAgent 加载失败: {e}，使用内置规则兜底")
            self._agent = None

    def analyze(self, data: dict) -> dict:
        """
        融合手势和语音，输出意图和 action_code。

        优先使用核心智能体，不可用时降级到本地规则。
        """
        # 尝试使用核心智能体
        if self._agent is not None:
            try:
                result = self._agent.analyze(data)
                # 转换为 orchestrator 兼容格式
                return self._to_compat_format(result, data)
            except Exception as e:
                logger.warning(f"核心智能体调用失败: {e}，降级到规则模式")

        # 降级：本地规则（向后兼容）
        return self._analyze_fallback(data)

    def _to_compat_format(self, result: dict, data: dict) -> dict:
        """将新格式结果转换为 orchestrator 兼容格式"""
        gesture = data.get("gesture", {})
        speech = data.get("speech", {})

        source = "speech" if speech.get("text") else (
            "gesture" if gesture.get("gesture") else "none"
        )

        confidence = 0.9 if result.get("allow_execute") else 0.5
        if result.get("knowledge_ref"):
            top_score = result["knowledge_ref"][0].get("score", 0.5) if result["knowledge_ref"] else 0.5
            confidence = top_score

        return {
            "action_code": result.get("action_code", "unknown"),
            "recommendation_text": result.get("reply_text", ""),
            "confidence": confidence,
            "source": source,
            # 扩展字段
            "intent_type": result.get("intent_type", "unknown"),
            "driver_risk": result.get("driver_risk", "safe"),
            "allow_execute": result.get("allow_execute", True),
            "warning_msg": result.get("warning_msg", ""),
            "knowledge_ref": result.get("knowledge_ref", []),
        }

    def _analyze_fallback(self, data: dict) -> dict:
        """本地规则兜底（向后兼容旧逻辑）"""
        gesture = data.get("gesture", {})
        speech = data.get("speech", {})

        gesture_name = gesture.get("gesture", "")
        speech_text = speech.get("text", "")

        # 语音优先
        if speech_text:
            return {
                "action_code": self._parse_speech(speech_text),
                "recommendation_text": f"收到指令：{speech_text}",
                "confidence": 0.9,
                "source": "speech",
            }

        # 手势兜底
        if gesture_name and gesture_name in self.GESTURE_MAP:
            return {
                "action_code": self.GESTURE_MAP[gesture_name],
                "recommendation_text": f"手势指令：{gesture_name}",
                "confidence": gesture.get("confidence", 0.8),
                "source": "gesture",
            }

        return {
            "action_code": "unknown",
            "recommendation_text": "",
            "confidence": 0.0,
            "source": "none",
        }

    def _parse_speech(self, text: str) -> str:
        """简单语音指令解析"""
        mapping = {
            "空调": "TurnOnAC", "开空调": "TurnOnAC", "冷": "TurnOnAC",
            "关空调": "TurnOffAC", "热": "TurnOffAC",
            "音乐": "PlayMusic", "放歌": "PlayMusic", "播放": "PlayMusic",
            "关音乐": "StopMusic", "停": "StopMusic",
            "导航": "Navigate", "去": "Navigate",
        }
        for keyword, action in mapping.items():
            if keyword in text:
                return action
        return "unknown"
