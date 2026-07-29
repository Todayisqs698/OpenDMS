"""
schemas.py 单元测试 — Pydantic 模型校验

覆盖:
  - AgentStatus / RiskLevel 枚举值
  - ScaffoldAgentOutput 基类字段与默认值
  - SafetyAgentInput 入参范围校验 (perclos 0-1, fatigue_score 0-100)
  - SafetyOutput 字段与 VETO 语义
  - AuditResult 审计状态 (passed/issues_found/blocking)
  - AuditIssue 问题代码与严重度
"""
import pytest
from pydantic import ValidationError

from modules.ai.schemas import (
    AgentStatus,
    RiskLevel,
    ScaffoldAgentOutput,
    SafetyAgentInput,
    SafetyOutput,
    IntentionAgentInput,
    IntentionOutput,
    SubIntent,
    IntentCategory,
    AgentTarget,
    InteractionAgentInput,
    InteractionOutput,
    DiagnoseAgentInput,
    DiagnosisOutput,
    AnalyzeAgentInput,
    DrivingAnalysisOutput,
    RecommendAgentInput,
    TripPlanOutput,
    EvidenceAuditInput,
    AuditResult,
    AuditIssue,
    Budget,
    DayPlanItem,
    KnowledgeSource,
)


# ═══════════════════════════════════════════════════════════
#  枚举
# ═══════════════════════════════════════════════════════════

class TestAgentStatus:
    def test_enum_values(self):
        assert AgentStatus.SUCCEEDED == "succeeded"
        assert AgentStatus.INSUFFICIENT_DATA == "insufficient_data"
        assert AgentStatus.VETOED == "vetoed"
        assert AgentStatus.FAILED == "failed"

    def test_enum_count(self):
        assert len(AgentStatus) == 4


class TestRiskLevel:
    def test_enum_values(self):
        assert RiskLevel.NORMAL == "normal"
        assert RiskLevel.ATTN_DECLINING == "attn_declining"
        assert RiskLevel.DISTRACTED == "distracted"
        assert RiskLevel.DANGEROUS == "dangerous"

    def test_enum_count(self):
        assert len(RiskLevel) == 4


# ═══════════════════════════════════════════════════════════
#  ScaffoldAgentOutput 基类
# ═══════════════════════════════════════════════════════════

class TestScaffoldAgentOutput:
    def test_default_values(self):
        out = ScaffoldAgentOutput()
        assert out.status == AgentStatus.SUCCEEDED
        assert out.conclusions == []
        assert out.evidence_ids == []
        assert out.data_gaps == []
        assert out.warnings == []
        assert out.errors == []
        assert out.model_call_count == 0
        assert out.parse_retry_count == 0
        assert out.token_usage is None
        assert out.structured_output_parser == "PydanticOutputParser"

    def test_with_values(self):
        out = ScaffoldAgentOutput(
            status=AgentStatus.FAILED,
            conclusions=["test conclusion"],
            evidence_ids=["[SAFETY:§1]"],
            errors=["something went wrong"],
            model_call_count=3,
        )
        assert out.status == AgentStatus.FAILED
        assert len(out.conclusions) == 1
        assert out.evidence_ids[0] == "[SAFETY:§1]"

    def test_model_call_count_negative_rejected(self):
        with pytest.raises(ValidationError):
            ScaffoldAgentOutput(model_call_count=-1)


# ═══════════════════════════════════════════════════════════
#  SafetyAgentInput
# ═══════════════════════════════════════════════════════════

class TestSafetyAgentInput:
    def test_defaults(self):
        inp = SafetyAgentInput()
        assert inp.gaze == "center"
        assert inp.head_pitch == 0.0
        assert inp.perclos == 0.0
        assert inp.fatigue_score == 0.0
        assert inp.num_faces == 1
        assert inp.raw_data == {}

    def test_perclos_range(self):
        SafetyAgentInput(perclos=0.0)
        SafetyAgentInput(perclos=1.0)
        SafetyAgentInput(perclos=0.5)
        with pytest.raises(ValidationError):
            SafetyAgentInput(perclos=-0.1)
        with pytest.raises(ValidationError):
            SafetyAgentInput(perclos=1.5)

    def test_fatigue_score_range(self):
        SafetyAgentInput(fatigue_score=0)
        SafetyAgentInput(fatigue_score=100)
        SafetyAgentInput(fatigue_score=50)
        with pytest.raises(ValidationError):
            SafetyAgentInput(fatigue_score=-1)
        with pytest.raises(ValidationError):
            SafetyAgentInput(fatigue_score=101)

    def test_num_faces_non_negative(self):
        SafetyAgentInput(num_faces=0)
        SafetyAgentInput(num_faces=3)
        with pytest.raises(ValidationError):
            SafetyAgentInput(num_faces=-1)

    def test_from_dict(self):
        inp = SafetyAgentInput.model_validate({
            "gaze": "left",
            "fatigue_score": 85,
            "perclos": 0.6,
        })
        assert inp.gaze == "left"
        assert inp.fatigue_score == 85


# ═══════════════════════════════════════════════════════════
#  SafetyOutput
# ═══════════════════════════════════════════════════════════

