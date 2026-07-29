"""
multi_agent_graph.py 单元测试 — LangGraph 六Agent编排

覆盖:
  - _resolve_agent_node: Agent名称映射
  - _route_after_safety: VETO 短路路由
  - _build_evidence_pool: 证据池构建
  - GraphResponse / GraphResult 数据结构
  - MultiAgentOrchestrator: VETO 短路（图路径 + 顺序降级）
  - MultiAgentOrchestrator: 正常执行（非 VETO）
  - agents_used 累加（图路径 + 顺序降级）
"""
import pytest
from unittest.mock import patch

from modules.ai.multi_agent_graph import (
    GraphResponse,
    GraphResult,
    MultiAgentOrchestrator,
    _aggregate_node,
    _resolve_agent_node,
    _route_after_safety,
    _build_evidence_pool,
    _AGENT_NAME_MAP,
    _CATEGORY_TO_NODE,
)


# ═══════════════════════════════════════════════════════════
#  数据结构
# ═══════════════════════════════════════════════════════════

class TestGraphResult:
    def test_defaults(self):
        r = GraphResult(intent_id="test", intent_category="test", agent_name="Test")
        assert r.success is True
        assert r.reply_text == ""
        assert r.actions == []
        assert r.data == {}
        assert r.error == ""
        assert r.duration_ms == 0.0


class TestGraphResponse:
    def test_defaults(self):
        r = GraphResponse(success=True)
        assert r.overall_reply == ""
        assert r.results == []
        assert r.actions == []
        assert r.needs_clarification is False
        assert r.route == "multi_agent_graph"
        assert r.agents_used == []
        assert r.audit_result == {}
        assert r.evidence == []
        assert r.safety_output == {}


# ═══════════════════════════════════════════════════════════
#  Agent 名称映射
# ═══════════════════════════════════════════════════════════

class TestResolveAgentNode:
    def test_control_executor_maps_to_interaction(self):
        assert _resolve_agent_node("control_executor", "") == "interaction"

    def test_react_agent_maps_to_interaction(self):
        assert _resolve_agent_node("react_agent", "") == "interaction"

    def test_diagnose_agent_maps_to_diagnose(self):
        assert _resolve_agent_node("diagnose_agent", "") == "diagnose"

    def test_recommend_agent_maps_to_recommend(self):
        assert _resolve_agent_node("recommend_agent", "") == "recommend"

    def test_analyze_agent_maps_to_analyze(self):
        assert _resolve_agent_node("analyze_agent", "") == "analyze"

    def test_ac_control_category_maps_to_interaction(self):
        assert _resolve_agent_node("", "ac_control") == "interaction"

    def test_navigation_category_maps_to_recommend(self):
        assert _resolve_agent_node("", "navigation") == "recommend"

    def test_diagnosis_category_maps_to_diagnose(self):
        assert _resolve_agent_node("", "diagnosis") == "diagnose"

    def test_driving_analysis_category_maps_to_analyze(self):
        assert _resolve_agent_node("", "driving_analysis") == "analyze"

    def test_unknown_returns_empty(self):
        assert _resolve_agent_node("unknown", "unknown") == ""

    def test_agent_name_takes_priority(self):
        """agent_name 优先于 category"""
        assert _resolve_agent_node("diagnose_agent", "ac_control") == "diagnose"


# ═══════════════════════════════════════════════════════════
#  路由函数
# ═══════════════════════════════════════════════════════════

class TestRouteAfterSafety:
    def test_veto_routes_to_aggregate(self):
        """should_veto=True → aggregate（短路）"""
        state = {"safety_output": {"should_veto": True}}
        assert _route_after_safety(state) == "aggregate"

    def test_dangerous_routes_to_aggregate(self):
        """risk_level=dangerous → aggregate"""
        state = {"safety_output": {"risk_level": "dangerous", "should_veto": False}}
        assert _route_after_safety(state) == "aggregate"

    def test_normal_routes_to_intention(self):
        """正常状态 → intention"""
        state = {"safety_output": {"risk_level": "normal", "should_veto": False}}
        assert _route_after_safety(state) == "intention"

    def test_distracted_routes_to_intention(self):
        """distracted 不是 dangerous → intention"""
        state = {"safety_output": {"risk_level": "distracted", "should_veto": False}}
        assert _route_after_safety(state) == "intention"

    def test_empty_safety_output(self):
        """无 safety_output → intention（默认安全）"""
        assert _route_after_safety({}) == "intention"


