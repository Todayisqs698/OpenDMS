"""
LangGraph 六Agent编排 — 三层拓扑
=================================

SafetyAgent (串行, VETO) → IntentionAgent (串行, 路由)
  → 并行执行Agent (Interaction/Diagnose/Analyze/Recommend)
  → EvidenceAuditAgent (串行, 审计) → Aggregate

对齐 PLAN.md §8 LangGraph 编排拓扑。
所有 Agent 走 BaseScaffoldAgent.run() 统一入口，输出 Pydantic 校验。
"""

from __future__ import annotations

import logging
import operator
import time
from dataclasses import dataclass, field
from typing import Annotated, Optional, TypedDict

from langgraph.graph import END, START, StateGraph

from modules.ai.agents.analyze_agent import AnalyzeAgent
from modules.ai.agents.diagnose_agent import DiagnoseAgent
from modules.ai.agents.evidence_audit import EvidenceAuditAgent
from modules.ai.agents.interaction_agent import InteractionAgent
from modules.ai.agents.recommend_agent import RecommendAgent
from modules.ai.agents.safety_agent import SafetyAgent
from modules.ai.intention_agent import IntentionAgent
from modules.ai.schemas import (
    AgentStatus,
    AnalyzeAgentInput,
    DiagnoseAgentInput,
    DrivingAnalysisOutput,
    DiagnosisOutput,
    EvidenceAuditInput,
    InteractionAgentInput,
    InteractionOutput,
    RecommendAgentInput,
    SafetyAgentInput,
    SafetyOutput,
    TripPlanOutput,
)

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════
#  数据结构 — 兼容 OrchestratorResponse / ExecutionResult
# ═══════════════════════════════════════════════════════════

@dataclass
class GraphResult:
    """单个 Agent 执行结果 — 兼容 ExecutionResult"""
    intent_id: str
    intent_category: str
    agent_name: str
    success: bool = True
    reply_text: str = ""
    actions: list = field(default_factory=list)
    data: dict = field(default_factory=dict)
    error: str = ""
    duration_ms: float = 0.0


@dataclass
class GraphResponse:
    """编排器统一响应 — 兼容 OrchestratorResponse"""
    success: bool
    overall_reply: str = ""
    results: list = field(default_factory=list)
    actions: list = field(default_factory=list)
    needs_clarification: bool = False
    clarification_question: str = ""
    total_duration_ms: float = 0.0
    route: str = "multi_agent_graph"
    intent_plan: dict = field(default_factory=dict)
    agents_used: list = field(default_factory=list)
    audit_result: dict = field(default_factory=dict)
    audit_blocked: bool = False
    evidence: list = field(default_factory=list)
    safety_output: dict = field(default_factory=dict)


# ═══════════════════════════════════════════════════════════
#  LangGraph 状态
# ═══════════════════════════════════════════════════════════

class MultiAgentState(TypedDict):
    """LangGraph 状态：在各节点间流转"""
    # 输入
    user_input: str
    driver_state: dict
    conversation_context: str
    # 串行输出
    safety_output: Optional[dict]
    intention_output: Optional[dict]
    intention_plan: Optional[dict]
    agents_to_run: list[str]
    needs_clarification: bool
    clarification_question: str
    # 并行输出
    interaction_output: Optional[dict]
    diagnose_output: Optional[dict]
    analyze_output: Optional[dict]
    recommend_output: Optional[dict]
    # 审计输出
    audit_result: Optional[dict]
    # 聚合
    final_response: str
    # 累加字段（使用 reducer）
    agents_used: Annotated[list[str], operator.add]
    all_evidence: Annotated[list[str], operator.add]
    errors: Annotated[list[str], operator.add]


# ═══════════════════════════════════════════════════════════
#  Agent 名称映射
# ═══════════════════════════════════════════════════════════

# IntentionAgent 的 agent 字段 → 图节点名
_AGENT_NAME_MAP = {
    "control_executor": "interaction",
    "react_agent": "interaction",
    "diagnose_agent": "diagnose",
    "recommend_agent": "recommend",
    "analyze_agent": "analyze",
}