class TestSafetyOutput:
    def test_required_field_risk_level(self):
        with pytest.raises(ValidationError):
            SafetyOutput()

    def test_with_risk_level(self):
        out = SafetyOutput(risk_level=RiskLevel.DANGEROUS)
        assert out.risk_level == RiskLevel.DANGEROUS
        assert out.should_veto is False  # 默认 False

    def test_veto_semantics(self):
        out = SafetyOutput(
            risk_level=RiskLevel.DANGEROUS,
            should_veto=True,
            recommendation="立即停车休息",
        )
        assert out.should_veto is True
        assert out.risk_level == RiskLevel.DANGEROUS

    def test_normal_no_veto(self):
        out = SafetyOutput(risk_level=RiskLevel.NORMAL)
        assert out.should_veto is False
        assert out.risk_level == RiskLevel.NORMAL

    def test_risk_score_range(self):
        SafetyOutput(risk_level=RiskLevel.NORMAL, risk_score=0)
        SafetyOutput(risk_level=RiskLevel.NORMAL, risk_score=100)
        with pytest.raises(ValidationError):
            SafetyOutput(risk_level=RiskLevel.NORMAL, risk_score=-1)
        with pytest.raises(ValidationError):
            SafetyOutput(risk_level=RiskLevel.NORMAL, risk_score=101)


# ═══════════════════════════════════════════════════════════
#  IntentionAgent
# ═══════════════════════════════════════════════════════════

class TestIntentionSchemas:
    def test_sub_intent_defaults(self):
        si = SubIntent(category=IntentCategory.AC_CONTROL, agent=AgentTarget.INTERACTION)
        assert si.priority == 5
        assert si.confidence == 0.8

    def test_sub_intent_priority_range(self):
        SubIntent(category=IntentCategory.CHITCHAT, agent=AgentTarget.INTERACTION, priority=0)
        SubIntent(category=IntentCategory.CHITCHAT, agent=AgentTarget.INTERACTION, priority=9)
        with pytest.raises(ValidationError):
            SubIntent(category=IntentCategory.CHITCHAT, agent=AgentTarget.INTERACTION, priority=10)

    def test_intention_output_defaults(self):
        out = IntentionOutput()
        assert out.intents == []
        assert out.needs_clarification is False
        assert out.clarification_question == ""


# ═══════════════════════════════════════════════════════════
#  EvidenceAudit
# ═══════════════════════════════════════════════════════════

class TestAuditSchemas:
    def test_audit_issue_required_code(self):
        with pytest.raises(ValidationError):
            AuditIssue()

    def test_audit_issue_with_code(self):
        issue = AuditIssue(code="hallucinated_ref")
        assert issue.code == "hallucinated_ref"
        assert issue.severity == "warn"

    def test_audit_issue_error_severity(self):
        issue = AuditIssue(code="hallucinated_ref", severity="error")
        assert issue.severity == "error"

    def test_audit_result_defaults(self):
        result = AuditResult()
        assert result.audit_status == "passed"
        assert result.issues == []
        assert result.manual_review_required is False

    def test_audit_result_blocking(self):
        result = AuditResult(
            audit_status="blocking",
            manual_review_required=True,
        )
        assert result.audit_status == "blocking"
        assert result.manual_review_required is True

    def test_evidence_audit_input_defaults(self):
        inp = EvidenceAuditInput()
        assert inp.agent_outputs == {}
        assert inp.available_evidence == {}


# ═══════════════════════════════════════════════════════════
#  Recommend / TripPlan
# ═══════════════════════════════════════════════════════════

class TestRecommendSchemas:
    def test_budget_defaults(self):
        b = Budget()
        assert b.total == 0.0
        assert b.tickets == 0.0

    def test_day_plan_item(self):
        item = DayPlanItem(day_index=1)
        assert item.day_index == 1
        assert item.attractions == []
        assert item.hotel is None

    def test_recommend_agent_input_days_range(self):
        RecommendAgentInput(days=1)
        RecommendAgentInput(days=30)
        with pytest.raises(ValidationError):
            RecommendAgentInput(days=0)
        with pytest.raises(ValidationError):
            RecommendAgentInput(days=31)

    def test_trip_plan_output_defaults(self):
        out = TripPlanOutput()
        assert out.city == ""
        assert out.itinerary == []
        assert out.needs_clarification is False


# ═══════════════════════════════════════════════════════════
#  Diagnose / Analyze
# ═══════════════════════════════════════════════════════════

class TestDiagnoseAnalyzeSchemas:
    def test_diagnose_input_top_k_range(self):
        DiagnoseAgentInput(top_k=1)
        DiagnoseAgentInput(top_k=10)
        with pytest.raises(ValidationError):
            DiagnoseAgentInput(top_k=0)
        with pytest.raises(ValidationError):
            DiagnoseAgentInput(top_k=11)

    def test_diagnosis_output_urgency_values(self):
        DiagnosisOutput(urgency="immediate")
        DiagnosisOutput(urgency="soon")
        DiagnosisOutput(urgency="routine")
        with pytest.raises(ValidationError):
            DiagnosisOutput(urgency="critical")

    def test_driving_analysis_output_fatigue_trend(self):
        DrivingAnalysisOutput(fatigue_trend="improving")
        DrivingAnalysisOutput(fatigue_trend="stable")
        DrivingAnalysisOutput(fatigue_trend="declining")
        with pytest.raises(ValidationError):
            DrivingAnalysisOutput(fatigue_trend="unknown")

    def test_driving_analysis_output_score_range(self):
        DrivingAnalysisOutput(score=0)
        DrivingAnalysisOutput(score=100)
        with pytest.raises(ValidationError):
            DrivingAnalysisOutput(score=-1)
        with pytest.raises(ValidationError):
            DrivingAnalysisOutput(score=101)

    def test_knowledge_source(self):
        ks = KnowledgeSource(ref_id="[KB:manual §3.2]")
        assert ks.ref_id == "[KB:manual §3.2]"
        assert ks.score == 0.0
