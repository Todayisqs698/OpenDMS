"""
EdgeGuard Prompt 模板库

将所有散落在各模块中的 Prompts 集中管理，提供：
  1. 结构化模板对象（PromptTemplate）— 含元数据、参数、降级方案
  2. 集中式注册表（PromptRegistry）— 支持多维度检索
  3. 4 级安全门控模板 — 与 safety_gate 无缝对接
  4. Agent / 分析 / 环境 / 竞品模板 — 按业务域分类

使用方式：

    from modules.ai.prompts import render, get_template, list_by_category

    # 渲染安全提示
    hint = render("safety.distracted", extra_hint="请减速")

    # 获取 Agent 系统提示
    tpl = get_template("agent.system.base")
    prompt = tpl.render(gaze="center", safety_level="normal", ...)

    # 列出所有 safety 分类模板
    for t in list_by_category("safety"):
        print(t.id, t.name, t.version)

    # 导出 Markdown 文档
    print(export_markdown())

    # API 查询所有模板
    print(get_all_dicts())
"""
import logging
from .template import PromptTemplate
from .registry import PromptRegistry, prompt_registry, get_registry

logger = logging.getLogger(__name__)

# ── 导入所有模板定义 ──
from .safety_templates import SAFETY_TEMPLATES
from .agent_templates import AGENT_TEMPLATES
from .analysis_templates import ANALYSIS_TEMPLATES

# ── 启动时自动注册 ──
_ALL_TEMPLATES = SAFETY_TEMPLATES + AGENT_TEMPLATES + ANALYSIS_TEMPLATES
_registered = False


def _auto_register():
    """自动注册所有内置模板（只执行一次，幂等）。"""
    global _registered
    if _registered:
        return
    prompt_registry.register_many(_ALL_TEMPLATES)
    _registered = True
    logger.info(f"Prompt 模板库初始化完成: {len(_ALL_TEMPLATES)} 个模板已注册")


# 模块导入时自动注册
_auto_register()


# ═══════════════════════════════════════════════════════════════
#  便捷 API
# ═══════════════════════════════════════════════════════════════


def render(template_id: str, **kwargs) -> str:
    """渲染指定模板。最常用的便捷入口。"""
    return prompt_registry.get_render(template_id, **kwargs)


def get_template(template_id: str) -> PromptTemplate | None:
    """获取模板对象。"""
    return prompt_registry.get(template_id)


def list_by_category(category: str) -> list[PromptTemplate]:
    """列出某分类下所有模板。"""
    return prompt_registry.by_category(category)


def list_by_risk(risk_level: str) -> list[PromptTemplate]:
    """列出某安全等级下所有模板。"""
    return prompt_registry.by_risk_level(risk_level)


def search(keyword: str) -> list[PromptTemplate]:
    """关键词搜索模板。"""
    return prompt_registry.search(keyword)


def get_all() -> list[PromptTemplate]:
    """获取所有模板。"""
    return prompt_registry.list_all()


def get_all_dicts() -> list[dict]:
    """获取所有模板的字典表示（供 API 返回）。"""
    return prompt_registry.to_dict()


def export_markdown() -> str:
    """导出为 Markdown 文档。"""
    return prompt_registry.to_markdown()


def stats() -> dict:
    """获取注册表统计信息。"""
    return prompt_registry.stats()


def register(template: PromptTemplate) -> None:
    """手动注册自定义模板。"""
    prompt_registry.register(template)


# ═══════════════════════════════════════════════════════════════
#  向后兼容：与旧 safety_gate.py 的桥接
# ═══════════════════════════════════════════════════════════════


def get_safety_prompt(risk_level: str, **extra) -> str:
    """
    获取指定风险等级的安全提示（兼容旧 SAFETY_SYSTEM_PROMPTS dict）。
    这是 safety_gate.apply_safety_gate() 的模板库替代方案。

    Args:
        risk_level: normal / attn_declining / distracted / dangerous
        **extra: 额外参数（如 extra_hint, risk_reason, max_reply_len 等）

    Returns:
        渲染后的安全提示字符串
    """
    template_id_map = {
        "normal": "safety.normal",
        "attn_declining": "safety.attn_declining",
        "distracted": "safety.distracted",
        "dangerous": "safety.dangerous",
    }
    tid = template_id_map.get(risk_level)
    if tid is None:
        return ""
    return prompt_registry.get_render(tid, **extra)
