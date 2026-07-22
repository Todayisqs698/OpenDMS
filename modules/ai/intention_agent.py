"""
Intention Agent — 意图识别与调度计划生成
==========================================

接收用户多模态输入（语音/手势/传感器状态），
使用 LLM 进行意图分解，生成子 Agent 调度计划。

核心职责：
  1. 识别用户输入中的多个意图（单句多意图）
  2. 为每个意图分配合适的子 Agent / 执行器
  3. 设定优先级和依赖关系
  4. 输出结构化的调度计划

输出格式：
  {
    "intents": [
      {
        "id": "intent_1",
        "category": "ac_control" | "music_control" | "fatigue_assist" | 
                    "diagnosis" | "navigation" | "weather" | "chitchat",
        "agent": "control_executor" | "react_agent" | "diagnose_agent" | 
                   "analyze_agent" | "recommend_agent",
        "priority": 0~9 (0=最高),
        "description": "用户意图的简洁描述",
        "params": { ... }
      }
    ],
    "needs_clarification": false,
    "clarification_question": "",
    "overall_summary": "对用户整体需求的一句话总结"
  }
"""

import json
import logging
import re
from typing import List, Dict, Any
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════
#  数据结构
# ═══════════════════════════════════════════════════════════

@dataclass
class IntentItem:
    """单个意图项"""
    id: str
    category: str       # 意图类别
    agent: str        # 分配的子Agent/执行器
    priority: int     # 优先级 0-9
    description: str  # 意图描述
    params: dict = field(default_factory=dict)  # 提取的参数


@dataclass
class IntentionPlan:
    """完整的意图调度计划"""
    intents: List[IntentItem] = field(default_factory=list)
    needs_clarification: bool = False
    clarification_question: str = ""
    overall_summary: str = ""

    def to_dict(self) -> dict:
        return {
            "intents": [
                {
                    "id": i.id,
                    "category": i.category,
                    "agent": i.agent,
                    "priority": i.priority,
                    "description": i.description,
                    "params": i.params,
                }
                for i in self.intents
            ],
            "needs_clarification": self.needs_clarification,
            "clarification_question": self.clarification_question,
            "overall_summary": self.overall_summary,
        }


# ═══════════════════════════════════════════════════════════
#  规则匹配（快速通道 — 不经过 LLM）
# ═══════════════════════════════════════════════════════════

# 意图类别 → 关键词模式 → 子Agent映射
RULE_BASED_PATTERNS = {
    "ac_control": {
        "patterns": [
            r"空调|冷气|暖气|暖风|温度|制冷|制热|风速|风量",
            r"开.*空调|关.*空调|空调.*开|空调.*关",
            r"调[高低]|温度[升降]|再[高低冷热]一点",
            r"\d{1,2}\s*(度|°|℃)",
        ],
        "agent": "control_executor",
        "priority": 5,
    },
    "music_control": {
        "patterns": [
            r"音乐|歌曲|歌|播放|放歌|听歌|来首|放首",
            r"暂停|停止播放|停播|下一首|上一首|切歌",
            r"音量|声音.*大小|声.*大|声.*小",
            r"周杰伦|王菲|林俊杰|陈奕迅|邓紫棋|薛之谦",  # 常见歌手名
        ],
        "agent": "control_executor",
        "priority": 6,
    },
    "fatigue_assist": {
        "patterns": [
            r"累|困|疲惫|疲劳|没精神|想睡觉|打瞌睡|眼皮",
            r"好累|好困|有点困|累死了",
            r"提神|醒醒|清醒一下",
        ],
        "agent": "react_agent",
        "priority": 1,  # 高优先级，涉及安全
    },
    "diagnosis": {
        "patterns": [
            r"故障|坏了|异常|报警|警报|灯亮|指示灯",
            r"怎么办|怎么回事|什么问题|什么意思",
            r"异响|异味|不对劲|有问题",
        ],
        "agent": "diagnose_agent",
        "priority": 2,
    },
    "weather": {
        "patterns": [
            r"天气|下雨|温度.*几度|气温",
            r"明.*天|今天.*天",
        ],
        "agent": "recommend_agent",
        "priority": 7,
    },
    "navigation": {
        "patterns": [
            r"导航|路线|怎么走|去.*哪|到.*去",
        ],
        "agent": "recommend_agent",
        "priority": 4,
    },
}


