"""
EdgeGuard 多 Agent 架构 — 全路径端到端测试

覆盖 7 条核心路径：
  P1: 规则快速通道 → control_executor (明确指令)
  P2: 规则快速通道 → diagnose_agent (故障诊断)
  P3: 规则快速通道 → recommend_agent (天气/导航)
  P4: LLM 分解 → react_agent (疲劳+控制 复合意图)
  P5: LLM 分解 → diagnose_agent (疑问句式)
  P6: 安全短路 → dangerous → 直接告警
  P7: 降级兜底 → 无匹配规则 → LLM失败 → react_agent
  P8: 全流程 orchestrator.process()

用法: python test_agent_architecture.py
"""
import json
import time
import sys
import os


os.chdir(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ".")

from modules.ai.intention_agent import IntentionAgent, rule_based_intent_detection
from modules.ai.orchestrator import AgentOrchestrator, ControlExecutor

OK = "\033[92m✓\033[0m"
FAIL = "\033[91m✗\033[0m"
HEAD = "\033[96m"
RST = "\033[0m"

total_tests = 0
passed_tests = 0

def check(name, condition, detail=""):
    global total_tests, passed_tests
    total_tests += 1
    status = OK if condition else FAIL
    detail_str = f" — {detail}" if detail else ""
    print(f"  {status} {name}{detail_str}")
    if condition:
        passed_tests += 1
    return condition


# ═══════════════════════════════════════════════════════════
#  P1: 规则快速通道 — 明确单步指令
# ═══════════════════════════════════════════════════════════

def test_p1_explicit_commands():
    print(f"\n{HEAD}═══ P1: 规则快速通道 → control_executor ═══{RST}")
    agent = IntentionAgent()

    cases = [
        ("打开空调", "ac_control", "control_executor"),
        ("温度调到25度", "ac_control", "control_executor"),
        ("关闭空调", "ac_control", "control_executor"),
        ("播放周杰伦的歌", "music_control", "control_executor"),
        ("暂停音乐", "music_control", "control_executor"),
        ("下一首", "music_control", "control_executor"),
    ]

    for text, exp_category, exp_agent in cases:
        intents = rule_based_intent_detection(text)
        matched = intents and intents[0].category == exp_category and intents[0].agent == exp_agent
        detail = f"'{text}' → {intents[0].category}→{intents[0].agent}" if intents else f"'{text}' → NO MATCH"
        check(f"规则匹配 {exp_category}", matched, detail)

    # Rule-based should NOT trigger LLM
    for text in ["打开空调", "温度调到25度"]:
        intents = rule_based_intent_detection(text)
        needs = agent._needs_llm(text, intents)
        check(f"'{text}' 不触发LLM", not needs, f"needs_llm={needs}")


# ═══════════════════════════════════════════════════════════
#  P2: 规则匹配 + LLM 增强 — 故障诊断
# ═══════════════════════════════════════════════════════════

def test_p2_diagnosis_path():
    print(f"\n{HEAD}═══ P2: 故障诊断 → diagnose_agent ═══{RST}")
    agent = IntentionAgent()

    cases = [
        ("发动机故障灯亮了", True),
        ("胎压报警怎么办", True),
        ("刹车有异响怎么回事", True),
        ("仪表盘上有个灯一直闪", True),
    ]

    for text, expect_llm in cases:
        intents = rule_based_intent_detection(text)
        has_diagnosis = any(i.category == "diagnosis" for i in intents)
        needs = agent._needs_llm(text, intents)
        check(f"'{text}' → diagnosis意图", has_diagnosis)
        check(f"'{text}' → 需要LLM增强", needs == expect_llm)

    # Full LLM flow for one case
    plan = agent.analyze("发动机故障灯亮了怎么办")
    has_diag_intent = any(i.agent == "diagnose_agent" for i in plan.intents)
    check("LLM分解 → 包含diagnose_agent", has_diag_intent,
          f"agents: {[i.agent for i in plan.intents]}")


