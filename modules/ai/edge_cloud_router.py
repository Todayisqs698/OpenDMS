"""
边缘-云端混合路由器

核心职责：
1. 每个决策请求判断走本地推理还是云端 API
2. 检测网络状态，断网时自动标记所有请求走本地
3. 追踪延迟统计，超时自动切换

路由原则：
- 安全相关（眼动/分心/疲劳）→ 本地，<50ms
- 手势指令 → 本地，<30ms
- 语音转写 → 本地 Whisper，100-500ms
- 语音语义理解 → 混合（本地转写 + 云端 LLM）
- 知识问答 → 混合（本地 FAISS 检索 + 云端 LLM 生成）
- 复杂上下文推理 → 云端（离线降级 Ollama）
"""
import logging
import time
import socket
from typing import Optional

logger = logging.getLogger(__name__)

# 本地优先（安全相关，毫秒级）
LOCAL_ONLY = {"distract", "NoticeRoad", "fatigue_warning",
              "confirm", "cancel", "PlayMusic", "StopMusic",
              "TurnOnAC", "TurnOffAC"}

# 混合模式（本地预处理 + 云端生成）
HYBRID = {"semantic_query", "knowledge_qa", "weather_query",
          "navigation_query", "vehicle_question"}

# 云端优先（复杂推理）
CLOUD_FIRST = {"context_reasoning", "multi_turn_dialogue",
               "emotion_analysis", "driving_advice"}


class EdgeCloudRouter:
    """边缘-云端混合路由器"""

    def __init__(self):
        self.offline_mode = False
        self.last_network_check = 0
        self.network_check_interval = 10  # 每10秒检查一次网络
        self.cloud_latency_history = []   # 云端延迟历史（最近20次）
        self.cloud_timeout = 3.0          # 云端超时（秒）
        self.consecutive_timeouts = 0
        self.max_timeouts = 3             # 连续超时→标记离线

    def route(self, context: dict) -> str:
        """
        路由决策。

        Args:
            context: {
                "trigger": "gaze"|"gesture"|"speech"|"query",
                "action_code": "distract"|"TurnOnAC"|...,
                "type": "distraction_detected"|"user_input"|...,
                "text": "..."  (语音文本，用于语义判断)
            }

        Returns:
            "local"  — 本地规则引擎
            "cloud"  — DeepSeek API
            "hybrid" — 本地预处理 + 云端生成
        """
        trigger = context.get("trigger", "")
        action = context.get("action_code", "")
        ctx_type = context.get("type", "")

        # 如果已标记离线，全部走本地
        if self.offline_mode:
            # 定期检查网络是否恢复
            if time.time() - self.last_network_check > self.network_check_interval:
                if self._check_network():
                    self.offline_mode = False
                    logger.info("网络已恢复，退出离线模式")
            if self.offline_mode:
                return "local"

        # 安全相关 → 本地
        if trigger == "gaze" or "distraction" in str(ctx_type).lower():
            return "local"

        # 动作指令 → 本地
        if action in LOCAL_ONLY:
            return "local"

        # 手势 → 本地
        if trigger == "gesture":
            return "local"

        # 知识/语义查询 → 混合
        if action in HYBRID or trigger == "query":
            return "hybrid"

        # 语音 → 混合（本地转写已完成，现在需要语义理解）
        if trigger == "speech":
            text = context.get("text", "")
            # 简单指令本地处理
            if self._is_simple_command(text):
                return "local"
            return "hybrid"

        return "local"  # 默认本地（安全优先）

    def report_cloud_result(self, latency: float, success: bool):
        """上报云端调用结果，用于动态调整路由"""
        if success:
            self.cloud_latency_history.append(latency)
            if len(self.cloud_latency_history) > 20:
                self.cloud_latency_history.pop(0)
            self.consecutive_timeouts = 0
        else:
            self.consecutive_timeouts += 1
            if self.consecutive_timeouts >= self.max_timeouts:
                self.offline_mode = True
                logger.warning(f"连续 {self.max_timeouts} 次云端调用失败，切换到离线模式")

    def is_offline(self) -> bool:
        return self.offline_mode

    def get_cloud_latency_stats(self) -> dict:
        """云端延迟统计"""
        if not self.cloud_latency_history:
            return {"avg": 0, "min": 0, "max": 0, "count": 0}
        return {
            "avg": round(sum(self.cloud_latency_history) / len(self.cloud_latency_history), 3),
            "min": round(min(self.cloud_latency_history), 3),
            "max": round(max(self.cloud_latency_history), 3),
            "count": len(self.cloud_latency_history),
        }

    # ── 内部 ──

    @staticmethod
    def _is_simple_command(text: str) -> bool:
        """判断是否为简单指令（本地即可处理）"""
        if not text:
            return True
        simple_keywords = ["空调", "音乐", "导航", "温度", "风扇", "窗户", "灯光",
                          "打开", "关闭", "调高", "调低", "播放", "暂停", "停止"]
        return any(kw in text for kw in simple_keywords) and len(text) < 15

    @staticmethod
    def _check_network() -> bool:
        """快速网络检查"""
        try:
            socket.create_connection(("8.8.8.8", 53), timeout=2)
            return True
        except Exception:
            return False


# 全局单例
_router: Optional[EdgeCloudRouter] = None


def get_router() -> EdgeCloudRouter:
    global _router
    if _router is None:
        _router = EdgeCloudRouter()
    return _router


def route_decision(context: dict) -> str:
    """快捷函数：路由决策"""
    return get_router().route(context)