# 意图类别 → 图节点名（备用映射）
_CATEGORY_TO_NODE = {
    "ac_control": "interaction",
    "music_control": "interaction",
    "fatigue_assist": "interaction",
    "diagnosis": "diagnose",
    "weather": "recommend",
    "navigation": "recommend",
    "trip_plan": "recommend",
    "attractions": "recommend",
    "location_management": "interaction",
    "context_query": "interaction",
    "chitchat": "interaction",
    "driving_analysis": "analyze",
}


def _resolve_agent_node(agent_name: str, category: str) -> str:
    """将 IntentionAgent 的 agent/category 映射到图节点名"""
    return _AGENT_NAME_MAP.get(agent_name, "") or _CATEGORY_TO_NODE.get(category, "")


# ═══════════════════════════════════════════════════════════
#  图节点函数
# ═══════════════════════════════════════════════════════════

def _safety_node(state: MultiAgentState, agent: SafetyAgent) -> dict:
    """安全 Agent 节点 — 传感器→风险评级，VETO 可短路

    传感器数据映射策略：
      - gaze / head_pitch / head_yaw / head_roll → 结构化字段（canonical）
      - eye_frames → raw_data（PERCLOS 计算需要原始帧序列）
      - 不把 gaze_data / head_pose dict 传入 raw_data，避免前端相机
        的小幅抖动误触发 heavy_head → distracted 误判。
    """
    if agent is None:
        return {"safety_output": {"status": "failed", "risk_level": "normal",
                                  "should_veto": False, "errors": ["agent not initialized"]}}

    ds = state.get("driver_state", {})
    try:
        # 仅提取 eye_frames 传入 raw_data（PERCLOS 计算需要）
        raw_data: dict = {}
        eye_frames = ds.get("eye_frames", [])
        if eye_frames:
            raw_data["eye_frames"] = eye_frames

        # gaze 和 head_pose 用结构化字段传入，避免原始相机数据误判
        # 优先从 driver_state 的扁平字段读取，兼容前端两种格式
        gaze_state = ds.get("gaze", "center")
        # 如果 gaze 是 dict（如 {"state": "left", "duration": 3.5}），提取 state
        if isinstance(gaze_state, dict):
            gaze_state = gaze_state.get("state", "center")

        head_pitch = ds.get("head_pitch", 0.0)
        head_yaw = ds.get("head_yaw", 0.0)
        head_roll = ds.get("head_roll", 0.0)
        # 也兼容 head_pose 为 dict 的情况，但做钳位避免误判
        head_pose_dict = ds.get("head_pose")
        if isinstance(head_pose_dict, dict):
            head_pitch = head_pose_dict.get("pitch", head_pitch)
            head_yaw = head_pose_dict.get("yaw", head_yaw)
            head_roll = head_pose_dict.get("roll", head_roll)

        inp = SafetyAgentInput(
            gaze=gaze_state,
            head_pitch=head_pitch,
            head_yaw=head_yaw,
            head_roll=head_roll,
            perclos=ds.get("perclos", 0.0),
            blink_rate=ds.get("blink_rate", 0.0),
            fatigue_score=ds.get("fatigue_score", 0.0),
            num_faces=ds.get("num_faces", 1),
            raw_data=raw_data,
        )
        output: SafetyOutput = agent.run(inp)
        return {
            "safety_output": output.model_dump(),
            "agents_used": ["safety"],
        }
    except Exception as e:
        logger.error("SafetyAgent 执行失败: %s", e, exc_info=True)
        return {
            "safety_output": {"status": "failed", "risk_level": "normal",
                              "risk_score": 0, "should_veto": False,
                              "recommendation": "", "errors": [str(e)]},
            "agents_used": ["safety"],
            "errors": [f"safety: {e}"],
        }


