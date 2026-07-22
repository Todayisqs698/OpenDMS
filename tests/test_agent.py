"""
EdgeGuard Agent 验证脚本
=======================
验证 ReActAgent 的 6 大能力：
  1. 闲聊（无工具调用）
  2. 工具调用（LLM function calling）
  3. 安全门控（分心/疲劳拦截）
  4. 多步推理（复杂任务分解）
  5. 知识检索（RAG 故障查询）
  6. 记忆系统（偏好加载 + 会话持久化）

用法: py -3.13 tests/test_agent.py
"""
import sys
import os
import io
import json
import time

# 修复 Windows 编码
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

# 项目根加入路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from modules.ai.agent_graph import ReActAgent


PASS = 0
FAIL = 0


def check(name: str, condition: bool, detail: str = ""):
    global PASS, FAIL
    if condition:
        PASS += 1
        print(f"  ✅ {name}")
    else:
        FAIL += 1
        print(f"  ❌ {name}  -- {detail}")


def section(title: str):
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}")


# ═══════════════════════════════════════════════════════════
#  测试 1：闲聊 — 无需工具调用
# ═══════════════════════════════════════════════════════════

def test_chitchat():
    section("1. 闲聊 — LLM 直接回复，不走工具")

    agent = ReActAgent()
    result = agent.chat("你好，介绍一下你自己", driver_state={"gaze": "center"})

    check("返回 reply 非空", bool(result.get("reply")))
    check("steps = 1（不需要工具）", result.get("steps") == 1)
    check("status = success", result.get("status") == "success")
    check("safety_level = normal", result.get("safety_level") == "normal")

    print(f"    回复: {result.get('reply', '')[:120]}...")
    agent.close()


# ═══════════════════════════════════════════════════════════
#  测试 2：工具调用 — 空调控制
# ═══════════════════════════════════════════════════════════

def test_tool_ac():
    section("2. 工具调用 — 空调控制（LLM 自主调用 control_ac）")

    agent = ReActAgent()
    result = agent.chat("把空调调到22度", driver_state={"gaze": "center"})

    check("返回 reply 非空", bool(result.get("reply")))
    check("steps >= 2（推理 + 工具调用 + 观察）", result.get("steps", 0) >= 2)
    check("status = success", result.get("status") == "success")

    print(f"    回复: {result.get('reply', '')[:120]}...")
    print(f"    步数: {result.get('steps')}")
    agent.close()


# ═══════════════════════════════════════════════════════════
#  测试 3：音乐控制
# ═══════════════════════════════════════════════════════════

def test_tool_music():
    section("3. 工具调用 — 音乐搜索 + 播放")

    agent = ReActAgent()
    result = agent.chat("我想听周杰伦的歌", driver_state={"gaze": "center"})

    check("返回 reply 非空", bool(result.get("reply")))
    check("status = success", result.get("status") == "success")

    print(f"    回复: {result.get('reply', '')[:120]}...")
    print(f"    步数: {result.get('steps')}")
    agent.close()


# ═══════════════════════════════════════════════════════════
#  测试 4：安全门控 — distracted 状态
# ═══════════════════════════════════════════════════════════

def test_safety_distracted():
    section("4. 安全门控 — 分心状态下拦截娱乐指令")

    agent = ReActAgent()
    # 模拟分心驾驶
    driver = {
        "gaze": "left",
        "gaze_duration": 5.0,
        "head_pose": {"pitch": 25, "yaw": 15, "roll": 0},
        "perclos": 0.1,
        "fatigue_score": 10,
    }
    result = agent.chat("播放音乐", driver_state=driver)

    safety_ok = result.get("safety_level") in ("distracted", "dangerous")
    check(f"safety_level 非 normal（当前={result.get('safety_level')}）", safety_ok)

    reply = result.get("reply", "")
    # 检查回复是否包含安全提示
    blocked = any(kw in reply for kw in ["安全", "分心", "道路", "暂时", "注意"])
    check("回复包含安全提示", blocked, f"回复前80字: {reply[:80]}")

    print(f"    安全等级: {result.get('safety_level')}")
    print(f"    回复: {reply[:150]}...")
    agent.close()


# ═══════════════════════════════════════════════════════════
#  测试 5：安全门控 — dangerous 短路
# ═══════════════════════════════════════════════════════════

def test_safety_dangerous():
    section("5. 安全门控 — dangerous 级别直接短路告警")

    agent = ReActAgent()
    driver = {
        "gaze": "right",
        "gaze_duration": 8.0,
        "head_pose": {"pitch": 35, "yaw": 30, "roll": 5},
        "perclos": 0.7,
        "fatigue_score": 85,
    }
    result = agent.chat("开空调", driver_state=driver)

    check("status = emergency", result.get("status") == "emergency")
    check("safety_level = dangerous", result.get("safety_level") == "dangerous")

    print(f"    状态: {result.get('status')}")
    print(f"    安全等级: {result.get('safety_level')}")
    print(f"    回复: {result.get('reply', '')[:150]}...")
    agent.close()


# ═══════════════════════════════════════════════════════════
#  测试 6：知识检索（RAG）
# ═══════════════════════════════════════════════════════════

def test_rag_knowledge():
    section("6. 知识检索 — 车辆故障 RAG 查询")

    agent = ReActAgent()
    result = agent.chat("发动机故障灯亮了怎么办", driver_state={"gaze": "center"})

    check("返回 reply 非空", bool(result.get("reply")))
    check("status = success", result.get("status") == "success")
    # RAG 查询应该包含关键词
    has_fault_info = any(kw in result.get("reply", "") for kw in ["故障", "发动机", "检测", "建议", "检查", "停车"])
    check("回复包含故障相关信息", has_fault_info)

    print(f"    回复: {result.get('reply', '')[:200]}...")
    print(f"    步数: {result.get('steps')}")
    agent.close()


