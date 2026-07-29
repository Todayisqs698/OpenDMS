"""
测试本地决策引擎 — 无外部依赖。

覆盖：
  - SPEECH_KEYWORD_MAP 关键词映射完整性
  - _handle_speech 正则模式匹配
  - decide_locally 分发逻辑
  - 告警阈值函数（crowd / absence / fatigue / head / gaze）
"""
import pytest
from modules.ai.local_decision_engine import (
    SPEECH_KEYWORD_MAP,
    GESTURE_MAP,
    decide_locally,
    _handle_speech,
    check_crowd,
    check_absence,
    check_fatigue,
    check_head_deviation,
    check_gaze_deviation,
    ALERT_CATEGORIES,
)


# ═══════════════════════════════════════════
# SPEECH_KEYWORD_MAP 完整性测试
# ═══════════════════════════════════════════

class TestSpeechKeywordMap:
    """语音关键词映射表完整性。"""

    def test_keyword_count(self):
        """至少 20 条关键词映射。"""
        assert len(SPEECH_KEYWORD_MAP) >= 20

    def test_ac_keywords(self):
        """空调关键词正确映射。"""
        assert SPEECH_KEYWORD_MAP["开空调"] == "TurnOnAC"
        assert SPEECH_KEYWORD_MAP["关空调"] == "TurnOffAC"
        assert SPEECH_KEYWORD_MAP["太热"] == "TurnOnAC"
        assert SPEECH_KEYWORD_MAP["太冷"] == "TurnOffAC"

    def test_music_keywords(self):
        """音乐关键词正确映射。"""
        assert SPEECH_KEYWORD_MAP["放音乐"] == "PlayMusic"
        assert SPEECH_KEYWORD_MAP["下一首"] == "next_track"
        assert SPEECH_KEYWORD_MAP["暂停"] == "StopMusic"

    def test_navigation_keywords(self):
        """导航关键词正确映射。"""
        assert SPEECH_KEYWORD_MAP["导航"] == "Navigate"

    def test_safety_keywords(self):
        """安全确认关键词正确映射。"""
        assert SPEECH_KEYWORD_MAP["我在看路"] == "NoticeRoad"
        assert SPEECH_KEYWORD_MAP["已注意"] == "NoticeRoad"

    def test_all_mappings_have_valid_action(self):
        """所有映射值都是有效的 action_code。"""
        valid_actions = {
            "TurnOnAC", "TurnOffAC", "temp_up", "temp_down",
            "PlayMusic", "StopMusic", "next_track", "previous_track",
            "volume_up", "volume_down",
            "Navigate", "window_open", "window_close",
            "light_on", "light_off", "NoticeRoad", "knowledge_qa",
        }
        for keyword, action in SPEECH_KEYWORD_MAP.items():
            assert action in valid_actions, f"Invalid action '{action}' for keyword '{keyword}'"


# ═══════════════════════════════════════════
# _handle_speech 正则模式测试
# ═══════════════════════════════════════════

class TestHandleSpeech:
    """语音命令正则匹配。"""

    def test_turn_on_ac_short(self):
        """短指令"开空调"正确匹配。"""
        result = _handle_speech({"text": "开空调"})
        assert result["action_code"] == "TurnOnAC"
        assert result["source"] == "local"

    def test_turn_on_ac_full(self):
        """完整指令"打开空调"正确匹配。"""
        result = _handle_speech({"text": "打开空调"})
        assert result["action_code"] == "TurnOnAC"

    def test_turn_off_ac(self):
        """关空调指令匹配。"""
        result = _handle_speech({"text": "关空调"})
        assert result["action_code"] == "TurnOffAC"

    def test_turn_off_ac_variant(self):
        """关空调变体"关闭空调"。"""
        result = _handle_speech({"text": "关闭空调"})
        assert result["action_code"] == "TurnOffAC"

    def test_play_music(self):
        """播放音乐指令。"""
        result = _handle_speech({"text": "播放音乐"})
        assert result["action_code"] == "PlayMusic"

    def test_play_music_with_artist(self):
        """带歌手名的播放指令。"""
        result = _handle_speech({"text": "播放周杰伦的歌"})
        assert result["action_code"] == "PlayMusic"

    def test_stop_music(self):
        """暂停音乐指令。"""
        result = _handle_speech({"text": "暂停音乐"})
        assert result["action_code"] == "StopMusic"

    def test_next_track(self):
        """下一首指令。"""
        result = _handle_speech({"text": "下一首"})
        assert result["action_code"] == "next_track"

    def test_temp_up(self):
        """调高温度指令。"""
        result = _handle_speech({"text": "调高温度"})
        assert result["action_code"] == "temp_up"

    def test_temp_down(self):
        """调低温度指令。"""
        result = _handle_speech({"text": "调低温度"})
        assert result["action_code"] == "temp_down"

    def test_volume_up(self):
        """音量加大指令。"""
        result = _handle_speech({"text": "音量加大"})
        assert result["action_code"] == "volume_up"

    def test_volume_down(self):
        """音量减小指令。"""
        result = _handle_speech({"text": "音量减小"})
        assert result["action_code"] == "volume_down"

    def test_window_open(self):
        """打开车窗指令。"""
        result = _handle_speech({"text": "打开车窗"})
        assert result["action_code"] == "window_open"

    def test_window_close(self):
        """关闭车窗指令。"""
        result = _handle_speech({"text": "关闭车窗"})
        assert result["action_code"] == "window_close"

    def test_light_on(self):
        """开灯指令。"""
        result = _handle_speech({"text": "打开灯"})
        assert result["action_code"] == "light_on"

    def test_light_off(self):
        """关灯指令。"""
        result = _handle_speech({"text": "关闭灯"})
        assert result["action_code"] == "light_off"

    def test_notice_road(self):
        """安全确认指令。"""
        result = _handle_speech({"text": "我在看路"})
        assert result["action_code"] == "NoticeRoad"

    def test_empty_text(self):
        """空文本返回 unknown。"""
        result = _handle_speech({"text": ""})
        assert result["action_code"] == "unknown"

    def test_unmatched_text(self):
        """未匹配文本返回 semantic_query。"""
        result = _handle_speech({"text": "今天天气怎么样"})
        assert result["action_code"] == "semantic_query"

    def test_weak_keyword(self):
        """弱关键词返回 CLARIFY 模式。"""
        result = _handle_speech({"text": "导航去天津"})
        assert result["action_code"] == "semantic_query"
        assert result.get("decision_mode") == "CLARIFY"


