"""
invoke_structured — 六步 LLM → Pydantic 执行链

对齐 TradePilot 的 structured_output.py，EdgeGuard 简化版：
  - 不需要 token 用量追踪和 normalize 回调
  - 六步: prompt → model → decode → serialize → PydanticOutputParser → 失败重试
"""

from __future__ import annotations

import json
import logging
from collections.abc import Mapping
from typing import Any

from langchain_core.exceptions import OutputParserException
from langchain_core.output_parsers import PydanticOutputParser
from langchain_core.runnables import Runnable, RunnableLambda
from pydantic import BaseModel, ValidationError

logger = logging.getLogger("edgeguard.agent.structured_output")


def invoke_structured(
    *,
    prompt: Runnable[Any, Any],
    model: Runnable[Any, Any],
    values: Mapping[str, Any],
    output_model: type[BaseModel],
    max_parse_retries: int = 3,
) -> BaseModel:
    """
    执行一条 LCEL 链: prompt → model → decode → serialize → PydanticOutputParser

    六步:
      1. prompt.invoke(values)   — 填充模板
      2. model.invoke(messages)  — 调 LLM（自动路由到豆包/DeepSeek）
      3. decode                  — 提取 JSON
      4. serialize               — json.dumps
      5. PydanticOutputParser    — 校验 Schema
      6. 失败重试（最多 max_parse_retries 次）

    Returns:
        已校验的 Pydantic BaseModel 实例
    """
    parser = PydanticOutputParser(pydantic_object=output_model)

    def decode(message: object) -> str:
        content = getattr(message, "content", str(message))
        text = str(content).strip()
        # 去掉 markdown 代码块
        if text.startswith("```"):
            lines = text.split("\n")
            lines = lines[1:] if lines[0].startswith("```") else lines
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            text = "\n".join(lines)
        # 提取 JSON 对象
        start = text.find("{")
        end = text.rfind("}")
        if start >= 0 and end > start:
            text = text[start:end + 1]
        return text

    def serialize(text: str) -> str:
        # 校验是合法 JSON 后再序列化（PydanticOutputParser 需要字符串输入）
        parsed = json.loads(text)
        return json.dumps(parsed, ensure_ascii=False)

    chain = (
        prompt
        | model
        | RunnableLambda(decode)
        | RunnableLambda(serialize)
        | parser
    )

    retryable = (OutputParserException, ValidationError, ValueError, json.JSONDecodeError)

    for attempt in range(max_parse_retries + 1):
        try:
            value = chain.invoke(dict(values))
            if not isinstance(value, BaseModel):
                raise ValidationError(
                    f"Expected {output_model.__name__}, got {type(value)}",
                    output_model,
                )
            return value
        except retryable as exc:
            logger.warning(
                "structured_output parse retry attempt=%d/%d type=%s model=%s",
                attempt + 1, max_parse_retries, type(exc).__name__, output_model.__name__,
            )
            if attempt >= max_parse_retries:
                raise

    raise AssertionError("unreachable")