def _intention_node(state: MultiAgentState, agent: IntentionAgent) -> dict:
    """意图识别 Agent 节点 — 文本→意图图，决定走哪些下游 Agent"""
    if agent is None:
        return {
            "intention_output": {"status": "failed", "intents": [],
                                  "needs_clarification": False, "overall_summary": ""},
            "intention_plan": {"intents": [], "overall_summary": ""},
            "agents_to_run": ["interaction"],
            "needs_clarification": False,
            "errors": ["intention agent not initialized"],
        }

    text = state.get("user_input", "")
    ds = state.get("driver_state", {})
    ctx = state.get("conversation_context", "")

    try:
        plan = agent.analyze(text, ds, conversation_context=ctx)
        plan_dict = plan.to_dict()

        # 确定需要执行的 Agent（仅在无需澄清时）
        agents_to_run: set[str] = set()
        if not plan.needs_clarification:
            for intent in plan.intents:
                node = _resolve_agent_node(intent.agent, intent.category)
                if node:
                    agents_to_run.add(node)
            if not agents_to_run:
                agents_to_run.add("interaction")

        return {
            "intention_output": {
                "status": "succeeded",
                "intents": plan_dict.get("intents", []),
                "needs_clarification": plan.needs_clarification,
                "clarification_question": plan.clarification_question,
                "overall_summary": plan.overall_summary,
            },
            "intention_plan": plan_dict,
            "agents_to_run": list(agents_to_run),
            "needs_clarification": plan.needs_clarification,
            "clarification_question": plan.clarification_question,
            "agents_used": ["intention"],
        }
    except Exception as e:
        logger.error("IntentionAgent 执行失败: %s", e, exc_info=True)
        return {
            "intention_output": {"status": "failed", "intents": [],
                                  "needs_clarification": False, "overall_summary": text[:30]},
            "intention_plan": {"intents": [], "overall_summary": text[:30]},
            "agents_to_run": ["interaction"],
            "needs_clarification": False,
            "agents_used": ["intention"],
            "errors": [f"intention: {e}"],
        }


def _interaction_node(state: MultiAgentState, agent: InteractionAgent) -> dict:
    """交互 Agent 节点 — 手势/语音意图理解"""
    if "interaction" not in state.get("agents_to_run", []):
        return {"interaction_output": None}
    if agent is None:
        return {"interaction_output": None, "errors": ["interaction agent not initialized"]}

    intention = state.get("intention_output", {})
    intents = intention.get("intents", [])

    interaction_intents = [
        i for i in intents
        if _resolve_agent_node(i.get("agent", ""), i.get("category", "")) == "interaction"
    ]
    primary = interaction_intents[0] if interaction_intents else {}
    user_input = state.get("user_input", "")

    try:
        inp = InteractionAgentInput(
            intent_category=primary.get("category", "chitchat"),
            params=primary.get("params", {}),
            user_input=user_input,
            keyword_match=primary.get("description", ""),
        )
        output: InteractionOutput = agent.run(inp)
        return {
            "interaction_output": output.model_dump(),
            "agents_used": ["interaction"],
        }
    except Exception as e:
        logger.error("InteractionAgent 执行失败: %s", e, exc_info=True)
        return {
            "interaction_output": {"status": "failed", "action_code": "unknown",
                                   "confirmation_text": f"交互处理失败: {str(e)[:30]}",
                                   "errors": [str(e)]},
            "agents_used": ["interaction"],
            "errors": [f"interaction: {e}"],
        }


def _diagnose_node(state: MultiAgentState, agent: DiagnoseAgent) -> dict:
    """故障诊断 Agent 节点 — RAG 知识库检索"""
    if "diagnose" not in state.get("agents_to_run", []):
        return {"diagnose_output": None}
    if agent is None:
        return {"diagnose_output": None, "errors": ["diagnose agent not initialized"]}

    intention = state.get("intention_output", {})
    intents = intention.get("intents", [])

    diagnose_intents = [
        i for i in intents
        if _resolve_agent_node(i.get("agent", ""), i.get("category", "")) == "diagnose"
    ]
    primary = diagnose_intents[0] if diagnose_intents else {}
    symptom = primary.get("params", {}).get("query", "") or state.get("user_input", "")

    try:
        inp = DiagnoseAgentInput(symptom=symptom, query=symptom, top_k=3)
        output: DiagnosisOutput = agent.run(inp)
        return {
            "diagnose_output": output.model_dump(),
            "agents_used": ["diagnose"],
        }
    except Exception as e:
        logger.error("DiagnoseAgent 执行失败: %s", e, exc_info=True)
        return {
            "diagnose_output": {"status": "failed", "symptom": symptom,
                                "diagnosis": f"诊断失败: {str(e)[:30]}", "errors": [str(e)]},
            "agents_used": ["diagnose"],
            "errors": [f"diagnose: {e}"],
        }


