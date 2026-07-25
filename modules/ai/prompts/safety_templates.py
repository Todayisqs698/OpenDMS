"""
安全门控类 Prompt 模板 — 4 级风险注入策略

与原 safety_gate.py 的区别：
  - 从硬编码 dict 升级为结构化 PromptTemplate 对象
  - 支持版本管理、参数绑定、降级模板
  - 可通过 registry 统一检索和导出
"""
from .template import PromptTemplate

# ═══════════════════════════════════════════════════════════════
#  4 级安全注入提示（原 SAFETY_SYSTEM_PROMPTS）
# ═══════════════════════════════════════════════════════════════

SAFETY_NORMAL = PromptTemplate(
    id="safety.normal",
    category="safety",
    name="正常驾驶状态",
    version="1.0",
    description="驾驶员状态正常时的系统提示（空提示，不干扰交互）",
    risk_level="normal",
    tags=["safety", "normal", "silent"],
    content="",
    params=[],
    fallback_content="",
)

SAFETY_ATTN_DECLINING = PromptTemplate(
    id="safety.attn_declining",
    category="safety",
    name="注意力下降提示",
    version="1.0",
    description="驾驶员注意力开始下降，优先安全任务，缩短交互",
    risk_level="attn_declining",
    tags=["safety", "attention", "warning", "soft"],
    content="【注意】驾驶员注意力开始下降，优先执行安全相关任务，避免长时间交互。建议回复控制在{max_reply_len}字以内。",
    params=["max_reply_len"],
    fallback_content="【注意】驾驶员注意力开始下降，优先执行安全相关任务，避免长时间交互。",
)

SAFETY_DISTRACTED = PromptTemplate(
    id="safety.distracted",
    category="safety",
    name="分心状态警告",
    version="1.0",
    description="驾驶员分心，禁用音乐/导航功能，优先提醒安全",
    risk_level="distracted",
    tags=["safety", "distracted", "warning", "restrict"],
    content="【警告】驾驶员处于分心状态！音乐和导航功能已禁用。优先提醒驾驶员注视前方道路。{extra_hint}",
    params=["extra_hint"],
    fallback_content="【警告】驾驶员处于分心状态！音乐和导航功能已禁用。优先提醒驾驶员注意安全。",
)

SAFETY_DANGEROUS = PromptTemplate(
    id="safety.dangerous",
    category="safety",
    name="危险状态紧急告警",
    version="1.0",
    description="驾驶员处于危险状态，仅允许安全告警，禁止其他所有操作",
    risk_level="dangerous",
    tags=["safety", "dangerous", "emergency", "restrict"],
    content="【紧急】驾驶员处于危险状态（{risk_reason}）！只能执行安全告警，禁止其他任何操作。立即提醒驾驶员！",
    params=["risk_reason"],
    fallback_content="【紧急】驾驶员处于危险状态！只能执行安全告警，禁止其他操作。",
)

# ═══════════════════════════════════════════════════════════════
#  工具白名单注入提示
# ═══════════════════════════════════════════════════════════════

TOOL_RESTRICTION_HINT = PromptTemplate(
    id="safety.tool_restriction",
    category="safety",
    name="工具白名单限制提示",
    version="1.0",
    description="告知 LLM 当前可用的工具范围",
    risk_level="distracted",
    tags=["safety", "tools", "restriction"],
    content="当前安全状态下，你只能使用以下工具：{allowed_tools}。如果驾驶员请求超出此范围，请礼貌告知当前无法执行。",
    params=["allowed_tools"],
    fallback_content="",
)

# ═══════════════════════════════════════════════════════════════
#  安全告警兜底消息
# ═══════════════════════════════════════════════════════════════

EMERGENCY_ALERT = PromptTemplate(
    id="safety.emergency_alert",
    category="safety",
    name="紧急告警兜底消息",
    version="1.0",
    description="危险状态下跳过 Agent 直接播报的固定文本",
    risk_level="dangerous",
    tags=["safety", "emergency", "tts", "fallback"],
    content="请立即注视前方道路！您已连续偏离视线{off_road_seconds}秒，请确保行车安全！",
    params=["off_road_seconds"],
    fallback_content="请立即注视前方道路！确保行车安全！",
)

# ── 汇总列表（供 registry 批量注册）──
SAFETY_TEMPLATES = [
    SAFETY_NORMAL,
    SAFETY_ATTN_DECLINING,
    SAFETY_DISTRACTED,
    SAFETY_DANGEROUS,
    TOOL_RESTRICTION_HINT,
    EMERGENCY_ALERT,
]
