"""
Agent Graph -- LangGraph 风格的 ReAct Agent 循环
=================================================

实现基于 LangGraph StateGraph 的 ReAct 循环，包含感知、安全门控、
LLM 推理、工具调用和紧急告警等节点。

架构流程：
  START
    -> perceive (读取传感器状态 + 用户输入)
    -> safety_gate (评估 risk_level, 过滤工具白名单)
    -> [risk = dangerous?] -> safety_response -> END (紧急告警)
    -> agent_node (LLM 推理: 理解意图、决定是否调用工具)
    -> [需要工具?]
        |- 是 -> tool_node (执行工具调用) -> 回到 agent_node
        +- 否 -> respond -> END

降级方案：若 LangGraph 未安装，自动切换为手动 while 循环实现，
接口保持一致。
"""

import json
import logging
import operator
import time
import concurrent.futures
from typing import Optional, TypedDict
try:
    from typing import Annotated
except ImportError:
    from typing_extensions import Annotated

logger = logging.getLogger(__name__)

MAX_AGENT_MESSAGES = 8
MAX_TOOL_CONTENT_CHARS = 1200

# ================================================================
#  LangGraph 导入（降级处理）
# ================================================================

try:
    from langgraph.graph import StateGraph, END

    LANGGRAPH_AVAILABLE = True
except Exception as e:
    LANGGRAPH_AVAILABLE = False
    logger.warning("LangGraph 不可用，将使用手动循环实现 ReAct Agent: %s", e)

# ================================================================
#  项目内模块导入
# ================================================================

from modules.ai.tools import TOOL_SCHEMAS, execute_tool
from modules.ai.safety_gate import apply_safety_gate, get_risk_level_from_safety_agent
from modules.ai.memory import AgentMemory
from modules.ai.model_factory import get_model_for_agent

# ── 全局驾驶员状态机（由 app.py 摄像头循环实时更新）──
from modules.ai.driver_state_machine import DriverStateMachine

_driver_state_machine = DriverStateMachine()


def update_sensor_data(sensor_data: dict) -> str:
    """
    供 app.py 摄像头循环调用的传感器数据更新接口。
    将 7 维传感器数据喂入 DriverStateMachine，返回当前状态。
    """
    return _driver_state_machine.update(sensor_data)


def get_driver_state() -> dict:
    """获取当前驾驶员状态快照（供 API 端点查询）"""
    return {
        "state": _driver_state_machine.get_state(),
        "risk_score": _driver_state_machine.get_risk_score(),
        "trend": _driver_state_machine.get_trend(),
        "vector": _driver_state_machine.get_vector(),
    }

# ================================================================
#  状态定义
# ================================================================


class AgentState(TypedDict):
    """Agent 循环的完整状态，每个节点返回部分更新，由框架合并。"""
    messages: Annotated[list, operator.add]   # 完整对话历史（含 tool_calls 和 tool results）
    driver_state: dict        # 实时传感器数据
    safety_level: str         # normal / attn_declining / distracted / dangerous
    allowed_tools: list       # 安全门控过滤后的可用工具
    safety_prompt: str        # 安全级别对应的系统提示（由 safety_gate 注入）
    conversation_id: str      # 会话 ID
    user_preferences: dict    # 用户偏好
    final_response: str       # 最终回复文本
    task_complete: bool       # 任务是否完成
    step_count: int           # 当前循环步数
    max_steps: int            # 最大步数（默认 5）
    _tool_cache: dict         # 当前请求内的工具结果缓存


# ================================================================
#  System Prompt — 从 Prompt 模板库获取（兜底使用内嵌模板）
# ================================================================

# 内嵌兜底（模板库不可用时使用）
_FALLBACK_SYSTEM_PROMPT = """\
你是 DrivePilot/EdgeGuard 智能座舱中的执行型 AI Agent。

你的职责：
1. 理解用户通过键盘或语音输入的请求。
2. 在需要操作车机时调用提供的工具。
3. 必须等待工具真实返回结果后，才能告诉用户操作成功。
4. 一次请求可以连续调用多个工具；每一步都应根据上一步结果决定下一步。
5. 当请求依赖当前车况而上下文不足时，先调用能读取状态的工具；若当前 tools 列表没有该能力，应说明无法读取，不要猜测。
6. 对空调温度、风量和音量使用工具允许的范围，不得绕过参数限制。
7. 危险、模糊或项目尚未提供的车辆能力，不要编造已经完成；应说明当前无法执行。
8. 最终回复简洁、自然，明确说明完成了什么以及失败了什么。
9. 不要向用户输出隐式思维链。界面会单独展示安全的分析阶段、计划、工具调用和观察结果。

这是一个中控屏模拟项目。允许操作的能力完全以 tools 列表为准。

当前驾驶状态：
- 视线方向: {gaze}
- 安全等级: {safety_level}

{safety_prompt}

{user_context}

你可以使用以下工具来帮助驾驶员。请根据驾驶员的需求选择合适的工具。
如果不需要任何工具（只是闲聊或简单回答），直接回复即可。
只有工具返回 success/ok 且结果表明执行完成时，才能说“已完成/已开启/已播放”；工具失败、无数据或需要补充信息时，必须如实说明。

当用户提到旅行需求时，调用 plan_trip 工具生成结构化行程。
景点、天气、导航、行程的结果会自动展示在专属面板中，语音回复简要总结即可。
若上下文含"上次行程参数"，用户要求调整行程时必须复用该参数，只改用户提到的部分，不要从零询问城市/天数/偏好。
"""


# ================================================================
#  辅助函数
# ================================================================


