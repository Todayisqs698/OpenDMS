"""
model_factory.py 单元测试 — 模型工厂

覆盖:
  - _get_settings() 返回预期配置键
  - _get_settings() 从环境变量读取
  - create_fast_model() 返回 ChatOpenAI（需 API key）
  - create_reasoning_model() 返回 ChatOpenAI（需 API key）
  - AGENT_MODEL 映射 7 个 Agent
  - get_model_for_agent() 正确路由
  - get_model_for_agent() 未知 Agent 回退到 fast model
"""
import os

import pytest
from langchain_openai import ChatOpenAI

from modules.ai.model_factory import (
    _get_settings,
    create_fast_model,
    create_reasoning_model,
    AGENT_MODEL,
    get_model_for_agent,
)


class TestGetSettings:
    def test_returns_dict(self):
        s = _get_settings()
        assert isinstance(s, dict)

    def test_has_expected_keys(self):
        s = _get_settings()
        expected_keys = {
            "doubao_api_key", "doubao_base_url", "doubao_fast_model",
            "deepseek_api_key", "deepseek_base_url",
            "deepseek_chat_model", "deepseek_reasoner_model",
            "model_temperature", "model_timeout",
            "model_max_retries", "model_max_tokens",
        }
        assert expected_keys.issubset(s.keys())

    def test_doubao_base_url(self):
        s = _get_settings()
        assert "ark.cn-beijing.volces.com" in s["doubao_base_url"]

    def test_deepseek_base_url(self):
        s = _get_settings()
        assert "api.deepseek.com" in s["deepseek_base_url"]

    def test_default_temperature(self):
        s = _get_settings()
        assert isinstance(s["model_temperature"], float)

    def test_default_timeout(self):
        s = _get_settings()
        assert isinstance(s["model_timeout"], int)

    def test_reads_env_var(self, monkeypatch):
        """环境变量覆盖默认值"""
        monkeypatch.setenv("DEEPSEEK_CHAT_MODEL", "custom-model")
        s = _get_settings()
        assert s["deepseek_chat_model"] == "custom-model"


class TestCreateFastModel:
    def test_returns_chat_openai(self):
        """有 API key 时返回 ChatOpenAI 实例"""
        try:
            model = create_fast_model()
            assert isinstance(model, ChatOpenAI)
        except RuntimeError:
            pytest.skip("No API key available (DOUBAO_API_KEY and DEEPSEEK_API_KEY both empty)")

    def test_raises_without_key(self, monkeypatch):
        """无 API key 时抛 RuntimeError"""
        monkeypatch.delenv("DOUBAO_API_KEY", raising=False)
        monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
        with pytest.raises(RuntimeError, match="均为空"):
            create_fast_model()

    def test_prefers_doubao(self, monkeypatch):
        """豆包 key 优先"""
        monkeypatch.setenv("DOUBAO_API_KEY", "test-key")
        monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")
        model = create_fast_model()
        assert isinstance(model, ChatOpenAI)


class TestCreateReasoningModel:
    def test_returns_chat_openai(self):
        try:
            model = create_reasoning_model()
            assert isinstance(model, ChatOpenAI)
        except RuntimeError:
            pytest.skip("No API key available")

    def test_raises_without_key(self, monkeypatch):
        monkeypatch.delenv("DOUBAO_API_KEY", raising=False)
        monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
        with pytest.raises(RuntimeError, match="均为空"):
            create_reasoning_model()


class TestAgentModelMapping:
    def test_agent_model_has_seven_agents(self):
        assert len(AGENT_MODEL) == 7

    def test_agent_model_keys(self):
        expected = {"safety", "intention", "interaction", "diagnose",
                    "analyze", "recommend", "evidence_audit"}
        assert set(AGENT_MODEL.keys()) == expected

    def test_fast_agents_use_fast_model(self):
        """safety/intention/interaction/evidence_audit 用 fast model"""
        assert AGENT_MODEL["safety"] == create_fast_model
        assert AGENT_MODEL["intention"] == create_fast_model
        assert AGENT_MODEL["interaction"] == create_fast_model
        assert AGENT_MODEL["evidence_audit"] == create_fast_model

    def test_reasoning_agents_use_reasoning_model(self):
        """diagnose/analyze/recommend 用 reasoning model"""
        assert AGENT_MODEL["diagnose"] == create_reasoning_model
        assert AGENT_MODEL["analyze"] == create_reasoning_model
        assert AGENT_MODEL["recommend"] == create_reasoning_model


class TestGetModelForAgent:
    def test_known_agent_returns_model(self):
        try:
            model = get_model_for_agent("safety")
            assert isinstance(model, ChatOpenAI)
        except RuntimeError:
            pytest.skip("No API key available")

    def test_unknown_agent_falls_back_to_fast(self, monkeypatch):
        """未知 Agent 回退到 fast model"""
        monkeypatch.setenv("DOUBAO_API_KEY", "test-key")
        model = get_model_for_agent("nonexistent_agent")
        assert isinstance(model, ChatOpenAI)