def rule_based_intent_detection(text: str) -> List[IntentItem]:
    """
    基于规则的快速意图识别（不经过 LLM，延迟 < 10ms）。
    返回匹配到的意图列表。
    """
    detected = []
    intent_id = 0

    for category, config in RULE_BASED_PATTERNS.items():
        matched = False
        extracted_params = {}

        for pattern in config["patterns"]:
            if re.search(pattern, text):
                matched = True
                # 提取简单参数
                if category == "ac_control":
                    temp_match = re.search(r"(\d{1,2})\s*(度|°|℃)", text)
                    if temp_match:
                        extracted_params["temperature"] = int(temp_match.group(1))
                    if re.search(r"开|启动|打开", text) and "空调" in text:
                        extracted_params["action"] = "TurnOnAC"
                    elif re.search(r"关|关闭|关掉", text) and "空调" in text:
                        extracted_params["action"] = "TurnOffAC"
                elif category == "music_control":
                    singer_match = re.search(r"(周杰伦|王菲|林俊杰|陈奕迅|邓紫棋|薛之谦)", text)
                    if singer_match:
                        extracted_params["singer"] = singer_match.group(1)
                    if re.search(r"播放|放|来|听", text):
                        extracted_params["action"] = "play"
                    elif re.search(r"暂停|停止|停", text):
                        extracted_params["action"] = "pause"
                break

        if matched:
            intent_id += 1
            detected.append(IntentItem(
                id=f"intent_{intent_id}",
                category=category,
                agent=config["agent"],
                priority=config["priority"],
                description=_generate_description(category, extracted_params, text),
                params=extracted_params,
            ))

    # 按优先级排序（数字越小越先）
    detected.sort(key=lambda x: x.priority)
    return detected


def _generate_description(category: str, params: dict, text: str) -> str:
    """根据类别和参数生成人类可读的意图描述"""
    if category == "ac_control":
        if params.get("action") == "TurnOnAC":
            return "打开空调"
        if params.get("action") == "TurnOffAC":
            return "关闭空调"
        if "temperature" in params:
            return f"空调温度调节至 {params['temperature']} 度"
        return "空调控制"
    if category == "music_control":
        if "singer" in params:
            return f"播放 {params['singer']} 的歌曲"
        if params.get("action") == "play":
            return "播放音乐"
        if params.get("action") == "pause":
            return "暂停音乐"
        return "音乐控制"
    if category == "fatigue_assist":
        return "疲劳辅助：需要提神"
    if category == "diagnosis":
        return "故障诊断"
    if category == "weather":
        return "天气查询"
    if category == "navigation":
        return "导航查询"
    return category


# ═══════════════════════════════════════════════════════════
#  LLM 意图分解（复杂场景 — 模糊/复合意图）
# ═══════════════════════════════════════════════════════════

INTENT_DECOMPOSE_PROMPT = """\
你是车载智能助手的意图识别引擎。请分析用户输入，分解为多个独立意图。

## 可用的意图类别和对应处理Agent：

| 类别 | 处理Agent | 说明 |
|------|-----------|------|
| ac_control | control_executor | 空调控制（开关/温度/模式/风速） |
| music_control | control_executor | 音乐控制（播放/暂停/切歌/音量/搜索） |
| fatigue_assist | react_agent | 疲劳/困倦辅助（需要组合操作） |
| diagnosis | diagnose_agent | 车辆故障诊断（需要知识库RAG） |
| weather | recommend_agent | 天气查询 |
| navigation | recommend_agent | 导航/路线规划 |
| chitchat | react_agent | 闲聊/问答 |

## 规则
1. 仔细分析用户说的每一个独立需求，拆分为单独意图
2. 每个意图分配最合适的 Agent
3. priority 数字越小优先级越高（0=最高）
4. 安全相关（疲劳/故障）优先级高
5. **如果同时检测到疲劳+控制意图，只输出一个 fatigue_assist 意图给 react_agent**，
   不要拆成多个单独意图。因为 react_agent 会统一编排所有控制操作，
   提供更自然的组合响应。
6. 如果用户意图不明确，设置 needs_clarification=true
7. **必须从用户原话中提取关键参数填入 params**：
   - navigation 类别 → params: {{"destination": "提取的地名（去掉导航/帮/到/去等前缀词）"}}
   - weather 类别 → params: {{"city": "提取的城市名"}}
   - music_control 类别 → params: {{"singer": "提取的歌手名", "action": "play/pause"}}
   - ac_control 类别 → params: {{"action": "TurnOnAC/TurnOffAC", "temperature": 温度数字}}

## 当前驾驶员状态：
- 视线方向: {gaze}
- 疲劳等级: {fatigue_level}
- 安全等级: {safety_level}

用户输入："{user_text}

请严格输出JSON格式回复：
```json
{{
  "intents": [
    {{
      "id": "intent_1",
      "category": "ac_control",
      "agent": "control_executor",
      "priority": 5,
      "description": "打开空调",
      "params": {{ "action": "TurnOnAC" }}
    }}
  ],
  "needs_clarification": false,
  "clarification_question": "",
  "overall_summary": "用户想要打开空调并播放音乐"
}}
```
"""


