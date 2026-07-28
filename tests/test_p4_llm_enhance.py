"""P4 smoketest: LLM 增强高德 POI 数据验证

验证 llm_enhance_attractions 函数的核心功能:
- 函数可导入且签名正确
- 空列表输入安全处理
- LLM 不可用时优雅降级（返回原始数据）
- LLM 返回结果正确合并回原始数据（mock 测试）
- agent.py 在 XHS 不可用时走 LLM 兜底路径

运行: python tests/test_p4_llm_enhance.py
"""
import sys
import os
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# 确保不读取真实 .env 中的 cookie（测试隔离）
os.environ.pop("XHS_COOKIE", None)


# ── 导入验证 ────────────────────────────────────────────────────────

def test_import_llm_enhance():
    """llm_enhance_attractions 可从 xhs_service 导入"""
    from modules.ai.trip_planner.xhs_service import llm_enhance_attractions
    assert callable(llm_enhance_attractions)


def test_import_in_agent():
    """agent.py 能正常导入（含 llm_enhance_attractions 引用）"""
    from modules.ai.trip_planner.agent import EdgeGuardTripPlanner
    assert EdgeGuardTripPlanner is not None


# ── 空输入处理 ──────────────────────────────────────────────────────

def test_empty_input_returns_empty():
    """空列表输入应原样返回"""
    from modules.ai.trip_planner.xhs_service import llm_enhance_attractions
    result = llm_enhance_attractions([], "杭州")
    assert result == []


def test_none_input_returns_none():
    """None 输入应原样返回（不崩溃）"""
    from modules.ai.trip_planner.xhs_service import llm_enhance_attractions
    result = llm_enhance_attractions(None, "杭州")
    assert result is None


# ── LLM 不可用降级 ──────────────────────────────────────────────────

def test_llm_unavailable_returns_original():
    """DeepSeek 不可用时应返回原始数据，不崩溃"""
    from modules.ai.trip_planner.xhs_service import llm_enhance_attractions

    items = [
        {"name": "西湖", "category": "自然风光", "visit_duration": 120, "source": "amap"},
        {"name": "灵隐寺", "category": "宗教文化", "visit_duration": 90, "source": "amap"},
    ]

    with patch("modules.ai.deepseek_client.deepseek_client") as mock_client:
        mock_client.is_available = False
        result = llm_enhance_attractions(items, "杭州")

    # 应返回原始数据，无修改
    assert result is items
    assert result[0]["source"] == "amap"
    assert "description" not in result[0] or result[0].get("description") is None


def test_llm_import_error_returns_original():
    """deepseek_client 模块导入失败时应返回原始数据"""
    from modules.ai.trip_planner.xhs_service import llm_enhance_attractions

    items = [{"name": "西湖", "source": "amap"}]

    # 模拟 import 失败
    import builtins
    real_import = builtins.__import__

    def mock_import(name, *args, **kwargs):
        if "deepseek_client" in name:
            raise ImportError("模拟导入失败")
        return real_import(name, *args, **kwargs)

    with patch.object(builtins, "__import__", side_effect=mock_import):
        result = llm_enhance_attractions(items, "杭州")

    assert result is items
    assert result[0]["source"] == "amap"


# ── LLM 返回结果合并（mock）────────────────────────────────────────

def test_llm_enhance_merges_results():
    """LLM 返回有效结果时，应正确合并回原始数据"""
    from modules.ai.trip_planner.xhs_service import llm_enhance_attractions

    items = [
        {"name": "西湖", "category": "自然风光", "type": "风景名胜", "address": "杭州",
         "visit_duration": 120, "source": "amap"},
        {"name": "灵隐寺", "category": "宗教文化", "type": "寺庙", "address": "杭州",
         "visit_duration": 90, "source": "amap"},
    ]

    # 模拟 LLM 返回的 JSON 数组
    mock_llm_response = '''[
      {"index": 0, "description": "建议清晨前往人少景美，西湖十景集中在此区域。", "visit_duration": 180, "reservation_required": false, "reservation_tips": ""},
      {"index": 1, "description": "需买飞来峰门票才能进，每周一闭馆。", "visit_duration": 150, "reservation_required": true, "reservation_tips": "提前在公众号预约"}
    ]'''

    mock_response = MagicMock()
    mock_response.choices = [MagicMock()]
    mock_response.choices[0].message.content = mock_llm_response

    with patch("modules.ai.deepseek_client.deepseek_client") as mock_client:
        mock_client.is_available = True
        mock_client.client.chat.completions.create.return_value = mock_response
        result = llm_enhance_attractions(items, "杭州")

    # 验证合并结果
    assert len(result) == 2

    # 西湖
    assert result[0]["description"] == "建议清晨前往人少景美，西湖十景集中在此区域。"
    assert result[0]["visit_duration"] == 180
    assert result[0]["reservation_required"] is False
    assert result[0]["reservation_tips"] == ""
    assert result[0]["source"] == "amap+llm"

    # 灵隐寺
    assert result[1]["description"] == "需买飞来峰门票才能进，每周一闭馆。"
    assert result[1]["visit_duration"] == 150
    assert result[1]["reservation_required"] is True
    assert result[1]["reservation_tips"] == "提前在公众号预约"
    assert result[1]["source"] == "amap+llm"


