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
from typing import TypedDict
try:
    from typing import Annotated
except ImportError:
    from typing_extensions import Annotated

logger = logging.getLogger(__name__)

# ================================================================
#  LangGraph 导入（降级处理）
# ================================================================

try:
    from langgraph.graph import StateGraph, END

    LANGGRAPH_AVAILABLE = True
except ImportError:
    LANGGRAPH_AVAILABLE = False
    logger.warning("LangGraph 未安装，将使用手动循环实现 ReAct Agent")

# ================================================================
#  项目内模块导入
# ================================================================

from modules.ai.tools import TOOL_SCHEMAS, execute_tool
from modules.ai.safety_gate import apply_safety_gate, get_risk_level_from_safety_agent
from modules.ai.memory import AgentMemory
from modules.ai.deepseek_client import deepseek_client

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


# ================================================================
#  System Prompt — 从 Prompt 模板库获取（兜底使用内嵌模板）
# ================================================================

# 内嵌兜底（模板库不可用时使用）
_FALLBACK_SYSTEM_PROMPT = """\
你是 EdgeGuard 车载智能助手。你的职责是协助驾驶员安全驾驶，提供舒适的车内环境控制。

当前驾驶状态：
- 视线方向: {gaze}
- 安全等级: {safety_level}

{safety_prompt}

{user_context}

你可以使用以下工具来帮助驾驶员。请根据驾驶员的需求选择合适的工具。
如果不需要任何工具（只是闲聊或简单回答），直接回复即可。

当用户提到旅行需求时，调用 plan_trip 工具生成结构化行程。
景点、天气、导航、行程的结果会自动展示在专属面板中，语音回复简要总结即可。
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
    感知节点：读取传感器状态，调用 SafetyAgent 获取 risk_level，
    调用 apply_safety_gate 获取 allowed_tools，更新 state。
    """
    driver_state = state.get("driver_state") or {}

    # 调用 SafetyAgent 获取风险等级
    risk_level = get_risk_level_from_safety_agent(driver_state)

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

    # 构建 system prompt
    system_prompt = _build_system_prompt(state, user_context)

    # 拼装完整 messages：system prompt + 历史对话
    messages = [{"role": "system", "content": system_prompt}]

    for msg in state.get("messages", []):
        clean = {"role": msg["role"]}
        if msg.get("content") is not None:
            clean["content"] = msg["content"]
        if msg.get("name"):
            clean["name"] = msg["name"]
        if msg.get("tool_calls"):
            clean["tool_calls"] = msg["tool_calls"]
        if msg.get("tool_call_id"):
            clean["tool_call_id"] = msg["tool_call_id"]
        messages.append(clean)

    # 调用 LLM（传入安全门控过滤后的工具列表）
    allowed_tools = state.get("allowed_tools") or TOOL_SCHEMAS
    llm_response = deepseek_client.chat_with_tools(
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

    tool_results = []
    for tc in tool_calls:
        tool_name = tc["function"]["name"]
        tool_call_id = tc.get("id", "")

        # 解析参数 JSON
        try:
            arguments = json.loads(tc["function"]["arguments"])
        except (json.JSONDecodeError, TypeError):
            logger.error(
                "tool_node: 无法解析工具参数, raw=%s", tc["function"]["arguments"]
            )
            arguments = {}

        logger.info("tool_node: 执行工具 %s, args=%s", tool_name, arguments)

        result = execute_tool(tool_name, arguments)
        result_json = json.dumps(result, ensure_ascii=False)

        tool_results.append({
            "role": "tool",
            "name": tool_name,
            "content": result_json,
            "tool_call_id": tool_call_id,
        })

        logger.info("tool_node: %s 结果=%s", tool_name, result_json[:200])

    return {"messages": tool_results}


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
            content = msg.get("content", "")[:150]
            tool_results.append(f"{tool_name}: {content}")

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
                try:
                    tool_data = json.loads(tool_content)
                    if tool_name == "start_navigation":
                        _notify("navigation", {
                            "destination": tool_data.get("destination", ""),
                            "distance_km": tool_data.get("distance_km", 0),
                            "duration_min": tool_data.get("duration_min", 0),
                            "route_summary": tool_data.get("route_summary", ""),
                            "origin": tool_data.get("origin", "当前位置"),
                            "map_url": tool_data.get("map_url", ""),
                            "amap_nav_url": tool_data.get("amap_nav_url", ""),
                        })
                    elif tool_name == "search_attractions":
                        _notify("attractions", {
                            "city": tool_data.get("city", ""),
                            "attractions": tool_data.get("attractions", []),
                        })
                    elif tool_name == "get_weather":
                        _notify("weather_query", {
                            "city": tool_data.get("city", ""),
                            "temperature": tool_data.get("temperature"),
                            "humidity": tool_data.get("humidity"),
                            "weather": tool_data.get("weather", ""),
                            "weather_icon": tool_data.get("weather_icon", ""),
                            "weather_emoji": tool_data.get("weather_emoji", ""),
                            "weather_desc": tool_data.get("weather_desc", ""),
                            "wind_speed": tool_data.get("wind_speed"),
                            "driving_context": tool_data.get("driving_context", ""),
                        })
                    elif tool_name == "plan_trip":
                        _notify("trip_plan", {
                            "city": tool_data.get("city", ""),
                            "days": tool_data.get("days", 1),
                            "itinerary": tool_data.get("itinerary", []),
                            "budget": tool_data.get("budget", {}),
                            "weather": tool_data.get("weather", {}),
                            "attractions": tool_data.get("attractions", []),
                            "summary": tool_data.get("summary", ""),
                        })
                except Exception as e:
                    logger.debug("结构化推送解析跳过 (tool=%s): %s", tool_name, e)

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
        user_preferences = self.memory.long_term.get_all_preferences()

        # ── 多轮上下文回注：从 WorkingMemory 注入最近对话历史 ──
        history_msgs = self.memory.working.get_messages_for_llm()
        # 取最近 6 条（3 轮对话），避免 token 爆炸
        recent_history = history_msgs[-6:] if len(history_msgs) > 6 else history_msgs

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
            "final_response": "",
            "task_complete": False,
            "step_count": 0,
            "max_steps": 5,
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

        # 4. 判断状态
        safety_level = state.get("safety_level", "normal")
        status = "emergency" if safety_level == "dangerous" else "success"
        step_count = state.get("step_count", 0)

        # 5. 记录长期记忆（会话摘要）
        summary = reply[:200] if reply else ""
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

    def close(self):
        """释放资源（数据库连接等）。"""
        self.memory.close()