"""
base_agent.py 单元测试 — BaseScaffoldAgent 基类

覆盖:
  - 抽象类不可直接实例化
  - run() 接受 dict → 自动校验为 Pydantic
  - run() 接受 Pydantic 实例直接传入
  - _validate_output dict → Pydantic 自动转换
  - chain 执行顺序: validate_input → _run_impl → validate_output
  - _run_impl 返回 dict 时自动包装为 output_model
"""
import pytest
from pydantic import BaseModel, Field

from modules.ai.base_agent import BaseScaffoldAgent
from modules.ai.schemas import AgentStatus, ScaffoldAgentOutput


# ── 测试用的简单 Agent 实现 ──

class DummyInput(BaseModel):
    value: int = 0


class DummyOutput(ScaffoldAgentOutput):
    doubled: int = 0


class DummyAgent(BaseScaffoldAgent[DummyInput, DummyOutput]):
    input_model = DummyInput
    output_model = DummyOutput

    def _run_impl(self, context: DummyInput) -> dict:
        return {"doubled": context.value * 2, "status": AgentStatus.SUCCEEDED}


class FailingAgent(BaseScaffoldAgent[DummyInput, DummyOutput]):
    input_model = DummyInput
    output_model = DummyOutput

    def _run_impl(self, context: DummyInput) -> dict:
        raise RuntimeError("intentional failure")


# ═══════════════════════════════════════════════════════════

class TestBaseScaffoldAgent:
    def test_abstract_cannot_instantiate(self):
        """BaseScaffoldAgent 是抽象类，不能直接实例化"""
        with pytest.raises(TypeError):
            BaseScaffoldAgent()

    def test_subclass_works(self):
        """子类实现了 _run_impl 后可以实例化"""
        agent = DummyAgent()
        assert agent is not None

    def test_run_with_dict_input(self):
        """run() 接受 dict，自动校验为 input_model"""
        agent = DummyAgent()
        result = agent.run({"value": 21})
        assert isinstance(result, DummyOutput)
        assert result.doubled == 42

    def test_run_with_pydantic_input(self):
        """run() 接受 Pydantic 实例"""
        agent = DummyAgent()
        result = agent.run(DummyInput(value=10))
        assert isinstance(result, DummyOutput)
        assert result.doubled == 20

    def test_validate_input_dict_to_model(self):
        """_validate_input 将 dict 转为 Pydantic 模型"""
        agent = DummyAgent()
        inp = agent._validate_input({"value": 5})
        assert isinstance(inp, DummyInput)
        assert inp.value == 5

    def test_validate_input_passthrough_model(self):
        """_validate_input 对已有 Pydantic 实例直接返回"""
        agent = DummyAgent()
        original = DummyInput(value=7)
        inp = agent._validate_input(original)
        assert inp is original

    def test_validate_output_dict_to_model(self):
        """_validate_output 将 dict 转为 Pydantic 模型"""
        agent = DummyAgent()
        out = agent._validate_output({"doubled": 14})
        assert isinstance(out, DummyOutput)
        assert out.doubled == 14

    def test_validate_output_passthrough_model(self):
        """_validate_output 对已有 Pydantic 实例直接返回"""
        agent = DummyAgent()
        original = DummyOutput(doubled=3)
        out = agent._validate_output(original)
        assert out is original

    def test_chain_execution_order(self):
        """chain 按顺序执行: validate_input → _run_impl → validate_output"""
        agent = DummyAgent()
        result = agent.chain.invoke({"value": 50})
        assert isinstance(result, DummyOutput)
        assert result.doubled == 100
        assert result.status == AgentStatus.SUCCEEDED

    def test_run_impl_exception_propagates(self):
        """_run_impl 抛异常时，run() 也抛异常"""
        agent = FailingAgent()
        with pytest.raises(RuntimeError, match="intentional failure"):
            agent.run({"value": 1})

    def test_output_has_base_fields(self):
        """输出继承 ScaffoldAgentOutput 的元数据字段"""
        agent = DummyAgent()
        result = agent.run({"value": 1})
        assert hasattr(result, "conclusions")
        assert hasattr(result, "evidence_ids")
        assert hasattr(result, "errors")
        assert hasattr(result, "model_call_count")
        assert result.model_call_count == 0
