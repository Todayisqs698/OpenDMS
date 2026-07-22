"""
故障诊断 Agent — 基于 RAG 知识库的车辆故障诊断
================================================

接收用户描述的故障现象，从车辆知识库中检索相关文档，
并生成结构化的诊断报告。

接口规范：
  输入: {"query": "发动机故障灯亮了", "top_k": 3}
  输出: {
    "success": true,
    "query": "发动机故障灯亮了",
    "diagnosis": "可能的原因包括...",
    "related_docs": [
      {"content": "...", "source": "vehicle_manual", "score": 0.85}
    ],
    "suggestions": ["建议检查...", "如果持续则送修"],
    "severity": "medium"  # low / medium / high
  }
"""

import logging
from typing import List, Dict, Any

logger = logging.getLogger(__name__)


class DiagnoseAgent:
    """故障诊断智能体"""

    def __init__(self):
        self._kb = None
        self._llm_client = None

    @property
    def knowledge_base(self):
        if self._kb is None:
            from modules.ai.vehicle_knowledge_base import get_knowledge_base
            self._kb = get_knowledge_base()
        return self._kb

    @property
    def llm(self):
        if self._llm_client is None:
            from modules.ai.deepseek_client import deepseek_client
            self._llm_client = deepseek_client
        return self._llm_client

    def analyze(self, query: str, top_k: int = 3) -> dict:
        """
        执行故障诊断。

        Args:
            query: 故障描述
            top_k: 检索文档数量

        Returns:
            诊断结果 dict
        """
        try:
            # Step 1: RAG 检索
            kb_result = self.knowledge_base.retrieve_knowledge(query, top_k=top_k)
            docs = kb_result.get("docs", [])

            if not docs:
                return {
                    "success": True,
                    "query": query,
                    "diagnosis": "抱歉，知识库中没有找到相关信息。建议您联系专业维修人员进行检查。",
                    "related_docs": [],
                    "suggestions": ["联系专业维修人员", "注意观察故障是否持续"],
                    "severity": "unknown",
                }

            # Step 2: 用 LLM 生成诊断总结
            context = "\n\n".join([
                f"[{i+1}] {doc.get('content', '')}"
                for i, doc in enumerate(docs)
            ])

            diagnosis_prompt = f"""你是一名专业的汽车维修技师。
用户描述的问题：{query}

相关维修手册内容：
{context}

请给出：
1. 可能的原因（2-3条）
2. 建议的检查步骤
3. 严重程度评估（low/medium/high）

用简洁的中文回答，控制在150字内。"""

            try:
                response = self.llm.client.chat.completions.create(
                    model="deepseek-chat",
                    messages=[
                        {"role": "system", "content": "你是专业的汽车维修技师，回答简洁实用。"},
                        {"role": "user", "content": diagnosis_prompt},
                    ],
                    max_tokens=300,
                    temperature=0.5,
                )
                diagnosis = response.choices[0].message.content.strip()
            except Exception as e:
                logger.warning(f"诊断 LLM 调用失败: {e}，使用检索结果直接返回")
                diagnosis = f"根据维修手册，可能与以下内容相关：\n{docs[0].get('content', '')[:200]}"

            # Step 3: 生成建议
            suggestions = self._extract_suggestions(docs)

            # Step 4: 评估严重程度
            severity = self._assess_severity(query, docs)

            return {
                "success": True,
                "query": query,
                "diagnosis": diagnosis,
                "related_docs": [
                    {"content": d.get("content", ""),
                     "source": d.get("source", "manual"),
                     "score": d.get("score", 0)}
                    for d in docs
                ],
                "suggestions": suggestions,
                "severity": severity,
            }

        except Exception as e:
            logger.error(f"故障诊断失败: {e}")
            return {
                "success": False,
                "query": query,
                "diagnosis": f"诊断失败：{str(e)[:50]}",
                "related_docs": [],
                "suggestions": [],
                "severity": "unknown",
                "error": str(e),
            }

    def _extract_suggestions(self, docs: list) -> List[str]:
        """从检索文档中提取建议。"""
        suggestions = []
        for doc in docs:
            content = doc.get("content", "")
            # 简单提取包含建议关键词的句子
            for sentence in content.split("。"):
                if any(kw in sentence for kw in ["建议", "应", "需要", "请", "注意"]):
                    clean = sentence.strip()
                    if clean and len(clean) < 80:
                        suggestions.append(clean + "。")
                        if len(suggestions) >= 3:
                            break
            if len(suggestions) >= 3:
                break

        if not suggestions:
            suggestions = ["建议联系专业维修人员检查", "注意观察故障是否持续"]

        return suggestions[:3]

    def _assess_severity(self, query: str, docs: list) -> str:
        """评估故障严重程度。"""
        high_keywords = ["故障灯", "警告", "危险", "不能启动", "熄火", "制动", "刹车"]
        medium_keywords = ["异常", "异响", "异味", "抖动", "发热"]

        query_lower = query.lower()
        if any(kw in query_lower for kw in high_keywords):
            return "high"
        if any(kw in query_lower for kw in medium_keywords):
            return "medium"
        return "low"