def test_llm_enhance_partial_results():
    """LLM 只返回部分景点的增强时，未覆盖的保持不变"""
    from modules.ai.trip_planner.xhs_service import llm_enhance_attractions

    items = [
        {"name": "西湖", "category": "自然风光", "visit_duration": 120, "source": "amap"},
        {"name": "灵隐寺", "category": "宗教文化", "visit_duration": 90, "source": "amap"},
        {"name": "雷峰塔", "category": "历史古迹", "visit_duration": 60, "source": "amap"},
    ]

    # LLM 只返回 index 0 和 2 的结果
    mock_llm_response = '''[
      {"index": 0, "description": "清晨人少。", "visit_duration": 180, "reservation_required": false, "reservation_tips": ""},
      {"index": 2, "description": "需购票登塔。", "visit_duration": 90, "reservation_required": true, "reservation_tips": "现场购票"}
    ]'''

    mock_response = MagicMock()
    mock_response.choices = [MagicMock()]
    mock_response.choices[0].message.content = mock_llm_response

    with patch("modules.ai.deepseek_client.deepseek_client") as mock_client:
        mock_client.is_available = True
        mock_client.client.chat.completions.create.return_value = mock_response
        result = llm_enhance_attractions(items, "杭州")

    # index 0 被增强
    assert result[0]["description"] == "清晨人少。"
    assert result[0]["visit_duration"] == 180
    assert result[0]["source"] == "amap+llm"

    # index 1 未被增强（保持原始数据）
    assert result[1]["source"] == "amap"
    assert result[1]["visit_duration"] == 90

    # index 2 被增强
    assert result[2]["description"] == "需购票登塔。"
    assert result[2]["visit_duration"] == 90
    assert result[2]["source"] == "amap+llm"


def test_llm_enhance_invalid_json():
    """LLM 返回无效 JSON 时应优雅降级，返回原始数据"""
    from modules.ai.trip_planner.xhs_service import llm_enhance_attractions

    items = [{"name": "西湖", "source": "amap", "visit_duration": 120}]

    mock_response = MagicMock()
    mock_response.choices = [MagicMock()]
    mock_response.choices[0].message.content = "这不是 JSON 格式的文本"

    with patch("modules.ai.deepseek_client.deepseek_client") as mock_client:
        mock_client.is_available = True
        mock_client.client.chat.completions.create.return_value = mock_response
        result = llm_enhance_attractions(items, "杭州")

    # 应返回原始数据，无修改
    assert result is items
    assert result[0]["source"] == "amap"


def test_llm_enhance_api_exception():
    """LLM API 调用异常时应优雅降级"""
    from modules.ai.trip_planner.xhs_service import llm_enhance_attractions

    items = [{"name": "西湖", "source": "amap"}]

    with patch("modules.ai.deepseek_client.deepseek_client") as mock_client:
        mock_client.is_available = True
        mock_client.client.chat.completions.create.side_effect = Exception("API 超时")
        result = llm_enhance_attractions(items, "杭州")

    # 应返回原始数据
    assert result is items
    assert result[0]["source"] == "amap"


# ── agent.py 集成验证 ──────────────────────────────────────────────

def test_agent_search_attractions_imports_llm():
    """agent._search_attractions 应导入 llm_enhance_attractions"""
    # 验证 import 语句不会报错
    from modules.ai.trip_planner.agent import EdgeGuardTripPlanner
    planner = EdgeGuardTripPlanner()
    # 确保方法存在
    assert hasattr(planner, "_search_attractions")


