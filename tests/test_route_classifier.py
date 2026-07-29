"""
route_classifier.py 单元测试 — 路由分类器 + VETO 安全前置门

覆盖:
  - is_dangerous_driver_state(): 多字段危险状态检测
  - classify_route(): 危险 → multi，正常 → quick/react
  - 边界值测试 (fatigue_score=79/80, perclos=0.49/0.50)
  - 异常输入容错 (None, 空dict, 字符串型数值)
  - VETO 场景: 疲劳驾驶 + "播放音乐" → multi (非 quick)
"""
import pytest

from modules.ai.route_classifier import (
    is_dangerous_driver_state,
    classify_route,
    QUICK_PATTERNS,
    MULTI_INTENT_CONJUNCTIONS,
)


# ═══════════════════════════════════════════════════════════
#  is_dangerous_driver_state
# ═══════════════════════════════════════════════════════════

class TestIsDangerousDriverState:
    """测试危险状态检测的各种输入"""

    def test_severe_severity(self):
        """摄像头产生的 severity='severe' → dangerous"""
        assert is_dangerous_driver_state({"severity": "severe"})

    def test_dangerous_severity(self):
        """SafetyAgent 产生的 severity='dangerous' → dangerous"""
        assert is_dangerous_driver_state({"severity": "dangerous"})

    def test_moderate_severity_not_dangerous(self):
        assert not is_dangerous_driver_state({"severity": "moderate"})

    def test_normal_severity_not_dangerous(self):
        assert not is_dangerous_driver_state({"severity": "normal"})

    def test_high_risk(self):
        assert is_dangerous_driver_state({"risk": "high"})

    def test_dangerous_risk_level(self):
        assert is_dangerous_driver_state({"risk_level": "dangerous"})

    def test_danger_fatigue_level(self):
        """摄像头 fatigue_level='danger' → dangerous"""
        assert is_dangerous_driver_state({"fatigue_level": "danger"})

    def test_warning_fatigue_level_not_dangerous(self):
        assert not is_dangerous_driver_state({"fatigue_level": "warning"})

    def test_fatigue_score_threshold(self):
        """fatigue_score >= 80 → dangerous"""
        assert is_dangerous_driver_state({"fatigue_score": 80})
        assert is_dangerous_driver_state({"fatigue_score": 90})
        assert is_dangerous_driver_state({"fatigue_score": 100})

    def test_fatigue_score_below_threshold(self):
        """fatigue_score < 80 → not dangerous"""
        assert not is_dangerous_driver_state({"fatigue_score": 79})
        assert not is_dangerous_driver_state({"fatigue_score": 0})

    def test_perclos_threshold(self):
        """perclos >= 0.5 → dangerous"""
        assert is_dangerous_driver_state({"perclos": 0.5})
        assert is_dangerous_driver_state({"perclos": 0.8})

    def test_perclos_below_threshold(self):
        assert not is_dangerous_driver_state({"perclos": 0.49})
        assert not is_dangerous_driver_state({"perclos": 0.1})

    def test_empty_dict(self):
        assert not is_dangerous_driver_state({})

    def test_none(self):
        assert not is_dangerous_driver_state(None)

    def test_invalid_fatigue_score_string(self):
        """字符串型 fatigue_score 不崩溃，返回 False"""
        assert not is_dangerous_driver_state({"fatigue_score": "abc"})

    def test_invalid_perclos_string(self):
        assert not is_dangerous_driver_state({"perclos": "xyz"})

    def test_combined_dangerous_fields(self):
        """多个危险字段同时存在"""
        assert is_dangerous_driver_state({
            "severity": "severe",
            "fatigue_score": 95,
            "fatigue_level": "danger",
            "perclos": 0.7,
        })

    def test_combined_normal_fields(self):
        assert not is_dangerous_driver_state({
            "severity": "normal",
            "fatigue_score": 10,
            "fatigue_level": "normal",
            "perclos": 0.05,
        })


# ═══════════════════════════════════════════════════════════
#  classify_route
# ═══════════════════════════════════════════════════════════