# ═══════════════════════════════════════════════════════════
#  测试 7：多步推理 — 复合任务
# ═══════════════════════════════════════════════════════════

def test_multi_step():
    section("7. 多步推理 — 复合任务（调温度 + 问天气）")

    agent = ReActAgent()
    result = agent.chat("外面天气怎么样？如果太热就帮我把空调打开",
                       driver_state={"gaze": "center"})

    check("返回 reply 非空", bool(result.get("reply")))
    check("status = success", result.get("status") == "success")
    # 多步任务至少 2 步（查天气 + 空调控制）
    is_multi = result.get("steps", 0) >= 2
    check(f"steps >= 2（实际={result.get('steps')}）", is_multi)

    print(f"    回复: {result.get('reply', '')[:200]}...")
    print(f"    步数: {result.get('steps')}")
    agent.close()


# ═══════════════════════════════════════════════════════════
#  测试 8：记忆系统
# ═══════════════════════════════════════════════════════════

def test_memory():
    section("8. 记忆系统 — 会话持久化")

    agent = ReActAgent()

    # 设置偏好
    agent.memory.long_term.set_pref("ac_temp", 24)
    agent.memory.long_term.set_pref("music_artist", "周杰伦")

    # 读取回来
    prefs = agent.memory.long_term.get_all_preferences()
    check("偏好写入后能读取", prefs.get("ac_temp") == 24 and prefs.get("music_artist") == "周杰伦")

    # 短期记忆
    agent.memory.working.add_message("user", "我喜欢听轻音乐")
    msgs = agent.memory.working.get_messages_for_llm()
    check("短期记忆可写入读取", len(msgs) > 0)

    print(f"    偏好: {prefs}")
    agent.close()


# ═══════════════════════════════════════════════════════════
#  测试 9：工具注册表完整性
# ═══════════════════════════════════════════════════════════

def test_tools_registry():
    section("9. 工具注册表完整性")

    from modules.ai.tools import TOOL_SCHEMAS, TOOL_EXECUTOR

    expected = {"speak", "control_ac", "control_music", "search_knowledge",
                "get_weather", "alert_driver", "ask_clarification"}

    schema_names = {t["function"]["name"] for t in TOOL_SCHEMAS}
    check(f"TOOL_SCHEMAS 有 {len(schema_names)} 个工具（期望 7）", len(schema_names) == 7)
    check("Schema 与 Executor 名称一致", schema_names == set(TOOL_EXECUTOR.keys()))

    # 每个工具都有 function.name、description、parameters
    for t in TOOL_SCHEMAS:
        fn = t.get("function", {})
        ok = bool(fn.get("name")) and bool(fn.get("description")) and bool(fn.get("parameters"))
        check(f"  工具 {fn.get('name', '?')} schema 完整", ok)

    # 每个 executor 都能调通（不传参验证至少不崩溃）
    for name, func in TOOL_EXECUTOR.items():
        try:
            # 只验证函数存在且可调用，不进实际逻辑
            check(f"  执行器 {name} 可调用", callable(func))
        except Exception as e:
            check(f"  执行器 {name} 可调用", False, str(e))


# ═══════════════════════════════════════════════════════════
#  测试 10：边界条件
# ═══════════════════════════════════════════════════════════

def test_edge_cases():
    section("10. 边界条件")

    agent = ReActAgent()

    # 空输入
    result = agent.chat("", driver_state={"gaze": "center"})
    check("空输入不崩溃", isinstance(result, dict))

    # 超长输入
    long_text = "请帮我把空调打开" * 20
    result = agent.chat(long_text, driver_state={"gaze": "center"})
    check("超长输入不崩溃", isinstance(result, dict))
    check("超长输入有回复", bool(result.get("reply")))

    # 无 driver_state
    result = agent.chat("你好", driver_state=None)
    check("driver_state=None 不崩溃", result.get("status") in ("success", "normal", "emergency"))

    # 最大步数限制
    result = agent.chat("帮我同时处理打开空调、播放音乐、搜索导航去天安门、查天气、调低温度",
                       driver_state={"gaze": "center"})
    check("步数不超过 max_steps(5)", result.get("steps", 0) <= 5)

    agent.close()


# ═══════════════════════════════════════════════════════════
#  主入口
# ═══════════════════════════════════════════════════════════

if __name__ == "__main__":
    print("=" * 60)
    print("  EdgeGuard ReActAgent 验证套件")
    print(f"  时间: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)

    TOTAL_START = time.time()

    tests = [
        test_chitchat,
        test_tool_ac,
        test_tool_music,
        test_safety_distracted,
        test_safety_dangerous,
        test_rag_knowledge,
        test_multi_step,
        test_memory,
        test_tools_registry,
        test_edge_cases,
    ]

    for test_fn in tests:
        try:
            test_fn()
        except Exception as e:
            FAIL += 1
            print(f"  ❌ {test_fn.__name__} 异常: {e}")
            import traceback
            traceback.print_exc()

    elapsed = time.time() - TOTAL_START

    print(f"\n{'='*60}")
    print(f"  结果: {PASS} 通过 / {PASS + FAIL} 总计 ({elapsed:.1f}s)")
    if FAIL == 0:
        print(f"  🎉 全部通过！Agent 符合预期。")
    else:
        print(f"  ⚠️  {FAIL} 个失败，请检查。")
    print(f"{'='*60}")
