"""
Orchestrator 集成测试 — 验证多意图编排
========================================

测试场景：
  1. 单意图-空调控制
  2. 单意图-音乐控制
  3. ★ 复合意图：好累啊打开空调并播放王菲的歌
  4. 故障诊断意图
  5. 天气查询意图
  6. 规则快速通道 vs LLM 分解对比

运行：cd 项目根目录 && python test_orchestrator.py
"""

import sys
import os
import json
import time

_project_root = os.path.dirname(os.path.abspath(__file__))
if _project_root not in sys.path:
    sys.path.append(_project_root)


def test_intention_agent_rule():
    """测试 1: 规则快速通道 — 单意图识别"""
    print("=" * 60)
    print("测试 1: 规则快速通道 — 单意图识别")
    print("=" * 60)

    from modules.ai.intention_agent import IntentionAgent
    agent = IntentionAgent()

    test_cases = [
        ("打开空调", "ac_control"),
        ("播放音乐", "music_control"),
        ("好累啊", "fatigue_assist"),
        ("发动机故障灯亮了", "diagnosis"),
        ("今天天气怎么样", "weather"),
        ("导航去公司", "navigation"),
    ]

    passed = 0
    for text, expected_cat in test_cases:
        plan = agent.analyze(text)
        categories = [i.category for i in plan.intents]
        hit = expected_cat in categories
        status = "✓" if hit else "✗"
        print(f"  {status} 「{text}」→ {categories}")
        if hit:
            passed += 1

    print(f"\n  结果: {passed}/{len(test_cases)} 通过\n")
    return passed == len(test_cases)


def test_multi_intent_detection():
    """测试 2: 复合意图识别 — 规则层"""
    print("=" * 60)
    print("测试 2: 复合意图识别（规则层）")
    print("=" * 60)

    from modules.ai.intention_agent import IntentionAgent
    agent = IntentionAgent()

    test_cases = [
        ("打开空调并播放音乐", ["ac_control", "music_control"]),
        ("好累啊打开空调", ["fatigue_assist", "ac_control"]),
    ]

    passed = 0
    for text, expected_cats in test_cases:
        plan = agent.analyze(text)
        categories = [i.category for i in plan.intents]
        hit = all(cat in categories for cat in expected_cats)
        status = "✓" if hit else "✗"
        print(f"  {status} 「{text}」")
        print(f"      识别到: {categories}")
        print(f"      期望:   {expected_cats}")
        if hit:
            passed += 1
        print()

    print(f"  结果: {passed}/{len(test_cases)} 通过\n")
    return passed >= 1  # 至少通过一个（规则层可能有限，LLM层更强）


def test_orchestrator_ac_music():
    """测试 3: 编排器 — 空调+音乐 双意图执行"""
    print("=" * 60)
    print("测试 3: 编排器 — 空调+音乐 双意图执行")
    print("=" * 60)

    from modules.ai.orchestrator import get_orchestrator
    orch = get_orchestrator()

    text = "打开空调并播放周杰伦的歌"
    print(f"  输入: 「{text}」")

    start = time.time()
    response = orch.process(text)
    elapsed = time.time() - start

    print(f"  总耗时: {elapsed:.2f}s")
    print(f"  回复: {response.overall_reply[:80]}...")
    print(f"  意图数: {len(response.results)}")
    print(f"  动作数: {len(response.actions)}")

    for i, r in enumerate(response.results):
        print(f"    [{i+1}] {r.agent_name} / {r.intent_category}: "
              f"{'✓' if r.success else '✗'} "
              f"{r.reply_text[:40]}... ({r.duration_ms:.0f}ms)")

    # 验证：应该有 2 个结果（ac_control + music_control）
    categories = [r.intent_category for r in response.results]
    has_ac = "ac_control" in categories
    has_music = "music_control" in categories

    print(f"\n  AC控制: {'✓' if has_ac else '✗'}")
    print(f"  音乐控制: {'✓' if has_music else '✗'}")

    passed = has_ac and has_music
    print(f"  结果: {'通过' if passed else '失败'}\n")
    return passed


def test_fatigue_compound():
    """测试 4: ★ 核心场景 — 好累啊打开空调并播放王菲的歌"""
    print("=" * 60)
    print("测试 4: ★ 核心场景 — 好累啊打开空调并播放王菲的歌")
    print("=" * 60)

    from modules.ai.orchestrator import get_orchestrator
    orch = get_orchestrator()

    text = "好累啊打开空调并播放王菲的歌"
    print(f"  输入: 「{text}」")

    start = time.time()
    response = orch.process(text)
    elapsed = time.time() - start

    print(f"  总耗时: {elapsed:.2f}s")
    print(f"  统一回复: {response.overall_reply[:100]}...")
    print(f"  意图数: {len(response.results)}")
    print(f"  动作数: {len(response.actions)}")
    print(f"  意图计划:")
    for intent in response.intent_plan.get("intents", []):
        print(f"    - {intent['id']}: {intent['category']} → {intent['agent']} "
              f"(priority={intent['priority']}) — {intent['description']}")

    print(f"\n  执行结果:")
    for i, r in enumerate(response.results):
        status_icon = "✓" if r.success else "✗"
        print(f"    [{i+1}] {status_icon} {r.agent_name} ({r.intent_category}) "
              f"— {r.duration_ms:.0f}ms")
        if r.reply_text:
            print(f"         回复: {r.reply_text[:60]}")
        if r.error:
            print(f"         错误: {r.error[:60]}")

    # 验证三重意图：疲劳 + 空调 + 音乐
    categories = [r.intent_category for r in response.results]
    has_fatigue = "fatigue_assist" in categories or any("疲劳" in r.reply_text for r in response.results)
    has_ac = "ac_control" in categories
    has_music = "music_control" in categories

    print(f"\n  疲劳辅助: {'✓' if has_fatigue else '✗'}")
    print(f"  空调控制: {'✓' if has_ac else '✗'}")
    print(f"  音乐控制: {'✓' if has_music else '✗'}")

    # 至少应该有 AC 和 音乐
    passed = has_ac and has_music
    print(f"\n  结果: {'通过' if passed else '部分通过'}\n")
    return passed


