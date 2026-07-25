"""
EdgeGuard Agent Core — 感知-思考-行动循环 (Agentic Loop)
============================================================

解决旧架构的 6 大缺失：
  1. 规划能力  → GoalStack + TaskPlanner
  2. 工具调用  → ToolRegistry + dynamic dispatch
  3. 多轮记忆  → WorkingMemory + SessionMemory
  4. 自主决策  → ActiveGoal + PriorityEvaluator
  5. 反思纠错  → ReflectionEngine + RetryPolicy
  6. Agent Loop → while not_done: perceive → plan → act → reflect

架构：
  ┌─────────────────────────────────────────────┐
  │  Perception (摄像头/语音/手势/车辆CAN数据)   │
  └──────────────┬──────────────────────────────┘
                 │
  ┌──────────────▼──────────────────────────────┐
  │  WorkingMemory (短期上下文窗口)              │
  │  - 最近 N 轮对话                           │
  │  - 当前环境感知快照                        │
  │  - 活跃目标栈                              │
  └──────────────┬──────────────────────────────┘
                 │
  ┌──────────────▼──────────────────────────────┐
  │  GoalStack (目标管理)                      │
  │  - 自主目标（疲劳提醒、安全监控）          │
  │  - 用户目标（开空调、放音乐）              │
  │  - 系统目标（数据同步、状态上报）          │
  └──────────────┬──────────────────────────────┘
                 │
  ┌──────────────▼──────────────────────────────┐
  │  TaskPlanner (规划器)                      │
  │  - 目标 → 子任务分解                       │
  │  - 依赖排序 + 并行识别                     │
  │  - 工具选择（动态从 ToolRegistry 选）      │
  └──────────────┬──────────────────────────────┘
                 │
  ┌──────────────▼──────────────────────────────┐
  │  ToolExecutor (工具执行)                   │
  │  - 调用 AC API / Music API / Nav API       │
  │  - 调用 RAG 知识库                         │
  │  - 调用 LLM 做复杂推理                     │
  └──────────────┬──────────────────────────────┘
                 │
  ┌──────────────▼──────────────────────────────┐
  │  ReflectionEngine (反思)                   │
  │  - 结果验证（空调真的开了吗？）            │
  │  - 用户反馈检测（摇头 = 不满意）           │
  │  - 自动重试 / 回退                         │
  └──────────────┬──────────────────────────────┘
                 │
  ┌──────────────▼──────────────────────────────┐
  │  SessionMemory (持久记忆)                  │
  │  - 用户偏好（常设温度、喜欢的歌手）        │
  │  - 历史成功率统计                          │
  └─────────────────────────────────────────────┘
"""
import json
import time
import logging
from typing import Any, Optional
from dataclasses import dataclass, field, asdict
from collections import deque

logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════════
#  数据模型
# ═══════════════════════════════════════════════

@dataclass
class Perception:
    """感知输入 — 一帧环境快照"""
    timestamp: float = field(default_factory=time.time)
    gaze: str = "center"           # 视线方向
    gesture: str = ""              # 当前手势
    gesture_action: str = ""       # 手势映射的 action
    speech_text: str = ""          # 语音识别文本
    alert_category: str = ""       # 当前告警类别
    alert_severity: str = "normal" # 告警级别
    driver_risk: str = "safe"      # 安全评估
    fatigue_level: str = "normal"  # 疲劳级别
    ac_state: dict = field(default_factory=dict)
    music_state: dict = field(default_factory=dict)
    nav_state: dict = field(default_factory=dict)

@dataclass
class Goal:
    """目标 — Agent 要达成的事项"""
    id: str
    description: str
    priority: int = 5              # 1-10, 越小越优先
    source: str = "user"           # user / system / autonomous
    status: str = "pending"        # pending / active / done / failed
    created_at: float = field(default_factory=time.time)
    deadline: Optional[float] = None
    parent_id: Optional[str] = None
    metadata: dict = field(default_factory=dict)

@dataclass
class SubTask:
    """子任务 — 规划器分解后的可执行单元"""
    id: str
    description: str
    tool_name: str = ""            # 要调用的工具名
    tool_args: dict = field(default_factory=dict)
    depends_on: list = field(default_factory=list)  # 依赖的其他 task id
    status: str = "pending"        # pending / running / done / failed
    result: Any = None
    retry_count: int = 0
    max_retry: int = 2

