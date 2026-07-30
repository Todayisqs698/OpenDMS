"""运行时配置热更新 — 移植自 TripStar 的 config.py 热更新机制。

配置优先级（高 → 低）:
1. runtime_settings.json（运行时覆盖，持久化到磁盘）
2. .env 环境变量
3. 默认值

支持通过 API 在运行时修改 API Key、地图 Key、Cookie 等，
修改后立即生效并同步到 os.environ，无需重启服务。
"""
from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

logger = logging.getLogger(__name__)

# ── .env 加载（3 级目录回溯到项目根）─────────────────────────────────
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
_ENV_FILE = _PROJECT_ROOT / ".env"
if _ENV_FILE.exists():
    load_dotenv(_ENV_FILE)

# ── 运行时覆盖文件 ────────────────────────────────────────────────────
_RUNTIME_SETTINGS_FILE = _PROJECT_ROOT / "runtime_settings.json"

# 允许热更新的配置键（白名单，防止注入任意环境变量）
RUNTIME_SETTING_KEYS = {
    "DEEPSEEK_API_KEY",
    "AMAP_API_KEY",
    "OPENWEATHER_API_KEY",
    "XHS_COOKIE",
    "LLM_PROVIDER",
    "OPENAI_API_KEY",
    "HF_ENDPOINT",
}

# 敏感字段（API 返回时脱敏显示）
_SENSITIVE_KEYS = {
    "DEEPSEEK_API_KEY",
    "AMAP_API_KEY",
    "OPENAI_API_KEY",
    "XHS_COOKIE",
    "OPENWEATHER_API_KEY",
}

# ── 运行时覆盖加载与持久化 ────────────────────────────────────────────

_runtime_overrides: dict[str, str] = {}


def _load_runtime_overrides() -> dict[str, str]:
    """从 runtime_settings.json 加载持久化的运行时覆盖。"""
    if not _RUNTIME_SETTINGS_FILE.exists():
        return {}
    try:
        with open(_RUNTIME_SETTINGS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict):
            return {k: str(v) for k, v in data.items() if k in RUNTIME_SETTING_KEYS}
    except Exception as e:
        logger.warning("读取运行时配置失败，回退到环境变量: %s", e)
    return {}


def _persist_runtime_overrides(overrides: dict[str, str]) -> None:
    """持久化运行时覆盖到 JSON 文件。"""
    try:
        _RUNTIME_SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(_RUNTIME_SETTINGS_FILE, "w", encoding="utf-8") as f:
            json.dump(overrides, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error("持久化运行时配置失败: %s", e)


def _sync_env_from_overrides(overrides: dict[str, str]) -> None:
    """将运行时覆盖同步到 os.environ，兼容读取 env 的第三方组件。"""
    for key, value in overrides.items():
        if value:
            os.environ[key] = value


def _apply_runtime_overrides(overrides: dict[str, str]) -> None:
    """将覆盖项应用到 os.environ。"""
    _sync_env_from_overrides(overrides)


# ── 初始化: 加载持久化覆盖 ────────────────────────────────────────────
_runtime_overrides = _load_runtime_overrides()
_apply_runtime_overrides(_runtime_overrides)


# ── 公共 API ──────────────────────────────────────────────────────────

def get_runtime_settings() -> dict[str, str]:
    """获取当前运行时配置（供前端设置页读取）。

    优先级: runtime_settings.json 覆盖 > .env 环境变量 > 空字符串
    """
    result: dict[str, str] = {}
    for key in sorted(RUNTIME_SETTING_KEYS):
        # 运行时覆盖优先于环境变量
        if key in _runtime_overrides:
            result[key] = _runtime_overrides[key]
        else:
            result[key] = os.getenv(key, "")
    return result


def get_runtime_settings_masked() -> dict[str, str]:
    """获取脱敏后的运行时配置（敏感字段只显示是否已配置）。"""
    settings = get_runtime_settings()
    masked: dict[str, str] = {}
    for key, value in settings.items():
        if key in _SENSITIVE_KEYS:
            masked[key] = "***已配置***" if value else ""
        else:
            masked[key] = value
    return masked


def update_runtime_settings(updates: dict[str, Any]) -> dict[str, str]:
    """更新并持久化运行时配置，立即同步到 os.environ。

    更新后自动触发:
    - deepseek_client 重建（拾取新 API Key）
    - XHS 签名引擎缓存重置（拾取新 Cookie）

    Args:
        updates: {key: value} 字典，只接受白名单中的 key

    Returns:
        更新后的完整配置（未脱敏）
    """
    global _runtime_overrides

    normalized: dict[str, str] = {}
    for key, value in updates.items():
        if key not in RUNTIME_SETTING_KEYS:
            logger.warning("忽略不在白名单中的配置键: %s", key)
            continue
        normalized[key] = str(value).strip() if value is not None else ""

    _runtime_overrides.update(normalized)
    _persist_runtime_overrides(_runtime_overrides)
    _apply_runtime_overrides(_runtime_overrides)

    # ── 热更新钩子 ──────────────────────────────────────────────────
    _trigger_hot_reload(normalized.keys())

    logger.info("运行时配置已更新: %s", ", ".join(normalized.keys()))
    return get_runtime_settings()


def _trigger_hot_reload(changed_keys) -> None:
    """配置更新后触发相关组件重新加载。"""
    changed_set = set(changed_keys)

    # 模型客户端重建
    if changed_set & {"DEEPSEEK_API_KEY", "OPENAI_API_KEY", "DOUBAO_API_KEY"}:
        try:
            from modules.ai.model_factory import clear_model_cache
            clear_model_cache()
            logger.info("model_factory 缓存已清空（将在下次请求时使用新配置）")
        except Exception as e:
            logger.warning("model_factory 热重载失败: %s", e)
        # 兼容旧 deepseek_client
        try:
            from modules.ai.deepseek_client import deepseek_client
            deepseek_client.reload()
        except Exception:
            pass

    # XHS 签名引擎缓存重置（强制重新检查 Cookie）
    if "XHS_COOKIE" in changed_set:
        try:
            import modules.ai.trip_planner.xhs_service as xhs_svc
            xhs_svc._sign_engine_checked = False
            xhs_svc._sign_engine = None
            logger.info("XHS 签名引擎缓存已重置")
        except Exception as e:
            logger.warning("XHS 签名引擎重置失败: %s", e)


def get_config(key: str, default: str = "") -> str:
    """获取单个配置值（运行时覆盖优先于环境变量）。"""
    if key in _runtime_overrides:
        return _runtime_overrides[key]
    return os.getenv(key, default)


def is_configured(key: str) -> bool:
    """检查某个配置是否已设置（非空）。"""
    return bool(get_config(key))


def get_project_root() -> Path:
    """获取项目根目录。"""
    return _PROJECT_ROOT
