"""
evidence_audit.py 单元测试 — EvidenceAuditAgent

覆盖:
  - _check_evidence_exists: 检测虚构引用 (hallucinated_ref)
  - _check_contradictions: 检测矛盾描述 (contradiction)
  - _check_hypothesis_as_fact: 检测假设误报为事实 (hypothesis_as_fact)
  - _check_numeric_claims: 检测数字无来源 (numeric_without_source)
  - audit_status: passed / issues_found / blocking
  - run() 接受 dict 输入，返回 AuditResult
  - 空输入审计通过
"""
import pytest

from modules.ai.agents.evidence_audit import EvidenceAuditAgent
from modules.ai.schemas import (
    AgentStatus,
    AuditResult,
    EvidenceAuditInput,
)


@pytest.fixture
def auditor():
    return EvidenceAuditAgent()


# ═══════════════════════════════════════════════════════════
#  引用真实性校验
# ═══════════════════════════════════════════════════════════

class TestCheckEvidenceExists:
    def test_valid_ref_passes(self, auditor):
        """引用存在于证据池中 → 通过"""
        issues = auditor._check_evidence_exists(
            "recommend",
            {"evidence_ids": ["[SAFETY:§1]"]},
            {"[SAFETY": ["[SAFETY:§1]", "[SAFETY:§2]"]},
        )
        assert len(issues) == 0

    def test_hallucinated_ref_detected(self, auditor):
        """引用不存在于证据池 → hallucinated_ref error"""
        issues = auditor._check_evidence_exists(
            "recommend",
            {"evidence_ids": ["[SAFETY:§99]"]},
            {"[SAFETY": ["[SAFETY:§1]", "[SAFETY:§2]"]},
        )
        assert len(issues) == 1
        assert issues[0].code == "hallucinated_ref"
        assert issues[0].severity == "error"

    def test_multiple_hallucinated_refs(self, auditor):
        """多个虚构引用 → 多个 error"""
        issues = auditor._check_evidence_exists(
            "recommend",
            {"evidence_ids": ["[SAFETY:§1]", "[SAFETY:§99]", "[API:fake]"]},
            {"[SAFETY": ["[SAFETY:§1]"], "[API": ["[API:amap_nav]"]},
        )
        assert len(issues) == 2
        assert all(i.severity == "error" for i in issues)

    def test_empty_evidence_ids(self, auditor):
        """无引用声明 → 通过"""
        issues = auditor._check_evidence_exists(
            "recommend", {"evidence_ids": []}, {"[SAFETY": ["[SAFETY:§1]"]},
        )
        assert len(issues) == 0

    def test_ref_with_unknown_source_type(self, auditor):
        """引用的 source_type 不在证据池中 → 不报错（无法验证）"""
        issues = auditor._check_evidence_exists(
            "recommend",
            {"evidence_ids": ["[UNKNOWN:§1]"]},
            {"[SAFETY": ["[SAFETY:§1]"]},
        )
        assert len(issues) == 0


# ═══════════════════════════════════════════════════════════
#  矛盾检测
# ═══════════════════════════════════════════════════════════

class TestCheckContradictions:
    def test_no_contradiction(self, auditor):
        issues = auditor._check_contradictions("agent", {"summary": "价格便宜实惠"})
        assert len(issues) == 0

    def test_price_contradiction(self, auditor):
        """低价 vs 高端 矛盾"""
        issues = auditor._check_contradictions(
            "agent", {"summary": "价格便宜，但属于高端豪华品牌"}
        )
        assert len(issues) == 1
        assert issues[0].code == "contradiction"
        assert issues[0].severity == "warn"

    def test_safety_contradiction(self, auditor):
        """安全 vs 危险 矛盾"""
        issues = auditor._check_contradictions(
            "agent", {"text": "车辆安全可靠，但存在不稳定风险"}
        )
        assert len(issues) == 1

    def test_multiple_contradictions(self, auditor):
        """多对矛盾同时出现"""
        issues = auditor._check_contradictions(
            "agent", {"text": "便宜但豪华，安静但噪音大"}
        )
        assert len(issues) == 2


# ═══════════════════════════════════════════════════════════
#  假设→事实误报
# ═══════════════════════════════════════════════════════════