def _build_system_prompt(state: dict, user_context: str = "") -> str:
    """根据当前状态构建 system prompt。优先从模板库获取，失败用内嵌兜底。"""
    driver_state = state.get("driver_state") or {}
    gaze = driver_state.get("gaze", "center")
    safety_level = state.get("safety_level", "normal")
    safety_prompt = state.get("safety_prompt", "")

    try:
        from modules.ai.prompts import render
        return render(
            "agent.system.base",
            gaze=gaze,
            safety_level=safety_level,
            safety_prompt=safety_prompt,
            user_context=user_context,
        )
    except Exception:
        return _FALLBACK_SYSTEM_PROMPT.format(
            gaze=gaze,
            safety_level=safety_level,
            safety_prompt=safety_prompt,
            user_context=user_context,
        )


def _build_user_context(user_preferences: dict) -> str:
    """从用户偏好构建上下文文本。"""
    if not user_preferences:
        return ""
    pref_lines = [f"  - {k}: {v}" for k, v in user_preferences.items()]
    return "用户偏好:\n" + "\n".join(pref_lines)


def _clean_message_for_llm(msg: dict) -> dict:
    """Keep only OpenAI-compatible message fields and trim oversized tool payloads."""
    clean = {"role": msg["role"]}
    if msg.get("content") is not None:
        content = msg["content"]
        if msg.get("role") == "tool" and isinstance(content, str):
            content = content[:MAX_TOOL_CONTENT_CHARS]
        clean["content"] = content
    if msg.get("name"):
        clean["name"] = msg["name"]
    if msg.get("tool_calls"):
        clean["tool_calls"] = msg["tool_calls"]
    if msg.get("tool_call_id"):
        clean["tool_call_id"] = msg["tool_call_id"]
    return clean


def _window_messages_for_llm(messages: list) -> list:
    """Use a small sliding window and summarize dropped context."""
    if len(messages) <= MAX_AGENT_MESSAGES:
        return [_clean_message_for_llm(m) for m in messages]

    dropped = messages[:-MAX_AGENT_MESSAGES]
    recent = messages[-MAX_AGENT_MESSAGES:]
    summary_parts = []
    for msg in dropped[-6:]:
        role = msg.get("role", "")
        if msg.get("tool_calls"):
            called = [tc.get("function", {}).get("name", "unknown")
                      for tc in msg.get("tool_calls", [])]
            summary_parts.append(f"{role}: tool_calls={called}")
        else:
            content = str(msg.get("content", "")).replace("\n", " ")[:120]
            if content:
                summary_parts.append(f"{role}: {content}")

    summary = {
        "role": "system",
        "content": "Earlier conversation/tool context summary: " + " | ".join(summary_parts),
    }
    return [summary] + [_clean_message_for_llm(m) for m in recent]


def _tool_signature(tool_name: str, arguments: dict) -> str:
    return f"{tool_name}:{json.dumps(arguments, ensure_ascii=False, sort_keys=True)}"


def _summarize_tool_result(tool_name: str, result: dict) -> str:
    """Give the LLM a compact status line plus bounded JSON details."""
    if not isinstance(result, dict):
        return f"[OK] {str(result)[:MAX_TOOL_CONTENT_CHARS]}"

    if not result.get("success", result.get("status") == "ok"):
        return f"[FAILED: {result.get('error') or result.get('message') or 'unknown'}]"

    if tool_name == "get_weather":
        data = result.get("data", result)
        summary = (
            f"[OK] weather city={data.get('city', '')} "
            f"desc={data.get('weather_desc', data.get('weather', ''))} "
            f"temp={data.get('temperature', '')}"
        )
    elif tool_name == "plan_trip":
        summary = (
            f"[OK] trip city={result.get('city', '')} days={result.get('days', '')} "
            f"summary={result.get('summary', '')[:160]}"
        )
    elif tool_name == "start_navigation":
        summary = (
            f"[OK] navigation destination={result.get('destination', '')} "
            f"distance_km={result.get('distance_km', '')} duration_min={result.get('duration_min', '')}"
        )
    elif tool_name == "search_attractions":
        names = [a.get("name", "") for a in result.get("attractions", [])[:5]]
        summary = f"[OK] attractions city={result.get('city', '')} names={names}"
    else:
        summary = "[OK]"

    details = json.dumps(result, ensure_ascii=False)
    limit = MAX_TOOL_CONTENT_CHARS * 4 if tool_name in ("plan_trip", "search_attractions") else MAX_TOOL_CONTENT_CHARS
    if len(details) > limit:
        details = details[:limit] + "...[truncated]"
    return f"{summary}\n{details}"


def _apply_node_output(state: dict, updates: dict) -> None:
    """
    将节点输出应用到状态字典。

    - messages 字段使用追加语义（模拟 LangGraph 的 Annotated[list, add]）
    - 其他字段直接覆盖
    仅在手动循环模式中使用；LangGraph 模式由框架自动合并。
    """
    for key, value in updates.items():
        if key == "messages" and isinstance(value, list):
            if "messages" not in state or not isinstance(state["messages"], list):
                state["messages"] = []
            state["messages"].extend(value)
        else:
            state[key] = value


# ================================================================
#  节点函数
# ================================================================


