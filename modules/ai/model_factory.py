"""
模型工厂 — 按能力创建模型实例，模型名从 Settings（环境变量）读取

两种能力:
  - create_fast_model():      快速模型（豆包 Lite → 降级 DeepSeek Chat）
  - create_reasoning_model(): 推理模型（DeepSeek Reasoner → 降级豆包 Lite）

Agent → 模型映射通过 AGENT_MODEL 字典 + get_model_for_agent() 实现。
"""

from __future__ import annotations

import logging
import os
from typing import Any

from dotenv import load_dotenv
from langchain_openai import ChatOpenAI

# 3 级目录遍历到达项目根目录 edgeguard/
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))), '.env'))

logger = logging.getLogger("edgeguard.model_factory")


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

        "model_temperature": float(os.getenv("MODEL_TEMPERATURE", "0.3")),
        "model_timeout": int(os.getenv("MODEL_TIMEOUT", "60")),
        "model_max_retries": int(os.getenv("MODEL_MAX_RETRIES", "2")),
        "model_max_tokens": int(os.getenv("MODEL_MAX_TOKENS", "4096")),
    }


def create_fast_model() -> ChatOpenAI:
    """
    快速模型 — 用于 SafetyAgent / IntentionAgent / InteractionAgent。
    优先豆包 Lite，不可用时降级到 DeepSeek Chat。
    """
    s = _get_settings()
    if s["doubao_api_key"]:
        logger.info("fast model: %s @ ark", s["doubao_fast_model"])
        return ChatOpenAI(
            model=s["doubao_fast_model"],
            base_url=s["doubao_base_url"],
            api_key=s["doubao_api_key"],
            temperature=s["model_temperature"],
            timeout=s["model_timeout"],
            max_retries=s["model_max_retries"],
            max_tokens=min(s["model_max_tokens"], 2048),
        )
    if s["deepseek_api_key"]:
        logger.warning("fast model: 豆包不可用，降级到 %s", s["deepseek_chat_model"])
        return ChatOpenAI(
            model=s["deepseek_chat_model"],
            base_url=s["deepseek_base_url"],
            api_key=s["deepseek_api_key"],
            temperature=s["model_temperature"],
            timeout=s["model_timeout"],
            max_retries=s["model_max_retries"],
            max_tokens=min(s["model_max_tokens"], 2048),
        )
    raise RuntimeError("fast model: DOUBAO_API_KEY 和 DEEPSEEK_API_KEY 均为空")


def create_reasoning_model() -> ChatOpenAI:
    """
    推理模型 — 用于 DiagnoseAgent / AnalyzeAgent / RecommendAgent。
    优先 DeepSeek Reasoner，不可用时降级到 DeepSeek Chat。
    """
    s = _get_settings()
    if s["deepseek_api_key"]:
        logger.info("reasoning model: %s @ deepseek", s["deepseek_reasoner_model"])
        return ChatOpenAI(
            model=s["deepseek_reasoner_model"],
            base_url=s["deepseek_base_url"],
            api_key=s["deepseek_api_key"],
            temperature=0.2,  # 推理任务降低温度
            timeout=s["model_timeout"],
            max_retries=s["model_max_retries"],
            max_tokens=s["model_max_tokens"],
        )
    if s["doubao_api_key"]:
        logger.warning("reasoning model: DeepSeek 不可用，降级到豆包 Lite")
        return ChatOpenAI(
            model=s["doubao_fast_model"],
            base_url=s["doubao_base_url"],
            api_key=s["doubao_api_key"],
            temperature=0.2,
            timeout=s["model_timeout"],
            max_retries=s["model_max_retries"],
            max_tokens=s["model_max_tokens"],
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
    "evidence_audit": create_fast_model,  # 审计用快速模型够用
}


def get_model_for_agent(agent_name: str) -> ChatOpenAI:
    """根据 Agent 名获取对应的模型实例"""
    factory = AGENT_MODEL.get(agent_name)
    if factory is None:
        logger.warning("未知 Agent '%s'，使用 fast model", agent_name)
        factory = create_fast_model
    return factory()
