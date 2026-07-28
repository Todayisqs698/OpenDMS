import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import modules.ai.agent_graph as agent_graph


def test_tool_node_blocks_tools_outside_allowed_list(monkeypatch):
    called = {"execute_tool": False}

    def fake_execute_tool(name, args):
        called["execute_tool"] = True
        return {"success": True}

    monkeypatch.setattr(agent_graph, "execute_tool", fake_execute_tool)

    state = {
        "allowed_tools": [
            {
                "type": "function",
                "function": {"name": "speak", "parameters": {"type": "object"}},
            }
        ],
        "messages": [
            {
                "role": "assistant",
                "tool_calls": [
                    {
                        "id": "call_1",
                        "type": "function",
                        "function": {
                            "name": "control_music",
                            "arguments": json.dumps({"command": "play"}),
                        },
                    }
                ],
            }
        ],
        "_tool_cache": {},
    }

    result = agent_graph.tool_node(state)
    tool_msg = result["messages"][0]

    assert called["execute_tool"] is False
    assert tool_msg["name"] == "control_music"
    assert tool_msg["_raw_result"]["success"] is False
    assert "not allowed" in tool_msg["_raw_result"]["error"]
