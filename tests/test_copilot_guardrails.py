from types import SimpleNamespace

from modules.ai.intent_guard import BLOCK, CLARIFY, EXECUTE, guard_intent, normalize_intent
from modules.ai.intention_agent import rule_based_intent_detection
from modules.ai.local_decision_engine import decide_locally


NON_EXECUTABLE_UTTERANCES = [
    "好的",
    "不去了",
    "别导航了",
    "暂停这个话题",
    "这个路线是什么意思",
    "你觉得怎么样",
    "地址是什么",
    "刚才那个是什么",
    "先不要播放",
    "我只是问问",
]


def _intent(category, params=None, confidence=0.9, agent="recommend_agent"):
    return SimpleNamespace(
        id="i1",
        category=category,
        agent=agent,
        priority=5,
        description=category,
        params=params or {},
        confidence=confidence,
        metadata={},
    )


def test_local_decision_does_not_execute_ambiguous_utterances():
    for text in NON_EXECUTABLE_UTTERANCES:
        result = decide_locally({"trigger": "speech", "data": {"text": text}})
        assert result.get("decision_mode") != EXECUTE


def test_explicit_local_commands_still_execute():
    cases = {
        "打开空调": "TurnOnAC",
        "关闭空调": "TurnOffAC",
        "播放音乐": "PlayMusic",
        "下一首": "next_track",
    }
    for text, action in cases.items():
        result = decide_locally({"trigger": "speech", "data": {"text": text}})
        assert result.get("decision_mode") == EXECUTE
        assert result.get("action_code") == action


def test_navigation_rule_requires_destination_slot():
    weak = rule_based_intent_detection("这个路线是什么意思")
    strong = rule_based_intent_detection("导航到北京天安门")

    assert all(not (i.category == "navigation" and i.params.get("destination")) for i in weak)
    assert any(i.category == "navigation" and i.params.get("destination") == "北京天安门" for i in strong)


def test_guard_clarifies_missing_required_slots():
    decision = guard_intent(normalize_intent(_intent("navigation", {})), {"severity": "normal"})

    assert decision.mode == CLARIFY
    assert decision.missing_slots == ["destination"]


def test_guard_blocks_distracting_tasks_when_dangerous():
    decision = guard_intent(
        normalize_intent(_intent("music_control", {"action": "play"}, agent="control_executor")),
        {"severity": "dangerous"},
    )

    assert decision.mode == BLOCK