# ═══════════════════════════════════════════════════════════
#  P3: 规则匹配 — 天气/导航 → recommend_agent
# ═══════════════════════════════════════════════════════════

def test_p3_recommend_path():
    print(f"\n{HEAD}═══ P3: 出行建议 → recommend_agent ═══{RST}")
    agent = IntentionAgent()

    cases = [
        ("今天天气怎么样", "weather", "recommend_agent"),
        ("导航到天津", "navigation", "recommend_agent"),
    ]

    for text, exp_cat, exp_agent in cases:
        intents = rule_based_intent_detection(text)
        matched = intents and intents[0].category == exp_cat
        detail = f"'{text}' → {intents[0].category if intents else 'NO MATCH'}"
        check(f"意图类别: {exp_cat}", matched, detail)


# ═══════════════════════════════════════════════════════════
#  P4: LLM 分解 — 疲劳 + 控制复合意图
# ═══════════════════════════════════════════════════════════

def test_p4_fatigue_composite():
    print(f"\n{HEAD}═══ P4: 复合意图 → LLM分解 → react_agent ═══{RST}")
    agent = IntentionAgent()

    # Rule detects fatigue + ac_control separately
    text = "我有点累了，帮我开空调放点音乐"
    rule_intents = rule_based_intent_detection(text)
    categories = [i.category for i in rule_intents]
    needs = agent._needs_llm(text, rule_intents)

    check("规则检测到疲劳+控制", "fatigue_assist" in categories,
          f"categories: {categories}")
    check("触发 LLM 分解", needs, f"has_fatigue + has_control → needs_llm=True")

    # Full LLM flow
    plan = agent.analyze(text)
    check("LLM 输出有效计划", len(plan.intents) >= 1,
          f"intents: {[(i.agent, i.description) for i in plan.intents]}")

    # Should prefer react_agent over individual control_executor
    has_react = any(i.agent == "react_agent" for i in plan.intents)
    print(f"  {' ' * 2} 调度: {[(i.agent, i.priority) for i in plan.intents]}")
    check("应使用react_agent统一编排", has_react,
          "LLM 合并为 fatigue_assist → react_agent")


# ═══════════════════════════════════════════════════════════
#  P5: 模糊输入 → LLM 分解
# ═══════════════════════════════════════════════════════════

def test_p5_vague_input():
    print(f"\n{HEAD}═══ P5: 模糊输入 → LLM分解 ═══{RST}")
    agent = IntentionAgent()

    cases = [
        ("帮我调一下", True, "模糊表达"),
        ("这个灯为什么亮了", True, "疑问句式"),
        ("好像有点问题", True, "模糊+疑问"),
        ("太热了", False, "明确情感表达（规则可匹配）"),
    ]

    for text, expect_llm, reason in cases:
        rule_intents = rule_based_intent_detection(text)
        needs = agent._needs_llm(text, rule_intents)
        check(f"'{text}' ({reason})", needs == expect_llm,
              f"rule: {[i.category for i in rule_intents]}, needs_llm={needs}")


# ═══════════════════════════════════════════════════════════
#  P6: 安全短路 — dangerous 级别直接告警
# ═══════════════════════════════════════════════════════════

def test_p6_safety_shortcut():
    print(f"\n{HEAD}═══ P6: 安全短路 — dangerous → 直接告警 ═══{RST}")

    orch = AgentOrchestrator()

    # 模拟危险状态
    dangerous_state = {
        "gaze": "left",
        "gaze_duration": 8.0,
        "fatigue_level": "danger",
        "severity": "dangerous",
    }

    result = orch.process("播放周杰伦的晴天", dangerous_state)
    check("安全短路触发", result.route == "safety_shortcut",
          f"route={result.route}")
    check("跳过其他Agent", not any(r.agent_name != "safety_gate" for r in result.results))
    check("仅返回告警文本",
          "注视前方" in result.overall_reply or "警告" in result.overall_reply,
          result.overall_reply[:60])

    # 正常状态 — 不触发短路
    normal_state = {"severity": "normal"}
    result2 = orch.process("播放周杰伦的晴天", normal_state)
    check("正常状态不触发安全短路", result2.route != "safety_shortcut",
          f"route={result2.route}")


