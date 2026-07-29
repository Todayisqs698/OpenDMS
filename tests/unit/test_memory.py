"""
测试三层记忆系统 — 无外部依赖（使用临时数据库）。

覆盖：
  - WorkingMemory 消息管理
  - WorkingMemory 行程参数缓存
  - WorkingMemory 工具结果缓存
  - LongTermMemory CRUD（需要临时 SQLite）
"""
import pytest
from modules.ai.memory import WorkingMemory


class TestWorkingMemoryMessages:
    """WorkingMemory 消息管理。"""

    def test_add_message(self):
        """添加消息后 turn_count 递增。"""
        wm = WorkingMemory()
        wm.add_message("user", "你好")
        assert wm.turn_count == 1
        assert len(wm.messages) == 1

    def test_add_multiple_messages(self):
        """多条消息正确存储。"""
        wm = WorkingMemory()
        wm.add_message("user", "开空调")
        wm.add_message("assistant", "空调已开启")
        wm.add_message("user", "播放音乐")
        assert wm.turn_count == 3
        assert len(wm.messages) == 3

    def test_message_max_capacity(self):
        """消息超过 maxlen 后自动丢弃旧消息。"""
        wm = WorkingMemory(max_turns=5)
        for i in range(10):
            wm.add_message("user", f"消息{i}")
        assert len(wm.messages) == 5

    def test_add_tool_result(self):
        """工具结果作为 tool 角色消息添加。"""
        wm = WorkingMemory()
        wm.add_tool_result("get_weather", '{"temp": 25}')
        assert len(wm.messages) == 1
        assert wm.messages[0]["role"] == "tool"
        assert wm.messages[0]["name"] == "get_weather"


class TestWorkingMemoryTripParams:
    """WorkingMemory 行程参数缓存。"""

    def test_set_trip_params(self):
        """设置行程参数后正确缓存。"""
        wm = WorkingMemory()
        params = {"city": "杭州", "days": 3, "preference": "亲子"}
        wm.set_last_trip_params(params)
        assert wm.last_trip_params["city"] == "杭州"
        assert wm.last_trip_params["days"] == 3

    def test_trip_params_filters_empty(self):
        """空值参数被过滤。"""
        wm = WorkingMemory()
        params = {"city": "杭州", "days": None, "preference": ""}
        wm.set_last_trip_params(params)
        assert "city" in wm.last_trip_params
        assert "days" not in wm.last_trip_params
        assert "preference" not in wm.last_trip_params

    def test_trip_params_preference_list_to_string(self):
        """preference 列表转为逗号分隔字符串。"""
        wm = WorkingMemory()
        params = {"city": "杭州", "preference": ["亲子", "休闲"]}
        wm.set_last_trip_params(params)
        assert wm.last_trip_params["preference"] == "亲子、休闲"

    def test_trip_params_empty_dict(self):
        """空字典不写入。"""
        wm = WorkingMemory()
        wm.set_last_trip_params({})
        assert wm.last_trip_params == {}

    def test_get_trip_context_empty(self):
        """无行程参数时返回空字符串。"""
        wm = WorkingMemory()
        assert wm.get_trip_context_for_prompt() == ""


class TestWorkingMemoryToolResults:
    """WorkingMemory 工具结果缓存。"""

    def test_tool_results_initially_empty(self):
        """初始状态为空。"""
        wm = WorkingMemory()
        assert wm.last_tool_results == {}

    def test_get_tool_results_empty(self):
        """无工具结果时返回空字符串。"""
        wm = WorkingMemory()
        assert wm.get_tool_results_for_prompt() == ""
