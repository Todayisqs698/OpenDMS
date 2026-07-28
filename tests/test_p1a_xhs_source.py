"""P1a smoketest: 小红书数据源移植验证

验证 xhs_service 的核心功能:
- Cookie 归一化
- 签名引擎懒加载（可用/不可用都安全）
- 数据源可用性检查
- 搜索函数在未配置时优雅降级
- agent.py 的 _merge_xhs_attractions 合并逻辑

运行: python tests/test_p1a_xhs_source.py
"""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# 确保不读取真实 .env 中的 cookie（测试隔离）
os.environ.pop("XHS_COOKIE", None)


# ── xhs_service 模块导入 ───────────────────────────────────────────

from modules.ai.trip_planner.xhs_service import (
    _normalize_xhs_cookie,
    _get_xhs_cookie,
    _get_sign_engine,
    is_xhs_available,
    search_xhs_attractions,
    get_xhs_client,
    XHSCookieExpiredError,
)


# ── Cookie 归一化 ───────────────────────────────────────────────────

def test_normalize_cookie_plain_string():
    cookie = "a1=xxx; web_session=yyy; webId=zzz"
    assert _normalize_xhs_cookie(cookie) == cookie


def test_normalize_cookie_json_array():
    cookie = '[{"name": "a1", "value": "xxx"}, {"name": "webId", "value": "zzz"}]'
    result = _normalize_xhs_cookie(cookie)
    assert "a1=xxx" in result
    assert "webId=zzz" in result


def test_normalize_cookie_single_object():
    cookie = '{"name": "a1", "value": "xxx"}'
    result = _normalize_xhs_cookie(cookie)
    assert "a1=xxx" in result


def test_normalize_cookie_quoted():
    cookie = '"a1=xxx; webId=zzz"'
    result = _normalize_xhs_cookie(cookie)
    assert result == "a1=xxx; webId=zzz"


def test_normalize_cookie_empty():
    assert _normalize_xhs_cookie("") == ""


# ── 签名引擎懒加载 ──────────────────────────────────────────────────

def test_sign_engine_lazy_load():
    """签名引擎应该能加载（Node.js + execjs 已安装）或优雅返回 None"""
    engine = _get_sign_engine()
    # 在测试环境中 Node.js 已安装，应该成功
    # 但即使失败也不应该抛异常
    assert engine is None or isinstance(engine, dict)
    if engine:
        assert "generate_request_params" in engine
        assert "generate_x_b3_traceid" in engine


def test_sign_engine_cached():
    """第二次调用应返回缓存结果"""
    engine1 = _get_sign_engine()
    engine2 = _get_sign_engine()
    assert engine1 is engine2


# ── 数据源可用性 ────────────────────────────────────────────────────

def test_is_xhs_available_no_cookie():
    """未配置 Cookie 时返回 False"""
    os.environ.pop("XHS_COOKIE", None)
    assert is_xhs_available() is False


def test_get_xhs_client_no_cookie():
    """未配置 Cookie 时返回 None"""
    os.environ.pop("XHS_COOKIE", None)
    assert get_xhs_client() is None


def test_search_returns_empty_when_not_configured():
    """未配置 Cookie 时搜索返回空列表，不报错"""
    os.environ.pop("XHS_COOKIE", None)
    result = search_xhs_attractions(city="杭州")
    assert result == []


def test_search_returns_empty_on_invalid_cookie():
    """配置了无效 Cookie 但签名引擎可用时，搜索应优雅失败返回空列表"""
    os.environ["XHS_COOKIE"] = "invalid_cookie=xxx"
    try:
        # 即使签名引擎可用，实际 API 调用会失败，应返回空列表
        result = search_xhs_attractions(city="测试城市")
        assert result == []
    finally:
        os.environ.pop("XHS_COOKIE", None)


# ── agent.py _merge_xhs_attractions ────────────────────────────────

def _make_planner():
    from modules.ai.trip_planner.agent import EdgeGuardTripPlanner
    return EdgeGuardTripPlanner()


def test_merge_empty_xhs():
    """XHS 返回空列表时，高德数据不变"""
    planner = _make_planner()
    amap_items = [{"name": "西湖", "ticket_price": 0, "source": "amap"}]
    result = planner._merge_xhs_attractions(amap_items, [], "杭州")
    assert result == amap_items