def perceive_node(state: dict) -> dict:
    """
    感知节点：优先从 DriverStateMachine 读取 7 维状态向量 + 趋势预测，
    降级到 SafetyAgent 单点判断（无传感器数据时）。
    支持通过 driver_state["_force_safety"] 强制指定安全等级（用于只读模式）。
    """
    driver_state = state.get("driver_state") or {}

    # 检查是否强制指定安全等级（如 readonly 模式）
    force_safety = driver_state.get("_force_safety")
    if force_safety:
        risk_level = force_safety
        logger.info("Perceive (forced safety): risk_level=%s", risk_level)
    elif _driver_state_machine.history:
        risk_level = _driver_state_machine.get_state()
        trend = _driver_state_machine.get_trend()
        risk_score = _driver_state_machine.get_risk_score()

        # 将趋势信息注入 driver_state，供 safety_gate 模板使用
        driver_state = {
            **driver_state,
            "risk_score": risk_score,
            "trend": trend,
        }
        logger.info(
            "Perceive (DSM): risk_level=%s, score=%.3f, trend=%s",
            risk_level, risk_score, trend,
        )
    else:
        # 降级：无传感器历史数据，用 SafetyAgent 单点判断
        risk_level = get_risk_level_from_safety_agent(driver_state)
        logger.info("Perceive (fallback SafetyAgent): risk_level=%s", risk_level)

    # 应用安全门控，获取过滤后的工具列表和安全提示
    gate_result = apply_safety_gate(risk_level, TOOL_SCHEMAS, driver_state=driver_state)

    allowed_names = [t["function"]["name"] for t in gate_result["allowed_tools"]]
    logger.info(
        "Perceive: risk_level=%s, allowed_tools=%s, emergency=%s",
        risk_level, allowed_names, gate_result["is_emergency"],
    )

    return {
        "driver_state": driver_state,
        "safety_level": gate_result["risk_level"],
        "allowed_tools": gate_result["allowed_tools"],
        "safety_prompt": gate_result["safety_prompt"],
    }


def safety_gate_node(state: dict) -> dict:
    """
    安全门控独立节点。

    可被 StateGraph 引用。当前流程中感知节点已内嵌门控逻辑，
    此节点保留用于图结构扩展或独立调用。
    """
    driver_state = state.get("driver_state") or {}

    if _driver_state_machine.history:
        risk_level = _driver_state_machine.get_state()
    else:
        risk_level = get_risk_level_from_safety_agent(driver_state)

    gate_result = apply_safety_gate(risk_level, TOOL_SCHEMAS, driver_state=driver_state)

    return {
        "safety_level": gate_result["risk_level"],
        "allowed_tools": gate_result["allowed_tools"],
        "safety_prompt": gate_result["safety_prompt"],
    }


def agent_node(state: dict) -> dict:
    """
    Agent 推理节点：构建 system prompt，调用 LLM，决定是否使用工具。

    - 如果 LLM 返回 tool_calls -> 更新 messages，task_complete=False
    - 如果 LLM 返回文本 -> 设置 final_response，task_complete=True
    - step_count += 1
    """
    user_preferences = state.get("user_preferences") or {}
    user_context = _build_user_context(user_preferences)
    memory_context = state.get("memory_context", "")
    if memory_context:
        user_context = (user_context + "\n" + memory_context).strip() if user_context else memory_context

    # 构建 system prompt
    system_prompt = _build_system_prompt(state, user_context)

    # 拼装完整 messages：system prompt + 历史对话
    messages = [{"role": "system", "content": system_prompt}]

    messages.extend(_window_messages_for_llm(state.get("messages", [])))

    # 调用 LLM（传入安全门控过滤后的工具列表）
    allowed_tools = state.get("allowed_tools") or TOOL_SCHEMAS
    orchestrator = get_model_for_agent("orchestrator")
    llm_response = orchestrator.chat_with_tools(
        messages=messages,
        tools=allowed_tools,
    )

    step_count = state.get("step_count", 0) + 1
    updates: dict = {"step_count": step_count}

    if llm_response.get("tool_calls"):
        # LLM 请求调用工具
        assistant_msg = {
            "role": "assistant",
            "content": llm_response.get("content") or "",
            "tool_calls": llm_response["tool_calls"],
        }
        called = [tc["function"]["name"] for tc in llm_response["tool_calls"]]
        logger.info("Agent step %d: 请求工具调用 %s", step_count, called)
        updates["messages"] = [assistant_msg]
        updates["task_complete"] = False
    else:
        # LLM 返回纯文本
        content = llm_response.get("content") or ""
        assistant_msg = {
            "role": "assistant",
            "content": content,
        }
        logger.info("Agent step %d: 直接回复 (len=%d)", step_count, len(content))
        updates["messages"] = [assistant_msg]
        updates["final_response"] = content
        updates["task_complete"] = True

    return updates