def _analyze_node(state: MultiAgentState, agent: AnalyzeAgent) -> dict:
    """驾驶分析 Agent 节点 — 驾驶行为数据分析"""
    if "analyze" not in state.get("agents_to_run", []):
        return {"analyze_output": None}
    if agent is None:
        return {"analyze_output": None, "errors": ["analyze agent not initialized"]}

    ds = state.get("driver_state", {})
    try:
        inp = AnalyzeAgentInput(
            duration_min=ds.get("duration_min", 0.0),
            total_alerts=ds.get("total_alerts", 0),
            distractions=ds.get("distractions", 0),
            severe_distractions=ds.get("severe_distractions", 0),
            attention_score=ds.get("attention_score", 100),
            avg_gaze=ds.get("avg_gaze", "center"),
            fatigue_level=ds.get("fatigue_level", "normal"),
        )
        output: DrivingAnalysisOutput = agent.run(inp)
        return {
            "analyze_output": output.model_dump(),
            "agents_used": ["analyze"],
        }
    except Exception as e:
        logger.error("AnalyzeAgent 执行失败: %s", e, exc_info=True)
        return {
            "analyze_output": {"status": "failed", "summary": f"分析失败: {str(e)[:30]}",
                               "errors": [str(e)]},
            "agents_used": ["analyze"],
            "errors": [f"analyze: {e}"],
        }


def _recommend_node(state: MultiAgentState, agent: RecommendAgent) -> dict:
    """出行建议 Agent 节点 — 天气/导航/路线规划"""
    if "recommend" not in state.get("agents_to_run", []):
        return {"recommend_output": None}
    if agent is None:
        return {"recommend_output": None, "errors": ["recommend agent not initialized"]}

    intention = state.get("intention_output", {})
    intents = intention.get("intents", [])

    recommend_intents = [
        i for i in intents
        if _resolve_agent_node(i.get("agent", ""), i.get("category", "")) == "recommend"
    ]
    primary = recommend_intents[0] if recommend_intents else {}
    params = primary.get("params", {})
    category = primary.get("category", "general")
    user_input = state.get("user_input", "")

    _cat_map = {"weather": "weather", "navigation": "navigation",
                "trip_plan": "trip_plan", "attractions": "attractions"}

    try:
        inp = RecommendAgentInput(
            city=params.get("city", ""),
            days=params.get("days", 3),
            preference=params.get("preference", ""),
            query=user_input,
            category=_cat_map.get(category, "general"),
            destination=params.get("destination", ""),
        )
        output: TripPlanOutput = agent.run(inp)
        return {
            "recommend_output": output.model_dump(),
            "agents_used": ["recommend"],
        }
    except Exception as e:
        logger.error("RecommendAgent 执行失败: %s", e, exc_info=True)
        return {
            "recommend_output": {"status": "failed",
                                 "reply": f"建议生成失败: {str(e)[:30]}", "errors": [str(e)]},
            "agents_used": ["recommend"],
            "errors": [f"recommend: {e}"],
        }


def _evidence_audit_node(state: MultiAgentState, agent: EvidenceAuditAgent) -> dict:
    """证据审计 Agent 节点 — 真实性校验"""
    if agent is None:
        return {"audit_result": {"status": "failed", "audit_status": "passed",
                                 "issues": [], "errors": ["agent not initialized"]}}

    agent_outputs: dict[str, dict] = {}
    for name, key in [("safety", "safety_output"), ("interaction", "interaction_output"),
                      ("diagnose", "diagnose_output"), ("analyze", "analyze_output"),
                      ("recommend", "recommend_output")]:
        output = state.get(key)
        if output is not None:
            agent_outputs[name] = output

    if not agent_outputs:
        return {"audit_result": {"status": "succeeded", "audit_status": "passed",
                                 "issues": [], "manual_review_required": False}}

    available_evidence = _build_evidence_pool(agent_outputs)

    try:
        inp = EvidenceAuditInput(
            agent_outputs=agent_outputs,
            available_evidence=available_evidence,
        )
        output = agent.run(inp)
        return {"audit_result": output.model_dump(), "agents_used": ["evidence_audit"]}
    except Exception as e:
        logger.error("EvidenceAuditAgent 执行失败: %s", e, exc_info=True)
        return {
            "audit_result": {"status": "failed", "audit_status": "passed",
                             "issues": [], "errors": [str(e)]},
            "agents_used": ["evidence_audit"],
            "errors": [f"evidence_audit: {e}"],
        }