class IntentionAgent:
    """
    意图识别 Agent。

    双通道策略：
      - 规则快速通道：明确的单步指令（开空调、播放音乐等）< 10ms
      - LLM 分解通道：模糊/复合意图 → LLM 拆解 → 结构化计划
    """

    def __init__(self):
        self._client = None

    @property
    def client(self):
        if self._client is None:
            from modules.ai.deepseek_client import deepseek_client
            self._client = deepseek_client
        return self._client

    def analyze(self, text: str, driver_state: dict = None) -> IntentionPlan:
        """
        分析用户输入，返回意图调度计划。

        Args:
            text: 用户语音/文本输入
            driver_state: 驾驶员状态（用于上下文）
        """
        if not text or not text.strip():
            return IntentionPlan(overall_summary="空输入")

        ds = driver_state or {}
        gaze = ds.get("gaze", "center")
        fatigue_level = ds.get("fatigue_level", "normal")
        safety_level = ds.get("severity", "normal")

        # ── Step 1: 规则快速匹配
        rule_intents = rule_based_intent_detection(text)

        # 简单情况（1-2个明确意图，直接用规则结果 + 补充描述
        if len(rule_intents) >= 1 and not self._needs_llm(text, rule_intents):
            summary = self._build_summary(rule_intents)
            return IntentionPlan(
                intents=rule_intents,
                overall_summary=summary,
            )

        # ── Step 2: 复杂情况 → LLM 分解
        try:
            return self._llm_decompose(text, gaze, fatigue_level, safety_level)
        except Exception as e:
            logger.warning(f"LLM 意图分解失败: {e}，使用规则结果兜底")
            if rule_intents:
                return IntentionPlan(
                    intents=rule_intents,
                    overall_summary=self._build_summary(rule_intents),
                )
            return IntentionPlan(
                intents=[IntentItem(
                    id="intent_1",
                    category="chitchat",
                    agent="react_agent",
                    priority=9,
                    description=text[:30],
                    params={"text": text},
                )],
                overall_summary=text[:30],
            )

    def _needs_llm(self, text: str, rule_intents: List[IntentItem]) -> bool:
        """判断是否需要 LLM 分解/编排。"""
        categories = [i.category for i in rule_intents]

        # 多个意图（≥2）→ 需要 LLM 统一编排，避免碎片化响应
        if len(categories) >= 2:
            return True

        # 疲劳 + 控制类复合意图 → 需要 ReAct Agent 统一编排
        has_fatigue = "fatigue_assist" in categories
        has_control = any(c in categories for c in ["ac_control", "music_control"])
        if has_fatigue and has_control:
            return True  # 疲劳+控制 → 需要组合编排

        # 有诊断类意图 → 需要 RAG + LLM
        if "diagnosis" in categories:
            return True

        # 导航类 → 需要 LLM 提取目的地等关键参数
        if "navigation" in categories:
            return True

        # 模糊表达（不是明确指令词）→ 需要 LLM
        vague_words = ["有点", "好像", "感觉", "不知道", "怎么办", "为什么"]
        if any(w in text for w in vague_words):
            return True

        # 疑问句式
        if "？" in text or "?" in text:
            return True

        return False

    def _llm_decompose(self, text: str, gaze: str, fatigue: str, safety: str) -> IntentionPlan:
        """使用 LLM 进行意图分解。"""
        prompt = INTENT_DECOMPOSE_PROMPT.format(
            user_text=text,
            gaze=gaze,
            fatigue_level=fatigue,
            safety_level=safety,
        )

        response = self.client.client.chat.completions.create(
            model="deepseek-chat",
            messages=[
                {"role": "system", "content": "你是专业的车载意图识别引擎，只输出JSON，不要输出任何非JSON文本。"},
                {"role": "user", "content": prompt},
            ],
            max_tokens=800,
            temperature=0.3,
        )

        content = response.choices[0].message.content.strip()

        # 解析 JSON
        try:
            data = json.loads(content)
        except json.JSONDecodeError:
            # 尝试提取 JSON 代码块
            if "```json" in content:
                start = content.find("```json") + 7
                end = content.find("```", start)
                try:
                    data = json.loads(content[start:end].strip())
                except json.JSONDecodeError as e2:
                    logger.error(f"LLM JSON解析失败 (code block): {e2}\n原始响应: {content[:500]}")
                    raise
            else:
                logger.error(f"LLM JSON解析失败: 原始响应前500字: {content[:500]}")
                raise

        intents = []
        for idx, item in enumerate(data.get("intents", [])):
            intents.append(IntentItem(
                id=item.get("id", f"intent_{idx+1}"),
                category=item.get("category", "chitchat"),
                agent=item.get("agent", "react_agent"),
                priority=item.get("priority", 5),
                description=item.get("description", ""),
                params=item.get("params", {}),
            ))

        # 按优先级排序
        intents.sort(key=lambda x: x.priority)

        return IntentionPlan(
            intents=intents,
            needs_clarification=data.get("needs_clarification", False),
            clarification_question=data.get("clarification_question", ""),
            overall_summary=data.get("overall_summary", text[:30]),
        )

    def _build_summary(self, intents: List[IntentItem]) -> str:
        """从意图列表生成一句话总结。"""
        if not intents:
            return "无明确意图"
        descs = [i.description for i in intents]
        if len(descs) == 1:
            return descs[0]
        return "、".join(descs[:-1]) + "和" + descs[-1]