def tool_node(state: dict) -> dict:
    """
    工具执行节点：从 messages 最后一条取 tool_calls，逐一执行，
    将结果以 role="tool" 附加到 messages。
    """
    messages = state.get("messages", [])
    if not messages:
        logger.warning("tool_node: messages 为空，无工具调用可执行")
        return {
            "task_complete": True,
            "final_response": "系统内部错误：消息列表为空",
        }

    # 获取最后一条 assistant 消息中的 tool_calls
    last_msg = messages[-1]
    tool_calls = last_msg.get("tool_calls", [])

    if not tool_calls:
        logger.warning("tool_node: 最后一条消息不包含 tool_calls")
        return {"task_complete": True, "final_response": state.get("final_response", "")}

    tool_cache = state.setdefault("_tool_cache", {})
    allowed_tool_names = {
        item.get("function", {}).get("name")
        for item in (state.get("allowed_tools") or TOOL_SCHEMAS)
    }
    allowed_tool_names.discard(None)

    def _exec_one(tc):
        """执行单个工具调用，返回 tool message"""
        tool_name = tc["function"]["name"]
        tool_call_id = tc.get("id", "")
        try:
            arguments = json.loads(tc["function"]["arguments"])
        except (json.JSONDecodeError, TypeError):
            logger.error("tool_node: 无法解析工具参数, raw=%s", tc["function"]["arguments"])
            arguments = {}

        if tool_name not in allowed_tool_names:
            logger.warning("tool_node: 工具 %s 不在当前白名单中", tool_name)
            result = {
                "success": False,
                "error": f"Tool {tool_name} is not allowed in the current safety state.",
            }
            return {
                "role": "tool",
                "name": tool_name,
                "content": _summarize_tool_result(tool_name, result),
                "tool_call_id": tool_call_id,
                "_raw_result": result,
            }

        signature = _tool_signature(tool_name, arguments)
        if signature in tool_cache:
            logger.info("tool_node: 命中工具缓存 %s", signature)
            cached = tool_cache[signature]
            msg = {
                "role": "tool",
                "name": tool_name,
                "content": cached if isinstance(cached, str) else cached["content"],
                "tool_call_id": tool_call_id,
            }
            if isinstance(cached, dict) and "_raw_result" in cached:
                msg["_raw_result"] = cached["_raw_result"]
            return msg

        logger.info("tool_node: 执行工具 %s, args=%s", tool_name, arguments)
        result = execute_tool(tool_name, arguments)
        content = _summarize_tool_result(tool_name, result)
        tool_cache[signature] = {"content": content, "_raw_result": result} if isinstance(result, dict) else content
        logger.info("tool_node: %s 结果=%s", tool_name, content[:200])
        msg = {
            "role": "tool",
            "name": tool_name,
            "content": content,
            "tool_call_id": tool_call_id,
        }
        if isinstance(result, dict):
            msg["_raw_result"] = result
        return msg

    # 多工具并行执行（如 get_weather + search_knowledge 互不依赖）
    if len(tool_calls) == 1:
        tool_results = [_exec_one(tool_calls[0])]
    else:
        logger.info("tool_node: 并行执行 %d 个工具: %s",
                     len(tool_calls), [tc["function"]["name"] for tc in tool_calls])
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
            tool_results = list(pool.map(_exec_one, tool_calls))

    return {"messages": tool_results, "_tool_cache": tool_cache}


def safety_response_node(state: dict) -> dict:
    """
    紧急安全响应节点：构建告警消息，调用 alert_driver 和 speak 工具，
    设置 final_response，task_complete=True。
    """
    driver_state = state.get("driver_state") or {}
    safety_level = state.get("safety_level", "dangerous")
    gaze = driver_state.get("gaze", "unknown")

    if safety_level == "dangerous":
        alert_msg = (
            "紧急安全警告：检测到严重驾驶风险！"
            f"当前视线方向: {gaze}。"
            "请立即注意前方道路状况，确保行车安全！"
        )
        alert_type = "gaze"
        severity = "severe"
    else:
        alert_msg = (
            f"安全提醒：当前驾驶状态为 {safety_level}，"
            "请注意保持注意力集中。"
        )
        alert_type = "distraction"
        severity = "moderate"

    # 调用安全告警工具
    execute_tool("alert_driver", {
        "alert_type": alert_type,
        "severity": severity,
        "message": alert_msg,
    })

    # 语音播报告警
    execute_tool("speak", {"text": alert_msg})

    logger.warning("Safety response: level=%s, msg=%s", safety_level, alert_msg)

    return {
        "final_response": alert_msg,
        "task_complete": True,
        "messages": [{"role": "assistant", "content": alert_msg}],
    }


def respond_node(state: dict) -> dict:
    """
    响应节点：标记 task_complete=True，返回最终状态。
    """
    return {"task_complete": True}


# ================================================================
#  条件路由函数
# ================================================================


def route_after_safety(state: dict) -> str:
    """
    感知/安全门控后的路由：
    - safety_level == "dangerous" -> "safety_response"
    - 其他 -> "agent"
    """
    if state.get("safety_level") == "dangerous":
        return "safety_response"
    return "agent"


def route_after_agent(state: dict) -> str:
    """
    Agent 推理后的路由：
    - task_complete 或 step_count >= max_steps -> "respond"
    - 最后一条 message 有 tool_calls -> "tool_node"
    - 否则 -> "respond"
    """
    if state.get("task_complete", False):
        return "respond"

    max_steps = state.get("max_steps", 5)
    if state.get("step_count", 0) >= max_steps:
        logger.warning("Agent 达到最大步数 %d, 强制结束", max_steps)
        return "respond"

    messages = state.get("messages", [])
    if messages and messages[-1].get("tool_calls"):
        return "tool_node"

    return "respond"


# ================================================================
#  图构建
# ================================================================


def build_agent_graph():
    """
    构建 LangGraph StateGraph。

    流程：
      START -> perceive -> [conditional] -> safety_response -> END
                               -> agent -> [conditional] -> tool_node -> agent (循环)
                                                   -> respond -> END
    """
    if not LANGGRAPH_AVAILABLE:
        raise ImportError("LangGraph 未安装，请执行 pip install langgraph")

    graph = StateGraph(AgentState)

    # 添加节点
    graph.add_node("perceive", perceive_node)
    graph.add_node("safety_gate_node", safety_gate_node)
    graph.add_node("agent", agent_node)
    graph.add_node("tool_node", tool_node)
    graph.add_node("safety_response", safety_response_node)
    graph.add_node("respond", respond_node)

    # 设置入口
    graph.set_entry_point("perceive")

    # 感知后的条件路由：dangerous 走紧急告警，其余走正常推理
    graph.add_conditional_edges(
        "perceive",
        route_after_safety,
        {
            "safety_response": "safety_response",
            "agent": "agent",
        },
    )

    # Agent 推理后的条件路由：需要工具则执行，否则结束
    graph.add_conditional_edges(
        "agent",
        route_after_agent,
        {
            "tool_node": "tool_node",
            "respond": "respond",
        },
    )

    # 工具执行后回到 agent 观察结果
    graph.add_edge("tool_node", "agent")

    # 终止节点
    graph.add_edge("safety_response", END)
    graph.add_edge("respond", END)

    return graph.compile()