def _aggregate_node(state: MultiAgentState) -> dict:
    """聚合节点 — 生成最终回复"""
    # 安全 VETO 短路
    safety = state.get("safety_output") or {}
    if safety.get("should_veto") or safety.get("risk_level") == "dangerous":
        alert = (safety.get("recommendation") or safety.get("alert_msg")
                 or "⚠️ 检测到危险驾驶状态，请立即注意安全！")
        return {"final_response": alert}

    # 需要澄清
    if state.get("needs_clarification"):
        return {"final_response": state.get("clarification_question", "请提供更多信息")}

    # ── 审计阻断门：audit_status == "blocking" → 阻止不安全回复 ──
    audit = state.get("audit_result") or {}
    if audit.get("audit_status") == "blocking":
        blocking_issues = [i for i in audit.get("issues", [])
                           if i.get("severity") == "error"]
        issue_lines = [f"  • {i.get('message', '未知问题')}" for i in blocking_issues[:3]]
        safe_reply = (
            "抱歉，本次回复未通过真实性审计，已拦截可能不准确的内容。\n"
            + ("\n".join(issue_lines) if issue_lines else "")
            + "\n请稍后重试或换一种方式提问。"
        )
        logger.warning("审计阻断: %d 个严重问题，已拦截不安全回复", len(blocking_issues))
        return {"final_response": safe_reply}

    # 收集各 Agent 的回复文本
    parts: list[str] = []

    interaction = state.get("interaction_output")
    if interaction:
        text = interaction.get("confirmation_text") or interaction.get("recommendation_text", "")
        if text:
            parts.append(text)

    diagnose = state.get("diagnose_output")
    if diagnose:
        text = diagnose.get("diagnosis") or diagnose.get("suggestion", "")
        if text:
            parts.append(text)

    analyze = state.get("analyze_output")
    if analyze:
        text = analyze.get("summary", "")
        if text:
            parts.append(text)

    recommend = state.get("recommend_output")
    if recommend:
        text = recommend.get("reply", "")
        if text:
            parts.append(text)

    # 审计结果摘要（非阻断的 warn 级问题仍附在回复末尾）
    audit_issues = audit.get("issues", [])
    audit_suffix = ""
    if audit_issues:
        blocking = [i for i in audit_issues if i.get("severity") == "error"]
        if blocking:
            audit_suffix = f"\n⚠️ 审计发现 {len(blocking)} 个严重问题"

    if not parts:
        return {"final_response": "抱歉，我无法处理您的请求。请尝试重新表述。"}

    # 尝试用 LLM 合成最终回复
    try:
        from modules.ai.deepseek_client import deepseek_client
        if deepseek_client.is_available:
            user_input = state.get("user_input", "")
            parts_text = "\n".join(f"- {p}" for p in parts)
            prompt = (
                f"你是车载智能助手。根据以下各Agent的分析结果，生成一段简洁的自然语言回复（100字以内）。\n\n"
                f"用户输入: {user_input}\n\n各Agent结果:\n{parts_text}\n\n"
                f"请直接输出回复内容，不要加前缀。"
            )
            response = deepseek_client.client.chat.completions.create(
                model=deepseek_client.chat_model,
                messages=[
                    {"role": "system", "content": "你是车载智能助手，回复简洁实用。"},
                    {"role": "user", "content": prompt},
                ],
                max_tokens=512,
                temperature=0.5,
            )
            final = response.choices[0].message.content.strip()
            if audit_suffix:
                final += audit_suffix
            return {"final_response": final}
    except Exception as e:
        logger.warning("聚合 LLM 调用失败: %s，使用拼接回复", e)

    # 降级：拼接各 Agent 回复
    final = "\n".join(parts)
    if audit_suffix:
        final += audit_suffix
    return {"final_response": final}


# ═══════════════════════════════════════════════════════════
#  路由函数
# ═══════════════════════════════════════════════════════════

def _route_after_safety(state: MultiAgentState) -> str:
    """SafetyAgent VETO 时短路到 aggregate"""
    safety = state.get("safety_output") or {}
    if safety.get("should_veto") or safety.get("risk_level") == "dangerous":
        return "aggregate"
    return "intention"


