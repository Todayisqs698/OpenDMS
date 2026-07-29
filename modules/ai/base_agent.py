"""
BaseScaffoldAgent — TradePilot 风格的 Agent 基类

每个 Agent:
  - input_model: 入参 Pydantic 类型
  - output_model: 出参 Pydantic 类型
  - _validate_input / _validate_output: 自动校验
  - _run_impl: 子类实现具体推理逻辑

与 TradePilot 的差异（EdgeGuard 简化）：
  - 方法名 _run_impl（TradePilot 用 _run_stub），语义更清晰
  - 统一在基类定义 chain，子类只覆写 _run_impl
  - 不在 Agent 构造时注入 model / retrieval_pipeline
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Generic, TypeVar

from langchain_core.runnables import RunnableLambda, RunnableSequence
from pydantic import BaseModel

InputT = TypeVar("InputT", bound=BaseModel)
OutputT = TypeVar("OutputT", bound=BaseModel)


class BaseScaffoldAgent(Generic[InputT, OutputT], ABC):
    """TradePilot 风格的 Agent 基类。

    子类需声明:
      - input_model:  入参 Pydantic 类型
      - output_model: 出参 Pydantic 类型
      - _run_impl:    具体推理逻辑

    对外统一入口 run(context) → 自动校验 → 执行 → 输出校验
    """

    input_model: type[InputT]
    output_model: type[OutputT]

    def __init__(self) -> None:
        self.chain: RunnableSequence = (
            RunnableLambda(self._validate_input)
            | RunnableLambda(self._run_impl)
            | RunnableLambda(self._validate_output)
        )

    def run(self, context: InputT | dict) -> OutputT:
        """对外统一入口：输入 Pydantic → 自动校验 → 执行 → 输出 Pydantic"""
        return self.chain.invoke(context)

    def _validate_input(self, value: InputT | dict) -> InputT:
        """如果传入 dict 则自动校验为 input_model 实例"""
        if isinstance(value, dict):
            return self.input_model.model_validate(value)
        return value

    @abstractmethod
    def _run_impl(self, context: InputT) -> OutputT | dict:
        """子类实现：接收已验证的 InputT，返回 OutputT 或其 dict"""

    def _validate_output(self, value: OutputT | dict) -> OutputT:
        """如果返回 dict 则自动校验为 output_model 实例"""
        if isinstance(value, dict):
            return self.output_model.model_validate(value)
        return value