# ================================================================
#  手动循环实现（LangGraph 降级方案）
# ================================================================


def _force_finish_response(state: dict) -> str:
    """
    降级策略：当 LLM 调用失败或达到最大步数时，
    从已收集的工具结果中合成一个兜底回复。
    """
    messages = state.get("messages", [])
    tool_results = []
    user_text = ""

    for msg in messages:
        if msg.get("role") == "user" and not user_text:
            user_text = msg.get("content", "")
        elif msg.get("role") == "tool":
            tool_name = msg.get("name", "")
            # 尝试从原始结果中提取结构化信息，而非原样输出 JSON
            raw = msg.get("_raw_result")
            if isinstance(raw, dict):
                if tool_name == "plan_trip":
                    trip = raw.get("trip_plan") or raw
                    city = trip.get("city", "")
                    days = trip.get("days", "")
                    summary = trip.get("summary", "")
                    budget = trip.get("budget", {}).get("total", "")
                    parts = [f"{city}{days}日游"]
                    if summary:
                        parts.append(summary[:60])
                    if budget:
                        parts.append(f"预算约¥{budget}")
                    tool_results.append("行程：" + "，".join(parts))
                    continue
                elif tool_name == "search_hotels":
                    hotels = raw.get("hotels", [])[:3]
                    names = [h.get("name", "") for h in hotels if h.get("name")]
                    if names:
                        tool_results.append(f"酒店推荐：{'、'.join(names)}")
                    continue
                elif tool_name == "search_attractions":
                    attrs = raw.get("attractions", [])[:3]
                    names = [a.get("name", "") for a in attrs if a.get("name")]
                    if names:
                        tool_results.append(f"景点推荐：{'、'.join(names)}")
                    continue
                elif tool_name == "get_weather":
                    w = raw.get("weather", {}) or raw
                    desc = w.get("weather_desc", "")
                    temp = w.get("temperature", "")
                    city = raw.get("city", "")
                    tool_results.append(f"天气：{city} {desc} {temp}°C".strip())
                    continue
                elif tool_name == "start_navigation":
                    dest = raw.get("destination", "")
                    dist = raw.get("distance_km", "")
                    dur = raw.get("duration_min", "")
                    tool_results.append(f"导航：到{dest} {dist}km {dur}分钟".strip())
                    continue
            # 非结构化结果：只取前 80 字符摘要
            content = msg.get("content", "")
            clean = content.split("\n")[0][:80] if content else ""
            tool_results.append(f"{tool_name}: {clean}")

    if tool_results:
        return f"已为您处理完毕。{'；'.join(tool_results)}"
    elif user_text:
        return f'抱歉，处理"{user_text[:30]}"时遇到问题，请稍后再试。'
    else:
        return "抱歉，系统暂时无法处理您的请求，请稍后再试。"


