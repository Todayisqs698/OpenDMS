"""
LangGraph 多 Agent 编排引擎 — 真正的状态图编排

三个 Agent 并行分析，条件路由，安全 Agent 优先级最高。
如果 langgraph 未安装，自动降级为顺序调用模式。
所有 Agent 调用走 safe_executor，任何 Agent 崩了都不影响主流程。
"""
import logging
from typing import TypedDict, Optional
from modules.ai.safe_executor import safe_agent_call

logger = logging.getLogger(__name__)

# ── 状态定义 ──

class AgentState(TypedDict):
    """LangGraph 状态：在各节点间流转"""
    # 输入
    gaze_data: dict
    gesture_data: dict
    speech_data: dict
    head_pose_data: Optional[dict]
    context: dict

    # 各 Agent 输出
    safety_result: Optional[dict]
    interaction_result: Optional[dict]
    environment_result: Optional[dict]

    # 最终决策
    action_code: str
    recommendation_text: str
    risk_level: str
    source: str
    edge_cloud_route: str


class Orchestrator:
    """
    LangGraph 编排器 — 三 Agent 协作决策

    状态图流程：
        START → safety_agent → [条件路由]
          ├─ dangerous/distracted → END（直接告警，跳过其他Agent）
          └─ safe → interaction_agent + environment_agent（并行）→ merge → END

    关键设计：安全 Agent 的决策永远覆盖其他 Agent。
    """

    def __init__(self):
        self.safety_agent = None
        self.interaction_agent = None
        self.environment_agent = None
        self._graph = None
        self._use_graph = False  # 是否使用真正的 LangGraph
        self._init_agents()
        self._init_graph()

    def _init_agents(self):
        """加载三个 Agent"""
        for name, cls_path in [
            ("SafetyAgent", "modules.ai.agents.safety_agent"),
            ("InteractionAgent", "modules.ai.agents.interaction_agent"),
            ("EnvironmentAgent", "modules.ai.agents.environment_agent"),
        ]:
            try:
                mod = __import__(cls_path, fromlist=[name])
                agent_cls = getattr(mod, name)
                if name == "SafetyAgent":
                    self.safety_agent = agent_cls()
                elif name == "InteractionAgent":
                    self.interaction_agent = agent_cls()
                else:
                    self.environment_agent = agent_cls()
            except Exception as e:
                logger.warning(f"{name} 加载失败: {e}")

    def _init_graph(self):
        """尝试构建 LangGraph 状态图，失败则降级为顺序模式"""
        try:
            from langgraph.graph import StateGraph, END

            builder = StateGraph(AgentState)

            # 节点
            builder.add_node("safety_check", self._node_safety)
            builder.add_node("interaction_analyze", self._node_interaction)
            builder.add_node("environment_analyze", self._node_environment)
            builder.add_node("merge_decision", self._node_merge)

            # 入口
            builder.set_entry_point("safety_check")

            # 条件路由：安全 Agent 判定危险 → 直接结束
            builder.add_conditional_edges(
                "safety_check",
                self._route_after_safety,
                {
                    "end": END,
                    "continue": "interaction_analyze",
                }
            )

            # 交互 → 环境（并行会更好，但顺序也能体现优先级）
            builder.add_edge("interaction_analyze", "environment_analyze")
            builder.add_edge("environment_analyze", "merge_decision")
            builder.add_edge("merge_decision", END)

            self._graph = builder.compile()
            self._use_graph = True
            logger.info("LangGraph 状态图初始化成功")

        except ImportError:
            logger.warning("langgraph 未安装，降级为顺序编排模式")
            self._use_graph = False
        except Exception as e:
            logger.warning(f"LangGraph 初始化失败: {e}，降级为顺序编排模式")
            self._use_graph = False

    # ── 图节点 ──

    def _node_safety(self, state: AgentState) -> AgentState:
        """安全 Agent 节点"""
        result = safe_agent_call(
            self.safety_agent, "analyze",
            {"gaze": state.get("gaze_data", {}), "head_pose": state.get("head_pose_data")},
            default={"risk_level": "normal", "alert": ""},
            name="safety_agent"
        )
        state["safety_result"] = result
        state["risk_level"] = result.get("risk_level", "normal")
        return state

    def _route_after_safety(self, state: AgentState) -> str:
        """条件路由：危险状态直接结束"""
        risk = state.get("risk_level", "normal")
        if risk in ("dangerous", "distracted"):
            state["action_code"] = "distract"
            state["recommendation_text"] = state.get("safety_result", {}).get("alert", "请注视前方")
            state["source"] = "safety_agent_priority"
            return "end"
        return "continue"

    def _node_interaction(self, state: AgentState) -> AgentState:
        """交互 Agent 节点"""
        result = safe_agent_call(
            self.interaction_agent, "analyze",
            {"gesture": state.get("gesture_data", {}), "speech": state.get("speech_data", {})},
            default={},
            name="interaction_agent"
        )
        state["interaction_result"] = result
        return state

    def _node_environment(self, state: AgentState) -> AgentState:
        """环境 Agent 节点"""
        result = safe_agent_call(
            self.environment_agent, "analyze",
            {},
            default={},
            name="environment_agent"
        )
        state["environment_result"] = result
        return state

    def _node_merge(self, state: AgentState) -> AgentState:
        """融合决策节点：交互结果为主，安全结果兜底"""
        interaction = state.get("interaction_result", {})
        env = state.get("environment_result", {})

        state["action_code"] = interaction.get("action_code", "unknown")
        state["recommendation_text"] = interaction.get("recommendation_text", "")
        state["source"] = "orchestrator"
        return state

    # ── 公共接口 ──

    def process(self, multimodal_input) -> dict:
        """
        处理多模态输入，返回决策结果。

        优先使用 LangGraph 状态图；不可用时降级为顺序调用。
        """
        initial_state: AgentState = {
            "gaze_data": multimodal_input.gaze_data,
            "gesture_data": multimodal_input.gesture_data,
            "speech_data": multimodal_input.speech_data,
            "head_pose_data": getattr(multimodal_input, 'head_pose_data', None),
            "context": multimodal_input.context if hasattr(multimodal_input, 'context') else {},
            "safety_result": None,
            "interaction_result": None,
            "environment_result": None,
            "action_code": "unknown",
            "recommendation_text": "",
            "risk_level": "normal",
            "source": "orchestrator",
            "edge_cloud_route": "local",
        }

        if self._use_graph and self._graph:
            try:
                final = self._graph.invoke(initial_state)
                return {
                    "action_code": final.get("action_code", "unknown"),
                    "recommendation_text": final.get("recommendation_text", ""),
                    "risk_level": final.get("risk_level", "normal"),
                    "source": final.get("source", "orchestrator"),
                    "env_context": final.get("environment_result", {}),
                }
            except Exception as e:
                logger.warning(f"LangGraph 执行失败: {e}，降级顺序模式")

        # 降级：顺序调用
        return self._process_sequential(initial_state)

    def _process_sequential(self, state: AgentState) -> dict:
        """顺序编排（LangGraph 不可用时的降级方案）"""
        safety = safe_agent_call(
            self.safety_agent, "analyze",
            {"gaze": state["gaze_data"], "head_pose": state["head_pose_data"]},
            default={"risk_level": "normal", "alert": ""},
            name="safety_agent"
        )
        if safety.get("risk_level") in ("dangerous", "distracted"):
            return {
                "action_code": "distract",
                "recommendation_text": safety.get("alert", "请注视前方道路"),
                "risk_level": safety.get("risk_level"),
                "source": "safety_agent",
            }

        interaction = safe_agent_call(
            self.interaction_agent, "analyze",
            {"gesture": state["gesture_data"], "speech": state["speech_data"]},
            default={},
            name="interaction_agent"
        )

        env = safe_agent_call(
            self.environment_agent, "analyze", {},
            default={},
            name="environment_agent"
        )

        return {
            "action_code": interaction.get("action_code", "unknown"),
            "recommendation_text": interaction.get("recommendation_text", ""),
            "risk_level": "normal",
            "source": "orchestrator_sequential",
            "env_context": env,
        }