# ═══════════════════════════════════════════
# decide_locally 分发逻辑测试
# ═══════════════════════════════════════════

class TestDecideLocally:
    """decide_locally 主入口分发。"""

    def test_speech_trigger(self):
        """speech 触发器正确分发。"""
        result = decide_locally({"trigger": "speech", "data": {"text": "开空调"}})
        assert result["action_code"] == "TurnOnAC"
        assert result["source"] == "local"

    def test_gesture_trigger(self):
        """gesture 触发器正确分发。"""
        result = decide_locally({"trigger": "gesture", "data": {"gesture": "Open", "confidence": 0.9}})
        assert result["action_code"] == "TurnOnAC"

    def test_unknown_trigger(self):
        """未知触发器返回 unknown。"""
        result = decide_locally({"trigger": "unknown", "data": {}})
        assert result["action_code"] == "unknown"


# ═══════════════════════════════════════════
# 告警阈值测试
# ═══════════════════════════════════════════

class TestAlertThresholds:
    """5 类告警的阈值判断。"""

    def test_crowd_normal(self):
        """单人不触发多人告警。"""
        result = check_crowd(duration=1.0, face_count=1)
        assert result["action_code"] == "normal"

    def test_crowd_triggered(self):
        """多人触发告警。"""
        result = check_crowd(duration=1.0, face_count=2)
        assert result["action_code"] != "normal"
        assert result["alert_category"] == "crowd"

    def test_absence_normal(self):
        """短时间离开不触发。"""
        result = check_absence(duration=1.0)
        assert result["action_code"] == "normal"

    def test_absence_triggered(self):
        """长时间离开触发。"""
        result = check_absence(duration=3.0)
        assert result["action_code"] != "normal"
        assert result["alert_category"] == "absence"

    def test_fatigue_normal(self):
        """低疲劳值不触发。"""
        result = check_fatigue(duration=0.5)
        assert result["action_code"] == "normal"

    def test_fatigue_triggered(self):
        """高疲劳值触发。"""
        result = check_fatigue(duration=2.0)
        assert result["action_code"] != "normal"
        assert result["alert_category"] == "fatigue"

    def test_head_deviation_center(self):
        """头部居中不触发。"""
        result = check_head_deviation("center", 5.0)
        assert result["action_code"] == "normal"

    def test_head_deviation_triggered(self):
        """头部偏离触发。"""
        result = check_head_deviation("left", 3.0)
        assert result["action_code"] != "normal"
        assert result["head_direction"] == "left"

    def test_gaze_deviation_center(self):
        """视线居中不触发。"""
        result = check_gaze_deviation("center", 5.0)
        assert result["action_code"] == "normal"

    def test_gaze_deviation_triggered(self):
        """视线偏离触发。"""
        result = check_gaze_deviation("right", 3.0)
        assert result["action_code"] != "normal"
        assert result["gaze_direction"] == "right"


# ═══════════════════════════════════════════
# ALERT_CATEGORIES 结构测试
# ═══════════════════════════════════════════

class TestAlertCategories:
    """告警类别配置完整性。"""

    def test_five_categories(self):
        """5 类告警都存在。"""
        expected = {"crowd", "absence", "fatigue", "head", "gaze"}
        assert set(ALERT_CATEGORIES.keys()) == expected

    def test_each_category_has_three_levels(self):
        """每类告警都有 mild/moderate/severe 三级。"""
        for cat_name, cat in ALERT_CATEGORIES.items():
            levels = set(cat["severities"].keys())
            assert levels == {"mild", "moderate", "severe"}, \
                f"{cat_name} missing severity levels: {levels}"

    def test_threshold_ordering(self):
        """阈值递增：mild < moderate < severe。"""
        for cat_name, cat in ALERT_CATEGORIES.items():
            mild = cat["severities"]["mild"]["threshold"]
            moderate = cat["severities"]["moderate"]["threshold"]
            severe = cat["severities"]["severe"]["threshold"]
            assert mild <= moderate <= severe, \
                f"{cat_name} thresholds not ordered: {mild} <= {moderate} <= {severe}"
