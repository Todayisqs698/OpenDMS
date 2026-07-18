"""
交互智能体 — 手势 + 语音意图解析 + RAG 知识检索
==================================================
B岗核心模块：解析驾驶员手势/语音输入，识别意图，安全拦截，知识库检索。

架构：
  - 意图分类（fault / control / entertain）
  - 安全拦截规则（疲劳/分心时拦截娱乐类指令）
  - FAISS RAG 知识库检索（故障咨询类）
  - 标准化输出 dict，供 LangGraph 编排 & WebSocket 推送

输入格式（兼容 langgraph_orchestrator 调用）：
  {
    "gesture": {"gesture": "Thumbs Up", "confidence": 0.9},
    "speech": {"text": "打开空调", "intent": "command"},
    "driver_state": {"risk": "safe", "fatigue": False, "distracted": False}  # 可选
  }

输出格式（标准 dict，不可修改字段）：
  {
    "intent_type": "fault|control|entertain|unknown",
    "driver_risk": "safe|distract|fatigue",
    "allow_execute": bool,
    "action_code": str,
    "reply_text": str,
    "knowledge_ref": list,
    "warning_msg": str
  }
"""

import logging
import time
from typing import Optional

logger = logging.getLogger(__name__)

# ── 意图关键词库 ──

# 车辆故障咨询关键词
FAULT_KEYWORDS = [
    "故障", "坏了", "警告灯", "指示灯", "报警", "异响", "漏油", "漏水",
    "发动机", "变速箱", "制动", "刹车", "ABS", "ESP", "胎压", "机油",
    "冷却液", "电池", "蓄电池", "高压电池", "充电", "传感器", "故障码",
    "P0", "P1", "P2", "P3", "P4", "P5",  # 故障码前缀
    "C1", "B1", "B2", "TPMS", "三元催化", "氧传感器", "节气门",
    "失火", "抖动", "熄火", "打不着", "启动不了", "没反应",
    "什么意思", "怎么回事", "什么问题", "正常吗", "要不要紧",
]

# 车载功能控制关键词
CONTROL_KEYWORDS = [
    "打开", "关闭", "开启", "启动", "停止", "调", "设",
    "空调", "温度", "风速", "风量", "循环", "制冷", "制热",
    "车窗", "天窗", "座椅", "加热", "通风", "按摩",
    "导航", "路线", "目的地", "回家", "去公司",
    "音乐", "收音机", "FM", "AM",
    "音量", "静音", "下一首", "上一首", "暂停", "继续",
    "灯光", "远光", "近光", "雾灯", "双闪",
    "巡航", "ECO", "运动模式", "雪地模式",
    "锁车", "解锁", "后备箱",
]

# 娱乐多媒体关键词
ENTERTAIN_KEYWORDS = [
    "播放", "放歌", "放音乐", "来一首", "我想听",
    "相声", "小说", "故事", "电台", "播客",
    "笑话", "新闻", "天气", "股票",
    "蓝牙", "CarPlay", "投屏",
    "视频", "电影", "电视剧",
    "游戏", "K歌", "唱吧",
]

# 确认/否定关键词（用于分心恢复确认）
CONFIRM_KEYWORDS = [
    "已注意", "注意道路", "看路", "专心", "集中", "明白", "知道了",
    "好的", "收到", "确定", "是的", "没问题", "我已恢复",
    "注意前方", "我在看路", "会注意", "知道了", "行", "嗯", "OK",
]


