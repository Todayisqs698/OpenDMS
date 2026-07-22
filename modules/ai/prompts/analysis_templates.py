"""
分析类 Prompt 模板 — 环境分析 / 驾驶洞察 / 报告生成

涵盖：
  - 环境+天气驾驶分析（替代 environment_agent.py 中的内嵌 prompt）
  - 驾驶洞察（替代 backend/main.py 中 /api/drive/insight 的内嵌 prompt）
  - 驾驶报告（替代 backend/main.py 中 /api/drive/report 的内嵌 prompt）
  - 意图分析降级（替代 interaction_agent.py 中的 _llm_fallback_intent）
"""
from .template import PromptTemplate

# ═══════════════════════════════════════════════════════════════
#  环境分析（天气 + 时间 → 驾驶建议）
# ═══════════════════════════════════════════════════════════════

ENVIRONMENT_ANALYSIS = PromptTemplate(
    id="analysis.environment",
    category="analysis",
    name="环境驾驶分析",
    version="1.0",
    description="基于天气+时段综合判断驾驶风险并给出建议",
    risk_level="normal",
    tags=["analysis", "environment", "weather", "driving"],
    content="""你是车载智能驾驶系统的环境分析专家。请根据环境数据分析驾驶风险并给出建议。

## 环境数据
- 时段: {time_of_day} ({time_tip})
- 天气: {weather_desc} ({weather_type})
- 温度: {temperature}°C
- 湿度: {humidity}%
- 风速: {wind_speed}km/h
- 能见度: {visibility}km

## 任务
1. 综合判断驾驶环境的风险等级（low/medium/high/critical）
2. 给出简洁的驾驶建议（一句话，适合语音播报，{max_words}字以内）
3. 识别需要预警的事项（最多3条）

严格按 JSON 格式输出：
{{"driving_context": "一句话建议", "alerts": [{{"level": "warning", "text": "...", "icon": "⚠️"}}], "reasoning": "推理过程"}}""",
    params=["time_of_day", "time_tip", "weather_desc", "weather_type",
            "temperature", "humidity", "wind_speed", "visibility", "max_words"],
    fallback_content="""请根据以下环境数据生成驾驶建议（JSON格式）：
天气: {weather_desc}，温度: {temperature}°C，时段: {time_of_day}。""",
)

# ═══════════════════════════════════════════════════════════════
#  驾驶主动洞察（触发式观察）
# ═══════════════════════════════════════════════════════════════

DRIVE_INSIGHT = PromptTemplate(
    id="analysis.drive_insight",
    category="analysis",
    name="驾驶主动洞察",
    version="1.0",
    description="摄像头检测到异常时主动观察驾驶员行为，决定是否播报",
    risk_level="normal",
    tags=["analysis", "insight", "proactive", "camera"],
    content="""你是驾驶伙伴，语气温和亲切。就驾驶员行为说一句提醒或鼓励({max_chars}字内)。

驾驶员状态：观察: {gaze_pattern}，注意力: {attention}分。

{trigger_hint}

一切正常就回NONE。""",
    params=["gaze_pattern", "attention", "max_chars", "trigger_hint"],
    fallback_content="""你是驾驶伙伴。观察: {gaze_pattern}，注意力: {attention}分。{trigger_hint}一切正常回NONE。""",
)

# ═══════════════════════════════════════════════════════════════
#  驾驶报告生成
# ═══════════════════════════════════════════════════════════════

DRIVE_REPORT = PromptTemplate(
    id="analysis.drive_report",
    category="analysis",
    name="驾驶行为报告",
    version="1.0",
    description="根据驾驶统计生成结构化报告",
    risk_level="normal",
    tags=["analysis", "report", "statistics", "driving"],
    content="""你是驾驶行为分析师。根据以下数据生成简短报告（{max_words}字内）：

- 驾驶时长: {duration_min}分钟
- 分心次数: {distractions}次（严重{severe}次）
- 注意力评分: {attention_score}分
- 主要视线方向: {avg_gaze}

请输出两部分：
1. 驾驶总结（一句话）
2. 建议（一句话）

格式：总结|建议""",
    params=["duration_min", "distractions", "severe", "attention_score", "avg_gaze", "max_words"],
    fallback_content="驾驶时长{duration_min}分钟，分心{distractions}次。请生成总结和建议。",
)

# ═══════════════════════════════════════════════════════════════
#  意图分析降级（离线/API 不可用时的本地兜底）
# ═══════════════════════════════════════════════════════════════

INTENT_LLM_FALLBACK = PromptTemplate(
    id="analysis.intent_fallback",
    category="analysis",
    name="意图分析LLM降级",
    version="1.0",
    description="LLM 意图分析 API 不可用时的简化 prompt",
    risk_level="normal",
    tags=["analysis", "intent", "fallback", "offline"],
    content="""你是一个车载智能助手。用户说了：「{text}」

请判断意图类型：
- control: 控制车辆功能（空调/音乐/车窗等）
- fault: 询问车辆故障
- entertainment: 娱乐相关（笑话/闲聊等）
- unknown: 其他

只需回复意图类型和简短说明。""",
    params=["text"],
    fallback_content="用户说：「{text}」，请判断意图类型。",
)

# ── 汇总列表 ──
ANALYSIS_TEMPLATES = [
    ENVIRONMENT_ANALYSIS,
    DRIVE_INSIGHT,
    DRIVE_REPORT,
    INTENT_LLM_FALLBACK,
]