class TestCheckHypothesisAsFact:
    def test_no_hypothesis(self, auditor):
        issues = auditor._check_hypothesis_as_fact("agent", {"text": "车辆状态正常"})
        assert len(issues) == 0

    def test_hypothesis_detected(self, auditor):
        issues = auditor._check_hypothesis_as_fact(
            "agent", {"text": "用户普遍认为这款车型省油"}
        )
        assert len(issues) == 1
        assert issues[0].code == "hypothesis_as_fact"

    def test_multiple_hypotheses(self, auditor):
        issues = auditor._check_hypothesis_as_fact(
            "agent", {"text": "大多数情况下，通常来说这个功能很好用"}
        )
        assert len(issues) >= 2


# ═══════════════════════════════════════════════════════════
#  数字溯源
# ═══════════════════════════════════════════════════════════

class TestCheckNumericClaims:
    def test_no_numbers(self, auditor):
        issues = auditor._check_numeric_claims("agent", {"text": "没有数字的文本"})
        assert len(issues) == 0

    def test_numbers_with_evidence(self, auditor):
        """有数字且有 evidence_ids → 通过"""
        issues = auditor._check_numeric_claims(
            "agent", {"text": "油耗降低了15%", "evidence_ids": ["[API:test]"]},
        )
        assert len(issues) == 0

    def test_numbers_without_evidence(self, auditor):
        """有数字但无 evidence_ids → warn"""
        issues = auditor._check_numeric_claims(
            "agent", {"text": "占比30%，减少了20%"},
        )
        assert len(issues) == 1
        assert issues[0].code == "numeric_without_source"
        assert issues[0].severity == "warn"


# ═══════════════════════════════════════════════════════════
#  集成: run() 完整审计
# ═══════════════════════════════════════════════════════════

class TestEvidenceAuditRun:
    def test_empty_input_passes(self, auditor):
        """空输入 → passed"""
        result = auditor.run({})
        assert isinstance(result, AuditResult)
        assert result.audit_status == "passed"
        assert len(result.issues) == 0

    def test_clean_output_passes(self, auditor):
        """干净的输出 → passed"""
        result = auditor.run({
            "agent_outputs": {
                "recommend": {
                    "reply": "推荐西湖，风景优美",
                    "evidence_ids": ["[API:amap_poi]"],
                },
            },
            "available_evidence": {
                "[API": ["[API:amap_poi]"],
            },
        })
        assert result.audit_status == "passed"

    def test_hallucinated_ref_blocks(self, auditor):
        """虚构引用 → blocking"""
        result = auditor.run({
            "agent_outputs": {
                "recommend": {
                    "reply": "根据研究推荐",
                    "evidence_ids": ["[SAFETY:§99]"],
                },
            },
            "available_evidence": {
                "[SAFETY": ["[SAFETY:§1]"],
            },
        })
        assert result.audit_status == "blocking"
        assert result.manual_review_required is True
        assert any(i.code == "hallucinated_ref" for i in result.issues)

    def test_warnings_only_issues_found(self, auditor):
        """仅有 warn 级问题 → issues_found（非 blocking）"""
        result = auditor.run({
            "agent_outputs": {
                "recommend": {
                    "reply": "便宜但豪华",
                },
            },
            "available_evidence": {},
        })
        assert result.audit_status == "issues_found"
        assert result.manual_review_required is False

    def test_multiple_agents_audited(self, auditor):
        """多 Agent 输出均被审计"""
        result = auditor.run({
            "agent_outputs": {
                "recommend": {"reply": "推荐", "evidence_ids": ["[SAFETY:§99]"]},
                "diagnose": {"diagnosis": "便宜但豪华"},
            },
            "available_evidence": {"[SAFETY": ["[SAFETY:§1]"]},
        })
        # recommend 有虚构引用(error) + diagnose 有矛盾(warn)
        assert len(result.issues) >= 2
        assert result.audit_status == "blocking"

    def test_run_with_pydantic_input(self, auditor):
        """接受 EvidenceAuditInput 实例"""
        inp = EvidenceAuditInput(
            agent_outputs={"a": {"text": "正常"}},
            available_evidence={},
        )
        result = auditor.run(inp)
        assert isinstance(result, AuditResult)
        assert result.status == AgentStatus.SUCCEEDED