# ═══════════════════════════════════════════════════════════
#  证据池构建
# ═══════════════════════════════════════════════════════════

class TestBuildEvidencePool:
    def test_has_safety_refs(self):
        pool = _build_evidence_pool({})
        assert "[SAFETY:§1]" in pool["[SAFETY"]
        assert "[SAFETY:§5]" in pool["[SAFETY"]

    def test_has_api_refs(self):
        pool = _build_evidence_pool({})
        assert "[API:amap_nav]" in pool["[API"]
        assert "[API:amap_weather]" in pool["[API"]

    def test_has_template_refs(self):
        pool = _build_evidence_pool({})
        assert "[TMPL" in pool
        assert len(pool["[TMPL"]) > 0

    def test_merges_agent_evidence(self):
        """Agent 声称的引用被合并到证据池"""
        pool = _build_evidence_pool({
            "recommend": {"evidence_ids": ["[CUSTOM:§1]", "[SAFETY:§1]"]},
        })
        assert "[CUSTOM:§1]" in pool.get("[CUSTOM", [])

    def test_empty_agent_outputs(self):
        pool = _build_evidence_pool({})
        assert isinstance(pool, dict)
        assert len(pool) > 0


# ═══════════════════════════════════════════════════════════
#  Orchestrator: VETO 短路
# ═══════════════════════════════════════════════════════════

DANGEROUS_STATE = {
    "fatigue_score": 90, "fatigue_level": "danger",
    "perclos": 0.55, "severity": "severe", "gaze": "center",
    "head_pose": {"pitch": 5, "yaw": 2, "roll": 0},
}

NORMAL_STATE = {
    "fatigue_score": 10, "fatigue_level": "normal",
    "perclos": 0.05, "severity": "normal", "gaze": "center",
    "head_pose": {"pitch": 5, "yaw": 2, "roll": 0},
}


class TestOrchestratorVeto:
    """VETO 短路验证 — 答辩 Demo Slide 18 关键场景"""

    @pytest.fixture
    def orch(self):
        return MultiAgentOrchestrator()

    def test_dangerous_triggers_veto(self, orch):
        """危险状态 → route=safety_shortcut"""
        resp = orch.process(text="播放音乐", driver_state=DANGEROUS_STATE)
        assert resp.route == "safety_shortcut"

    def test_veto_reply_is_safety_alert(self, orch):
        """VETO 回复是安全告警，不是音乐播放"""
        resp = orch.process(text="播放音乐", driver_state=DANGEROUS_STATE)
        assert len(resp.overall_reply) > 0
        assert any(kw in resp.overall_reply for kw in ["疲劳", "休息", "停车", "安全", "危险"])

    def test_veto_should_veto_true(self, orch):
        resp = orch.process(text="播放音乐", driver_state=DANGEROUS_STATE)
        assert resp.safety_output.get("should_veto") is True

    def test_veto_risk_level_dangerous(self, orch):
        resp = orch.process(text="播放音乐", driver_state=DANGEROUS_STATE)
        assert resp.safety_output.get("risk_level") == "dangerous"

    def test_veto_skips_interaction_agent(self, orch):
        """VETO 短路 → interaction Agent 不执行"""
        resp = orch.process(text="播放音乐", driver_state=DANGEROUS_STATE)
        assert "safety" in resp.agents_used
        assert "interaction" not in resp.agents_used

    def test_veto_agents_used_nonempty(self, orch):
        """VETO 时 agents_used 仍非空"""
        resp = orch.process(text="播放音乐", driver_state=DANGEROUS_STATE)
        assert len(resp.agents_used) > 0

    def test_sequential_veto_works(self, orch):
        """顺序降级路径也正确 VETO"""
        original = orch._graph
        orch._graph = None
        try:
            resp = orch.process(text="播放音乐", driver_state=DANGEROUS_STATE)
            assert resp.route == "safety_shortcut"
            assert resp.safety_output.get("should_veto") is True
            assert len(resp.agents_used) > 0
        finally:
            orch._graph = original


