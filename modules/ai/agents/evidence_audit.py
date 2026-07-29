"""
EvidenceAuditAgent — 真实性审计 Agent

对齐 TradePilot 的 EvidenceAuditAgent，EdgeGuard 简化版：
  - 冲突检测：同一输出中的矛盾描述
  - 引用真实性校验：声称的 evidence_id 是否存在于证据池
  - 假设→事实误报：推测性语言未标注
  - 数字溯源：数字声明是否有来源

审计检查矩阵:
  | 审计项                  | 检测内容                    | 严重度 |
  | hallucinated_ref        | 引用的 evidence_id 不存在    | error  |
  | contradiction           | 同一输出中有矛盾描述         | warn   |
  | hypothesis_as_fact      | 推测性语言未标注             | warn   |
  | numeric_without_source  | 数字声明无来源               | warn   |
"""

from __future__ import annotations

import json
import logging
import re

from modules.ai.base_agent import BaseScaffoldAgent
from modules.ai.schemas import (
    AgentStatus,
    AuditIssue,
    AuditResult,
    EvidenceAuditInput,
)

logger = logging.getLogger("edgeguard.agent.evidence_audit")


class EvidenceAuditAgent(BaseScaffoldAgent[EvidenceAuditInput, AuditResult]):
    """审计所有执行 Agent 的输出，检测幻觉、矛盾、未标注假设和数字溯源问题"""

    input_model = EvidenceAuditInput
    output_model = AuditResult

    # ── 冲突检测对 ──
    CONFLICT_PAIRS = (
        (("低价", "便宜", "经济", "便宜实惠"), ("高端", "豪华", "premium", "奢华")),
        (("安全", "可靠", "稳定"), ("危险", "不稳定", "风险高")),
        (("静音", "安静", "低噪音"), ("噪音", "吵闹", "轰鸣")),
        (("省油", "节能", "低油耗"), ("费油", "耗油", "高油耗")),
    )

    # ── 需要证据支撑的声明模式 ──
    FACTUAL_CLAIM_PATTERNS = (
        r"根据.{0,10}规范",
        r"研究表明",
        r"数据显示",
        r"占比?\d+%",
        r"\d+次",
        r"减少了?\d+%",
    )

    # ── 假设常被误报为事实的关键词 ──
    HYPOTHESIS_FLAG_PHRASES = (
        "用户普遍",
        "多数用户",
        "大多数情况下",
        "通常",
        "一般来说",
        "往往是",
        "一般来说",
        "据估计",
    )

    def __init__(self) -> None:
        super().__init__()

    def _run_impl(self, context: EvidenceAuditInput) -> AuditResult:
        """执行四项审计检查"""
        issues: list[AuditIssue] = []

        for agent_name, output in context.agent_outputs.items():
            # 1. 引用真实性校验
            issues.extend(self._check_evidence_exists(
                agent_name, output, context.available_evidence
            ))
            # 2. 冲突检测
            issues.extend(self._check_contradictions(agent_name, output))
            # 3. 假设→事实误报
            issues.extend(self._check_hypothesis_as_fact(agent_name, output))
            # 4. 数字溯源
            issues.extend(self._check_numeric_claims(agent_name, output))

        blocking = any(i.severity == "error" for i in issues)
        audit_status = "blocking" if blocking else ("issues_found" if issues else "passed")

        return AuditResult(
            status=AgentStatus.SUCCEEDED,
            audit_status=audit_status,
            issues=issues,
            manual_review_required=blocking,
            conclusions=[
                f"审计完成: {len(issues)} 个问题"
                + (f" ({sum(1 for i in issues if i.severity == 'error')} 个严重)" if blocking else "")
            ],
        )

    def _check_evidence_exists(
        self, agent_name: str, output, available: dict[str, list[str]]
    ) -> list[AuditIssue]:
        """校验 Agent 声称的引用是否真实存在"""
        issues = []
        claimed = output.get("evidence_ids", []) if isinstance(output, dict) else []
        for ref in claimed:
            source_type = ref.split(":")[0] if ":" in ref else ""
            if source_type in available:
                if ref not in available[source_type]:
                    issues.append(AuditIssue(
                        code="hallucinated_ref",
                        severity="error",
                        agent_name=agent_name,
                        message=f"引用 '{ref}' 在可用证据池中不存在",
                        fix_hint="移除该引用或修正引用编号",
                    ))
        return issues

    def _check_contradictions(self, agent_name: str, output) -> list[AuditIssue]:
        """检测同一输出中的矛盾声明"""
        text = json.dumps(output, ensure_ascii=False) if isinstance(output, dict) else str(output)
        issues = []
        for (low_terms, high_terms) in self.CONFLICT_PAIRS:
            has_low = any(t in text for t in low_terms)
            has_high = any(t in text for t in high_terms)
            if has_low and has_high:
                issues.append(AuditIssue(
                    code="contradiction",
                    severity="warn",
                    agent_name=agent_name,
                    message=f"同时出现矛盾描述: {low_terms[0]} vs {high_terms[0]}",
                    fix_hint="确认实际状态，删除错误描述",
                ))
        return issues

    def _check_hypothesis_as_fact(self, agent_name: str, output) -> list[AuditIssue]:
        """检测假设被当作事实陈述"""
        text = json.dumps(output, ensure_ascii=False) if isinstance(output, dict) else str(output)
        issues = []
        for phrase in self.HYPOTHESIS_FLAG_PHRASES:
            if phrase in text:
                issues.append(AuditIssue(
                    code="hypothesis_as_fact",
                    severity="warn",
                    agent_name=agent_name,
                    message=f"'{phrase}' 是假设性表述，需标注为'待验证假设'或附带证据",
                    fix_hint="在陈述前加'待验证假设:'或提供 evidence_id",
                ))
        return issues

    def _check_numeric_claims(self, agent_name: str, output) -> list[AuditIssue]:
        """检测数字声明是否有来源"""
        text = json.dumps(output, ensure_ascii=False) if isinstance(output, dict) else str(output)
        issues = []
        numbers = re.findall(r"(?<![A-Za-z0-9_.-])\d+(?:\.\d+)?%?", text)
        has_evidence = bool(output.get("evidence_ids")) if isinstance(output, dict) else False
        if numbers and not has_evidence:
            issues.append(AuditIssue(
                code="numeric_without_source",
                severity="warn",
                agent_name=agent_name,
                message=f"输出含数字 {numbers[:3]} 但未标注来源",
                fix_hint="标明数字来源或添加 evidence_id",
            ))
        return issues
