"""
Agent Orchestrator — 多 Agent 编排引擎
========================================

接收 IntentionAgent 输出的调度计划，按优先级/依赖关系
依次调度各子 Agent 执行，聚合结果后返回统一响应。

核心设计原则：
  - 简单控制（空调/音乐）→ ControlExecutor 直接调 API，不走 LLM
  - 复杂推理（故障诊断/疲劳辅助）→ 走子 Agent 的 ReAct/推理循环
  - 安全检查始终最先执行

子 Agent 注册在 agents/ 目录下：
  - control_executor → 内联类（直接调API）
  - react_agent → agent_graph.ReActAgent（完整ReAct循环）
  - diagnose_agent → agents.diagnose_agent.DiagnoseAgent
  - analyze_agent → agents.analyze_agent.AnalyzeAgent
  - recommend_agent → agents.recommend_agent.RecommendAgent

执行流程：
  1. 意图分解 (IntentionAgent)
  2. 安全预检（dangerous → 直接告警，跳过其他）
  3. 按 priority 排序依次执行
  4. 聚合结果 → 统一自然语言回复
"""

import logging
import time
import concurrent.futures
import threading
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field

from modules.ai.intent_guard import guard_intent, normalize_intent

logger = logging.getLogger(__name__)

PARALLEL_INTENT_TIMEOUT_SEC = 30.0


# ═══════════════════════════════════════════════════════════
#  数据结构
# ═══════════════════════════════════════════════════════════

@dataclass
class ExecutionResult:
    """单个意图的执行结果"""
    intent_id: str
    intent_category: str
    agent_name: str
    success: bool
    reply_text: str = ""
    actions: list = field(default_factory=list)
    data: dict = field(default_factory=dict)
    error: str = ""
    duration_ms: float = 0.0


@dataclass
class OrchestratorResponse:
    """编排器统一响应"""
    success: bool
    overall_reply: str = ""
    results: List[ExecutionResult] = field(default_factory=list)
    actions: list = field(default_factory=list)
    needs_clarification: bool = False
    clarification_question: str = ""
    total_duration_ms: float = 0.0
    route: str = "orchestrator"
    intent_plan: dict = field(default_factory=dict)


# ═══════════════════════════════════════════════════════════
#  ControlExecutor — 直接调 API（空调/音乐，不走 LLM）
# ═══════════════════════════════════════════════════════════

