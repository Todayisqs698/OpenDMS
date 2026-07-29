"""
EdgeGuard Agent Schema — 所有 Agent 的 Input/Output Pydantic 模型

对齐 TradePilot 的 Schema 继承体系：
  - ScaffoldAgentOutput 基类（含 token_usage 等元数据）
  - 每个 Agent 有独立的 Input 模型 + Output 子类

设计原则：
  - Input 模型负责入参校验（替代旧的 **kwargs dict）
  - Output 模型继承 ScaffoldAgentOutput，统一携带执行元数据
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Literal, Optional

from pydantic import BaseModel, Field


# ═══════════════════════════════════════════════════════════
#  基类
# ═══════════════════════════════════════════════════════════

class AgentStatus(str, Enum):
    """Agent 执行状态"""
    SUCCEEDED = "succeeded"
    INSUFFICIENT_DATA = "insufficient_data"
    VETOED = "vetoed"
    FAILED = "failed"


class ScaffoldAgentOutput(BaseModel):
    """所有 Agent 输出的基类 — 含元数据追踪

    子类在此基础上添加各自领域字段。
    """
    status: AgentStatus = AgentStatus.SUCCEEDED
    conclusions: list[str] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)
    data_gaps: list[dict] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    # 执行元数据
    model_call_count: int = Field(default=0, ge=0)
    parse_retry_count: int = Field(default=0, ge=0)
    token_usage: Optional[dict[str, int]] = None
    structured_output_parser: str = "PydanticOutputParser"


# ═══════════════════════════════════════════════════════════
#  SafetyAgent
# ═══════════════════════════════════════════════════════════

class RiskLevel(str, Enum):
    NORMAL = "normal"
    ATTN_DECLINING = "attn_declining"
    DISTRACTED = "distracted"
    DANGEROUS = "dangerous"


class SafetyAgentInput(BaseModel):
    """SafetyAgent 入参 — 传感器数据"""
    gaze: str = Field(default="center", description="视线方向")
    head_pitch: float = Field(default=0.0, description="头部俯仰角 °")
    head_yaw: float = Field(default=0.0, description="头部偏航角 °")
    head_roll: float = Field(default=0.0, description="头部翻滚角 °")
    perclos: float = Field(default=0.0, ge=0.0, le=1.0, description="PERCLOS 闭眼比例")
    blink_rate: float = Field(default=0.0, description="眨眼频率 次/分钟")
    fatigue_score: float = Field(default=0.0, ge=0.0, le=100.0, description="疲劳评分")
    num_faces: int = Field(default=1, ge=0, description="检测到的人脸数")
    # 兼容旧接口：完整的原始数据
    raw_data: dict = Field(default_factory=dict, description="原始传感器数据（可选）")


class SafetyOutput(ScaffoldAgentOutput):
    risk_level: RiskLevel = Field(description="风险等级")
    risk_score: float = Field(default=0.0, ge=0.0, le=100.0, description="风险评分")
    primary_factor: str = Field(default="", description="主要风险因素")
    recommendation: str = Field(default="", description="口语化安全建议")
    should_veto: bool = Field(default=False, description="是否否决后续所有 Agent")
    safety_knowledge_refs: list[str] = Field(default_factory=list)
    # 兼容旧接口
    alert_msg: str = Field(default="", description="告警消息")
    metrics: dict = Field(default_factory=dict, description="指标详情")


# ═══════════════════════════════════════════════════════════
#  IntentionAgent
# ═══════════════════════════════════════════════════════════

class IntentCategory(str, Enum):
    AC_CONTROL = "ac_control"
    MUSIC_CONTROL = "music_control"
    NAVIGATION = "navigation"
    WEATHER = "weather"
    DIAGNOSIS = "diagnosis"
    DRIVING_ANALYSIS = "driving_analysis"
    TRIP_PLANNING = "trip_planning"
    KNOWLEDGE_QA = "knowledge_qa"
    CHITCHAT = "chitchat"


class AgentTarget(str, Enum):
    INTERACTION = "interaction"
    DIAGNOSE = "diagnose"
    ANALYZE = "analyze"
    RECOMMEND = "recommend"


class SubIntent(BaseModel):
    category: IntentCategory
    priority: int = Field(default=5, ge=0, le=9)
    agent: AgentTarget
    params: dict = Field(default_factory=dict)
    confidence: float = Field(default=0.8, ge=0.0, le=1.0)


class IntentionAgentInput(BaseModel):
    user_input: str = Field(description="用户原始输入")
    safety_level: str = Field(default="normal")
    conversation_context: str = Field(default="", description="多轮对话上下文")


class IntentionOutput(ScaffoldAgentOutput):
    intents: list[SubIntent] = Field(default_factory=list, description="识别到的意图列表")
    needs_clarification: bool = False
    clarification_question: str = ""
    overall_summary: str = ""


# ═══════════════════════════════════════════════════════════
#  InteractionAgent
# ═══════════════════════════════════════════════════════════

class InteractionAgentInput(BaseModel):
    intent_category: str = Field(default="", description="意图类别")
    params: dict = Field(default_factory=dict)
    user_input: str = Field(default="")
    keyword_match: str = Field(default="未命中", description="本地关键词匹配结果")
    # 兼容旧接口
    gesture: dict = Field(default_factory=dict)
    speech: dict = Field(default_factory=dict)


class InteractionOutput(ScaffoldAgentOutput):
    action_code: str = Field(default="unknown")
    confirmation_text: str = Field(default="")
    params: dict = Field(default_factory=dict)
    match_type: Literal["keyword", "gesture", "llm"] = "llm"
    source: str = ""
    # 兼容旧接口
    recommendation_text: str = Field(default="")
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)


# ═══════════════════════════════════════════════════════════
#  DiagnoseAgent
# ═══════════════════════════════════════════════════════════

class DiagnoseAgentInput(BaseModel):
    symptom: str = Field(default="", description="用户描述的症状")
    knowledge_results: str = Field(default="", description="RAG 检索到的知识")
    faq_match: str = Field(default="未命中", description="FAQ 缓存命中结果")
    # 兼容旧接口
    query: str = Field(default="", description="故障描述（旧字段名）")
    top_k: int = Field(default=3, ge=1, le=10)


class KnowledgeSource(BaseModel):
    ref_id: str = Field(description="引用编号，如 [KB:manual §3.2]")
    snippet: str = Field(default="", description="知识片段摘要")
    score: float = Field(default=0.0, ge=0.0, le=1.0)


class DiagnosisOutput(ScaffoldAgentOutput):
    symptom: str = Field(default="")
    possible_causes: list[str] = Field(default_factory=list)
    knowledge_sources: list[KnowledgeSource] = Field(default_factory=list)
    suggestion: str = Field(default="")
    urgency: Literal["immediate", "soon", "routine"] = "routine"
    # 兼容旧接口
    diagnosis: str = Field(default="", description="诊断总结")
    related_docs: list[dict] = Field(default_factory=list)
    suggestions: list[str] = Field(default_factory=list)
    severity: str = Field(default="unknown")


# ═══════════════════════════════════════════════════════════
#  AnalyzeAgent
# ═══════════════════════════════════════════════════════════

class AnalyzeAgentInput(BaseModel):
    duration_min: float = Field(default=0.0)
    total_alerts: int = Field(default=0)
    alert_breakdown: str = Field(default="{}", description="JSON: {mild:N, moderate:N, dangerous:N}")
    primary_cause: str = Field(default="")
    avg_alerts_30d: str = Field(default="N/A")
    avg_cause_30d: str = Field(default="N/A")
    interactions_summary: str = Field(default="暂不支持")
    # 兼容旧接口
    distractions: int = Field(default=0)
    severe_distractions: int = Field(default=0)
    attention_score: int = Field(default=100)
    avg_gaze: str = Field(default="center")
    fatigue_level: str = Field(default="normal")


class DrivingAnalysisOutput(ScaffoldAgentOutput):
    session_duration_min: float = Field(default=0.0)
    total_alerts: int = Field(default=0)
    alert_breakdown: dict = Field(default_factory=dict)
    fatigue_trend: Literal["improving", "stable", "declining"] = "stable"
    primary_distraction_cause: str = Field(default="")
    improvement_suggestions: list[str] = Field(default_factory=list)
    historical_comparison: str = Field(default="")
    # 兼容旧接口
    summary: str = Field(default="")
    score: int = Field(default=100, ge=0, le=100)
    grade: str = Field(default="A")
    highlights: list[str] = Field(default_factory=list)
    safety_tips: list[str] = Field(default_factory=list)


# ═══════════════════════════════════════════════════════════
#  RecommendAgent
# ═══════════════════════════════════════════════════════════

class Budget(BaseModel):
    total: float = 0.0
    tickets: float = 0.0
    hotels: float = 0.0
    meals: float = 0.0
    transport: float = 0.0


class DayPlanItem(BaseModel):
    day_index: int
    date: str = ""
    attractions: list[dict] = Field(default_factory=list)
    meals: list[dict] = Field(default_factory=list)
    hotel: Optional[dict] = None
    note: str = ""


class RecommendAgentInput(BaseModel):
    city: str = ""
    days: int = Field(default=3, ge=1, le=30)
    preference: str = ""
    forbidden_cities: str = ""
    budget: str = "中等"
    attractions: str = Field(default="[]", description="JSON: 搜索到的景点")
    hotels: str = Field(default="[]", description="JSON: 搜索到的酒店")
    weather_info: str = Field(default="{}", description="JSON: 天气预报")
    template_hit: str = "未命中模板"
    # 兼容旧接口
    query: str = Field(default="")
    category: str = Field(default="general")
    destination: str = Field(default="")


class TripPlanOutput(ScaffoldAgentOutput):
    city: str = Field(default="")
    days: int = Field(default=1)
    itinerary: list[DayPlanItem] = Field(default_factory=list)
    budget: Budget = Field(default_factory=Budget)
    weather_notes: list[str] = Field(default_factory=list)
    template_id: Optional[str] = None
    # 兼容旧接口
    reply: str = Field(default="")
    type: str = Field(default="general")
    trip_plan: Optional[dict] = None
    weather: dict = Field(default_factory=dict)
    nav_data: Optional[dict] = Field(default=None, description="导航数据（兼容 push_structured_results）")
    attractions: list = Field(default_factory=list, description="景点列表（兼容 push_structured_results）")
    suggestions: list[str] = Field(default_factory=list)
    needs_clarification: bool = False
    clarification_question: str = ""


# ═══════════════════════════════════════════════════════════
#  EvidenceAuditAgent
# ═══════════════════════════════════════════════════════════

class AuditIssue(BaseModel):
    code: str = Field(description="问题代码: contradiction / unattributed_fact / hallucinated_ref")
    severity: Literal["error", "warn"] = "warn"
    agent_name: str = Field(default="", description="来源 Agent")
    message: str = Field(default="", description="问题描述")
    fix_hint: str = ""


class EvidenceAuditInput(BaseModel):
    """审计所有执行 Agent 的输出"""
    product: dict = Field(default_factory=dict, description="原始用户输入上下文")
    agent_outputs: dict[str, dict] = Field(
        default_factory=dict,
        description="{agent_name: output_dict} — 所有执行Agent的产出"
    )
    available_evidence: dict[str, list[str]] = Field(
        default_factory=dict,
        description="{source_type: [ref_id, ...]} — 可用的证据池"
    )
    statistics: Optional[dict] = None


class AuditResult(ScaffoldAgentOutput):
    audit_status: Literal["passed", "issues_found", "blocking"] = "passed"
    issues: list[AuditIssue] = Field(default_factory=list)
    conflicting_evidence_ids: list[str] = Field(default_factory=list)
    unresolved_questions: list[str] = Field(default_factory=list)
    manual_review_required: bool = False
