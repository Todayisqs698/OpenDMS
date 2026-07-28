from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_system_prompt_requires_real_tool_results():
    content = (ROOT / "modules" / "ai" / "prompts" / "agent_templates.py").read_text(encoding="utf-8")

    assert "必须等待工具真实返回结果后" in content
    assert "允许操作的能力完全以 tools 列表为准" in content
    assert "不要向用户输出隐式思维链" in content
    assert "工具返回 success/ok" in content


def test_fallback_prompt_has_same_execution_guardrails():
    content = (ROOT / "modules" / "ai" / "agent_graph.py").read_text(encoding="utf-8")

    assert "必须等待工具真实返回结果后" in content
    assert "允许操作的能力完全以 tools 列表为准" in content