def test_merge_matching_name():
    """同名景点: XHS 数据增强高德数据"""
    planner = _make_planner()
    amap_items = [
        {"name": "西湖", "ticket_price": 0, "rating": 4.8, "location": "120.1,30.2",
         "source": "amap", "description": "杭州著名景点", "visit_duration": 60}
    ]
    xhs_items = [
        {"name": "西湖", "description": "免费开放，建议清晨去人少。", "visit_duration": 180,
         "category": "自然风光", "source": "xhs"}
    ]
    result = planner._merge_xhs_attractions(amap_items, xhs_items, "杭州")
    assert len(result) == 1
    merged = result[0]
    # XHS 覆盖的字段
    assert "清晨" in merged["description"]
    assert merged["visit_duration"] == 180
    assert merged["category"] == "自然风光"
    # 高德保留的字段
    assert merged["ticket_price"] == 0
    assert merged["rating"] == 4.8
    assert merged["location"] == "120.1,30.2"
    assert merged["source"] == "amap+xhs"


def test_merge_xhs_only_attraction():
    """XHS 独有的景点追加到列表末尾"""
    planner = _make_planner()
    amap_items = [{"name": "西湖", "source": "amap"}]
    xhs_items = [
        {"name": "九溪烟树", "description": "小众秘境", "visit_duration": 120,
         "category": "自然风光", "source": "xhs", "route_city": ""}
    ]
    result = planner._merge_xhs_attractions(amap_items, xhs_items, "杭州")
    assert len(result) == 2
    assert result[0]["name"] == "西湖"
    assert result[1]["name"] == "九溪烟树"
    assert result[1]["route_city"] == "杭州"


def test_merge_case_insensitive():
    """名称匹配忽略大小写"""
    planner = _make_planner()
    amap_items = [{"name": "West Lake", "source": "amap"}]
    xhs_items = [{"name": "west lake", "description": "Great place", "source": "xhs"}]
    result = planner._merge_xhs_attractions(amap_items, xhs_items, "杭州")
    assert len(result) == 1
    assert result[0]["description"] == "Great place"


def test_merge_multiple_xhs():
    """多个 XHS 景点，部分匹配部分新增"""
    planner = _make_planner()
    amap_items = [
        {"name": "西湖", "source": "amap", "description": "amap desc"},
        {"name": "灵隐寺", "source": "amap", "description": "amap desc"},
    ]
    xhs_items = [
        {"name": "西湖", "description": "xhs desc", "source": "xhs"},
        {"name": "九溪烟树", "description": "xhs new", "source": "xhs", "route_city": ""},
    ]
    result = planner._merge_xhs_attractions(amap_items, xhs_items, "杭州")
    assert len(result) == 3
    # 西湖被增强
    assert result[0]["description"] == "xhs desc"
    assert result[0]["source"] == "amap+xhs"
    # 灵隐寺保持不变
    assert result[1]["description"] == "amap desc"
    assert result[1]["source"] == "amap"
    # 九溪烟树新增
    assert result[2]["name"] == "九溪烟树"
    assert result[2]["route_city"] == "杭州"


# ── _to_attraction 兼容 XHS 格式 ─────────────────────────────────────

def test_to_attraction_from_xhs_format():
    """_to_attraction 能正确处理 XHS 格式的 dict"""
    from modules.ai.trip_planner.agent import EdgeGuardTripPlanner
    planner = EdgeGuardTripPlanner()
    xhs_item = {
        "name": "九溪烟树",
        "address": "杭州",
        "location": "120.1,30.2",
        "visit_duration": 120,
        "description": "小众秘境",
        "category": "自然风光",
        "ticket_price": 0,
        "rating": None,
        "photo_url": "",
        "id": "xhs_0",
        "source": "xhs",
        "route_city": "杭州",
    }
    attraction = planner._to_attraction(xhs_item)
    assert attraction.name == "九溪烟树"
    assert attraction.description == "小众秘境"
    assert attraction.visit_duration == 120
    assert attraction.category == "自然风光"
    assert attraction.route_city == "杭州"


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
    print(f"\n{'='*50}")
    print(f"P1a 小红书数据源: {passed} passed, {failed} failed, {len(tests)} total")
    sys.exit(1 if failed else 0)