@dataclass
class ActionTrace:
    """行动轨迹 — 用于反思"""
    timestamp: float
    action: str
    input_data: dict
    output_data: dict
    success: bool
    latency_ms: int = 0

# ═══════════════════════════════════════════════
#  WorkingMemory — 短期上下文窗口
# ═══════════════════════════════════════════════

class WorkingMemory:
    """
    工作记忆 — 类似人类短期记忆，容量有限，随时间衰减。
    存储最近 N 轮交互 + 当前环境感知。
    """
    def __init__(self, max_turns: int = 10, max_perceptions: int = 30):
        self.turns: deque[dict] = deque(maxlen=max_turns)
        self.perceptions: deque[Perception] = deque(maxlen=max_perceptions)
        self.current_goals: list[Goal] = []
        self.current_plan: list[SubTask] = []
        self.last_action_result: Optional[dict] = None

    def add_turn(self, user_input: str, agent_response: str, actions: list = None):
        self.turns.append({
            "timestamp": time.time(),
            "user": user_input,
            "agent": agent_response,
            "actions": actions or [],
        })

    def add_perception(self, p: Perception):
        self.perceptions.append(p)

    def get_recent_perception(self, seconds: float = 5.0) -> Optional[Perception]:
        """获取最近几秒内的感知"""
        now = time.time()
        for p in reversed(self.perceptions):
            if now - p.timestamp <= seconds:
                return p
        return None

    def get_summary(self) -> str:
        """生成工作记忆摘要，供 LLM 使用"""
        lines = []
        if self.current_goals:
            lines.append(f"当前目标: {', '.join(g.description for g in self.current_goals if g.status == 'active')}")
        if self.turns:
            lines.append(f"最近对话 ({len(self.turns)} 轮):")
            for t in list(self.turns)[-3:]:
                lines.append(f"  用户: {t['user'][:50]} | Agent: {t['agent'][:50]}")
        p = self.get_recent_perception()
        if p:
            lines.append(f"环境: 视线={p.gaze}, 手势={p.gesture}, 风险={p.driver_risk}, 告警={p.alert_category}")
        return "\n".join(lines)

# ═══════════════════════════════════════════════
#  SessionMemory — 跨会话持久记忆
# ═══════════════════════════════════════════════

