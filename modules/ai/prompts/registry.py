"""
PromptRegistry — 集中式 Prompt 模板注册与检索

支持多维检索：
  - by_id: 精确查找
  - by_category: 按分类查找（safety / agent / analysis / ...）
  - by_risk_level: 按安全等级查找
  - by_tags: 按标签查找
  - search: 关键词模糊搜索
"""
import logging
from typing import Optional
from .template import PromptTemplate

logger = logging.getLogger(__name__)


class PromptRegistry:
    """Prompt 模板注册表（单例）"""

    _instance: Optional["PromptRegistry"] = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._templates: dict[str, PromptTemplate] = {}
            cls._instance._initialized = False
        return cls._instance

    # ── 注册 / 注销 ──

    def register(self, template: PromptTemplate) -> None:
        """注册一个模板（重复 id 会覆盖并警告）。"""
        if template.id in self._templates:
            logger.warning(f"模板 {template.id} 已存在，将被覆盖 (旧版本: {self._templates[template.id].version})")
        self._templates[template.id] = template
        logger.debug(f"Registered prompt template: {template.id} v{template.version}")

    def register_many(self, templates: list[PromptTemplate]) -> None:
        """批量注册模板。"""
        for t in templates:
            self.register(t)

    def unregister(self, template_id: str) -> bool:
        """注销模板。返回是否成功。"""
        if template_id in self._templates:
            del self._templates[template_id]
            return True
        return False

    # ── 检索 ──

    def get(self, template_id: str) -> Optional[PromptTemplate]:
        """按 ID 精确获取模板。"""
        return self._templates.get(template_id)

    def get_render(self, template_id: str, **kwargs) -> str:
        """
        获取并渲染模板。
        如果模板不存在，返回内置错误提示。
        """
        tpl = self.get(template_id)
        if tpl is None:
            logger.error(f"Template not found: {template_id}")
            return f"[模板缺失: {template_id}]"
        try:
            return tpl.render(**kwargs)
        except KeyError as e:
            logger.error(f"Template render failed: {e}")
            return f"[模板参数错误: {e}]"

    def by_category(self, category: str) -> list[PromptTemplate]:
        """按分类获取所有模板。"""
        return [t for t in self._templates.values() if t.category == category]

    def by_risk_level(self, risk_level: str) -> list[PromptTemplate]:
        """按安全等级获取模板。"""
        return [t for t in self._templates.values() if t.risk_level == risk_level]

    def by_tags(self, tags: list[str], match_all: bool = False) -> list[PromptTemplate]:
        """
        按标签检索。
        match_all=True: 必须包含所有标签
        match_all=False: 包含任一标签即可
        """
        tag_set = set(tags)
        results = []
        for t in self._templates.values():
            t_tags = set(t.tags)
            if match_all:
                if tag_set.issubset(t_tags):
                    results.append(t)
            else:
                if tag_set & t_tags:
                    results.append(t)
        return results

    def search(self, keyword: str) -> list[PromptTemplate]:
        """
        关键词模糊搜索（在 id / name / description / tags 中匹配）。
        """
        kw = keyword.lower()
        results = []
        for t in self._templates.values():
            if (kw in t.id.lower()
                or kw in t.name.lower()
                or kw in t.description.lower()
                or any(kw in tag.lower() for tag in t.tags)):
                results.append(t)
        return results

    # ── 统计与导出 ──

    def list_all(self) -> list[PromptTemplate]:
        """返回所有已注册模板。"""
        return list(self._templates.values())

    def categories(self) -> list[str]:
        """返回所有分类。"""
        return sorted(set(t.category for t in self._templates.values()))

    def stats(self) -> dict:
        """返回注册表统计信息。"""
        cats = {}
        for t in self._templates.values():
            cats[t.category] = cats.get(t.category, 0) + 1
        return {
            "total": len(self._templates),
            "categories": cats,
            "risk_levels": sorted(set(t.risk_level for t in self._templates.values())),
        }

    def to_dict(self) -> list[dict]:
        """序列化所有模板（供 API 返回）。"""
        return [t.to_dict() for t in self._templates.values()]

    def to_markdown(self) -> str:
        """导出为 Markdown 文档（便于查阅和分享）。"""
        lines = ["# Prompt 模板库文档", "", f"共 {len(self._templates)} 个模板", ""]
        for cat in self.categories():
            lines.append(f"## {cat}")
            lines.append("")
            for t in self.by_category(cat):
                lines.append(f"### {t.name} (`{t.id}`)")
                lines.append(f"- 版本: {t.version}")
                lines.append(f"- 参数: {', '.join(t.params) if t.params else '无'}")
                lines.append(f"- 标签: {', '.join(t.tags) if t.tags else '无'}")
                if t.description:
                    lines.append(f"- 说明: {t.description}")
                lines.append("")
                lines.append("```")
                lines.append(t.content.strip())
                lines.append("```")
                lines.append("")
        return "\n".join(lines)


# ── 全局单例 ──
prompt_registry = PromptRegistry()


def get_registry() -> PromptRegistry:
    """获取全局 Prompt 注册表单例。"""
    return prompt_registry
