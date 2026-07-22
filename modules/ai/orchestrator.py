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
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


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
            songs = data.get("songs", [])  # /api/music/search 返回 {"status":"ok","songs":[...]}
            if songs:
                first = songs[0]
                httpx.post(f"{self._backend_base}/api/music/play",
                          json={"song_id": first.get("id")}, timeout=5)
                actions.append({"type": "music", "command": "play",
                               "song": first.get("name", ""), "artist": singer})
                return f"开始播放 {singer} 的《{first.get('name', '')}》"
            actions.append({"type": "music", "command": "search_failed"})
            return f"没有找到 {singer} 的歌曲"

        if action == "play":
            httpx.post(f"{self._backend_base}/api/music/play", timeout=5)
            actions.append({"type": "music", "command": "play"})
            return "开始播放音乐"

        if action == "pause":
            httpx.post(f"{self._backend_base}/api/music/pause", timeout=5)
            actions.append({"type": "music", "command": "pause"})
            return "音乐已暂停"

        # 默认播放
        httpx.post(f"{self._backend_base}/api/music/play", timeout=5)
        actions.append({"type": "music", "command": "play"})
        return "开始播放音乐"


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

    # ── 延迟加载 ──

    @property
    def control_executor(self):
        if self._control_executor is None:
            self._control_executor = ControlExecutor()
        return self._control_executor

    @property
    def react_agent(self):
        if self._react_agent is None:
            from modules.ai.agent_graph import ReActAgent
            self._react_agent = ReActAgent()
        return self._react_agent

    @property
    def diagnose_agent(self):
        if self._diagnose_agent is None:
            from modules.ai.agents.diagnose_agent import DiagnoseAgent
            self._diagnose_agent = DiagnoseAgent()
        return self._diagnose_agent

    @property
    def analyze_agent(self):
        if self._analyze_agent is None:
            from modules.ai.agents.analyze_agent import AnalyzeAgent
            self._analyze_agent = AnalyzeAgent()
        return self._analyze_agent

    @property
    def recommend_agent(self):
        if self._recommend_agent is None:
            from modules.ai.agents.recommend_agent import RecommendAgent
            self._recommend_agent = RecommendAgent()
        return self._recommend_agent

    @property
    def intention_agent(self):
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
        plan = self.intention_agent.analyze(text, ds)
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

        # Step 3: 按优先级执行各意图
        results = []
        all_actions = []

        for intent in plan.intents:
            if callbacks and callbacks.get("on_step"):
                callbacks["on_step"]({
                    "intent": intent.id,
                    "agent": intent.agent,
                    "category": intent.category,
                    "description": intent.description,
                })

            result = self._dispatch_intent(intent, text, ds)
            results.append(result)
            all_actions.extend(result.actions)

            if callbacks and callbacks.get("on_result"):
                callbacks["on_result"]({
                    "intent_id": intent.id,
                    "agent": intent.agent,
                    "success": result.success,
                    "reply": result.reply_text,
                })

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
