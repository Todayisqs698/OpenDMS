"""
Agent 工具注册表 — 兼容桥接层（已迁移至 tools.py）

此文件保留向后兼容，所有工具实现已统一到 modules/ai/tools.py 的 TOOL_EXECUTOR。
新代码请直接使用：
    from modules.ai.tools import TOOL_EXECUTOR, execute_tool
"""
import logging
from typing import Callable

logger = logging.getLogger(__name__)


def get_tool_registry() -> dict[str, Callable]:
    """获取完整工具注册表（委托给 tools.TOOL_EXECUTOR）。"""
    from modules.ai.tools import TOOL_EXECUTOR
    logger.debug("agent_tools.get_tool_registry() 已委托至 tools.TOOL_EXECUTOR")
    return dict(TOOL_EXECUTOR)