class ControlExecutor:
    """
    控制执行器 — 直接调用后端 API 执行空调/音乐控制。
    延迟 < 100ms，不走 LLM。
    """

    def __init__(self):
        self._backend_base = "http://localhost:8000"

    def execute(self, category: str, params: dict, full_text: str = "") -> ExecutionResult:
        """执行控制指令。"""
        import httpx

        start = time.time()
        actions = []

        try:
            if category == "ac_control":
                reply = self._execute_ac(params, actions, full_text)
            elif category == "music_control":
                reply = self._execute_music(params, actions, full_text)
            else:
                return ExecutionResult(
                    intent_id=f"{category}_exec",
                    intent_category=category,
                    agent_name="control_executor",
                    success=False,
                    error=f"不支持的控制类别: {category}",
                )

            duration = (time.time() - start) * 1000
            return ExecutionResult(
                intent_id=f"{category}_exec",
                intent_category=category,
                agent_name="control_executor",
                success=True,
                reply_text=reply,
                actions=actions,
                duration_ms=duration,
            )
        except Exception as e:
            duration = (time.time() - start) * 1000
            return ExecutionResult(
                intent_id=f"{category}_exec",
                intent_category=category,
                agent_name="control_executor",
                success=False,
                error=str(e),
                duration_ms=duration,
            )

    def _execute_ac(self, params: dict, actions: list, text: str) -> str:
        """执行空调控制。"""
        import httpx

        action = params.get("action", "")
        temperature = params.get("temperature")

        if action == "TurnOnAC":
            httpx.post(f"{self._backend_base}/api/ac/command",
                      json={"command": "TurnOnAC"}, timeout=5)
            actions.append({"type": "ac", "command": "TurnOnAC"})
            return "空调已开启"

        if action == "TurnOffAC":
            httpx.post(f"{self._backend_base}/api/ac/command",
                      json={"command": "TurnOffAC"}, timeout=5)
            actions.append({"type": "ac", "command": "TurnOffAC"})
            return "空调已关闭"

        if temperature:
            httpx.post(f"{self._backend_base}/api/ac/command",
                      json={"command": "set", "params": {"temperature": temperature}},
                      timeout=5)
            actions.append({"type": "ac", "command": "set",
                           "params": {"temperature": temperature}})
            return f"空调温度已调至 {temperature} 度"

        # 默认打开（无明确参数时）
        httpx.post(f"{self._backend_base}/api/ac/command",
                  json={"command": "TurnOnAC"}, timeout=5)
        actions.append({"type": "ac", "command": "TurnOnAC"})
        return "空调已开启"

    def _execute_music(self, params: dict, actions: list, text: str) -> str:
        """执行音乐控制。"""
        import httpx

        action = params.get("action", "")
        singer = params.get("singer", "")

        if singer and action == "play":
            # 搜索并播放
            r = httpx.post(f"{self._backend_base}/api/music/search",
                          json={"keyword": singer}, timeout=10)
            data = r.json()
            songs = data.get("songs", []) or data.get("data", [])
            if songs:
                first = songs[0]
                pr = httpx.post(f"{self._backend_base}/api/music/play",
                          json={"song_id": first.get("id")}, timeout=5)
                pdata = pr.json()
                if pdata.get("status") == "ok":
                    actions.append({"type": "music", "command": "play",
                                   "song": first.get("name", ""), "artist": singer})
                    return f"开始播放 {singer} 的《{first.get('name', '')}》"
                else:
                    actions.append({"type": "music", "command": "play_failed"})
                    return f"找到歌曲但播放失败：{pdata.get('message', '未知错误')}"
            actions.append({"type": "music", "command": "search_failed"})
            return f"没有找到 {singer} 的歌曲"

        if action == "play":
            # 无 song_id：调用 pause 端点恢复当前播放（pause 是 toggle）
            r = httpx.post(f"{self._backend_base}/api/music/pause", timeout=5)
            data = r.json()
            status = data.get("status", "")
            state = data.get("data", {})
            playing = state.get("playing") if isinstance(state, dict) else None
            if status == "ok" and playing:
                actions.append({"type": "music", "command": "play"})
                return "开始播放音乐"
            elif status == "needs_audio":
                actions.append({"type": "music", "command": "play_failed"})
                return "当前没有可播放的歌曲，请先搜索并选择歌曲"
            elif status == "ok" and not playing:
                # toggle 后变为暂停，再 toggle 一次恢复
                httpx.post(f"{self._backend_base}/api/music/pause", timeout=5)
                actions.append({"type": "music", "command": "play"})
                return "开始播放音乐"
            else:
                actions.append({"type": "music", "command": "play_failed"})
                return f"播放失败：{data.get('message', '未知错误')}"

        if action == "pause":
            # First check current state to handle "already paused" gracefully
            try:
                state_r = httpx.get(f"{self._backend_base}/api/music/state", timeout=5)
                state_data = state_r.json()
                cur_state = state_data.get("data", {})
                if isinstance(cur_state, dict) and not cur_state.get("playing"):
                    actions.append({"type": "music", "command": "pause"})
                    return "音乐已经是暂停状态"
            except Exception:
                pass
            r = httpx.post(f"{self._backend_base}/api/music/pause", timeout=5)
            data = r.json()
            if data.get("status") == "ok":
                actions.append({"type": "music", "command": "pause"})
                state = data.get("data", {})
                playing = state.get("playing") if isinstance(state, dict) else None
                return "音乐已暂停" if not playing else "已恢复播放"
            elif data.get("status") == "needs_audio":
                actions.append({"type": "music", "command": "pause"})
                return "当前没有在播放的音乐"
            actions.append({"type": "music", "command": "pause_failed"})
            return "暂停失败"

        # 默认播放：调用 pause 端点恢复当前播放
        r = httpx.post(f"{self._backend_base}/api/music/pause", timeout=5)
        data = r.json()
        status = data.get("status", "")
        state = data.get("data", {})
        playing = state.get("playing") if isinstance(state, dict) else None
        if status == "ok" and playing:
            actions.append({"type": "music", "command": "play"})
            return "开始播放音乐"
        elif status == "needs_audio":
            actions.append({"type": "music", "command": "play_failed"})
            return "当前没有可播放的歌曲，请先搜索并选择歌曲"
        elif status == "ok" and not playing:
            httpx.post(f"{self._backend_base}/api/music/pause", timeout=5)
            actions.append({"type": "music", "command": "play"})
            return "开始播放音乐"
        actions.append({"type": "music", "command": "play_failed"})
        return f"播放失败：{data.get('message', '未知错误')}"