# ═══════════════════════════════════════════════════════════
#  Orchestrator: 正常执行
# ═══════════════════════════════════════════════════════════

class TestOrchestratorNormal:
    """正常状态下的编排验证"""

    @pytest.fixture
    def orch(self):
        return MultiAgentOrchestrator()

    def test_normal_no_veto(self, orch):
        """正常状态 → 不 VETO"""
        resp = orch.process(text="播放音乐", driver_state=NORMAL_STATE)
        assert resp.route != "safety_shortcut"
        assert resp.safety_output.get("should_veto") is False

    def test_normal_risk_level_normal(self, orch):
        resp = orch.process(text="播放音乐", driver_state=NORMAL_STATE)
        assert resp.safety_output.get("risk_level") == "normal"

    def test_normal_agents_used_includes_safety(self, orch):
        """正常执行也经过 SafetyAgent"""
        resp = orch.process(text="播放音乐", driver_state=NORMAL_STATE)
        assert "safety" in resp.agents_used

    def test_normal_agents_used_includes_intention(self, orch):
        resp = orch.process(text="播放音乐", driver_state=NORMAL_STATE)
        assert "intention" in resp.agents_used

    def test_response_has_results(self, orch):
        resp = orch.process(text="播放音乐", driver_state=NORMAL_STATE)
        assert isinstance(resp.results, list)

    def test_response_has_safety_output(self, orch):
        resp = orch.process(text="播放音乐", driver_state=NORMAL_STATE)
        assert isinstance(resp.safety_output, dict)
        assert "risk_level" in resp.safety_output


# ═══════════════════════════════════════════════════════════
#  Orchestrator: 容错
# ═══════════════════════════════════════════════════════════

class TestOrchestratorResilience:
    """容错性验证"""

    @pytest.fixture
    def orch(self):
        return MultiAgentOrchestrator()

    def test_empty_driver_state(self, orch):
        """空 driver_state 不崩溃"""
        resp = orch.process(text="你好", driver_state={})
        assert resp is not None
        assert isinstance(resp, GraphResponse)

    def test_none_driver_state(self, orch):
        """None driver_state 不崩溃"""
        resp = orch.process(text="你好", driver_state=None)
        assert resp is not None

    def test_empty_text(self, orch):
        """空文本不崩溃"""
        resp = orch.process(text="", driver_state=NORMAL_STATE)
        assert resp is not None

    def test_agents_initialized(self, orch):
        """所有 7 个 Agent 都已初始化"""
        assert orch._safety_agent is not None
        assert orch._intention_agent is not None
        assert orch._interaction_agent is not None
        assert orch._diagnose_agent is not None
        assert orch._analyze_agent is not None
        assert orch._recommend_agent is not None
        assert orch._evidence_audit_agent is not None

    def test_graph_built(self, orch):
        """LangGraph 图已构建"""
        assert orch._graph is not None


# ═══════════════════════════════════════════════════════════
#  审计阻断门 (P1) — EvidenceAudit blocking 阻止不安全回复
# ═══════════════════════════════════════════════════════════

