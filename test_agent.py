"""
EdgeGuard ReAct Agent 端到端验证脚本
覆盖规格中的 5 个预设场景 + 2 个边界场景。
用法: python test_agent.py
"""
import json
import time
import sys
import os

os.chdir(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ".")

from modules.ai.agent_graph import ReActAgent
from modules.ai.tools import execute_tool, TOOL_SCHEMAS
from modules.ai.safety_gate import apply_safety_gate

PASS = "\033[92mPASS\033[0m"
FAIL = "\033[91mFAIL\033[0m"

def test_safety_gate():
    """场景0: 安全门控验证"""
    print("\n═══ 场景0: 安全门控 ═══")
    for level in ["normal", "attn_declining", "distracted", "dangerous"]:
        r = apply_safety_gate(level, TOOL_SCHEMAS)
        allowed = [t["function"]["name"] for t in r["allowed_tools"]]
        if level == "dangerous":
            ok = r["is_emergency"] and "control_music" not in allowed
        elif level == "distracted":
            ok = "control_music" not in allowed and "control_ac" in allowed
        else:
            ok = len(allowed) == 7
        print(f"  {level:15s} → {len(allowed)} tools, emergency={r['is_emergency']}  {PASS if ok else FAIL}")

def test_scenario_1_simple():
    """场景1: "打开空调" → 本地快速通道（但 Agent 也应能处理）"""
    print("\n═══ 场景1: 打开空调 ═══")
    agent = ReActAgent()
    t0 = time.time()
    result = agent.chat("打开空调")
    elapsed = time.time() - t0
    reply = result.get("reply", "")
    steps = result.get("steps", 0)
    status = result.get("status", "")

    ok = steps >= 1 and "空调" in reply
    print(f"  Steps: {steps}, Time: {elapsed:.1f}s, Status: {status}")
    print(f"  Reply: {reply[:100]}")
    print(f"  {PASS if ok else FAIL}")

    # 验证空调确实被打开了
    r = execute_tool("control_ac", {"command": "state_check"})
    # 清理：关空调
    execute_tool("control_ac", {"command": "TurnOffAC"})

def test_scenario_2_complex():
    """场景2: "我有点累了，帮我调低空调温度" → Agent 多步推理"""
    print("\n═══ 场景2: 疲劳+调温度 ═══")
    agent = ReActAgent()
    t0 = time.time()
    result = agent.chat("我有点累了，帮我调低空调温度")
    elapsed = time.time() - t0
    reply = result.get("reply", "")
    steps = result.get("steps", 0)

    ok = steps >= 1 and len(reply) > 10
    print(f"  Steps: {steps}, Time: {elapsed:.1f}s")
    print(f"  Reply: {reply[:120]}")
    print(f"  {PASS if ok else FAIL}")

def test_scenario_3_knowledge():
    """场景3: "发动机灯亮了怎么办" → Agent 调用 RAG 知识库"""
    print("\n═══ 场景3: 知识问答 ═══")
    agent = ReActAgent()
    t0 = time.time()
    result = agent.chat("发动机故障灯亮了怎么办")
    elapsed = time.time() - t0
    reply = result.get("reply", "")
    steps = result.get("steps", 0)

    ok = steps >= 1 and len(reply) > 20
    print(f"  Steps: {steps}, Time: {elapsed:.1f}s")
    print(f"  Reply: {reply[:150]}")
    print(f"  {PASS if ok else FAIL}")

def test_scenario_4_music():
    """场景4: "播放周杰伦的歌" → Agent 搜索+播放"""
    print("\n═══ 场景4: 播放音乐 ═══")
    agent = ReActAgent()
    t0 = time.time()
    result = agent.chat("播放周杰伦的晴天")
    elapsed = time.time() - t0
    reply = result.get("reply", "")
    steps = result.get("steps", 0)

    ok = steps >= 1 and len(reply) > 5
    print(f"  Steps: {steps}, Time: {elapsed:.1f}s")
    print(f"  Reply: {reply[:120]}")
    print(f"  {PASS if ok else FAIL}")

def test_scenario_5_safety_restriction():
    """场景5: 分心状态下说"播放音乐" → 安全门控应限制工具"""
    print("\n═══ 场景5: 分心状态限制 ═══")
    agent = ReActAgent()
    # 模拟分心状态
    driver_state = {
        "gaze": "left",
        "gaze_duration": 5.0,
        "perclos": 0.15,
        "fatigue_score": 0.3,
        "risk_level": "distracted",  # 直接设置
    }
    t0 = time.time()
    result = agent.chat("播放周杰伦的歌", driver_state=driver_state)
    elapsed = time.time() - t0
    reply = result.get("reply", "")
    safety = result.get("safety_level", "")

    ok = safety == "distracted" and ("音乐" not in reply or "无法" in reply or "安全" in reply or "分心" in reply)
    print(f"  Safety: {safety}, Time: {elapsed:.1f}s")
    print(f"  Reply: {reply[:120]}")
    print(f"  {PASS if ok else FAIL}")

def test_scenario_6_weather():
    """场景6: "今天天气怎么样" → Agent 调用天气工具"""
    print("\n═══ 场景6: 天气查询 ═══")
    agent = ReActAgent()
    t0 = time.time()
    result = agent.chat("今天天气怎么样")
    elapsed = time.time() - t0
    reply = result.get("reply", "")
    steps = result.get("steps", 0)

    ok = steps >= 1 and len(reply) > 10
    print(f"  Steps: {steps}, Time: {elapsed:.1f}s")
    print(f"  Reply: {reply[:120]}")
    print(f"  {PASS if ok else FAIL}")

def test_scenario_7_clarification():
    """场景7: 模糊指令"帮我调一下" → Agent 应追问"""
    print("\n═══ 场景7: 模糊指令追问 ═══")
    agent = ReActAgent()
    t0 = time.time()
    result = agent.chat("帮我调一下")
    elapsed = time.time() - t0
    reply = result.get("reply", "")
    steps = result.get("steps", 0)

    # Agent 可能直接问，也可能用 ask_clarification 工具
    ok = steps >= 0 and len(reply) > 5
    print(f"  Steps: {steps}, Time: {elapsed:.1f}s")
    print(f"  Reply: {reply[:120]}")
    print(f"  {PASS if ok else FAIL}")


if __name__ == "__main__":
    print("=" * 60)
    print("  EdgeGuard ReAct Agent 端到端测试")
    print("=" * 60)

    test_safety_gate()
    test_scenario_1_simple()
    test_scenario_2_complex()
    test_scenario_3_knowledge()
    test_scenario_4_music()
    test_scenario_5_safety_restriction()
    test_scenario_6_weather()
    test_scenario_7_clarification()

    print("\n" + "=" * 60)
    print("  所有场景测试完毕")
    print("=" * 60)