# ═══════════════════════════════════════════════════════════
#  P7: 降级兜底 — 无匹配 → LLM失败 → react_agent
# ═══════════════════════════════════════════════════════════

def test_p7_fallback():
    print(f"\n{HEAD}═══ P7: 降级兜底 → react_agent ═══{RST}")
    agent = IntentionAgent()

    # 闲聊输入：规则匹配不到，也会进入LLM增强
    text = "今天心情不错"
    rule_intents = rule_based_intent_detection(text)
    check("闲聊无规则匹配", len(rule_intents) == 0,
          f"matched: {[i.category for i in rule_intents]}")

    # 全流程：最终兜底到 react_agent
    plan = agent.analyze(text)
    check("LLM 兜底生成计划", len(plan.intents) >= 1,
          f"intents: {[(i.agent, i.description) for i in plan.intents]}")
    has_chat = any(i.agent in ("react_agent",) for i in plan.intents)
    check("降级到 react_agent / chitchat", has_chat)

    # 空输入
    plan2 = agent.analyze("")
    check("空输入不崩溃", len(plan2.intents) == 0,
          f"summary: {plan2.overall_summary}")


# ═══════════════════════════════════════════════════════════
#  P8: 全流程 — orchestrator.process()
# ═══════════════════════════════════════════════════════════

def test_p8_full_orchestrator():
    print(f"\n{HEAD}═══ P8: 全流程 orchestrator.process() ═══{RST}")

    orch = AgentOrchestrator()
    driver_state = {"gaze": "center", "fatigue_level": "normal", "severity": "normal"}

    full_cases = [
        ("打开空调",
         ["control_executor"],
         "应走规则快速通道"),
        ("发动机故障灯亮了怎么办",
         ["diagnose_agent"],
         "故障诊断应走 diagnose_agent"),
        ("我有点累了帮我调低温度放首歌",
         ["react_agent"],
         "疲劳+复合控制应由 react_agent 统一编排"),
        ("帮我分析一下最近的驾驶表现",
         ["analyze_agent"],
         "分析请求走 analyze_agent"),
        ("今天天气怎么样",
         ["recommend_agent"],
         "天气查询走 recommend_agent"),
        ("你好",
         ["react_agent"],
         "闲聊走 react_agent"),
    ]

    for text, expected_agents, reason in full_cases:
        t_start = time.time()
        result = orch.process(text, driver_state)
        elapsed = round((time.time() - t_start) * 1000)

        if result.route == "safety_shortcut":
            check(f"'{text}': {reason}", False, "意外触发安全短路")
            continue

        agents_used = [r.agent_name for r in result.results]
        has_expected = any(ea in agents_used for ea in expected_agents)

        detail = f"agents={agents_used}, reply={result.overall_reply[:50]}..., {elapsed}ms"
        check(f"'{text}': {reason}", has_expected, detail)


# ═══════════════════════════════════════════════════════════
# 主入口
# ═══════════════════════════════════════════════════════════

if __name__ == "__main__":
    print("=" * 60)
    print("  EdgeGuard 多Agent架构 全路径测试")
    print("=" * 60)

    test_p1_explicit_commands()
    test_p2_diagnosis_path()
    test_p3_recommend_path()
    test_p4_fatigue_composite()
    test_p5_vague_input()
    test_p6_safety_shortcut()
    test_p7_fallback()
    test_p8_full_orchestrator()

    print(f"\n{'=' * 60}")
    print(f"  结果: {passed_tests}/{total_tests} 通过 "
          f"({'✓ 全部通过!' if passed_tests == total_tests else '✗ 有失败项'})")
    print(f"{'=' * 60}")
    sys.exit(0 if passed_tests == total_tests else 1)
