"""
Safety Gate — Agent 循环前置安全过滤器
每次 Agent 循环开始前调用 SafetyAgent.analyze() 评估驾驶员状态，
根据 risk_level 过滤可用工具列表。
"""
import logging

logger = logging.getLogger(__name__)

# 各风险级别下允许使用的工具白名单
TOOL_RESTRICTIONS = {
    "normal": None,          # None 表示所有工具可用
    "attn_declining": None,  # 所有工具可用，但注入提示
    "distracted": ["speak", "alert_driver", "ask_clarification", "control_ac"],  # 娱乐受限
    "dangerous": ["speak", "alert_driver"],  # 仅安全告警和语音反馈
}

# 各级别的系统提示注入
# 保留硬编码兜底（向后兼容），优先从模板库获取
SAFETY_SYSTEM_PROMPTS = {
    "normal": "",
    "attn_declining": "【注意】驾驶员注意力开始下降，优先执行安全相关任务，避免长时间交互。",
    "distracted": "【警告】驾驶员处于分心状态，音乐和导航功能已禁用。优先提醒驾驶员注意安全。",
    "dangerous": "【紧急】驾驶员处于危险状态！只能执行安全告警，禁止其他操作。",
}


def _get_safety_prompt(risk_level: str, **extra) -> str:
    """
    获取安全提示文本。
    优先从 Prompt 模板库取（支持参数填充），失败则用硬编码兜底。
    
    Args:
        risk_level: normal / attn_declining / distracted / dangerous
        **extra: 模板参数，如 max_reply_len, extra_hint, risk_reason 等
    """
    try:
        from modules.ai.prompts import get_safety_prompt
        return get_safety_prompt(risk_level, **extra)
    except Exception:
        return SAFETY_SYSTEM_PROMPTS.get(risk_level, "")

def apply_safety_gate(risk_level: str, all_tools: list, driver_state: dict = None) -> dict:
    """
    应用安全门控。

    Args:
        risk_level: SafetyAgent.analyze() 返回的风险等级
        all_tools: 完整的工具 schema 列表
        driver_state: 驾驶员状态（可选，用于填充模板上下文参数）

    Returns:
        {
            "allowed_tools": list,  # 过滤后的工具列表
            "risk_level": str,      # 传入的风险等级
            "safety_prompt": str,   # 注入的系统提示
            "is_emergency": bool,   # 是否紧急（dangerous 级别直接告警，跳过 Agent）
        }
    """
    is_emergency = risk_level == "dangerous"

    allowed_names = TOOL_RESTRICTIONS.get(risk_level)
    if allowed_names is None:
        allowed = all_tools
    else:
        allowed = [t for t in all_tools if t["function"]["name"] in allowed_names]

    # 构建模板参数，根据 driver_state 提供上下文信息
    ds = driver_state or {}
    extra_params = {}
    if risk_level == "attn_declining":
        extra_params["max_reply_len"] = 20
    elif risk_level == "distracted":
        gaze = ds.get("gaze", "未知方向")
        extra_params["extra_hint"] = f"当前视线方向: {gaze}"
    elif risk_level == "dangerous":
        gaze = ds.get("gaze", "未知方向")
        extra_params["risk_reason"] = f"视线严重偏离({gaze})"

    safety_prompt = _get_safety_prompt(risk_level, **extra_params)

    if is_emergency:
        logger.warning(f"Safety gate EMERGENCY: risk={risk_level}, only tools: {[t['function']['name'] for t in allowed]}")

    return {
        "allowed_tools": allowed,
        "risk_level": risk_level,
        "safety_prompt": safety_prompt,
        "is_emergency": is_emergency,
    }

def get_risk_level_from_safety_agent(driver_state: dict) -> str:
    """
    调用 SafetyAgent.analyze() 获取风险等级。
    driver_state 是从 camera/sensor 汇总的驾驶状态。
    """
    try:
        from modules.ai.agents.safety_agent import SafetyAgent
        agent = SafetyAgent()
        data = {
            "gaze": driver_state.get("gaze", "center"),
            "head_pose": driver_state.get("head_pose", {}),
            "eye_frames": driver_state.get("eye_frames", []),
        }
        # 使用简化接口
        risk = agent.calculate_risk(
            gaze_state=driver_state.get("gaze", "center"),
            gaze_duration=driver_state.get("gaze_duration", 0),
            perclos=driver_state.get("perclos", 0),
            fatigue_score=driver_state.get("fatigue_score", 0),
        )
        return risk.get("risk_level", "normal")
    except Exception as e:
        logger.warning(f"SafetyAgent call failed: {e}, defaulting to normal")
        return "normal"