"""P1b smoketest: 运行时配置热更新验证

验证 runtime_config 模块的核心功能:
- 配置加载（.env → runtime_settings.json 覆盖）
- 配置读取（脱敏/未脱敏）
- 配置更新与持久化
- 热更新钩子（deepseek_client reload / XHS 缓存重置）
- 白名单过滤

运行: python tests/test_p1b_runtime_config.py
"""
import sys
import os
import json
import tempfile
import shutil

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


# ── 测试前: 备份并清理 runtime_settings.json ─────────────────────────

from modules.ai.runtime_config import (
    get_runtime_settings,
    get_runtime_settings_masked,
    update_runtime_settings,
    get_config,
    is_configured,
    RUNTIME_SETTING_KEYS,
    _RUNTIME_SETTINGS_FILE,
    _runtime_overrides,
)


def _backup_runtime():
    """备份 runtime_settings.json"""
    if _RUNTIME_SETTINGS_FILE.exists():
        return _RUNTIME_SETTINGS_FILE.read_text(encoding="utf-8")
    return None


def _restore_runtime(backup):
    """恢复 runtime_settings.json"""
    if backup is not None:
        _RUNTIME_SETTINGS_FILE.write_text(backup, encoding="utf-8")
    elif _RUNTIME_SETTINGS_FILE.exists():
        _RUNTIME_SETTINGS_FILE.unlink()


# ── 测试 ─────────────────────────────────────────────────────────────

_backup = _backup_runtime()


def test_get_runtime_settings_returns_all_keys():
    """get_runtime_settings 返回所有白名单键"""
    settings = get_runtime_settings()
    for key in RUNTIME_SETTING_KEYS:
        assert key in settings, f"缺少键: {key}"


def test_get_runtime_settings_masked_hides_sensitive():
    """脱敏配置隐藏敏感字段"""
    # 先设置一个测试值
    os.environ["DEEPSEEK_API_KEY"] = "test-secret-key-123"
    update_runtime_settings({"DEEPSEEK_API_KEY": "test-secret-key-123"})
    masked = get_runtime_settings_masked()
    assert masked["DEEPSEEK_API_KEY"] == "***已配置***"
    # 未脱敏的完整值
    full = get_runtime_settings()
    assert full["DEEPSEEK_API_KEY"] == "test-secret-key-123"


def test_get_runtime_settings_masked_empty():
    """未配置的敏感字段显示为空"""
    update_runtime_settings({"XHS_COOKIE": ""})
    masked = get_runtime_settings_masked()
    assert masked["XHS_COOKIE"] == ""


def test_update_persists_to_file():
    """更新配置后持久化到 runtime_settings.json"""
    update_runtime_settings({"AMAP_API_KEY": "test-amap-key-456"})
    assert _RUNTIME_SETTINGS_FILE.exists()
    data = json.loads(_RUNTIME_SETTINGS_FILE.read_text(encoding="utf-8"))
    assert data.get("AMAP_API_KEY") == "test-amap-key-456"


def test_update_syncs_to_environ():
    """更新配置后同步到 os.environ"""
    update_runtime_settings({"AMAP_API_KEY": "env-sync-test-789"})
    assert os.getenv("AMAP_API_KEY") == "env-sync-test-789"


def test_update_overrides_env():
    """运行时覆盖优先于环境变量"""
    os.environ["OPENWEATHER_API_KEY"] = "from-env"
    update_runtime_settings({"OPENWEATHER_API_KEY": "from-runtime"})
    assert get_config("OPENWEATHER_API_KEY") == "from-runtime"
    assert os.getenv("OPENWEATHER_API_KEY") == "from-runtime"


def test_update_ignores_non_whitelist_keys():
    """非白名单键被忽略"""
    result = update_runtime_settings({"MALICIOUS_KEY": "hacked"})
    assert "MALICIOUS_KEY" not in result


def test_get_config():
    """get_config 返回单个配置值"""
    update_runtime_settings({"LLM_PROVIDER": "deepseek"})
    assert get_config("LLM_PROVIDER") == "deepseek"


def test_get_config_default():
    """get_config 返回默认值"""
    assert get_config("NONEXISTENT_KEY", "default") == "default"


def test_is_configured_true():
    """is_configured 已配置返回 True"""
    update_runtime_settings({"AMAP_API_KEY": "configured"})
    assert is_configured("AMAP_API_KEY") is True


def test_is_configured_false():
    """is_configured 未配置返回 False"""
    update_runtime_settings({"AMAP_API_KEY": ""})
    assert is_configured("AMAP_API_KEY") is False


def test_update_clears_value():
    """空字符串清除配置"""
    update_runtime_settings({"AMAP_API_KEY": "has-value"})
    assert is_configured("AMAP_API_KEY") is True
    update_runtime_settings({"AMAP_API_KEY": ""})
    assert is_configured("AMAP_API_KEY") is False


def test_hot_reload_deepseek():
    """更新 DEEPSEEK_API_KEY 后触发 deepseek_client reload"""
    from modules.ai.deepseek_client import deepseek_client
    update_runtime_settings({"DEEPSEEK_API_KEY": "new-hot-key"})
    assert deepseek_client._api_key == "new-hot-key"


def test_hot_reload_xhs_cache_reset():
    """更新 XHS_COOKIE 后重置签名引擎缓存"""
    import modules.ai.trip_planner.xhs_service as xhs_svc
    # 先触发签名引擎加载
    xhs_svc._get_sign_engine()
    assert xhs_svc._sign_engine_checked is True
    # 更新 Cookie 触发缓存重置
    update_runtime_settings({"XHS_COOKIE": "new-cookie-value"})
    assert xhs_svc._sign_engine_checked is False
    assert xhs_svc._sign_engine is None


def test_multiple_updates_merge():
    """多次更新合并到 runtime_settings.json"""
    update_runtime_settings({"AMAP_API_KEY": "key1"})
    update_runtime_settings({"LLM_PROVIDER": "openai"})
    data = json.loads(_RUNTIME_SETTINGS_FILE.read_text(encoding="utf-8"))
    assert data.get("AMAP_API_KEY") == "key1"
    assert data.get("LLM_PROVIDER") == "openai"


def test_runtime_survives_module_reload():
    """runtime_settings.json 在重新导入模块后仍然生效"""
    update_runtime_settings({"AMAP_API_KEY": "persistent-key"})
    # 重新导入模块
    import importlib
    import modules.ai.runtime_config as rc
    importlib.reload(rc)
    assert rc.get_config("AMAP_API_KEY") == "persistent-key"


if __name__ == "__main__":
    import traceback
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    passed = 0
    failed = 0
    for test in tests:
        try:
            test()
            print(f"  PASS  {test.__name__}")
            passed += 1
        except Exception:
            print(f"  FAIL  {test.__name__}")
            traceback.print_exc()
            failed += 1

    # 恢复原始 runtime_settings.json
    _restore_runtime(_backup)

    print(f"\n{'='*50}")
    print(f"P1b 运行时配置热更新: {passed} passed, {failed} failed, {len(tests)} total")
    sys.exit(1 if failed else 0)