def manual_react_loop(state: dict, callbacks=None) -> dict:
    """
    手动 ReAct 循环实现，当 LangGraph 不可用时使用。
    遵循与 StateGraph 相同的节点执行顺序和路由逻辑。

    Args:
        state: 初始 AgentState 字典
        callbacks: 流式回调函数列表，每个回调签名为 callback(event_type: str, data: dict)
                   event_type: "think" | "tool_call" | "tool_result" | "final" | "error"

    Returns:
        执行完毕后的完整 state 字典
    """
    def _notify(event_type: str, data: dict):
        if callbacks:
            for cb in callbacks:
                try:
                    cb(event_type, data)
                except Exception:
                    pass

    # 1. perceive
    _apply_node_output(state, perceive_node(state))
    _notify("think", {"thought": f"安全等级: {state.get('safety_level', 'normal')}"})

    # 2. route_after_safety
    if state.get("safety_level") == "dangerous":
        _notify("think", {"thought": "检测到危险状态，触发紧急安全响应"})
        _apply_node_output(state, safety_response_node(state))
        _notify("final", {"text": state.get("final_response", "")})
        return state

    # 3. agent loop (ReAct 循环) — 含多级降级策略
    LLM_TIMEOUT_SEC = 30  # 单次 LLM 调用超时阈值
    LLM_MAX_RETRY = 1     # 格式异常时重试次数

    while True:
        # ── 降级策略 1: LLM 超时重试 ──
        llm_success = False
        for attempt in range(1 + LLM_MAX_RETRY):
            t0 = time.time()
            try:
                _apply_node_output(state, agent_node(state))
                llm_success = True
                break
            except Exception as e:
                elapsed = time.time() - t0
                logger.warning("agent_node 第 %d 次调用失败 (%.1fs): %s", attempt + 1, elapsed, e)
                if attempt < LLM_MAX_RETRY:
                    _notify("think", {"thought": f"推理异常，正在重试... ({e})"})
                    time.sleep(1)
                else:
                    # 重试仍失败 → 强制结束
                    logger.error("agent_node 重试仍失败，触发强制降级")
                    _notify("error", {"message": f"LLM 调用失败: {e}"})
                    state["final_response"] = _force_finish_response(state)
                    state["task_complete"] = True
                    break

        if not llm_success:
            break

        # ── 推送 LLM 思考内容（方案 B：兼容 function calling 和纯文本）──
        messages = state.get("messages", [])
        if messages:
            last_msg = messages[-1]
            # 优先取 content（纯文本回复模式）
            content = last_msg.get("content", "")
            if content:
                _notify("think", {"thought": content})
            # function calling 模式：msg.content 常为 null，从 tool_calls 合成 thought
            elif last_msg.get("tool_calls"):
                tc = last_msg["tool_calls"][0]
                func_name = tc.get("function", {}).get("name", "unknown")
                try:
                    raw_args = tc.get("function", {}).get("arguments", "{}")
                    args = json.loads(raw_args) if isinstance(raw_args, str) else raw_args
                    arg_str = ", ".join(f"{k}={v}" for k, v in args.items())
                except (json.JSONDecodeError, TypeError):
                    arg_str = str(tc.get("function", {}).get("arguments", ""))
                _notify("think", {"thought": f"需要调用工具 {func_name}（{arg_str}）来获取信息"})

        # 检查是否有 tool_calls
        if messages and messages[-1].get("tool_calls"):
            for tc in messages[-1]["tool_calls"]:
                tool_name = tc["function"]["name"]
                try:
                    args = json.loads(tc["function"]["arguments"])
                except Exception:
                    args = {}
                _notify("tool_call", {"tool": tool_name, "args": args})

            # ── 降级策略 2: 工具执行异常捕获 ──
            msg_count_before = len(state.get("messages", []))
            try:
                _apply_node_output(state, tool_node(state))
            except Exception as e:
                logger.error("tool_node 执行异常: %s", e)
                _notify("error", {"message": f"工具执行失败: {e}"})
                # 注入错误信息让 Agent 知道
                state.setdefault("messages", []).append({
                    "role": "tool",
                    "content": f"工具执行出错: {e}",
                    "name": "error",
                    "tool_call_id": "error_fallback",
                })

            # 通知工具结果 — 仅处理本轮新增的 tool 消息
            all_msgs = state.get("messages", [])
            new_tool_msgs = [m for m in all_msgs[msg_count_before:] if m.get("role") == "tool"]
            for m in new_tool_msgs:
                tool_name = m.get("name", "")
                tool_content = m.get("content", "")
                _notify("tool_result", {
                    "tool": tool_name,
                    "result": tool_content[:200]
                })
                # ── 结构化工具结果推送：Agent 结果分发到多个面板 ──
                raw = m.get("_raw_result")
                if isinstance(raw, dict):
                    if tool_name == "start_navigation":
                        _notify("navigation", {
                            "destination": raw.get("destination", ""),
                            "distance_km": raw.get("distance_km", 0),
                            "duration_min": raw.get("duration_min", 0),
                            "route_summary": raw.get("route_summary", ""),
                            "origin": raw.get("origin", "当前位置"),
                            "origin_coords": raw.get("origin_coords"),
                            "destination_coords": raw.get("destination_coords"),
                            "geometry": raw.get("geometry", []),
                            "steps": raw.get("steps", []),
                            "coordinate_system": raw.get("coordinate_system", ""),
                            "source": raw.get("source", ""),
                            "origin_source": raw.get("origin_source", ""),
                            "map_url": raw.get("map_url", ""),
                            "amap_nav_url": raw.get("amap_nav_url", ""),
                        })
                    elif tool_name == "search_attractions":
                        _notify("attractions", {
                            "city": raw.get("city", ""),
                            "attractions": raw.get("attractions", []),
                        })
                    elif tool_name == "get_weather":
                        weather_data = raw.get("data", raw)
                        _notify("weather_query", {
                            "city": raw.get("city", weather_data.get("city", "")),
                            "temperature": weather_data.get("temperature"),
                            "humidity": weather_data.get("humidity"),
                            "weather": weather_data.get("weather", ""),
                            "weather_icon": weather_data.get("weather_icon", ""),
                            "weather_emoji": weather_data.get("weather_emoji", ""),
                            "weather_desc": weather_data.get("weather_desc", ""),
                            "wind_speed": weather_data.get("wind_speed"),
                            "driving_context": weather_data.get("driving_context", ""),
                        })
                    elif tool_name == "plan_trip":
                        trip = raw.get("trip_plan", raw)
                        _notify("trip_plan", {
                            "city": trip.get("city", raw.get("city", "")),
                            "days": trip.get("days", raw.get("days", 1)),
                            "itinerary": trip.get("itinerary", []),
                            "budget": trip.get("budget", {}),
                            "weather": raw.get("weather", {}),
                            "attractions": raw.get("attractions", []),
                            "summary": trip.get("summary", raw.get("summary", "")),
                        })

            # 回到 agent 继续推理
            continue

        # route_after_agent
        if state.get("task_complete", False):
            break

        max_steps = state.get("max_steps", 5)
        if state.get("step_count", 0) >= max_steps:
            # ── 降级策略 3: 达到最大步数，强制 Finish ──
            logger.warning("手动循环达到最大步数 %d, 强制结束", max_steps)
            _notify("think", {"thought": "已达到最大推理步数，正在合成最终回复..."})
            state["final_response"] = _force_finish_response(state)
            state["task_complete"] = True
            break

        # 无工具调用且未完成 → 结束
        break

    # 4. respond
    _apply_node_output(state, respond_node(state))
    _notify("final", {"text": state.get("final_response", "")})

    return state


# ================================================================
#  对外接口：ReActAgent
# ================================================================