# ═══════════════════════════════════════════════════════════
#  辅助函数
# ═══════════════════════════════════════════════════════════

def _build_evidence_pool(agent_outputs: dict[str, dict]) -> dict[str, list[str]]:
    """构建可用证据池：知识库已知引用 + 各 Agent 声称的引用，按 source_type 分组。

    知识库引用来自 safety_guidelines.txt (§1-§5) 和 trip_templates.json，
    确保 EvidenceAuditAgent 能检测到引用了不存在的知识库章节。
    """
    pool: dict[str, list[str]] = {
        # 安全知识库 — safety_guidelines.txt 共5章
        "[SAFETY": ["[SAFETY:§1]", "[SAFETY:§2]", "[SAFETY:§3]", "[SAFETY:§4]", "[SAFETY:§5]"],
        # API 引用
        "[API": ["[API:amap_nav]", "[API:amap_weather]", "[API:amap_poi]", "[API:amap_geocode]"],
        # 关键词/手势引用
        "[KEYWORD": [],
        "[GESTURE": [],
        # 数据库引用
        "[DB": [],
    }

    # 加载行程模板的已知引用
    try:
        import json
        import os
        tmpl_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(
                os.path.abspath(__file__)))),
            "data", "knowledge", "trip_templates.json"
        )
        with open(tmpl_path, "r", encoding="utf-8") as f:
            templates = json.load(f)
        pool["[TMPL"] = [f"[TMPL:{t['id']}]" for t in templates]
    except Exception:
        pool["[TMPL"] = []

    # 合并各 Agent 声称的引用（用于自洽性检查）
    for output in agent_outputs.values():
        if not isinstance(output, dict):
            continue
        for ref in output.get("evidence_ids", []):
            source_type = ref.split(":")[0] + ":" if ":" in ref else ref
            # 使用 "[" 前缀分组（如 [SAFETY:§1] → "[SAFETY"）
            prefix = ref.split(":")[0] if ":" in ref else ref
            pool.setdefault(prefix, [])
            if ref not in pool[prefix]:
                pool[prefix].append(ref)
    return pool


# ═══════════════════════════════════════════════════════════
#  编排器
# ═══════════════════════════════════════════════════════════

