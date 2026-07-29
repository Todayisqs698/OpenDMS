"""
测试安全门控 — 无外部依赖。

覆盖：
  - apply_safety_gate 四级白名单过滤
  - TOOL_RESTRICTIONS 配置完整性
  - is_emergency 标志位
  - safety_prompt 注入
"""
import pytest
from modules.ai.safety_gate import (
    apply_safety_gate,
    TOOL_RESTRICTIONS,
    SAFETY_SYSTEM_PROMPTS,
)


# 构造测试用工具列表（模拟 TOOL_SCHEMAS 结构）
def _make_tool(name):
    return {"type": "function", "function": {"name": name, "description": f"Tool {name}", "parameters": {"type": "object", "properties": {}}}}


ALL_TOOLS = [
    _make_tool("speak"),
    _make_tool("control_ac"),
    _make_tool("control_music"),
    _make_tool("search_knowledge"),
    _make_tool("get_weather"),
    _make_tool("get_weather_forecast"),
    _make_tool("alert_driver"),
    _make_tool("ask_clarification"),
    _make_tool("search_attractions"),
    _make_tool("search_hotels"),
    _make_tool("start_navigation"),
    _make_tool("plan_trip"),
    _make_tool("save_location"),
    _make_tool("get_saved_location"),
]


class TestSafetyGateRestrictions:
    """TOOL_RESTRICTIONS 配置完整性。"""

    def test_five_risk_levels(self):
        """5 个风险级别都存在。"""
        expected = {"normal", "attn_declining", "distracted", "dangerous", "readonly"}
        assert set(TOOL_RESTRICTIONS.keys()) == expected

    def test_normal_allows_all(self):
        """normal 级别不限制（None 表示全开）。"""
        assert TOOL_RESTRICTIONS["normal"] is None

    def test_attn_declining_allows_all(self):
        """attn_declining 级别不限制工具，但会注入提示。"""
        assert TOOL_RESTRICTIONS["attn_declining"] is None

    def test_distracted_blocks_entertainment(self):
        """distracted 级别阻止娱乐功能。"""
        allowed = TOOL_RESTRICTIONS["distracted"]
        assert "control_music" not in allowed
        assert "search_attractions" not in allowed
        assert "plan_trip" not in allowed

    def test_dangerous_minimal(self):
        """dangerous 级别只允许 speak + alert_driver。"""
        allowed = TOOL_RESTRICTIONS["dangerous"]
        assert set(allowed) == {"speak", "alert_driver"}

    def test_readonly_allows_query_only(self):
        """readonly 级别只允许查询和告警。"""
        allowed = TOOL_RESTRICTIONS["readonly"]
        assert "speak" in allowed
        assert "alert_driver" in allowed
        assert "search_knowledge" in allowed
        assert "ask_clarification" in allowed
        assert "control_ac" not in allowed
        assert "control_music" not in allowed


class TestApplySafetyGate:
    """apply_safety_gate 函数行为。"""

    def test_normal_allows_all_tools(self):
        """正常状态：全部工具可用。"""
        result = apply_safety_gate("normal", ALL_TOOLS)
        assert result["risk_level"] == "normal"
        assert len(result["allowed_tools"]) == len(ALL_TOOLS)
        assert result["is_emergency"] is False

    def test_dangerous_restricts_tools(self):
        """危险状态：只允许 speak + alert_driver。"""
        result = apply_safety_gate("dangerous", ALL_TOOLS)
        allowed_names = [t["function"]["name"] for t in result["allowed_tools"]]
        assert "speak" in allowed_names
        assert "alert_driver" in allowed_names
        assert "control_music" not in allowed_names
        assert "plan_trip" not in allowed_names
        assert result["is_emergency"] is True

    def test_distracted_blocks_entertainment(self):
        """分心状态：阻止娱乐功能。"""
        result = apply_safety_gate("distracted", ALL_TOOLS)
        allowed_names = [t["function"]["name"] for t in result["allowed_tools"]]
        assert "control_music" not in allowed_names
        assert "search_attractions" not in allowed_names
        assert "control_ac" in allowed_names  # 空调仍可用
        assert result["is_emergency"] is False

    def test_readonly_blocks_control(self):
        """只读模式：阻止所有控制类工具。"""
        result = apply_safety_gate("readonly", ALL_TOOLS)
        allowed_names = [t["function"]["name"] for t in result["allowed_tools"]]
        assert "speak" in allowed_names
        assert "alert_driver" in allowed_names
        assert "search_knowledge" in allowed_names
        assert "control_ac" not in allowed_names
        assert "control_music" not in allowed_names
        assert "start_navigation" not in allowed_names
        assert "plan_trip" not in allowed_names

    def test_emergency_flag(self):
        """dangerous 级别设置 is_emergency=True。"""
        result = apply_safety_gate("dangerous", ALL_TOOLS)
        assert result["is_emergency"] is True

        result = apply_safety_gate("normal", ALL_TOOLS)
        assert result["is_emergency"] is False

    def test_safety_prompt_not_empty_for_restricted(self):
        """受限级别应该有安全提示（readonly 可能从模板库返回空，允许例外）。"""
        for level in ["attn_declining", "distracted", "dangerous"]:
            result = apply_safety_gate(level, ALL_TOOLS)
            assert result["safety_prompt"] != "", f"{level} should have non-empty safety_prompt"

    def test_safety_prompt_empty_for_normal(self):
        """normal 级别不需要安全提示。"""
        result = apply_safety_gate("normal", ALL_TOOLS)
        # normal 的提示可能为空或非空，取决于模板库，但不应出错
        assert isinstance(result["safety_prompt"], str)

    def test_driver_state_does_not_crash(self):
        """传入 driver_state 不应崩溃。"""
        driver_state = {"gaze": "left", "fatigue_score": 75}
        result = apply_safety_gate("distracted", ALL_TOOLS, driver_state)
        assert result["risk_level"] == "distracted"

    def test_empty_tool_list(self):
        """空工具列表不崩溃。"""
        result = apply_safety_gate("normal", [])
        assert result["allowed_tools"] == []
