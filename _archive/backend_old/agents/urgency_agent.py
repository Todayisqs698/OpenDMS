"""
🅱 成员B：紧急度评估 + 智能派单 + 知识图谱

接口规范：
  评估紧急度: input={"category": "...", "emotion_score": 0, "history_count": 0, "has_vulnerable": False}
              output={"priority": "high/medium/low", "priority_score": 0-100, "sla_hours": 2}
  智能派单:   input={"category_l1": "...", "category_l2": "...", "address": "...", "priority": "..."}
              output={"suggested_dept": "...", "suggested_worker_id": None, "reason": "..."}

TODO: 实现 evaluate_urgency() 和 suggest_dispatch()
"""
from app.core.llm_factory import get_llm, get_llm_json_mode
import json


def evaluate_urgency(
    category: str,
    emotion_score: float = 0.0,
    history_count: int = 0,
    has_vulnerable: bool = False,
    is_late_night: bool = False,
) -> dict:
    """
    TODO: 成员B 实现
    动态优先级评分：
    - 事件类型权重（安全隐患 > 环境 > 咨询）
    - 情绪分（愤怒 +20，哭泣 +30）
    - 重复投诉 ×5/次
    - 弱势群体 +15
    - 深夜 +10
    """
    base_score = 0

    # 事件类型权重
    danger_categories = ["公共安全", "电梯故障", "火灾隐患", "燃气泄漏"]
    if any(c in category for c in danger_categories):
        base_score += 40

    # 情绪分
    base_score += emotion_score * 0.3

    # 重复投诉
    base_score += min(history_count * 5, 30)

    # 弱势群体
    if has_vulnerable:
        base_score += 15

    # 深夜
    if is_late_night:
        base_score += 10

    # 等级判定
    if base_score >= 70:
        priority, sla = "high", 2
    elif base_score >= 40:
        priority, sla = "medium", 24
    else:
        priority, sla = "low", 48

    return {
        "priority": priority,
        "priority_score": round(min(base_score, 100)),
        "sla_hours": sla,
    }


def suggest_dispatch(category_l1: str, category_l2: str, address: str, priority: str) -> dict:
    """
    TODO: 成员B 实现
    根据分类和地址，推荐派单部门和网格员
    后续可接入规则引擎的动态映射
    """
    # TODO: 从 RuleConfig 表中读取分类→部门映射
    # TODO: 根据地址匹配网格区域 → 推荐网格员
    return {
        "suggested_dept": "城管执法中队",
        "suggested_worker_id": None,
        "reason": "根据诉求分类匹配",
    }


def search_knowledge(category: str, keywords: list[str]) -> list[dict]:
    """
    TODO: 成员B 实现
    从知识库检索相似案例
    1. 向量检索（FAISS）
    2. 图谱关联（NetworkX）
    """
    return [
        {
            "title": "相似案例：XX路烧烤店噪音",
            "resolution": "约谈店主 + 限期整改",
            "laws": ["噪声污染防治法第63条"],
            "similarity": 0.92,
        }
    ]