def test_agent_fallback_to_llm_when_xhs_unavailable():
    """XHS 不可用时，_search_attractions 应走 LLM 兜底路径"""
    from modules.ai.trip_planner.agent import EdgeGuardTripPlanner
    from modules.ai.trip_planner.schemas import TripRequest

    planner = EdgeGuardTripPlanner()
    request = TripRequest.from_text(city="杭州", days=1, preference="历史文化", query="杭州一日游")

    # Mock 高德 POI 返回数据
    mock_amap_result = {
        "success": True,
        "attractions": [
            {"name": "西湖", "address": "杭州西湖区", "category": "自然风光",
             "type": "风景名胜", "rating": 4.8, "ticket_price": 0,
             "visit_duration": 120, "photo_url": "", "location": "120.1,30.2"},
            {"name": "灵隐寺", "address": "杭州西湖区", "category": "宗教文化",
             "type": "寺庙", "rating": 4.5, "ticket_price": 30,
             "visit_duration": 90, "photo_url": "", "location": "120.1,30.2"},
        ],
    }

    # Mock LLM 增强：验证被调用
    llm_called = {"value": False}

    def mock_llm_enhance(items, city, preference=None):
        llm_called["value"] = True
        for item in items:
            item["description"] = f"LLM增强的{item['name']}"
            item["source"] = "amap+llm"
        return items

    with patch("modules.ai.tools.search_attractions", return_value=mock_amap_result), \
         patch("modules.ai.trip_planner.xhs_service.is_xhs_available", return_value=False), \
         patch("modules.ai.trip_planner.xhs_service.llm_enhance_attractions", side_effect=mock_llm_enhance):
        attractions = planner._search_attractions(request)

    # LLM 增强应该被调用
    assert llm_called["value"] is True

    # 景点应该有 LLM 增强的描述
    assert len(attractions) >= 1
    has_llm_desc = any("LLM增强" in (a.description or "") for a in attractions)
    assert has_llm_desc, "至少一个景点应有 LLM 增强描述"


def test_agent_xhs_available_skips_llm():
    """XHS 可用且返回结果时应跳过 LLM 兜底"""
    from modules.ai.trip_planner.agent import EdgeGuardTripPlanner
    from modules.ai.trip_planner.schemas import TripRequest

    planner = EdgeGuardTripPlanner()
    request = TripRequest.from_text(city="杭州", days=1, query="杭州一日游")

    mock_amap_result = {
        "success": True,
        "attractions": [{"name": "西湖", "address": "杭州", "category": "自然风光",
                         "type": "风景名胜", "rating": 4.8, "ticket_price": 0,
                         "visit_duration": 120, "photo_url": "", "location": "120.1,30.2"}],
    }

    # XHS 返回非空结果
    mock_xhs_result = [
        {"name": "西湖", "description": "XHS真实游记描述", "visit_duration": 180,
         "category": "自然风光", "source": "xhs"}
    ]

    llm_called = {"value": False}

    def mock_llm_enhance(items, city, preference=None):
        llm_called["value"] = True
        return items

    with patch("modules.ai.tools.search_attractions", return_value=mock_amap_result), \
         patch("modules.ai.trip_planner.xhs_service.is_xhs_available", return_value=True), \
         patch("modules.ai.trip_planner.xhs_service.search_xhs_attractions", return_value=mock_xhs_result), \
         patch("modules.ai.trip_planner.xhs_service.llm_enhance_attractions", side_effect=mock_llm_enhance):
        attractions = planner._search_attractions(request)

    # XHS 返回了结果，LLM 不应被调用
    assert llm_called["value"] is False


def test_agent_xhs_empty_results_triggers_llm():
    """XHS 可用但返回空结果（Cookie 失效）时应走 LLM 兜底"""
    from modules.ai.trip_planner.agent import EdgeGuardTripPlanner
    from modules.ai.trip_planner.schemas import TripRequest

    planner = EdgeGuardTripPlanner()
    request = TripRequest.from_text(city="杭州", days=1, query="杭州一日游")

    mock_amap_result = {
        "success": True,
        "attractions": [{"name": "西湖", "address": "杭州", "category": "自然风光",
                         "type": "风景名胜", "rating": 4.8, "ticket_price": 0,
                         "visit_duration": 120, "photo_url": "", "location": "120.1,30.2"}],
    }

    llm_called = {"value": False}

    def mock_llm_enhance(items, city, preference=None):
        llm_called["value"] = True
        for item in items:
            item["description"] = f"LLM增强的{item['name']}"
            item["source"] = "amap+llm"
        return items

    with patch("modules.ai.tools.search_attractions", return_value=mock_amap_result), \
         patch("modules.ai.trip_planner.xhs_service.is_xhs_available", return_value=True), \
         patch("modules.ai.trip_planner.xhs_service.search_xhs_attractions", return_value=[]), \
         patch("modules.ai.trip_planner.xhs_service.llm_enhance_attractions", side_effect=mock_llm_enhance):
        attractions = planner._search_attractions(request)

    # XHS 返回空，LLM 应被调用
    assert llm_called["value"] is True
    has_llm_desc = any("LLM增强" in (a.description or "") for a in attractions)
    assert has_llm_desc, "景点应有 LLM 增强描述"


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
    print(f"P4 LLM 增强: {passed} passed, {failed} failed, {len(tests)} total")
    sys.exit(1 if failed else 0)