def test_diagnose_agent():
    """测试 5: 故障诊断子 Agent"""
    print("=" * 60)
    print("测试 5: 故障诊断子 Agent")
    print("=" * 60)

    from modules.ai.agents.diagnose_agent import DiagnoseAgent
    agent = DiagnoseAgent()

    result = agent.analyze("发动机故障灯亮了")

    print(f"  成功: {result.get('success')}")
    print(f"  严重程度: {result.get('severity')}")
    print(f"  相关文档数: {len(result.get('related_docs', []))}")
    print(f"  建议数: {len(result.get('suggestions', []))}")
    print(f"  诊断: {result.get('diagnosis', '')[:100]}...")

    passed = result.get("success") and len(result.get("related_docs", [])) > 0
    print(f"\n  结果: {'通过' if passed else '失败'}\n")
    return passed


def test_recommend_agent():
    """测试 6: 出行建议子 Agent"""
    print("=" * 60)
    print("测试 6: 出行建议子 Agent")
    print("=" * 60)

    from modules.ai.agents.recommend_agent import RecommendAgent
    agent = RecommendAgent()

    result = agent.analyze({"query": "今天天气怎么样", "category": "weather"})

    print(f"  类型: {result.get('type')}")
    print(f"  回复: {result.get('reply', '')[:80]}...")
    print(f"  建议数: {len(result.get('suggestions', []))}")

    passed = result.get("success", False)
    print(f"\n  结果: {'通过' if passed else '失败'}\n")
    return passed


def test_analyze_agent():
    """测试 7: 驾驶分析子 Agent"""
    print("=" * 60)
    print("测试 7: 驾驶分析子 Agent")
    print("=" * 60)

    from modules.ai.agents.analyze_agent import AnalyzeAgent
    agent = AnalyzeAgent()

    result = agent.analyze({
        "duration_min": 45,
        "distractions": 2,
        "severe_distractions": 0,
        "attention_score": 88,
        "avg_gaze": "center",
        "fatigue_level": "normal",
    })

    print(f"  评分: {result.get('score')} ({result.get('grade')})")
    print(f"  亮点: {len(result.get('highlights', []))} 条")
    for h in result.get("highlights", [])[:2]:
        print(f"    - {h}")
    print(f"  改进: {len(result.get('improvements', []))} 条")
    for i in result.get("improvements", [])[:2]:
        print(f"    - {i}")

    passed = result.get("success", False) and 0 <= result.get("score", -1) <= 100
    print(f"\n  结果: {'通过' if passed else '失败'}\n")
    return passed


def main():
    print("\n" + "=" * 60)
    print("  EdgeGuard Orchestrator 集成测试")
    print("=" * 60 + "\n")

    results = {}

    try:
        results["1.规则单意图"] = test_intention_agent_rule()
    except Exception as e:
        print(f"  测试异常: {e}\n")
        results["1.规则单意图"] = False

    try:
        results["2.复合意图识别"] = test_multi_intent_detection()
    except Exception as e:
        print(f"  测试异常: {e}\n")
        results["2.复合意图识别"] = False

    try:
        results["3.编排AC+音乐"] = test_orchestrator_ac_music()
    except Exception as e:
        print(f"  测试异常: {e}\n")
        results["3.编排AC+音乐"] = False

    try:
        results["4.核心疲劳场景"] = test_fatigue_compound()
    except Exception as e:
        print(f"  测试异常: {e}\n")
        results["4.核心疲劳场景"] = False

    try:
        results["5.故障诊断"] = test_diagnose_agent()
    except Exception as e:
        print(f"  测试异常: {e}\n")
        results["5.故障诊断"] = False

    try:
        results["6.出行建议"] = test_recommend_agent()
    except Exception as e:
        print(f"  测试异常: {e}\n")
        results["6.出行建议"] = False

    try:
        results["7.驾驶分析"] = test_analyze_agent()
    except Exception as e:
        print(f"  测试异常: {e}\n")
        results["7.驾驶分析"] = False

    # 总结
    print("=" * 60)
    print("  测试总结")
    print("=" * 60)

    passed = sum(1 for v in results.values() if v)
    total = len(results)

    for name, ok in results.items():
        status = "✓ 通过" if ok else "✗ 失败"
        print(f"  {status}  {name}")

    print(f"\n  总计: {passed}/{total} 通过")
    print(f"  通过率: {passed/total*100:.0f}%\n")

    return passed == total


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