DANGEROUS = {
    "fatigue_score": 90, "fatigue_level": "danger",
    "perclos": 0.55, "severity": "severe", "gaze": "center",
}
NORMAL = {
    "fatigue_score": 10, "fatigue_level": "normal",
    "perclos": 0.05, "severity": "normal", "gaze": "center",
}


class TestClassifyRouteDangerous:
    """危险状态下的路由分类"""

    def test_dangerous_music_routes_to_multi(self):
        """疲劳驾驶 + '播放音乐' → multi（非 quick）"""
        route = classify_route("播放音乐", DANGEROUS)
        assert route == "multi"

    def test_dangerous_ac_routes_to_multi(self):
        route = classify_route("开空调", DANGEROUS)
        assert route == "multi"

    def test_dangerous_chitchat_routes_to_multi(self):
        route = classify_route("你好", DANGEROUS)
        assert route == "multi"

    def test_dangerous_diagnosis_routes_to_multi(self):
        route = classify_route("发动机故障怎么办", DANGEROUS)
        assert route == "multi"

    def test_dangerous_multi_intent_routes_to_multi(self):
        """危险 + 多意图 → multi"""
        route = classify_route("开空调然后播放音乐", DANGEROUS)
        assert route == "multi"

    def test_fatigue_score_only_routes_to_multi(self):
        """仅 fatigue_score=85（无 severity）→ multi"""
        route = classify_route("播放音乐", {"fatigue_score": 85})
        assert route == "multi"

    def test_perclos_only_routes_to_multi(self):
        """仅 perclos=0.6 → multi"""
        route = classify_route("播放音乐", {"perclos": 0.6})
        assert route == "multi"


class TestClassifyRouteNormal:
    """正常状态下的路由分类"""

    def test_normal_music_routes_to_quick(self):
        route = classify_route("播放音乐", NORMAL)
        assert route == "quick"

    def test_normal_ac_routes_to_quick(self):
        route = classify_route("开空调", NORMAL)
        assert route == "quick"

    def test_normal_diagnosis_routes_to_react(self):
        route = classify_route("发动机故障怎么办", NORMAL)
        assert route == "react"

    def test_normal_multi_intent_routes_to_multi(self):
        route = classify_route("开空调然后播放音乐", NORMAL)
        assert route == "multi"

    def test_normal_chitchat_routes_to_react(self):
        route = classify_route("你好", NORMAL)
        assert route == "react"


class TestClassifyRouteEdgeCases:
    def test_empty_text(self):
        assert classify_route("", NORMAL) == "react"

    def test_none_text(self):
        assert classify_route(None, NORMAL) == "react"

    def test_no_driver_state(self):
        """无 driver_state → 按 quick/react 分类"""
        route = classify_route("播放音乐", None)
        assert route == "quick"

    def test_empty_driver_state(self):
        route = classify_route("播放音乐", {})
        assert route == "quick"


# ═══════════════════════════════════════════════════════════
#  VETO 关键场景：Slide 18 Demo
# ═══════════════════════════════════════════════════════════

class TestVetoScenario:
    """答辩 Demo Slide 18 关键场景：疲劳驾驶 + 播放音乐 → VETO"""

    def test_fatigued_driver_music_blocked(self):
        """疲劳驾驶状态下说'播放音乐' → 路由到 multi（走 SafetyAgent VETO）"""
        route = classify_route("播放音乐", {
            "fatigue_score": 90,
            "fatigue_level": "danger",
            "perclos": 0.55,
            "severity": "severe",
        })
        assert route == "multi"
        assert route != "quick"  # 关键：不被 quick 路径绕过

    def test_severe_severity_music_blocked(self):
        """仅有 severity='severe'（无 fatigue_score）→ multi"""
        route = classify_route("播放音乐", {"severity": "severe"})
        assert route == "multi"

    def test_normal_driver_music_allowed(self):
        """正常驾驶状态下说'播放音乐' → quick（正常执行）"""
        route = classify_route("播放音乐", {
            "fatigue_score": 5,
            "fatigue_level": "normal",
            "severity": "normal",
        })
        assert route == "quick"
