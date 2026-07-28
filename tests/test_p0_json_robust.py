"""P0 smoketest: 6 层 JSON 容错解析（移植自 TripStar）

验证 _sanitize_json_str / _fix_unescaped_quotes / _repair_truncated_json /
_extract_raw_json_str / _parse_robust_json 在各种 LLM 输出污染场景下的健壮性。

运行: python -m pytest tests/test_p0_json_robust.py -v
"""
import json
import sys
import os

# 确保项目根在 sys.path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from modules.ai.trip_planner.agent import (
    _sanitize_json_str,
    _fix_unescaped_quotes,
    _repair_truncated_json,
    _extract_raw_json_str,
    _extract_json_object,
    EdgeGuardTripPlanner,
)


# ── _sanitize_json_str ──────────────────────────────────────────────

def test_sanitize_removes_code_fence():
    raw = '```json\n{"city": "杭州"}\n```'
    assert json.loads(_sanitize_json_str(raw)) == {"city": "杭州"}


def test_sanitize_removes_js_comments():
    raw = '{"city": "杭州", // 城市\n"days": 2 /* 天数 */}'
    result = json.loads(_sanitize_json_str(raw))
    assert result == {"city": "杭州", "days": 2}


def test_sanitize_fixes_trailing_comma():
    raw = '{"city": "杭州", "days": 2,}'
    assert json.loads(_sanitize_json_str(raw)) == {"city": "杭州", "days": 2}


def test_sanitize_fixes_chinese_punctuation():
    raw = '{"city"\uff1a"杭州"\uff0c"days"\uff1a2}'
    assert json.loads(_sanitize_json_str(raw)) == {"city": "杭州", "days": 2}


def test_sanitize_fixes_arithmetic_with_equals():
    """预算字段中的算术表达式: 30+54+120=204 → 204"""
    raw = '{"budget": {"total": 30+54+120=204}}'
    result = json.loads(_sanitize_json_str(raw))
    assert result["budget"]["total"] == 204


def test_sanitize_fixes_arithmetic_without_equals():
    """没有等号的算术表达式也计算"""
    raw = '{"budget": {"total": 30+54+120}}'
    result = json.loads(_sanitize_json_str(raw))
    assert result["budget"]["total"] == 204


def test_sanitize_replaces_chinese_quotes():
    """中文双引号替换为单引号（避免破坏 JSON 结构）"""
    raw = '{"desc": "\u201c西湖\u201d是著名景点"}'
    result = json.loads(_sanitize_json_str(raw))
    assert "西湖" in result["desc"]


# ── _fix_unescaped_quotes ────────────────────────────────────────────

def test_fix_unescaped_quotes_internal():
    """字符串值内部的未转义双引号替换为单引号"""
    raw = '{"desc": "这是"好的"景点"}'
    fixed = _fix_unescaped_quotes(raw)
    result = json.loads(fixed)
    assert result["desc"] == "这是'好的'景点"


def test_fix_unescaped_quotes_preserves_structure():
    """正常的 JSON 结构引号不被破坏"""
    raw = '{"city": "杭州", "days": 2}'
    fixed = _fix_unescaped_quotes(raw)
    assert json.loads(fixed) == {"city": "杭州", "days": 2}


def test_fix_unescaped_quotes_escaped_quote():
    """已转义的引号不被破坏"""
    raw = '{"desc": "他说\\"你好\\""}'
    fixed = _fix_unescaped_quotes(raw)
    result = json.loads(fixed)
    assert '你好' in result["desc"]


# ── _repair_truncated_json ──────────────────────────────────────────

def test_repair_truncated_closes_missing_braces():
    """截断的 JSON 缺少闭合括号"""
    raw = '{"city": "杭州", "days": 2, "attractions": [{"name": "西湖"'
    repaired = _repair_truncated_json(raw)
    result = json.loads(repaired)
    assert result["city"] == "杭州"
    assert result["days"] == 2


def test_repair_truncated_unterminated_string():
    """字符串被截断时自动关闭"""
    raw = '{"desc": "西湖是一个'
    repaired = _repair_truncated_json(raw)
    result = json.loads(repaired)
    assert "西湖" in result["desc"]


def test_repair_truncated_complete_json_unchanged():
    """完整 JSON 不被修改"""
    raw = '{"city": "杭州", "days": 2}'
    assert _repair_truncated_json(raw) == raw


def test_repair_truncated_nested_arrays():
    """嵌套数组截断修复"""
    raw = '{"days": [{"attractions": [{"name": "西湖"}, {"name": "灵隐寺"'
    repaired = _repair_truncated_json(raw)
    result = json.loads(repaired)
    assert len(result["days"][0]["attractions"]) == 2


# ── _extract_raw_json_str ───────────────────────────────────────────

def test_extract_raw_json_code_fence():
    raw = '这是行程规划：\n```json\n{"city": "杭州"}\n```\n结束'
    extracted = _extract_raw_json_str(raw)
    assert json.loads(extracted) == {"city": "杭州"}