class TestAuditBlocking:
    """P1: audit_status == "blocking" 时阻止不安全回复"""

    def test_blocking_audit_replaces_reply(self):
        """审计阻断时，回复被替换为安全提示（不含原始 Agent 回复）"""
        state = {
            "safety_output": {"should_veto": False, "risk_level": "normal"},
            "needs_clarification": False,
            "audit_result": {
                "audit_status": "blocking",
                "issues": [
                    {"severity": "error", "code": "hallucinated_ref",
                     "message": "引用 '[SAFETY:§99]' 不存在"},
                ],
            },
            "interaction_output": {"confirmation_text": "这是可能不安全的回复"},
            "diagnose_output": None,
            "analyze_output": None,
            "recommend_output": None,
            "user_input": "测试",
        }
        result = _aggregate_node(state)
        reply = result["final_response"]
        # 安全提示关键词
        assert "审计" in reply or "拦截" in reply
        # 原始不安全回复不应出现
        assert "这是可能不安全的回复" not in reply

    def test_blocking_includes_issue_details(self):
        """阻断回复包含具体问题信息"""
        state = {
            "safety_output": {"should_veto": False, "risk_level": "normal"},
            "needs_clarification": False,
            "audit_result": {
                "audit_status": "blocking",
                "issues": [
                    {"severity": "error", "code": "hallucinated_ref",
                     "message": "引用不存在"},
                    {"severity": "warn", "code": "contradiction",
                     "message": "矛盾描述"},
                ],
            },
        }
        result = _aggregate_node(state)
        assert "引用不存在" in result["final_response"]

    def test_issues_found_does_not_block(self):
        """audit_status == "issues_found"（仅有 warn）→ 不阻断，保留 Agent 回复"""
        with patch("modules.ai.deepseek_client.deepseek_client") as mock_llm:
            mock_llm.is_available = False
            state = {
                "safety_output": {"should_veto": False, "risk_level": "normal"},
                "needs_clarification": False,
                "audit_result": {
                    "audit_status": "issues_found",
                    "issues": [
                        {"severity": "warn", "code": "contradiction",
                         "message": "矛盾描述"},
                    ],
                },
                "interaction_output": {"confirmation_text": "正常回复内容"},
            }
            result = _aggregate_node(state)
            # Agent 回复保留（未被审计阻断替换）
            assert "正常回复内容" in result["final_response"]
            assert "审计" not in result["final_response"] or "拦截" not in result["final_response"]

    def test_passed_audit_preserves_reply(self):
        """audit_status == "passed" → 完全保留 Agent 回复"""
        with patch("modules.ai.deepseek_client.deepseek_client") as mock_llm:
            mock_llm.is_available = False
            state = {
                "safety_output": {"should_veto": False, "risk_level": "normal"},
                "needs_clarification": False,
                "audit_result": {"audit_status": "passed", "issues": []},
                "interaction_output": {"confirmation_text": "干净的回复"},
            }
            result = _aggregate_node(state)
            assert "干净的回复" in result["final_response"]
            assert "未通过真实性审计" not in result["final_response"]

    def test_safety_veto_takes_priority_over_audit(self):
        """安全 VETO 优先于审计阻断"""
        state = {
            "safety_output": {"should_veto": True, "risk_level": "dangerous",
                              "recommendation": "请立即停车休息"},
            "needs_clarification": False,
            "audit_result": {"audit_status": "blocking", "issues": []},
        }
        result = _aggregate_node(state)
        assert "请立即停车休息" in result["final_response"]

    def test_no_audit_result_does_not_block(self):
        """无 audit_result → 不阻断（向后兼容）"""
        with patch("modules.ai.deepseek_client.deepseek_client") as mock_llm:
            mock_llm.is_available = False
            state = {
                "safety_output": {"should_veto": False, "risk_level": "normal"},
                "needs_clarification": False,
                "audit_result": None,
                "interaction_output": {"confirmation_text": "正常回复"},
            }
            result = _aggregate_node(state)
            assert "正常回复" in result["final_response"]
            assert "未通过真实性审计" not in result["final_response"]

    def test_graph_response_audit_blocked_field(self):
        """GraphResponse 有 audit_blocked 字段，默认 False"""
        r = GraphResponse(success=True)
        assert r.audit_blocked is False

    def test_graph_response_audit_blocked_true(self):
        """audit_blocked=True 时 success=False"""
        r = GraphResponse(success=False, audit_blocked=True)
        assert r.audit_blocked is True
        assert r.success is False
