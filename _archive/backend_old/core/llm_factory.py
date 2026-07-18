"""
多模型工厂 — 组员的 Agent 统一用 get_llm() 获取模型实例
用法: llm = get_llm(temperature=0.3)
"""
from app.core.config import settings


def get_llm(temperature: float = 0.3):
    """根据 LLM_PROVIDER 返回对应的 LangChain ChatModel"""
    provider = settings.LLM_PROVIDER

    if provider == "anthropic":
        from langchain_anthropic import ChatAnthropic
        return ChatAnthropic(
            model="claude-sonnet-4-6",
            api_key=settings.ANTHROPIC_API_KEY,
            temperature=temperature,
        )
    elif provider == "openai":
        from langchain_openai import ChatOpenAI
        return ChatOpenAI(
            model="gpt-4o",
            api_key=settings.OPENAI_API_KEY,
            temperature=temperature,
        )
    else:  # deepseek (默认)
        from langchain_deepseek import ChatDeepSeek
        return ChatDeepSeek(
            model="deepseek-chat",
            api_key=settings.DEEPSEEK_API_KEY,
            temperature=temperature,
        )


def get_llm_json_mode():
    """获取 JSON 结构化输出模式的 LLM"""
    provider = settings.LLM_PROVIDER

    if provider == "anthropic":
        from langchain_anthropic import ChatAnthropic
        return ChatAnthropic(
            model="claude-sonnet-4-6",
            api_key=settings.ANTHROPIC_API_KEY,
            temperature=0,
        )
    elif provider == "openai":
        from langchain_openai import ChatOpenAI
        return ChatOpenAI(
            model="gpt-4o",
            api_key=settings.OPENAI_API_KEY,
            temperature=0,
            model_kwargs={"response_format": {"type": "json_object"}},
        )
    else:
        from langchain_deepseek import ChatDeepSeek
        return ChatDeepSeek(
            model="deepseek-chat",
            api_key=settings.DEEPSEEK_API_KEY,
            temperature=0,
            model_kwargs={"response_format": {"type": "json_object"}},
        )