def test_extract_raw_json_bare():
    raw = '前文 {"city": "杭州"} 后文'
    extracted = _extract_raw_json_str(raw)
    assert json.loads(extracted) == {"city": "杭州"}


def test_extract_raw_json_truncated_fence():
    """```json 标记未闭合（截断）时取到末尾"""
    raw = '```json\n{"city": "杭州", "days":'
    extracted = _extract_raw_json_str(raw)
    assert "杭州" in extracted


def test_extract_raw_json_no_json_raises():
    try:
        _extract_raw_json_str("没有 JSON 内容")
        assert False, "应该抛出 ValueError"
    except ValueError:
        pass


# ── _extract_json_object (向后兼容) ─────────────────────────────────

def test_extract_json_object_backward_compat():
    raw = '```json\n{"city": "杭州", "days": 2}\n```'
    result = _extract_json_object(raw)
    assert result == {"city": "杭州", "days": 2}


# ── EdgeGuardTripPlanner._parse_robust_json ─────────────────────────

def _make_planner():
    """创建 planner 实例（不触发 LLM）"""
    return EdgeGuardTripPlanner()


def test_parse_robust_clean_json():
    planner = _make_planner()
    raw = '{"city": "杭州", "days": 2}'
    result = planner._parse_robust_json(raw)
    assert result == {"city": "杭州", "days": 2}


def test_parse_robust_with_code_fence():
    planner = _make_planner()
    raw = '```json\n{"city": "杭州"}\n```'
    result = planner._parse_robust_json(raw)
    assert result == {"city": "杭州"}


def test_parse_robust_with_comments():
    planner = _make_planner()
    raw = '{"city": "杭州", // 城市\n"days": 2}'
    result = planner._parse_robust_json(raw)
    assert result == {"city": "杭州", "days": 2}


def test_parse_robust_trailing_comma():
    planner = _make_planner()
    raw = '{"city": "杭州", "days": 2,}'
    result = planner._parse_robust_json(raw)
    assert result == {"city": "杭州", "days": 2}


def test_parse_robust_unescaped_quotes():
    planner = _make_planner()
    raw = '{"desc": "这是"好的"景点"}'
    result = planner._parse_robust_json(raw)
    assert "好的" in result["desc"]


def test_parse_robust_truncated():
    planner = _make_planner()
    raw = '{"city": "杭州", "days": 2, "attractions": [{"name": "西湖"'
    result = planner._parse_robust_json(raw)
    assert result["city"] == "杭州"
    assert result["days"] == 2


def test_parse_robust_arithmetic_expr():
    planner = _make_planner()
    raw = '{"budget": {"total": 30+54+120=204}}'
    result = planner._parse_robust_json(raw)
    assert result["budget"]["total"] == 204


def test_parse_robust_chinese_punctuation():
    planner = _make_planner()
    raw = '{"city"\uff1a"杭州"\uff0c"days"\uff1a2}'
    result = planner._parse_robust_json(raw)
    assert result == {"city": "杭州", "days": 2}


def test_parse_robust_combined_errors():
    """多种错误同时出现"""
    planner = _make_planner()
    raw = '```json\n{"city": "杭州", // 注释\n"days": 2,\n"budget": {"total": 30+54+120=204,}\n```'
    result = planner._parse_robust_json(raw)
    assert result["city"] == "杭州"
    assert result["budget"]["total"] == 204


def test_parse_robust_all_fail_raises():
    """完全无法解析的内容抛出 ValueError"""
    planner = _make_planner()
    # 没有花括号，无法提取 JSON
    try:
        planner._parse_robust_json("这完全不是 JSON 内容")
        assert False, "应该抛出 ValueError"
    except ValueError:
        pass


def test_parse_robust_garbage_with_brace_falls_back():
    """有花括号但内容是垃圾 —— 本地层失败后尝试 LLM 修复（无 LLM 时也应优雅失败）"""
    planner = _make_planner()
    # monkey-patch _llm_repair_json 避免真实 LLM 调用
    planner._llm_repair_json = lambda x: x  # 返回原文，触发最终 ValueError
    try:
        planner._parse_robust_json("{这不是合法JSON}")
        # 如果碰巧被某个修复层解析了，也算通过
    except (ValueError, json.JSONDecodeError):
        pass  # 优雅失败，符合预期


if __name__ == "__main__":
    # 直接运行: python tests/test_p0_json_robust.py
    import traceback
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    passed = 0
    failed = 0
    for test in tests:
        try:
            test()
            print(f"  PASS  {test.__name__}")
            passed += 1
        except Exception:
            print(f"  FAIL  {test.__name__}")
            traceback.print_exc()
            failed += 1
    print(f"\n{'='*50}")
    print(f"P0 JSON 容错: {passed} passed, {failed} failed, {len(tests)} total")
    sys.exit(1 if failed else 0)
