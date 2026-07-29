"""
测试 14 个工具 Schema 完整性 — 无外部依赖。

覆盖：
  - TOOL_SCHEMAS 结构完整性
  - 工具名唯一性
  - 关键工具存在
  - 参数 Schema 格式
  - TOOL_EXECUTOR 映射一致性
"""
import pytest
from modules.ai.tools import TOOL_SCHEMAS, TOOL_EXECUTOR, execute_tool


class TestToolSchemasStructure:
    """工具 Schema 结构验证。"""

    def test_tool_count(self):
        """至少 14 个工具。"""
        assert len(TOOL_SCHEMAS) >= 14

    def test_all_tools_have_required_fields(self):
        """每个工具都有 name, description, parameters。"""
        for tool in TOOL_SCHEMAS:
            assert "type" in tool
            assert tool["type"] == "function"
            func = tool["function"]
            assert "name" in func
            assert "description" in func
            assert "parameters" in func
            assert func["parameters"]["type"] == "object"

    def test_tool_names_unique(self):
        """工具名不重复。"""
        names = [t["function"]["name"] for t in TOOL_SCHEMAS]
        assert len(names) == len(set(names)), f"Duplicate tool names: {names}"

    def test_descriptions_not_empty(self):
        """每个工具都有非空描述。"""
        for tool in TOOL_SCHEMAS:
            desc = tool["function"]["description"]
            assert isinstance(desc, str) and len(desc) > 0

    def test_parameters_have_properties(self):
        """每个工具的 parameters 都有 properties 字段。"""
        for tool in TOOL_SCHEMAS:
            params = tool["function"]["parameters"]
            assert "properties" in params
            assert isinstance(params["properties"], dict)


class TestCriticalToolsExist:
    """关键工具不能丢失。"""

    def test_critical_tools_present(self):
        """7 个核心工具必须存在。"""
        names = {t["function"]["name"] for t in TOOL_SCHEMAS}
        required = {"speak", "control_ac", "control_music", "search_knowledge",
                    "alert_driver", "start_navigation", "plan_trip"}
        assert required.issubset(names), f"Missing tools: {required - names}"

    def test_all_tool_names(self):
        """验证 14 个工具全部存在。"""
        names = {t["function"]["name"] for t in TOOL_SCHEMAS}
        expected = {
            "speak", "control_ac", "control_music", "search_knowledge",
            "get_weather", "get_weather_forecast", "alert_driver",
            "ask_clarification", "search_attractions", "search_hotels",
            "start_navigation", "plan_trip", "save_location", "get_saved_location",
        }
        assert expected.issubset(names), f"Missing tools: {expected - names}"


class TestToolExecutorConsistency:
    """TOOL_EXECUTOR 与 TOOL_SCHEMAS 一致性。"""

    def test_executor_covers_all_schemas(self):
        """每个 Schema 中的工具都有对应的执行函数。"""
        schema_names = {t["function"]["name"] for t in TOOL_SCHEMAS}
        executor_names = set(TOOL_EXECUTOR.keys())
        assert schema_names == executor_names, \
            f"Mismatch: schema-only={schema_names - executor_names}, executor-only={executor_names - schema_names}"

    def test_executor_count(self):
        """执行器数量 >= 14。"""
        assert len(TOOL_EXECUTOR) >= 14

    def test_all_executors_are_callable(self):
        """所有执行器都是可调用对象。"""
        for name, func in TOOL_EXECUTOR.items():
            assert callable(func), f"Tool '{name}' executor is not callable"

    def test_execute_unknown_tool(self):
        """执行未知工具返回错误。"""
        result = execute_tool("nonexistent_tool", {})
        assert result["success"] is False
        assert "error" in result
