"""
PromptTemplate — 标准化 Prompt 模板数据结构

每个模板包含：
  - 元数据（id / category / version / author）
  - 参数定义（需要哪些变量注入）
  - 模板内容（支持 {param} 占位符）
  - 降级模板（参数缺失时的兜底）
"""
from dataclasses import dataclass, field
from typing import Optional
from datetime import datetime


@dataclass
class PromptTemplate:
    """单个 Prompt 模板"""

    # ── 元数据 ──
    id: str                          # 唯一标识，如 "safety.distracted"
    category: str                    # 分类：safety / agent / analysis / fallback / interaction
    name: str                        # 显示名称，如 "分心状态安全提示"
    version: str = "1.0"             # 语义化版本
    author: str = "system"           # 创建者

    # ── 模板内容 ──
    content: str = ""                # 模板正文，支持 {param} 占位符
    params: list[str] = field(default_factory=list)  # 需要的参数列表
    fallback_content: str = ""       # 参数缺失时的降级模板

    # ── 标签（支持多维度检索）──
    tags: list[str] = field(default_factory=list)    # 如 ["safety", "distracted", "warning"]
    risk_level: str = "normal"       # 关联的安全等级

    # ── 元信息 ──
    description: str = ""            # 用途简述
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now().isoformat())

    def render(self, **kwargs) -> str:
        """
        渲染模板：用传入参数填充占位符。
        缺失参数会尝试用 fallback_content，再不行抛 KeyError。
        """
        try:
            return self.content.format(**kwargs)
        except KeyError as e:
            if self.fallback_content:
                try:
                    return self.fallback_content.format(**kwargs)
                except KeyError:
                    pass
            raise KeyError(f"模板 {self.id} 缺少参数: {e}，且无可用降级模板")

    def validate_params(self, **kwargs) -> tuple[bool, list[str]]:
        """检查参数是否满足模板要求。返回 (是否有效, 缺失参数列表)。"""
        missing = [p for p in self.params if p not in kwargs]
        return len(missing) == 0, missing

    def to_dict(self) -> dict:
        """序列化为字典（便于前端展示/API 返回）。"""
        return {
            "id": self.id,
            "category": self.category,
            "name": self.name,
            "version": self.version,
            "author": self.author,
            "params": self.params,
            "tags": self.tags,
            "risk_level": self.risk_level,
            "description": self.description,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    def preview(self, **sample_params) -> str:
        """用示例参数预览渲染后的效果。"""
        # 只填充 sample_params 中有值的参数
        fill = {p: sample_params.get(p, f"{{{p}}}") for p in self.params}
        return self.content.format(**fill)

    def __repr__(self) -> str:
        return f"PromptTemplate(id='{self.id}', category='{self.category}', version='{self.version}')"
