"""
安全执行器 — 统一异常兜底，任何模块崩了都不影响主流程。
所有组员的 Agent 调用也应该走这个。

用法:
    result = safe_call(lambda: my_agent.analyze(data), default={"risk_level": "normal"})
"""
import logging
import traceback
import time

logger = logging.getLogger(__name__)


def safe_call(func, default=None, max_retries=1, timeout=None, name="unknown"):
    """
    安全调用：包装任意函数，异常时返回默认值，绝不抛异常。

    Args:
        func: 无参 lambda 或 callable
        default: 异常时返回的默认值
        max_retries: 最大重试次数
        timeout: 超时秒数（暂未实现）
        name: 调用名称（日志用）

    Returns:
        func() 的返回值，或 default
    """
    if default is None:
        default = {}

    start = time.time()
    last_error = None

    for attempt in range(max_retries + 1):
        try:
            result = func()
            elapsed = time.time() - start
            if elapsed > 0.5:
                logger.info(f"[{name}] 调用耗时 {elapsed:.2f}s")
            return result
        except Exception as e:
            last_error = e
            if attempt < max_retries:
                logger.warning(f"[{name}] 第{attempt+1}次调用失败: {e}，重试中...")
                time.sleep(0.1)
            else:
                logger.error(f"[{name}] 调用失败(已重试{max_retries}次): {e}")
                logger.debug(traceback.format_exc())

    return default


def safe_agent_call(agent, method: str, data: dict, default=None, name=""):
    """
    安全调用 Agent 方法。

    Args:
        agent: Agent 实例
        method: 方法名，如 "analyze"
        data: 输入数据 dict
        default: 异常时默认值
        name: Agent 名称

    Returns:
        Agent 返回值 dict，或 default
    """
    if default is None:
        default = {"error": "agent_unavailable", "source": name or "unknown"}

    def _call():
        fn = getattr(agent, method, None)
        if fn is None:
            raise AttributeError(f"Agent {name} 没有 {method} 方法")
        return fn(data)

    return safe_call(_call, default=default, name=name or method)


def safe_model_load(import_path: str, class_name: str, name=""):
    """
    安全加载模型/类。

    Returns:
        实例 或 None
    """
    def _load():
        mod = __import__(import_path, fromlist=[class_name])
        cls = getattr(mod, class_name)
        return cls()

    result = safe_call(_load, default=None, name=name or class_name)
    return result
