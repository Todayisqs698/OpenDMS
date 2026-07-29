"""
测试手势映射表完整性 — 无外部依赖。

覆盖：
  - GESTURE_MAP 映射数量
  - 关键手势映射正确性
  - 映射值有效性
"""
import pytest
from modules.ai.local_decision_engine import GESTURE_MAP, _handle_gesture


class TestGestureMap:
    """手势映射表完整性。"""

    def test_gesture_count(self):
        """至少 15 种手势映射。"""
        assert len(GESTURE_MAP) >= 15

    def test_ac_gestures(self):
        """空调手势正确映射。"""
        assert GESTURE_MAP["Open"] == "TurnOnAC"
        assert GESTURE_MAP["open_ac"] == "TurnOnAC"
        assert GESTURE_MAP["Close"] == "TurnOffAC"
        assert GESTURE_MAP["close_ac"] == "TurnOffAC"

    def test_confirm_gestures(self):
        """确认手势正确映射。"""
        assert GESTURE_MAP["Thumbs Up"] == "confirm"
        assert GESTURE_MAP["thumbs_up"] == "confirm"
        assert GESTURE_MAP["OK"] == "confirm"

    def test_cancel_gestures(self):
        """取消手势正确映射。"""
        assert GESTURE_MAP["Thumbs Down"] == "cancel"
        assert GESTURE_MAP["thumbs_down"] == "cancel"
        assert GESTURE_MAP["Peace"] == "cancel"

    def test_unique_action_count(self):
        """至少 10 种独立 action_code。"""
        unique_actions = set(GESTURE_MAP.values())
        assert len(unique_actions) >= 10

    def test_all_values_are_strings(self):
        """所有映射值都是字符串。"""
        for gesture, action in GESTURE_MAP.items():
            assert isinstance(action, str), f"Action for '{gesture}' is not a string"


class TestHandleGesture:
    """_handle_gesture 函数行为。"""

    def test_valid_gesture(self):
        """有效手势返回正确 action_code。"""
        result = _handle_gesture({"gesture": "Open", "confidence": 0.9})
        assert result["action_code"] == "TurnOnAC"
        assert result["source"] == "local"

    def test_low_confidence(self):
        """低置信度返回 unknown。"""
        result = _handle_gesture({"gesture": "Open", "confidence": 0.1})
        assert result["action_code"] == "unknown"

    def test_unknown_gesture(self):
        """未知手势返回 unknown。"""
        result = _handle_gesture({"gesture": "UnknownGesture", "confidence": 0.9})
        assert result["action_code"] == "unknown"

    def test_empty_gesture(self):
        """空手势名返回 unknown。"""
        result = _handle_gesture({"gesture": "", "confidence": 0.9})
        assert result["action_code"] == "unknown"
