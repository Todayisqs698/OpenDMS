from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_agent_chat_defaults_to_tool_calling_source():
    source = (ROOT / "backend" / "main.py").read_text(encoding="utf-8")

    assert 'os.getenv("AGENT_CHAT_MODE", "tool_calling")' in source
    assert 'if mode != "orchestrator":' in source
    assert "return _run_tool_calling_agent_sync" in source
    assert "def _run_orchestrator_agent_sync" in source


def test_voice_process_defaults_to_tool_calling_source():
    source = (ROOT / "backend" / "main.py").read_text(encoding="utf-8")

    assert 'os.getenv("VOICE_PROCESS_MODE", "tool_calling")' in source
    assert 'route": "tool_calling"' in source
