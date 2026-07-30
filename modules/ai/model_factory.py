"""
模型工厂 — 按能力创建模型实例，模型名从 Settings（环境变量）读取

两种能力:
  - create_fast_model():      快速模型（豆包 Lite → 降级 DeepSeek Chat）
  - create_reasoning_model(): 推理模型（DeepSeek Reasoner → 降级豆包 Lite）

Agent → 模型映射通过 AGENT_MODEL 字典 + get_model_for_agent() 实现。

返回对象兼容 deepseek_client 接口：拥有 .client（OpenAI 客户端）和 .chat_model（模型名）属性。
"""

from __future__ import annotations

import logging
import os
from typing import Any

from dotenv import load_dotenv
from openai import OpenAI

# 3 级目录遍历到达项目根目录 edgeguard/
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))), '.env'))

logger = logging.getLogger("edgeguard.model_factory")


class ModelClient:
    """兼容 deepseek_client 接口的模型客户端包装器。"""

    def __init__(self, client: OpenAI, model_name: str):
        self.client = client
        self.chat_model = model_name
        self._api_key = client.api_key

    @property
    def is_available(self) -> bool:
        return bool(self._api_key)

    def chat_with_tools(self, messages: list, tools: list = None,
                        tool_choice: str = "auto", temperature: float = 0.7,
                        max_tokens: int = 4096) -> dict:
        """
        支持 function calling 的对话接口（兼容 DeepSeekClient.chat_with_tools）。
        """
        kwargs = {
            "model": self.chat_model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = tool_choice

        response = self.client.chat.completions.create(**kwargs)
        msg = response.choices[0].message

        result = {
            "content": msg.content,
            "tool_calls": None,
            "raw_message": msg,
        }
        if hasattr(msg, "tool_calls") and msg.tool_calls:
            result["tool_calls"] = [
                {
                    "id": tc.id,
                    "type": tc.type,
                    "function": {
                        "name": tc.function.name,
                        "arguments": tc.function.arguments,
                    }
                }
                for tc in msg.tool_calls
            ]

        return result


# ── 模型配置（环境变量驱动，不写死模型名）──

def _get_settings() -> dict[str, Any]:
    return {
        "doubao_api_key": os.getenv("DOUBAO_API_KEY", ""),
        "doubao_base_url": "https://ark.cn-beijing.volces.com/api/v3",
        "doubao_fast_model": os.getenv("DOUBAO_FAST_MODEL", "doubao-lite-128k"),

        "deepseek_api_key": os.getenv("DEEPSEEK_API_KEY", ""),
        "deepseek_base_url": "https://api.deepseek.com",
        "deepseek_chat_model": os.getenv("DEEPSEEK_CHAT_MODEL", "deepseek-chat"),
        "deepseek_reasoner_model": os.getenv("DEEPSEEK_REASONER_MODEL", "deepseek-reasoner"),

        "model_timeout": int(os.getenv("MODEL_TIMEOUT", "60")),
        "model_max_retries": int(os.getenv("MODEL_MAX_RETRIES", "2")),
    }


def create_fast_model() -> ModelClient:
    """
    快速模型 — 用于 SafetyAgent / IntentionAgent / InteractionAgent。
    优先豆包 Lite，不可用时降级到 DeepSeek Chat。
    """
    s = _get_settings()
    if s["doubao_api_key"]:
        logger.info("fast model: %s @ ark", s["doubao_fast_model"])
        return ModelClient(
            client=OpenAI(
                api_key=s["doubao_api_key"],
                base_url=s["doubao_base_url"],
                timeout=s["model_timeout"],
                max_retries=s["model_max_retries"],
            ),
            model_name=s["doubao_fast_model"],
        )
    if s["deepseek_api_key"]:
        logger.warning("fast model: 豆包不可用，降级到 %s", s["deepseek_chat_model"])
        return ModelClient(
            client=OpenAI(
                api_key=s["deepseek_api_key"],
                base_url=s["deepseek_base_url"],
                timeout=s["model_timeout"],
                max_retries=s["model_max_retries"],
            ),
            model_name=s["deepseek_chat_model"],
        )
    raise RuntimeError("fast model: DOUBAO_API_KEY 和 DEEPSEEK_API_KEY 均为空")


def create_reasoning_model() -> ModelClient:
    """
    推理模型 — 用于 DiagnoseAgent / AnalyzeAgent / RecommendAgent。
    优先 DeepSeek Reasoner，不可用时降级到豆包 Lite。
    """
    s = _get_settings()
    if s["deepseek_api_key"]:
        logger.info("reasoning model: %s @ deepseek", s["deepseek_reasoner_model"])
        return ModelClient(
            client=OpenAI(
                api_key=s["deepseek_api_key"],
                base_url=s["deepseek_base_url"],
                timeout=s["model_timeout"],
                max_retries=s["model_max_retries"],
            ),
            model_name=s["deepseek_reasoner_model"],
        )
    if s["doubao_api_key"]:
        logger.warning("reasoning model: DeepSeek 不可用，降级到豆包 Lite")
        return ModelClient(
            client=OpenAI(
                api_key=s["doubao_api_key"],
                base_url=s["doubao_base_url"],
                timeout=s["model_timeout"],
                max_retries=s["model_max_retries"],
            ),
            model_name=s["doubao_fast_model"],
        )
    raise RuntimeError("reasoning model: DEEPSEEK_API_KEY 和 DOUBAO_API_KEY 均为空")


# Agent → 模型映射（轻量路由，不硬编码模型名）
AGENT_MODEL = {
    "safety":         create_fast_model,
    "intention":      create_fast_model,
    "interaction":    create_fast_model,
    "diagnose":       create_reasoning_model,
    "analyze":        create_reasoning_model,
    "recommend":      create_reasoning_model,
    "environment":    create_reasoning_model,  # 环境分析需要推理
    "evidence_audit": create_fast_model,  # 审计用快速模型够用
    "orchestrator":   create_fast_model,  # 主编排/多 agent 图需要可靠的工具调用，使用快速模型
}


# 模块级缓存：同一 agent 复用同一个 ModelClient 实例（避免重复创建 OpenAI 连接池）
_client_cache: dict[str, ModelClient] = {}


def get_model_for_agent(agent_name: str) -> ModelClient:
    """根据 Agent 名获取对应的模型实例（兼容 deepseek_client 接口）。
    
    同一 agent 复用缓存的 ModelClient 实例，避免重复创建 OpenAI 连接池。
    """
    if agent_name in _client_cache:
        return _client_cache[agent_name]

    factory = AGENT_MODEL.get(agent_name)
    if factory is None:
        logger.warning("未知 Agent '%s'，使用 fast model", agent_name)
        factory = create_fast_model

    client = factory()
    _client_cache[agent_name] = client
    return client


def clear_model_cache() -> None:
    """清空模块级缓存（用于热重载配置时重建客户端）"""
    _client_cache.clear()
    logger.info("model_factory 缓存已清空")
