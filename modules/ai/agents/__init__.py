"""
EdgeGuard 子 Agent 集合
========================

- safety_agent: 安全/疲劳/分心检测
- interaction_agent: 交互意图理解（兼容层）
- environment_agent: 天气/环境分析
- diagnose_agent: 故障诊断（RAG + LLM）
- analyze_agent: 驾驶行为分析
- recommend_agent: 出行建议（天气/导航）
"""

from .safety_agent import SafetyAgent
from .interaction_agent import InteractionAgent
from .environment_agent import EnvironmentAgent
from .diagnose_agent import DiagnoseAgent
from .analyze_agent import AnalyzeAgent
from .recommend_agent import RecommendAgent

__all__ = [
    "SafetyAgent",
    "InteractionAgent",
    "EnvironmentAgent",
    "DiagnoseAgent",
    "AnalyzeAgent",
    "RecommendAgent",
]