class MultiAgentOrchestrator:
    """LangGraph 六Agent编排器

    三层拓扑:
      SafetyAgent (串行, VETO) → IntentionAgent (串行, 路由)
      → 并行执行Agent (Interaction/Diagnose/Analyze/Recommend)
      → EvidenceAuditAgent (串行, 审计) → Aggregate
    """

    def __init__(self) -> None:
        self._safety_agent: SafetyAgent | None = None
        self._intention_agent: IntentionAgent | None = None
        self._interaction_agent: InteractionAgent | None = None
        self._diagnose_agent: DiagnoseAgent | None = None
        self._analyze_agent: AnalyzeAgent | None = None
        self._recommend_agent: RecommendAgent | None = None
        self._evidence_audit_agent: EvidenceAuditAgent | None = None
        self._graph = None
        self._init_agents()
        self._init_graph()

    def _init_agents(self) -> None:
        """延迟初始化各 Agent（任一失败不影响其他）"""
        for name, cls, attr in [
            ("SafetyAgent", SafetyAgent, "_safety_agent"),
            ("IntentionAgent", IntentionAgent, "_intention_agent"),
            ("InteractionAgent", InteractionAgent, "_interaction_agent"),
            ("DiagnoseAgent", DiagnoseAgent, "_diagnose_agent"),
            ("AnalyzeAgent", AnalyzeAgent, "_analyze_agent"),
            ("RecommendAgent", RecommendAgent, "_recommend_agent"),
            ("EvidenceAuditAgent", EvidenceAuditAgent, "_evidence_audit_agent"),
        ]:
            try:
                setattr(self, attr, cls())
            except Exception as e:
                logger.error("%s 初始化失败: %s", name, e)

    def _init_graph(self) -> None:
        """构建 LangGraph 状态图"""
        try:
            builder = StateGraph(MultiAgentState)

            # 节点 — 用 lambda 绑定 agent 实例
            builder.add_node("safety", lambda s: _safety_node(s, self._safety_agent))
            builder.add_node("intention", lambda s: _intention_node(s, self._intention_agent))
            builder.add_node("interaction", lambda s: _interaction_node(s, self._interaction_agent))
            builder.add_node("diagnose", lambda s: _diagnose_node(s, self._diagnose_agent))
            builder.add_node("analyze", lambda s: _analyze_node(s, self._analyze_agent))
            builder.add_node("recommend", lambda s: _recommend_node(s, self._recommend_agent))
            builder.add_node("evidence_audit",
                             lambda s: _evidence_audit_node(s, self._evidence_audit_agent))
            builder.add_node("aggregate", _aggregate_node)

            # 入口 → safety
            builder.set_entry_point("safety")

            # safety → 条件路由（VETO → aggregate，否则 → intention）
            builder.add_conditional_edges(
                "safety", _route_after_safety,
                {"aggregate": "aggregate", "intention": "intention"},
            )

            # intention → fan-out 到所有执行 Agent（并行）
            builder.add_edge("intention", "interaction")
            builder.add_edge("intention", "diagnose")
            builder.add_edge("intention", "analyze")
            builder.add_edge("intention", "recommend")

            # 执行 Agent → evidence_audit（fan-in）
            builder.add_edge("interaction", "evidence_audit")
            builder.add_edge("diagnose", "evidence_audit")
            builder.add_edge("analyze", "evidence_audit")
            builder.add_edge("recommend", "evidence_audit")

            # evidence_audit → aggregate → END
            builder.add_edge("evidence_audit", "aggregate")
            builder.add_edge("aggregate", END)

            self._graph = builder.compile()
            logger.info("MultiAgent LangGraph 状态图初始化成功")
        except Exception as e:
            logger.error("LangGraph 初始化失败: %s", e, exc_info=True)
            self._graph = None

    def process(self, text: str, driver_state: dict | None = None,
                callbacks: dict | None = None) -> GraphResponse:
        """处理用户输入，返回编排后的统一响应"""
        total_start = time.time()
        ds = driver_state or {}

        initial_state: MultiAgentState = {
            "user_input": text,
            "driver_state": ds,
            "conversation_context": "",
            "safety_output": None,
            "intention_output": None,
            "intention_plan": None,
            "agents_to_run": [],
            "needs_clarification": False,
            "clarification_question": "",
            "interaction_output": None,
            "diagnose_output": None,
            "analyze_output": None,
            "recommend_output": None,
            "audit_result": None,
            "final_response": "",
            "agents_used": [],
            "all_evidence": [],
            "errors": [],
        }

        if self._graph:
            try:
                final_state = self._graph.invoke(initial_state)
            except Exception as e:
                logger.error("LangGraph 执行失败: %s", e, exc_info=True)
                return GraphResponse(
                    success=False,
                    overall_reply=f"处理失败: {str(e)[:50]}",
                    route="multi_agent_graph",
                    total_duration_ms=(time.time() - total_start) * 1000,
                )
        else:
            final_state = self._process_sequential(initial_state)

        return self._build_response(final_state, total_start, callbacks)

    def _process_sequential(self, state: MultiAgentState) -> dict:
        """顺序执行（LangGraph 不可用时的降级方案）

        注意：state.update() 会覆盖 list 字段而非追加，
        所以 agents_used / all_evidence / errors 需要手动累加。
        """
        def merge(update: dict) -> None:
            for k in ("agents_used", "all_evidence", "errors"):
                if k in update and isinstance(update[k], list):
                    state[k] = (state.get(k) or []) + update[k]
                    del update[k]
            state.update(update)

        merge(_safety_node(state, self._safety_agent))

        safety = state.get("safety_output") or {}
        if safety.get("should_veto") or safety.get("risk_level") == "dangerous":
            merge(_aggregate_node(state))
            return state

        merge(_intention_node(state, self._intention_agent))

        if state.get("needs_clarification"):
            merge(_aggregate_node(state))
            return state

        for node_fn, agent in [
            (_interaction_node, self._interaction_agent),
            (_diagnose_node, self._diagnose_agent),
            (_analyze_node, self._analyze_agent),
            (_recommend_node, self._recommend_agent),
        ]:
            merge(node_fn(state, agent))

        merge(_evidence_audit_node(state, self._evidence_audit_agent))
        merge(_aggregate_node(state))
        return state

    def _build_response(self, state: dict, total_start: float,
                        callbacks: dict | None = None) -> GraphResponse:
        """从最终状态构建 GraphResponse"""
        results: list[GraphResult] = []
        agents_used = list(set(state.get("agents_used", [])))

        safety = state.get("safety_output")
        if safety:
            risk_level = safety.get("risk_level", "normal")
            results.append(GraphResult(
                intent_id="safety_check",
                intent_category="safety",
                agent_name="SafetyAgent",
                success=safety.get("status") == "succeeded",
                reply_text=safety.get("recommendation") or safety.get("alert_msg", ""),
                actions=[{"type": "alert", "level": risk_level}] if risk_level != "normal" else [],
                data=safety,
            ))

        interaction = state.get("interaction_output")
        if interaction:
            intents = (state.get("intention_output") or {}).get("intents", [])
            cat = intents[0].get("category", "chitchat") if intents else "chitchat"
            results.append(GraphResult(
                intent_id="interaction",
                intent_category=cat,
                agent_name="InteractionAgent",
                success=interaction.get("status") == "succeeded",
                reply_text=interaction.get("confirmation_text")
                or interaction.get("recommendation_text", ""),
                data=interaction,
            ))

        diagnose = state.get("diagnose_output")
        if diagnose:
            results.append(GraphResult(
                intent_id="diagnose",
                intent_category="diagnosis",
                agent_name="DiagnoseAgent",
                success=diagnose.get("status") == "succeeded",
                reply_text=diagnose.get("diagnosis", ""),
                data=diagnose,
            ))

        analyze = state.get("analyze_output")
        if analyze:
            results.append(GraphResult(
                intent_id="analyze",
                intent_category="driving_analysis",
                agent_name="AnalyzeAgent",
                success=analyze.get("status") == "succeeded",
                reply_text=analyze.get("summary", ""),
                data=analyze,
            ))

        recommend = state.get("recommend_output")
        if recommend:
            _cat_map = {"navigation": "navigation", "weather": "weather",
                        "trip_plan": "trip_plan", "attractions": "attractions"}
            results.append(GraphResult(
                intent_id="recommend",
                intent_category=_cat_map.get(recommend.get("type", "general"), "general"),
                agent_name="RecommendAgent",
                success=recommend.get("status") == "succeeded",
                reply_text=recommend.get("reply", ""),
                data=recommend,
            ))

        is_veto = bool(safety and (safety.get("should_veto")
                                   or safety.get("risk_level") == "dangerous"))
        route = "safety_shortcut" if is_veto else "multi_agent_graph"

        audit = state.get("audit_result") or {}
        is_audit_blocked = audit.get("audit_status") == "blocking"

        all_evidence: list[str] = []
        for r in results:
            all_evidence.extend(r.data.get("evidence_ids", []))

        response = GraphResponse(
            success=not is_audit_blocked,
            overall_reply=state.get("final_response", ""),
            results=results,
            needs_clarification=state.get("needs_clarification", False),
            clarification_question=state.get("clarification_question", ""),
            total_duration_ms=(time.time() - total_start) * 1000,
            route=route,
            intent_plan=state.get("intention_plan") or {},
            agents_used=agents_used,
            audit_result=audit,
            audit_blocked=is_audit_blocked,
            evidence=list(set(all_evidence)),
            safety_output=safety or {},
        )

        if callbacks:
            if callbacks.get("on_intent") and response.intent_plan:
                callbacks["on_intent"](response.intent_plan)
            if callbacks.get("on_result"):
                for r in results:
                    callbacks["on_result"]({
                        "type": r.intent_category, "text": r.reply_text,
                        "agent": r.agent_name,
                    })

        return response


# ═══════════════════════════════════════════════════════════
#  全局实例
# ═══════════════════════════════════════════════════════════

_orchestrator_instance: MultiAgentOrchestrator | None = None


def get_multi_agent_orchestrator() -> MultiAgentOrchestrator:
    """获取全局 MultiAgentOrchestrator 实例"""
    global _orchestrator_instance
    if _orchestrator_instance is None:
        _orchestrator_instance = MultiAgentOrchestrator()
    return _orchestrator_instance