# ═══════════════════════════════════════════════════════════
#  AgentOrchestrator — 编排主类
# ═══════════════════════════════════════════════════════════

class AgentOrchestrator:
    """
    多 Agent 编排器。

    流程：
      意图计划 → 安全预检 → 按优先级调度 → 聚合结果 → 统一响应
    """

    def __init__(self):
        self._control_executor = None
        self._react_agent = None
        self._diagnose_agent = None
        self._analyze_agent = None
        self._recommend_agent = None
        self._intention_agent = None
        self._lazy_lock = threading.Lock()
        # 上轮行程规划的结构化参数（city/days/preference 等），
        # 供下一轮意图识别复用，避免"重新规划"时 LLM 失忆重新询问城市。
        self._last_trip_params: dict = {}
        # 上轮工具结果摘要（如"推荐3个景点：外滩、东方明珠、豫园"）。
        self._last_tool_summary: str = ""
        # 上轮用户输入，供意图识别判断用户是否在"调整上轮"。
        self._last_user_text: str = ""

    # ── 延迟加载 ──

    @property
    def control_executor(self):
        if self._control_executor is None:
            with self._lazy_lock:
                if self._control_executor is None:
                    self._control_executor = ControlExecutor()
        return self._control_executor

    @property
    def react_agent(self):
        if self._react_agent is None:
            with self._lazy_lock:
                if self._react_agent is None:
                    from modules.ai.agent_graph import ReActAgent
                    self._react_agent = ReActAgent()
        return self._react_agent

    @property
    def diagnose_agent(self):
        if self._diagnose_agent is None:
            with self._lazy_lock:
                if self._diagnose_agent is None:
                    from modules.ai.agents.diagnose_agent import DiagnoseAgent
                    self._diagnose_agent = DiagnoseAgent()
        return self._diagnose_agent

    @property
    def analyze_agent(self):
        if self._analyze_agent is None:
            with self._lazy_lock:
                if self._analyze_agent is None:
                    from modules.ai.agents.analyze_agent import AnalyzeAgent
                    self._analyze_agent = AnalyzeAgent()
        return self._analyze_agent

    @property
    def recommend_agent(self):
        if self._recommend_agent is None:
            with self._lazy_lock:
                if self._recommend_agent is None:
                    from modules.ai.agents.recommend_agent import RecommendAgent
                    self._recommend_agent = RecommendAgent()
        return self._recommend_agent

    @property
    def intention_agent(self):
        if self._intention_agent is None:
            with self._lazy_lock:
                if self._intention_agent is None:
                    from modules.ai.intention_agent import IntentionAgent
                    self._intention_agent = IntentionAgent()
        return self._intention_agent

    # ── 主入口 ──

    def process(self, text: str, driver_state: dict = None,
                callbacks: dict = None) -> OrchestratorResponse:
        """
        处理用户输入，返回编排后的统一响应。

        Args:
            text: 用户文本/语音输入
            driver_state: 驾驶员状态（摄像头/传感器数据）
            callbacks: 回调函数字典 {on_intent, on_step, on_result}

        Returns:
            OrchestratorResponse
        """
        total_start = time.time()
        ds = driver_state or {}

        # Step 1: 意图分解
        # 构建 conversation_context：从 Orchestrator 自身缓存 + react_agent.memory
        # 提取上轮行程参数和工具结果，注入意图识别 prompt，
        # 让 LLM 在"重新规划"/"换个方案"等调整场景下复用 city/days，
        # 而不是从零询问"请问您想去哪个城市"。
        conversation_context = self._build_conversation_context()
        plan = self.intention_agent.analyze(text, ds, conversation_context=conversation_context)
        plan_dict = plan.to_dict()

        if callbacks and callbacks.get("on_intent"):
            callbacks["on_intent"](plan_dict)

        # 需要澄清的情况
        if plan.needs_clarification:
            return OrchestratorResponse(
                success=True,
                overall_reply=plan.clarification_question,
                needs_clarification=True,
                clarification_question=plan.clarification_question,
                intent_plan=plan_dict,
                total_duration_ms=(time.time() - total_start) * 1000,
            )

        # Step 2: 安全预检（dangerous → 短路）
        risk_level = ds.get("severity", "normal")
        if risk_level == "dangerous":
            alert_text = "⚠️ 严重警告：请立即注视前方道路！"
            if callbacks and callbacks.get("on_result"):
                callbacks["on_result"]({"type": "safety_alert", "text": alert_text})
            return OrchestratorResponse(
                success=True,
                overall_reply=alert_text,
                results=[ExecutionResult(
                    intent_id="safety_shortcut",
                    intent_category="safety",
                    agent_name="safety_gate",
                    success=True,
                    reply_text=alert_text,
                    actions=[{"type": "alert", "level": "dangerous"}],
                    duration_ms=(time.time() - total_start) * 1000,
                )],
                actions=[{"type": "alert", "level": "dangerous"}],
                total_duration_ms=(time.time() - total_start) * 1000,
                route="safety_shortcut",
                intent_plan=plan_dict,
            )

        # Step 3: 执行各意图。无依赖任务并行，组合推理/依赖任务保持顺序。
        results = self._execute_intents(plan.intents, text, ds, callbacks)
        all_actions = []
        for result in results:
            all_actions.extend(result.actions)

        # Step 3.5: 缓存本轮行程规划结果，供下一轮意图识别复用
        self._capture_last_results(results, text)

        # Step 4: 聚合结果，生成统一回复
        overall_reply = self._aggregate_reply(results, plan.overall_summary)
        total_duration = (time.time() - total_start) * 1000

        return OrchestratorResponse(
            success=True,
            overall_reply=overall_reply,
            results=results,
            actions=all_actions,
            total_duration_ms=total_duration,
            intent_plan=plan_dict,
        )

    def _build_conversation_context(self) -> str:
        """构建注入意图识别 prompt 的对话上下文。

        优先从 Orchestrator 自身缓存（_last_trip_params）提取，
        因为行程规划走 recommend_agent，不经过 react_agent。
        同时尝试 react_agent.memory.working 作为补充（用于 chitchat 场景）。
        """
        parts = []

        # 1. Orchestrator 自身缓存的行程参数（主要来源）
        if self._last_trip_params:
            p = self._last_trip_params
            trip_parts = []
            if p.get("origin") and p.get("city"):
                trip_parts.append(f"{p['origin']}→{p['city']}")
            elif p.get("city"):
                trip_parts.append(f"上次行程城市：{p['city']}")
            if p.get("days"):
                trip_parts.append(f"{p['days']}日游")
            if p.get("preference"):
                trip_parts.append(f"偏好「{p['preference']}」")
            if trip_parts:
                parts.append("上次行程参数（用户要求调整时请复用城市和天数，不要重新询问）：" + "，".join(trip_parts) + "。")

        if self._last_tool_summary:
            parts.append(f"上轮工具结果：{self._last_tool_summary}")

        if self._last_user_text:
            parts.append(f"上轮用户输入：{self._last_user_text[:80]}")

        # 2. react_agent.memory.working（补充来源，用于 chitchat/control 场景）
        try:
            wm = self.react_agent.memory.working
            trip_ctx = wm.get_trip_context_for_prompt()
            if trip_ctx and not self._last_trip_params:
                parts.append(trip_ctx)
            recent = wm.get_messages_for_llm()[-2:]
            for m in recent:
                role = "用户" if m.get("role") == "user" else "助手"
                content = str(m.get("content", ""))[:120]
                if content:
                    parts.append(f"上轮{role}：{content}")
        except Exception:
            pass

        return "\n".join(parts) if parts else ""

    def _capture_last_results(self, results: list, user_text: str) -> None:
        """从执行结果中缓存行程规划参数，供下一轮意图识别复用。

        行程规划走 recommend_agent → trip_planner，结果在 ExecutionResult.data 中。
        这里提取 city/days/preference 等关键字段，避免下一轮 LLM 失忆。
        """
        self._last_user_text = user_text[:200]
        for r in results:
            if not r.success or not r.data:
                continue
            data = r.data
            # trip_plan 类型
            if data.get("type") == "trip_plan" or data.get("trip_plan"):
                trip = data.get("trip_plan") or data
                if isinstance(trip, dict) and trip.get("success", True) is not False:
                    params = {
                        "city": trip.get("city", data.get("city", "")),
                        "days": trip.get("days", data.get("days")),
                        "preference": trip.get("preferences") or trip.get("preference") or data.get("preference", ""),
                        "origin": trip.get("origin", data.get("origin", "")),
                        "waypoints": trip.get("waypoints", []),
                        "forbidden_cities": trip.get("forbidden_cities", []),
                    }
                    # 只在有 city 时才缓存
                    if params["city"]:
                        # preference 可能是 list，归一化为字符串
                        pref = params["preference"]
                        if isinstance(pref, (list, tuple)):
                            params["preference"] = "、".join(str(x) for x in pref if x)
                        self._last_trip_params = params
                        # 生成摘要
                        summary_parts = [params["city"]]
                        if params["days"]:
                            summary_parts.append(f"{params['days']}日游")
                        budget = trip.get("budget") or data.get("budget")
                        if isinstance(budget, dict) and budget.get("total"):
                            summary_parts.append(f"预算¥{budget['total']}")
                        self._last_tool_summary = "，".join(summary_parts)
                        logger.info("Orchestrator 已缓存行程参数：%s", params)
                    break
            # attractions 类型
            elif data.get("type") == "attractions" or data.get("attractions"):
                attrs = data.get("attractions") or []
                if attrs:
                    names = [a.get("name", "") for a in attrs[:5] if a.get("name")]
                    if names:
                        self._last_tool_summary = f"推荐{len(attrs)}个景点：" + "、".join(names)
            # navigation 类型 — 补全之前缺失的导航结果捕获
            elif data.get("type") == "navigation" or data.get("destination"):
                dest = data.get("destination", "")
                dist = data.get("distance_km", "")
                dur = data.get("duration_min", "")
                parts = []
                if dest:
                    parts.append(f"到{dest}")
                if dist != "":
                    parts.append(f"{dist}公里")
                if dur != "":
                    parts.append(f"{dur}分钟")
                if parts:
                    self._last_tool_summary = "导航" + "，".join(parts)
                    logger.info("Orchestrator 已缓存导航结果: %s", self._last_tool_summary)

    def _execute_intents(self, intents: list, text: str, driver_state: dict,
                         callbacks: dict = None) -> List[ExecutionResult]:
        """按依赖关系执行 intent：安全/依赖/组合任务串行，互不依赖任务并行。"""
        if not intents:
            return []

        ordered = sorted(intents, key=lambda i: i.priority)
        if len(ordered) == 1 or not self._can_parallelize(ordered):
            return [self._execute_one_intent(intent, text, driver_state, callbacks)
                    for intent in ordered]

        max_workers = min(len(ordered), 4)
        logger.info(
            "AgentOrchestrator: parallel dispatch %d intents: %s",
            len(ordered), [i.category for i in ordered],
        )

        result_by_id = {}
        started_at = {intent.id: time.time() for intent in ordered}
        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as pool:
            future_map = {
                pool.submit(self._execute_one_intent, intent, text, driver_state, callbacks): intent
                for intent in ordered
            }
            done, pending = concurrent.futures.wait(
                future_map,
                timeout=PARALLEL_INTENT_TIMEOUT_SEC,
                return_when=concurrent.futures.ALL_COMPLETED,
            )

            for fut in done:
                intent = future_map[fut]
                try:
                    result_by_id[intent.id] = fut.result()
                except Exception as e:
                    logger.exception("Intent execution crashed: %s", intent.id)
                    result_by_id[intent.id] = ExecutionResult(
                        intent_id=intent.id,
                        intent_category=intent.category,
                        agent_name=intent.agent,
                        success=False,
                        error=str(e),
                        duration_ms=(time.time() - started_at[intent.id]) * 1000,
                    )

            for fut in pending:
                intent = future_map[fut]
                fut.cancel()
                logger.warning("Intent execution timed out: %s", intent.id)
                result_by_id[intent.id] = ExecutionResult(
                    intent_id=intent.id,
                    intent_category=intent.category,
                    agent_name=intent.agent,
                    success=False,
                    error=f"intent execution timed out after {PARALLEL_INTENT_TIMEOUT_SEC:.0f}s",
                    duration_ms=(time.time() - started_at[intent.id]) * 1000,
                )

        return [result_by_id[i.id] for i in ordered if i.id in result_by_id]

    def _execute_one_intent(self, intent, text: str, driver_state: dict,
                            callbacks: dict = None) -> ExecutionResult:
        normalized = normalize_intent(intent)
        if callbacks and callbacks.get("on_step"):
            callbacks["on_step"]({
                "intent": normalized.id,
                "agent": normalized.agent,
                "category": normalized.category,
                "description": normalized.description,
                "mode": normalized.mode,
                "confidence": normalized.confidence,
            })

        decision = guard_intent(normalized, driver_state)
        if not decision.allowed:
            result = ExecutionResult(
                intent_id=normalized.id,
                intent_category=normalized.category,
                agent_name=normalized.agent,
                success=True,
                reply_text=decision.message,
                actions=[],
                data={
                    "type": "guard_decision",
                    "mode": decision.mode,
                    "reason": decision.reason,
                    "missing_slots": decision.missing_slots,
                    "intent": {
                        "category": normalized.category,
                        "params": normalized.params,
                        "confidence": normalized.confidence,
                    },
                },
            )
        else:
            result = self._dispatch_intent(normalized, text, driver_state)

        if callbacks and callbacks.get("on_result"):
            callbacks["on_result"]({
                "intent_id": normalized.id,
                "agent": normalized.agent,
                "success": result.success,
                "reply": result.reply_text,
            })

        return result

    def _can_parallelize(self, intents: list) -> bool:
        """判断当前计划是否适合并行执行。"""
        if len(intents) < 2:
            return False

        # ReAct 通常是组合推理/工具循环，可能会自行编排多个动作；避免与外层并行重入。
        if any(i.agent == "react_agent" for i in intents):
            return False

        if any(getattr(i, "params", {}).get("depends_on") or
               getattr(i, "metadata", {}).get("depends_on") for i in intents):
            return False

        # 多个车控/音乐控制可能修改同一状态，保持顺序更可预期。
        mutating_categories = {"ac_control", "music_control", "fatigue_assist"}
        mutating_count = sum(1 for i in intents if i.category in mutating_categories)
        return mutating_count <= 1

    # ── 意图分发 ──

    def _dispatch_intent(self, intent, text: str, driver_state: dict) -> ExecutionResult:
        """
        根据 intent.agent 分发到对应的子 Agent/执行器。
        """
        agent_name = intent.agent
        category = intent.category
        params = intent.params

        if agent_name == "control_executor":
            return self.control_executor.execute(category, params, text)

        elif agent_name == "react_agent":
            return self._run_react_agent(category, params, text, driver_state)

        elif agent_name == "diagnose_agent":
            return self._run_diagnose_agent(category, params, text)

        elif agent_name == "analyze_agent":
            return self._run_analyze_agent(params)

        elif agent_name == "recommend_agent":
            return self._run_recommend_agent(category, params, text)

        else:
            logger.warning(f"未知 agent: {agent_name}，降级到 react_agent")
            return self._run_react_agent(category, params, text, driver_state)

    def _run_react_agent(self, category: str, params: dict, text: str,
                         driver_state: dict) -> ExecutionResult:
        """运行 ReAct Agent（完整的思考-行动循环）。"""
        start = time.time()
        try:
            user_text = text or params.get("text", "") or f"处理 {category} 相关请求"
            result = self.react_agent.chat(user_text, driver_state or {})

            duration = (time.time() - start) * 1000
            return ExecutionResult(
                intent_id=f"react_{category}",
                intent_category=category,
                agent_name="react_agent",
                success=result.get("success", True),
                reply_text=result.get("reply", ""),
                actions=result.get("actions", []),
                data={"thinking_steps": result.get("steps", [])},
                duration_ms=duration,
            )
        except Exception as e:
            duration = (time.time() - start) * 1000
            return ExecutionResult(
                intent_id=f"react_{category}",
                intent_category=category,
                agent_name="react_agent",
                success=False,
                error=str(e),
                duration_ms=duration,
            )

    def _run_diagnose_agent(self, category: str, params: dict, text: str) -> ExecutionResult:
        """运行故障诊断 Agent。"""
        start = time.time()
        try:
            query = text or params.get("description", "车辆故障")
            diag_result = self.diagnose_agent.analyze(query)

            duration = (time.time() - start) * 1000
            return ExecutionResult(
                intent_id="diagnose_1",
                intent_category=category,
                agent_name="diagnose_agent",
                success=diag_result.get("success", True),
                reply_text=diag_result.get("diagnosis", ""),
                actions=[{
                    "type": "diagnosis",
                    "severity": diag_result.get("severity", "unknown"),
                    "suggestions": diag_result.get("suggestions", []),
                }],
                data=diag_result,
                duration_ms=duration,
            )
        except Exception as e:
            duration = (time.time() - start) * 1000
            return ExecutionResult(
                intent_id="diagnose_1",
                intent_category=category,
                agent_name="diagnose_agent",
                success=False,
                error=str(e),
                duration_ms=duration,
            )

    def _run_analyze_agent(self, params: dict) -> ExecutionResult:
        """运行驾驶分析 Agent。"""
        start = time.time()
        try:
            analyze_result = self.analyze_agent.analyze(params)

            duration = (time.time() - start) * 1000
            return ExecutionResult(
                intent_id="analyze_1",
                intent_category="analysis",
                agent_name="analyze_agent",
                success=analyze_result.get("success", True),
                reply_text=analyze_result.get("summary", ""),
                actions=[{
                    "type": "analysis",
                    "score": analyze_result.get("score", 0),
                    "grade": analyze_result.get("grade", ""),
                    "highlights": analyze_result.get("highlights", []),
                }],
                data=analyze_result,
                duration_ms=duration,
            )
        except Exception as e:
            duration = (time.time() - start) * 1000
            return ExecutionResult(
                intent_id="analyze_1",
                intent_category="analysis",
                agent_name="analyze_agent",
                success=False,
                error=str(e),
                duration_ms=duration,
            )

    def _run_recommend_agent(self, category: str, params: dict, text: str) -> ExecutionResult:
        """运行出行建议 Agent。"""
        start = time.time()
        try:
            rec_result = self.recommend_agent.analyze({
                "query": text,
                "category": category,
                **params,
            })

            duration = (time.time() - start) * 1000

            # ── 关键修复：将本轮对话和结果写入 WorkingMemory ──
            # RecommendAgent 不经过 ReActAgent.chat()，所以 WorkingMemory
            # 不会被自动更新。下一轮 ReActAgent 就会完全失忆。
            # 这里手动写入，让后续轮次能看到上下文。
            try:
                wm = self.react_agent.memory.working
                wm.add_message("user", text)
                reply = rec_result.get("reply", "")
                if reply:
                    wm.add_message("assistant", reply)
                # 缓存导航结果摘要到 WorkingMemory
                rec_type = rec_result.get("type", category)
                if rec_type == "navigation" or rec_result.get("destination"):
                    dest = rec_result.get("destination", "")
                    dist = rec_result.get("distance_km", "")
                    dur = rec_result.get("duration_min", "")
                    parts = []
                    if dest:
                        parts.append(f"到{dest}")
                    if dist != "":
                        parts.append(f"{dist}km")
                    if dur != "":
                        parts.append(f"{dur}分钟")
                    summary = " ".join(parts) if parts else "导航已完成"
                    wm.set_last_tool_result("start_navigation", summary)
                    logger.info("RecommendAgent 导航结果已写入 WorkingMemory: %s", summary)
            except Exception as e:
                logger.warning("写入 WorkingMemory 失败（非致命）: %s", e)

            return ExecutionResult(
                intent_id="recommend_1",
                intent_category=category,
                agent_name="recommend_agent",
                success=rec_result.get("success", True),
                reply_text=rec_result.get("reply", ""),
                actions=[{
                    "type": rec_result.get("type", "general"),
                    "suggestions": rec_result.get("suggestions", []),
                }],
                data=rec_result,
                duration_ms=duration,
            )
        except Exception as e:
            duration = (time.time() - start) * 1000
            return ExecutionResult(
                intent_id="recommend_1",
                intent_category=category,
                agent_name="recommend_agent",
                success=False,
                error=str(e),
                duration_ms=duration,
            )

    # ── 结果聚合 ──

    def _aggregate_reply(self, results: List[ExecutionResult], summary: str) -> str:
        """聚合一键回复文本。"""
        if not results:
            return "抱歉，我没有理解您的意思。"

        successful = [r for r in results if r.success]
        failed = [r for r in results if not r.success]

        # 成功的回复拼接
        if successful:
            reply_parts = []
            for r in successful:
                if r.reply_text:
                    reply_parts.append(r.reply_text)
            overall = "，".join(reply_parts)
            if len(overall) > 200:
                overall = overall[:200] + "..."
            return overall

        # 全部失败
        if failed:
            return f"抱歉，操作失败：{failed[0].error}"

        return "好的。"


# ═══════════════════════════════════════════════════════════
#  全局单例
# ═══════════════════════════════════════════════════════════

_orchestrator: Optional[AgentOrchestrator] = None


def get_orchestrator() -> AgentOrchestrator:
    """获取全局编排器单例。"""
    global _orchestrator
    if _orchestrator is None:
        _orchestrator = AgentOrchestrator()
    return _orchestrator