class SessionMemory:
    """
    会话记忆 — 跨轮次持久化。
    存用户偏好、历史成功率、常见指令模式。
    """
    def __init__(self, storage_path: Optional[str] = None):
        self.preferences: dict = {}       # {"ac_temp": 24, "music_artist": "周杰伦"}
        self.success_stats: dict = {}     # {"TurnOnAC": {"ok": 15, "fail": 1}}
        self.storage_path = storage_path
        if storage_path:
            self._load()

    def set_pref(self, key: str, value: Any):
        self.preferences[key] = value
        self._save()

    def get_pref(self, key: str, default: Any = None) -> Any:
        return self.preferences.get(key, default)

    def record_success(self, action: str, success: bool):
        if action not in self.success_stats:
            self.success_stats[action] = {"ok": 0, "fail": 0}
        self.success_stats[action]["ok" if success else "fail"] += 1

    def get_success_rate(self, action: str) -> float:
        s = self.success_stats.get(action, {"ok": 0, "fail": 0})
        total = s["ok"] + s["fail"]
        return s["ok"] / total if total > 0 else 0.5

    def _load(self):
        try:
            with open(self.storage_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                self.preferences = data.get("preferences", {})
                self.success_stats = data.get("success_stats", {})
        except Exception:
            pass

    def _save(self):
        if not self.storage_path:
            return
        try:
            with open(self.storage_path, "w", encoding="utf-8") as f:
                json.dump({"preferences": self.preferences, "success_stats": self.success_stats}, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.warning(f"SessionMemory save failed: {e}")

# ═══════════════════════════════════════════════
#  GoalStack — 目标管理
# ═══════════════════════════════════════════════

class GoalStack:
    """
    目标栈 — 管理多层级目标。
    支持：用户目标 + 系统自主目标（安全监控等）。
    """
    def __init__(self):
        self._goals: list[Goal] = []
        self._counter = 0

    def _next_id(self) -> str:
        self._counter += 1
        return f"goal_{self._counter}"

    def push(self, description: str, priority: int = 5, source: str = "user", **meta) -> Goal:
        g = Goal(id=self._next_id(), description=description, priority=priority, source=source, metadata=meta)
        self._goals.append(g)
        self._goals.sort(key=lambda x: x.priority)
        logger.info(f"Goal pushed: {description} (p={priority}, src={source})")
        return g

    def pop(self) -> Optional[Goal]:
        active = [g for g in self._goals if g.status == "active"]
        if active:
            return active[0]
        pending = [g for g in self._goals if g.status == "pending"]
        if pending:
            pending[0].status = "active"
            return pending[0]
        return None

    def mark_done(self, goal_id: str):
        for g in self._goals:
            if g.id == goal_id:
                g.status = "done"
                logger.info(f"Goal done: {g.description}")

    def mark_failed(self, goal_id: str):
        for g in self._goals:
            if g.id == goal_id:
                g.status = "failed"
                logger.warning(f"Goal failed: {g.description}")

    def peek_top(self) -> Optional[Goal]:
        """查看当前最高优先级目标（不弹出）"""
        active = [g for g in self._goals if g.status == "active"]
        if active:
            return active[0]
        pending = [g for g in self._goals if g.status == "pending"]
        return pending[0] if pending else None

    def get_autonomous_goals(self) -> list[Goal]:
        """获取系统自主生成的目标"""
        return [g for g in self._goals if g.source == "autonomous" and g.status in ("pending", "active")]

    def clear_completed(self):
        self._goals = [g for g in self._goals if g.status not in ("done", "failed")]

# ═══════════════════════════════════════════════
#  EdgeGuardAgent — Agentic Loop 主循环
# ═══════════════════════════════════════════════

class EdgeGuardAgent:
    """
    EdgeGuard 智能体 — 真正的 Agentic Loop。

    使用方式：
        agent = EdgeGuardAgent()
        while True:
            perception = agent.perceive(camera_state, speech, gesture)
            result = agent.step(perception)
            if result:
                推送到前端 / 执行动作
    """

    def __init__(self, memory_path: Optional[str] = None):
        self.memory = WorkingMemory()
        self.session = SessionMemory(memory_path)
        self.goals = GoalStack()
        self.traces: deque[ActionTrace] = deque(maxlen=50)

        # 工具注册表（延迟加载避免循环导入）
        self._tools: dict[str, callable] = {}
        self._tools_loaded = False

        # 自主监控状态
        self._last_safety_check = 0
        self._safety_check_interval = 3.0  # 每 3 秒检查一次安全目标

    # ── 工具注册 ──

    def _load_tools(self):
        if self._tools_loaded:
            return
        from modules.ai.tools import TOOL_EXECUTOR
        self._tools = dict(TOOL_EXECUTOR)
        self._tools_loaded = True
        logger.info(f"Agent tools loaded: {list(self._tools.keys())}")

    def register_tool(self, name: str, func: callable):
        self._tools[name] = func

    # ── 感知 (Perceive) ──

    def perceive(self, state: dict) -> Perception:
        """
        从系统状态中提取感知快照。
        state: camera.get_state() 返回的 dict
        """
        p = Perception(
            gaze=state.get("gaze", "center"),
            gesture=state.get("gesture", ""),
            gesture_action=state.get("gesture_action", ""),
            speech_text=state.get("speech_text", ""),
            alert_category=state.get("alert_category", ""),
            alert_severity=state.get("severity", "normal"),
            driver_risk="safe" if state.get("severity", "normal") == "normal" else state.get("severity", "safe"),
            fatigue_level=state.get("fatigue_level", "normal"),
            ac_state={"power": state.get("ac_power"), "temp": state.get("ac_temp")},
            music_state={"playing": state.get("music_playing"), "song": state.get("music_song")},
        )
        self.memory.add_perception(p)
        self._check_autonomous_goals(p)
        return p

    def _check_autonomous_goals(self, p: Perception):
        """根据感知自动推入安全/监控类目标"""
        now = time.time()
        if now - self._last_safety_check < self._safety_check_interval:
            return
        self._last_safety_check = now

        # 疲劳告警 → 自动推入提醒目标
        if p.fatigue_level in ("warning", "danger"):
            existing = [g for g in self.goals.get_autonomous_goals() if "疲劳" in g.description]
            if not existing:
                self.goals.push("检测到疲劳驾驶，提醒休息并降低车内温度", priority=1, source="autonomous", alert_type="fatigue")

        # 视线偏离严重 → 自动推入安全提示目标
        if p.alert_category == "gaze" and p.alert_severity == "severe":
            existing = [g for g in self.goals.get_autonomous_goals() if "视线" in g.description]
            if not existing:
                self.goals.push("视线严重偏离，需要确认注意力", priority=1, source="autonomous", alert_type="gaze")

    # ── 规划 (Plan) ──

    def _plan_for_goal(self, goal: Goal) -> list[SubTask]:
        """
        将目标分解为子任务。
        简单规则版：根据目标描述匹配预设模板。
        复杂版：可调用 LLM 做动态分解。
        """
        desc = goal.description
        tasks = []

        # 模板匹配
        if "空调" in desc or "温度" in desc:
            if "打开" in desc or "开启" in desc or "热" in desc:
                tasks.append(SubTask(id="t1", description="打开空调", tool_name="ac_command", tool_args={"command": "TurnOnAC"}))
            elif "关闭" in desc or "关" in desc or "冷" in desc:
                tasks.append(SubTask(id="t1", description="关闭空调", tool_name="ac_command", tool_args={"command": "TurnOffAC"}))
            if "度" in desc or "温度" in desc:
                import re
                m = re.search(r"(\d{1,2})", desc)
                if m:
                    tasks.append(SubTask(id="t2", description="设定温度", tool_name="ac_command", tool_args={"command": "set", "temperature": int(m.group(1))}, depends_on=["t1"]))

        elif "音乐" in desc or "歌" in desc or "播放" in desc:
            if "停止" in desc or "暂停" in desc or "关闭" in desc:
                tasks.append(SubTask(id="t1", description="停止音乐", tool_name="music_command", tool_args={"command": "StopMusic"}))
            elif "下一首" in desc or "切歌" in desc:
                tasks.append(SubTask(id="t1", description="下一首", tool_name="music_command", tool_args={"command": "next_track"}))
            elif "上一首" in desc:
                tasks.append(SubTask(id="t1", description="上一首", tool_name="music_command", tool_args={"command": "previous_track"}))
            else:
                # 播放某首歌：先搜索，再播放
                tasks.append(SubTask(id="t1", description="搜索歌曲", tool_name="music_search", tool_args={"keyword": desc.replace("播放", "").replace("音乐", "").strip() or "热门歌曲"}))
                tasks.append(SubTask(id="t2", description="播放第一首", tool_name="music_play", tool_args={"index": 0}, depends_on=["t1"]))

        elif "疲劳" in desc or "休息" in desc:
            tasks.append(SubTask(id="t1", description="降低空调温度提神", tool_name="ac_command", tool_args={"command": "set", "temperature": 20}))
            tasks.append(SubTask(id="t2", description="TTS提醒休息", tool_name="tts_speak", tool_args={"text": "检测到疲劳驾驶，请就近休息。已为您调低温度提神。"}, depends_on=["t1"]))

        elif "视线" in desc or "注意" in desc:
            tasks.append(SubTask(id="t1", description="TTS提醒看路", tool_name="tts_speak", tool_args={"text": "请注意前方道路，确保行车安全。"}))

        else:
            # 默认：直接尝试执行
            tasks.append(SubTask(id="t1", description=f"执行: {desc}", tool_name="fallback_llm", tool_args={"query": desc}))

        return tasks

    # ── 执行 (Act) ──

    def _execute_task(self, task: SubTask) -> dict:
        """执行单个子任务，返回结果"""
        self._load_tools()
        tool = self._tools.get(task.tool_name)
        if not tool:
            return {"success": False, "error": f"Tool '{task.tool_name}' not found"}

        start = time.time()
        try:
            result = tool(**task.tool_args)
            success = result.get("success", True) if isinstance(result, dict) else True
            latency = int((time.time() - start) * 1000)
            self.traces.append(ActionTrace(
                timestamp=time.time(), action=task.tool_name,
                input_data=task.tool_args, output_data=result if isinstance(result, dict) else {"result": str(result)},
                success=success, latency_ms=latency
            ))
            return {"success": success, "result": result}
        except Exception as e:
            logger.error(f"Task execution failed: {e}")
            return {"success": False, "error": str(e)}

    def _run_plan(self, plan: list[SubTask]) -> list[SubTask]:
        """执行计划（支持依赖排序）"""
        done_ids = set()
        for task in plan:
            # 检查依赖是否完成
            if task.depends_on and not all(d in done_ids for d in task.depends_on):
                continue
            task.status = "running"
            result = self._execute_task(task)
            task.result = result
            task.status = "done" if result["success"] else "failed"
            done_ids.add(task.id)

            # 失败重试
            if not result["success"] and task.retry_count < task.max_retry:
                task.retry_count += 1
                task.status = "running"
                result2 = self._execute_task(task)
                task.result = result2
                task.status = "done" if result2["success"] else "failed"

        return plan

    # ── 反思 (Reflect) ──

    def _reflect(self, goal: Goal, plan: list[SubTask]) -> dict:
        """
        反思执行结果：
        - 所有子任务成功？→ goal done
        - 有失败？→ 分析原因，决定是否重试或降级
        - 用户可能有非语言反馈（摇头 = 不满意）
        """
        failed = [t for t in plan if t.status == "failed"]
        all_done = all(t.status == "done" for t in plan)

        if all_done:
            self.goals.mark_done(goal.id)
            self.session.record_success(goal.description, True)
            return {"status": "success", "message": f"目标完成: {goal.description}"}

        if failed:
            self.session.record_success(goal.description, False)
            # 检查是否有用户负面反馈（通过感知）
            recent_p = self.memory.get_recent_perception(3.0)
            user_dissatisfied = recent_p and recent_p.gesture in ("thumbs_down", "shake_head") if hasattr(recent_p, 'gesture') else False

            if user_dissatisfied:
                return {"status": "failed", "message": f"执行失败且检测到用户不满: {', '.join(t.description for t in failed)}", "needs_retry": False}

            return {"status": "partial", "message": f"部分失败: {', '.join(t.description for t in failed)}", "needs_retry": True}

        return {"status": "unknown", "message": "执行状态异常"}

    # ── 主循环入口 (Step) ──

    def step(self, perception: Optional[Perception] = None) -> Optional[dict]:
        """
        Agentic Loop 单步执行。
        返回要执行的动作列表 + 回复文本，或 None（无活跃目标）。
        """
        # 1. 获取当前最高优先级目标
        goal = self.goals.pop()
        if not goal:
            return None

        # 2. 规划
        plan = self._plan_for_goal(goal)
        self.memory.current_plan = plan

        # 3. 执行
        executed = self._run_plan(plan)

        # 4. 反思
        reflection = self._reflect(goal, executed)

        # 5. 组装输出
        actions = [t.result for t in executed if t.status == "done" and t.result]
        reply = reflection.get("message", "")

        # 6. 记录到工作记忆
        self.memory.add_turn(
            user_input=goal.description,
            agent_response=reply,
            actions=[{"tool": t.tool_name, "args": t.tool_args, "status": t.status} for t in executed]
        )

        return {
            "goal_id": goal.id,
            "goal_description": goal.description,
            "status": reflection["status"],
            "reply": reply,
            "actions": actions,
            "traces": [asdict(t) for t in self.traces if t.timestamp > time.time() - 10],
        }

    # ── 用户指令入口 ──

    def handle_user_input(self, text: str, gesture: str = "", driver_state: dict = None) -> dict:
        """
        用户发起交互时的入口。
        推入目标 + 立即执行一步。
        """
        goal_desc = text or f"手势指令: {gesture}"
        goal = self.goals.push(goal_desc, priority=3, source="user", gesture=gesture, speech=text)

        # 如果有语音/手势输入，也加入感知
        if driver_state:
            p = self.perceive(driver_state)
        else:
            p = None

        return self.step(p)

    def get_thinking_chain(self) -> list[dict]:
        """获取思维链，供前端可视化"""
        chain = []
        for t in self.traces:
            chain.append({
                "time": time.strftime("%H:%M:%S", time.localtime(t.timestamp)),
                "action": t.action,
                "success": t.success,
                "latency_ms": t.latency_ms,
            })
        return chain