class ReActAgent:
    """
    ReAct Agent 主入口类。

    封装 LangGraph StateGraph 或手动循环实现，
    提供统一的 chat() 接口。

    用法::

        agent = ReActAgent()
        result = agent.chat("把空调调到 24 度", driver_state={...})
        print(result["reply"])
    """

    def __init__(self):
        self.memory = AgentMemory()
        self.graph = None
        try:
            if LANGGRAPH_AVAILABLE:
                self.graph = build_agent_graph()
                logger.info("ReActAgent: 使用 LangGraph StateGraph 模式")
            else:
                logger.warning("ReActAgent: LangGraph 未安装，使用手动循环模式")
        except Exception as e:
            logger.warning(
                "ReActAgent: 构建 StateGraph 失败 (%s)，降级为手动循环", e
            )
            self.graph = None

    def chat(
        self,
        text: str,
        driver_state: dict = None,
        callbacks=None,
    ) -> dict:
        """
        主入口。返回完整结果。

        通过 callbacks 参数支持流式推送（后续 Phase 3 实现）。

        Args:
            text: 用户输入文本
            driver_state: 实时传感器数据（可选），包含 gaze, head_pose, perclos 等字段
            callbacks: 流式回调函数列表（预留接口）

        Returns:
            {
                "reply": str,           # 最终回复文本
                "steps": int,           # 执行步数
                "status": str,          # "success" / "emergency"
                "safety_level": str,    # 安全等级
            }
        """
        # 1. 初始化状态
        self.memory.learn_preferences_from_text(text)
        user_preferences = self.memory.long_term.get_all_preferences()
        memory_context = self.memory.get_user_context_for_prompt()

        # ── 多轮上下文回注：从 WorkingMemory 注入最近对话历史 ──
        history_msgs = self.memory.working.get_messages_for_llm()
        # 取最近 6 条（3 轮对话），避免 token 爆炸
        recent_history = history_msgs[-6:] if len(history_msgs) > 6 else history_msgs

        # ── 行程规划上下文回注：若上轮触发过 plan_trip，把结构化参数
        # 注入 memory_context，让 LLM 在"重新规划"时能复用而非从零询问。 ──
        trip_context = self.memory.working.get_trip_context_for_prompt()
        if trip_context:
            memory_context = (memory_context + "\n" + trip_context).strip() if memory_context else trip_context

        # ── P2 工具结果回注：若上轮触发过 search_attractions / get_weather /
        # start_navigation / plan_trip，把精简摘要注入上下文，让 LLM 能回答
        # "刚才推荐的那个景点在哪"等引用性问题，而不是失忆。 ──
        tool_results_ctx = self.memory.working.get_tool_results_for_prompt()
        if tool_results_ctx:
            memory_context = (memory_context + "\n" + tool_results_ctx).strip() if memory_context else tool_results_ctx

        state: AgentState = {
            "messages": [
                *recent_history,  # 注入历史对话上下文
                {
                    "role": "user",
                    "content": text,
                }
            ],
            "driver_state": driver_state or {},
            "safety_level": "normal",
            "allowed_tools": list(TOOL_SCHEMAS),
            "safety_prompt": "",
            "conversation_id": self.memory.session_id,
            "user_preferences": user_preferences,
            "memory_context": memory_context,
            "final_response": "",
            "task_complete": False,
            "step_count": 0,
            "max_steps": 5,
            "_tool_cache": {},
        }

        # 2. 执行 Agent 循环
        try:
            # 当需要流式回调时，优先使用手动循环（LangGraph invoke 不支持中间事件回调）
            if callbacks:
                state = manual_react_loop(state, callbacks=callbacks)
            elif self.graph is not None:
                # LangGraph 模式：由框架管理状态合并和节点调度
                state = self.graph.invoke(state)
            else:
                # 手动循环模式（降级）
                state = manual_react_loop(state, callbacks=None)
        except Exception as e:
            logger.error("ReActAgent chat 异常: %s", e, exc_info=True)
            state["final_response"] = "抱歉，系统处理过程中出现错误，请稍后再试。"
            state["task_complete"] = True

        # 3. 记录到短期记忆
        self.memory.working.add_message("user", text)
        reply = state.get("final_response", "")
        self.memory.working.add_message("assistant", reply)

        # 3.1 扫描本轮 tool 消息，缓存 plan_trip 结构化参数到 WorkingMemory。
        # 这是多轮对话上下文不断裂的关键：下一轮"重新规划"时 LLM 能
        # 看到 city/days/preference，而不是从口语化 reply 里猜。
        # P2 扩展：同时缓存 search_attractions/get_weather/start_navigation
        # 的精简摘要，让用户后续能引用"刚才推荐的那个景点"。
        self._capture_tool_results(state)

        # 4. 判断状态
        safety_level = state.get("safety_level", "normal")
        status = "emergency" if safety_level == "dangerous" else "success"
        step_count = state.get("step_count", 0)

        # 5. 记录长期记忆（会话摘要）
        summary = self._build_session_summary(text, reply, state)
        self.memory.end_session(summary=summary)

        logger.info(
            "ReActAgent chat 完成: status=%s, steps=%d, safety=%s",
            status, step_count, safety_level,
        )

        return {
            "reply": reply,
            "steps": step_count,
            "status": status,
            "safety_level": safety_level,
        }

    # ------------------------------------------------------------------
    #  多轮上下文辅助：缓存行程参数 + 构建结构化会话摘要
    # ------------------------------------------------------------------

    def _capture_tool_results(self, state: dict) -> None:
        """Scan this turn's tool messages and cache structured results.

        Two kinds of caching:
          1. plan_trip → last_trip_params (full param set, for replanning)
          2. search_attractions / get_weather / start_navigation →
             last_tool_results (one-line summaries, for "刚才推荐的那个景点")

        Silently no-ops on any malformed payload — this is context enrichment,
        never a failure surface.
        """
        try:
            import json as _json
            messages = state.get("messages", [])
            captured_trip = None
            # Reset tool-result cache for this turn; only the latest round is kept.
            self.memory.working.last_tool_results = {}

            for msg in messages:
                if msg.get("role") != "tool":
                    continue
                tool_name = msg.get("name", "")
                if not tool_name:
                    continue
                content = msg.get("content", "") or ""
                # tool content from our pipeline is "[OK] summary\n{json}";
                # extract the JSON payload (first '{' to last '}').
                start = content.find("{")
                end = content.rfind("}")
                data = None
                if 0 <= start < end:
                    try:
                        data = _json.loads(content[start:end + 1])
                    except _json.JSONDecodeError:
                        data = None

                if tool_name == "plan_trip":
                    if data is None or data.get("success", True) is False:
                        continue
                    captured_trip = data
                    # Also store a one-line summary for cross-reference.
                    summary = self._summarize_plan_trip(data)
                    if summary:
                        self.memory.working.set_last_tool_result("plan_trip", summary)
                elif tool_name == "search_attractions":
                    summary = self._summarize_attractions(data)
                    if summary:
                        self.memory.working.set_last_tool_result("search_attractions", summary)
                elif tool_name == "get_weather":
                    summary = self._summarize_weather(data)
                    if summary:
                        self.memory.working.set_last_tool_result("get_weather", summary)
                elif tool_name == "start_navigation":
                    summary = self._summarize_navigation(data)
                    if summary:
                        self.memory.working.set_last_tool_result("start_navigation", summary)

            if captured_trip is not None:
                params = {
                    "city": captured_trip.get("city"),
                    "days": captured_trip.get("days"),
                    "preference": (captured_trip.get("preferences") or captured_trip.get("preference")),
                    "origin": captured_trip.get("origin"),
                    "waypoints": captured_trip.get("waypoints"),
                    "forbidden_cities": captured_trip.get("forbidden_cities"),
                    "trip_type": captured_trip.get("trip_type"),
                    "accommodation": captured_trip.get("accommodation"),
                    "transportation": captured_trip.get("transportation"),
                }
                self.memory.working.set_last_trip_params(params)
                logger.info("已缓存上次行程参数供下轮对话复用：%s",
                           self.memory.working.last_trip_params)
            if self.memory.working.last_tool_results:
                logger.info("已缓存上轮工具结果摘要：%s",
                           list(self.memory.working.last_tool_results.keys()))
        except Exception as e:  # noqa: BLE001 — enrichment must never break chat
            logger.debug("捕获 tool_results 跳过：%s", e)

    # -- one-line summarizers (keep terse: full data lives in the HMI panels) --

    @staticmethod
    def _summarize_plan_trip(data: dict) -> str:
        city = data.get("city", "")
        days = data.get("days", "")
        budget = (data.get("budget") or {}).get("total", "") if isinstance(data.get("budget"), dict) else ""
        parts = []
        if city:
            parts.append(f"{city}")
        if days:
            parts.append(f"{days}日游")
        if budget:
            parts.append(f"预算¥{budget}")
        return "，".join(parts)

    @staticmethod
    def _summarize_attractions(data: Optional[dict]) -> str:
        if not isinstance(data, dict):
            return ""
        attrs = data.get("attractions") or []
        if not attrs:
            return ""
        names = [a.get("name", "") for a in attrs[:5] if a.get("name")]
        return f"推荐{len(attrs)}个景点：" + "、".join(names)

    @staticmethod
    def _summarize_weather(data: Optional[dict]) -> str:
        if not isinstance(data, dict):
            return ""
        inner = data.get("data") if isinstance(data.get("data"), dict) else data
        city = inner.get("city", "") or data.get("city", "")
        temp = inner.get("temperature", "") or data.get("temperature", "")
        desc = inner.get("weather_desc", "") or inner.get("weather", "") or data.get("weather", "")
        parts = []
        if city:
            parts.append(city)
        if desc:
            parts.append(desc)
        if temp != "":
            parts.append(f"{temp}°C")
        return " ".join(parts)

    @staticmethod
    def _summarize_navigation(data: Optional[dict]) -> str:
        if not isinstance(data, dict):
            return ""
        dest = data.get("destination", "")
        dist = data.get("distance_km", "")
        dur = data.get("duration_min", "")
        parts = []
        if dest:
            parts.append(f"到{dest}")
        if dist != "":
            parts.append(f"{dist}km")
        if dur != "":
            parts.append(f"{dur}分钟")
        return " ".join(parts)

    def _build_session_summary(self, user_text: str, reply: str, state: dict) -> str:
        """Build a structured one-line summary for long-term memory.

        Previously this was just reply[:200] — a spoken-style sentence that
        loses the user's intent. We now lead with the user's request and
        append a trimmed reply, so next-session context says e.g.
        '用户：上海两日游喜欢美食 → 已生成行程' instead of a fragment of
        the assistant's prose.
        """
        try:
            user_part = (user_text or "").strip().replace("\n", " ")[:80]
            reply_part = (reply or "").strip().replace("\n", " ")[:120]
            # Note which tools ran, for debugging multi-turn behavior.
            tool_names = sorted({
                m.get("name", "")
                for m in state.get("messages", [])
                if m.get("role") == "tool" and m.get("name")
            } - {""})
            tools_tag = f"[工具:{','.join(tool_names)}]" if tool_names else ""
            summary = f"用户：{user_part} → {reply_part}{tools_tag}"
            return summary[:300]
        except Exception:
            return (reply or "")[:200]

    def close(self):
        """释放资源（数据库连接等）。"""
        self.memory.close()