class InteractionAgent:
    """
    交互智能体 — 多模态意图理解

    职责：
      1. 融合手势和语音输入
      2. 区分指令类型（故障咨询/功能控制/影音娱乐）
      3. 执行安全拦截（疲劳/分心时禁娱乐指令）
      4. 故障咨询类调用 RAG 知识库
      5. 输出标准化 action_code + reply_text
    """

    # 手势 → action_code 映射表（扩展版）
    GESTURE_MAP = {
        "Thumbs Up": "confirm",
        "Thumbs Down": "cancel",
        "OK": "confirm",
        "Open": "PlayMusic",
        "Close": "StopMusic",
        "Point": "TurnOnAC",
        "Palm": "stop_all",
        "Fist": "stop_all",
        "Peace": "TakePhoto",
    }

    def __init__(self):
        self.knowledge_base = None
        self._kb_available = False
        self._init_kb()

    def _init_kb(self):
        """延迟初始化知识库"""
        try:
            from modules.ai.vehicle_knowledge_base import get_knowledge_base
            self.knowledge_base = get_knowledge_base()
            self._kb_available = True
            logger.info("RAG 知识库已连接")
        except Exception as e:
            logger.warning(f"RAG 知识库初始化失败: {e}，将使用规则匹配")
            self._kb_available = False

    # ═══════════════════════════════════════════════
    #  公共接口：analyze() — 兼容 LangGraph 编排
    # ═══════════════════════════════════════════════

    def analyze(self, data: dict) -> dict:
        """
        主入口：融合手势和语音，输出意图和 action_code。

        Args:
            data: {
                "gesture": {"gesture": str, "confidence": float, "intent": str},
                "speech": {"text": str, "intent": str, "emotion": str},
                "driver_state": {"risk": str, "fatigue": bool, "distracted": bool}  # 可选
            }

        Returns:
            标准化 dict（见模块文档）
        """
        try:
            return self._analyze_internal(data)
        except Exception as e:
            logger.error(f"InteractionAgent 分析异常: {e}", exc_info=True)
            return self._fallback_response(str(e))

    def process(self, state: dict) -> dict:
        """
        LangGraph 节点调用封装。
        兼容 langgraph_orchestrator 传入的 AgentState dict。

        输入 state 中提取:
          - gesture_data → gesture
          - speech_data → speech
          - safety_result / risk_level → driver_state

        Returns:
            标准化 interaction_result dict
        """
        gesture_data = state.get("gesture_data", {})
        speech_data = state.get("speech_data", {})
        safety = state.get("safety_result", {})
        risk_level = state.get("risk_level", "normal")

        # 从 safety_result 或 risk_level 构建 driver_state
        driver_state = {
            "risk": risk_level,
            "fatigue": safety.get("fatigue_detected", False) if safety else False,
            "distracted": risk_level in ("distracted", "dangerous"),
        }

        return self.analyze({
            "gesture": gesture_data,
            "speech": speech_data,
            "driver_state": driver_state,
        })

    # ═══════════════════════════════════════════════
    #  内部分析逻辑
    # ═══════════════════════════════════════════════

    def _analyze_internal(self, data: dict) -> dict:
        gesture = data.get("gesture", {})
        speech = data.get("speech", {})
        driver_state = data.get("driver_state", {})
        is_new_format = data.get("_new_format", False)  # 新格式标记

        gesture_name = gesture.get("gesture", "") if gesture else ""
        speech_text = speech.get("text", "").strip() if speech else ""
        speech_emotion = speech.get("emotion", "neutral") if speech else "neutral"

        # 判断驾驶员风险状态
        driver_risk = self._assess_driver_risk(driver_state)

        # 确定输入来源
        source = self._determine_source(speech_text, gesture_name)

        # ── 步骤 1：意图分类 ──
        intent_type = self._classify_intent(speech_text, gesture_name)

        # ── 步骤 2：安全检查 ──
        allow_execute, warning_msg = self._check_safety(intent_type, driver_risk)

        if not allow_execute:
            return {
                "intent_type": intent_type,
                "driver_risk": driver_risk,
                "allow_execute": False,
                "action_code": "blocked_by_safety",
                "reply_text": "",
                "knowledge_ref": [],
                "warning_msg": warning_msg,
            }

        # ── 步骤 3：根据意图类型处理 ──
        if intent_type == "fault":
            return self._handle_fault_query(speech_text, driver_risk)
        elif intent_type in ("control", "entertain"):
            return self._handle_action_command(speech_text, gesture_name, source, intent_type, driver_risk)
        else:
            return self._handle_unknown(speech_text, gesture_name, source, driver_risk)

    # ═══════════════════════════════════════════════
    #  意图分类
    # ═══════════════════════════════════════════════

    def _classify_intent(self, speech_text: str, gesture_name: str) -> str:
        """分类用户意图：fault / control / entertain / unknown"""
        text = speech_text or ""

        # 语音优先
        if text:
            text_lower = text.lower()
            # 故障咨询
            for kw in FAULT_KEYWORDS:
                if kw in text:
                    return "fault"
            # 娱乐多媒体（优先级高于功能控制：避免「播放音乐」因含「音乐」被误判为控制类而绕过疲劳/分心安全拦截）
            for kw in ENTERTAIN_KEYWORDS:
                if kw in text:
                    return "entertain"
            # 功能控制
            for kw in CONTROL_KEYWORDS:
                if kw in text:
                    return "control"
            # 确认类
            for kw in CONFIRM_KEYWORDS:
                if kw in text:
                    return "control"  # 确认指令归类为 control

        # 手势兜底
        if gesture_name:
            if gesture_name in ("Thumbs Up", "OK"):
                return "control"  # 确认
            elif gesture_name in ("Thumbs Down", "Palm", "Fist"):
                return "control"  # 取消/停止
            elif gesture_name in ("Open", "Close", "Point"):
                return "control"

        return "unknown"

    # ═══════════════════════════════════════════════
    #  安全检查
    # ═══════════════════════════════════════════════

    def _assess_driver_risk(self, driver_state: dict) -> str:
        """评估驾驶员风险等级"""
        risk = driver_state.get("risk", "safe")
        fatigue = driver_state.get("fatigue", False)
        distracted = driver_state.get("distracted", False)

        if risk in ("dangerous", "fatigue") or fatigue:
            return "fatigue"
        elif risk == "distracted" or distracted:
            return "distract"
        return "safe"

    def _check_safety(self, intent_type: str, driver_risk: str) -> tuple[bool, str]:
        """
        安全拦截检查。

        Returns:
            (allow_execute: bool, warning_msg: str)
        """
        # 安全状态：所有指令放行
        if driver_risk == "safe":
            return True, ""

        # 疲劳状态：拦截娱乐类指令
        if driver_risk == "fatigue":
            if intent_type == "entertain":
                return False, (
                    "检测到您处于疲劳驾驶状态，为了保证安全，"
                    "已自动禁用娱乐功能。建议您就近休息。"
                )
            elif intent_type == "control":
                return True, ""  # 疲劳时允许控制类指令（如开窗通风）
            elif intent_type == "fault":
                return True, ""  # 故障咨询随时可用

        # 分心状态：拦截娱乐类指令，控制类可执行但给警告
        if driver_risk == "distract":
            if intent_type == "entertain":
                return False, (
                    "检测到您的视线偏离道路，已禁用娱乐功能。"
                    "请注视前方，注意行车安全。"
                )
            elif intent_type == "control":
                return True, ""  # 控制类放行
            elif intent_type == "fault":
                return True, ""

        return True, ""

    # ═══════════════════════════════════════════════
    #  故障咨询处理
    # ═══════════════════════════════════════════════

    def _handle_fault_query(self, speech_text: str, driver_risk: str) -> dict:
        """处理车辆故障咨询：调用 RAG 知识库检索"""
        result = {
            "intent_type": "fault",
            "driver_risk": driver_risk,
            "allow_execute": True,
            "action_code": "knowledge_query",
            "reply_text": "",
            "knowledge_ref": [],
            "warning_msg": "",
        }

        # 调用 RAG 检索
        if self._kb_available and self.knowledge_base:
            try:
                kb_result = self.knowledge_base.retrieve_knowledge(speech_text, top_k=3)
                if kb_result.get("success"):
                    docs = kb_result.get("docs", [])
                    result["knowledge_ref"] = docs
                    # 拼接检索结果作为回复
                    if docs:
                        summaries = []
                        for i, doc in enumerate(docs, 1):
                            summaries.append(
                                f"{i}. [{doc.get('source', '未知来源')}] "
                                f"{doc.get('content', '')[:200]}"
                            )
                        result["reply_text"] = (
                            f"关于「{speech_text}」，以下是相关资料：\n"
                            + "\n".join(summaries)
                        )
                    else:
                        result["reply_text"] = f"未找到「{speech_text}」的相关资料，建议查阅随车说明书。"
                else:
                    result["reply_text"] = kb_result.get("fallback_msg", "知识库暂时不可用")
            except Exception as e:
                logger.error(f"RAG 检索异常: {e}")
                result["reply_text"] = f"知识检索服务异常，请稍后重试。"
        else:
            # 无 RAG：使用关键词规则兜底
            result["reply_text"] = self._rule_fallback(speech_text)

        return result

    # ═══════════════════════════════════════════════
    #  功能控制 / 娱乐指令处理
    # ═══════════════════════════════════════════════

    def _handle_action_command(
        self, speech_text: str, gesture_name: str, source: str,
        intent_type: str, driver_risk: str
    ) -> dict:
        """处理功能控制和娱乐指令"""

        # 语音优先解析
        if speech_text:
            action_code = self._parse_speech_action(speech_text)
            reply_text = f"收到指令：{speech_text}"
        elif gesture_name and gesture_name in self.GESTURE_MAP:
            action_code = self.GESTURE_MAP[gesture_name]
            reply_text = f"手势指令：{gesture_name}"
        else:
            action_code = "unknown"
            reply_text = "未识别到有效指令"

        return {
            "intent_type": intent_type,
            "driver_risk": driver_risk,
            "allow_execute": True,
            "action_code": action_code,
            "reply_text": reply_text,
            "knowledge_ref": [],
            "warning_msg": "",
        }

    # ═══════════════════════════════════════════════
    #  未知指令处理
    # ═══════════════════════════════════════════════

    def _handle_unknown(
        self, speech_text: str, gesture_name: str, source: str, driver_risk: str
    ) -> dict:
        """处理无法分类的指令"""
        if speech_text:
            # 尝试用 LLM 做兜底理解
            reply_text = self._llm_fallback_intent(speech_text)
        else:
            reply_text = "未识别到有效指令，请使用语音或手势操作。"

        return {
            "intent_type": "unknown",
            "driver_risk": driver_risk,
            "allow_execute": True,
            "action_code": "unknown",
            "reply_text": reply_text,
            "knowledge_ref": [],
            "warning_msg": "",
        }

    # ═══════════════════════════════════════════════
    #  辅助方法
    # ═══════════════════════════════════════════════

    def _determine_source(self, speech_text: str, gesture_name: str) -> str:
        """确定输入来源"""
        if speech_text and gesture_name:
            return "hybrid"
        elif speech_text:
            return "speech"
        elif gesture_name:
            return "gesture"
        return "none"

    def _parse_speech_action(self, text: str) -> str:
        """
        语音文本 → action_code 映射。
        扩展到完整指令库，覆盖车载全部功能。
        """
        text_lower = text

        # 空调控制
        if any(kw in text_lower for kw in ["开空调", "打开空调", "启动空调"]):
            return "TurnOnAC"
        if any(kw in text_lower for kw in ["关空调", "关闭空调", "停止空调"]):
            return "TurnOffAC"
        if any(kw in text_lower for kw in ["温度", "调温"]):
            return "SetTemperature"

        # 影音娱乐
        if any(kw in text_lower for kw in ["播放音乐", "放歌", "放音乐", "来一首"]):
            return "PlayMusic"
        if any(kw in text_lower for kw in ["关音乐", "停止播放", "暂停音乐"]):
            return "StopMusic"
        if any(kw in text_lower for kw in ["下一首", "切歌"]):
            return "NextTrack"
        if any(kw in text_lower for kw in ["上一首"]):
            return "PreviousTrack"
        if any(kw in text_lower for kw in ["音量", "大声", "小声"]):
            return "SetVolume"
        if any(kw in text_lower for kw in ["收音机", "FM", "电台"]):
            return "OpenRadio"

        # 导航
        if any(kw in text_lower for kw in ["导航到", "导航去", "去"]):
            return "Navigate"
        if any(kw in text_lower for kw in ["取消导航", "停止导航"]):
            return "CancelNavigate"
        if any(kw in text_lower for kw in ["路况"]):
            return "TrafficQuery"

        # 车窗
        if any(kw in text_lower for kw in ["开车窗", "打开车窗"]):
            return "OpenWindow"
        if any(kw in text_lower for kw in ["关车窗", "关闭车窗"]):
            return "CloseWindow"
        if any(kw in text_lower for kw in ["天窗", "开天窗"]):
            return "OpenSunroof"
        if any(kw in text_lower for kw in ["关天窗"]):
            return "CloseSunroof"

        # 座椅
        if any(kw in text_lower for kw in ["座椅加热", "加热"]):
            return "SeatHeat"
        if any(kw in text_lower for kw in ["座椅通风", "通风"]):
            return "SeatVent"
        if any(kw in text_lower for kw in ["按摩"]):
            return "SeatMassage"

        # 灯光
        if any(kw in text_lower for kw in ["远光", "大灯"]):
            return "HighBeam"
        if any(kw in text_lower for kw in ["双闪", "危险报警"]):
            return "HazardLight"

        # 确认/否定
        if any(kw in text_lower for kw in CONFIRM_KEYWORDS):
            return "confirm"
        if any(kw in text_lower for kw in ["不", "取消", "不要", "否", "拒绝"]):
            return "cancel"

        # 最终兜底
        for keyword, action in [
            ("空调", "TurnOnAC"), ("冷", "TurnOnAC"), ("热", "TurnOffAC"),
            ("音乐", "PlayMusic"), ("播", "PlayMusic"),
            ("停", "StopMusic"), ("关", "StopMusic"),
            ("导航", "Navigate"),
        ]:
            if keyword in text_lower:
                return action

        return "unknown"

    def _rule_fallback(self, query: str) -> str:
        """RAG 不可用时的规则兜底"""
        rules = [
            ("胎压", "胎压标准：前轮 2.3-2.5 bar，后轮 2.2-2.4 bar。警告灯亮请立即检查。"),
            ("空调", "空调系统：语音说「打开空调」启动，支持 16-30°C 温度调节。"),
            ("发动机", "发动机故障灯亮起时，请减速行驶并尽快到店检测。红灯亮起请立即安全停车。"),
            ("制动", "制动系统警告灯亮表示制动液不足或系统故障，请立即停车。"),
            ("机油", "机油压力警告灯亮表示机油不足，立即停车检查。"),
            ("电池", "蓄电池电压异常可能导致启动困难，请检查或更换电池。"),
            ("ABS", "ABS 警告灯亮表示防抱死制动系统故障，请尽快检修。"),
            ("ESP", "ESP/ESC 警告灯亮表示电子稳定程序故障或已关闭。"),
        ]
        for keyword, msg in rules:
            if keyword in query:
                return f"[离线模式] {msg}"

        return "当前无法连接知识库。请您查阅随车说明书或联系售后服务中心获取帮助。"

    def _llm_fallback_intent(self, text: str) -> str:
        """
        使用 LLM（DeepSeek/豆包）对未知意图做兜底理解。
        调用失败则返回规则兜底。
        """
        try:
            from modules.ai.deepseek_client import deepseek_client

            prompt = f"""你是一个车载智能助手。用户说了：「{text}」

请判断用户的意图是什么，用简短的一句话回复（10字以内），如果是以下情况：
- 和车辆故障、警告灯、故障码有关 → 回答故障咨询相关
- 和车载功能控制有关（空调、车窗、导航、音乐等）→ 回答功能控制相关  
- 和娱乐有关（听歌、相声、新闻等）→ 回答娱乐相关
- 其他闲聊 → 回答友好引导

只回复意图说明，不要加其他内容。"""

            response = deepseek_client.client.chat.completions.create(
                model="deepseek-chat",
                messages=[
                    {"role": "system", "content": "你是车载助手，只回复简短意图说明。"},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.3,
                max_tokens=50,
                timeout=5,
            )
            return f"「{text}」的意图分析：{response.choices[0].message.content}"
        except Exception as e:
            logger.warning(f"LLM 意图理解失败: {e}")
            return f"收到指令「{text}」，系统正在处理中。"

    def _fallback_response(self, error_msg: str = "") -> dict:
        """系统级兜底响应"""
        return {
            "intent_type": "unknown",
            "driver_risk": "safe",
            "allow_execute": True,
            "action_code": "system_error",
            "reply_text": "系统处理异常，请稍后重试。驾驶安全不受影响。",
            "knowledge_ref": [],
            "warning_msg": "",
        }


# ── 全局单例 ──
_agent_instance: Optional[InteractionAgent] = None


def get_interaction_agent() -> InteractionAgent:
    """获取全局交互智能体单例"""
    global _agent_instance
    if _agent_instance is None:
        _agent_instance = InteractionAgent()
    return _agent_instance
