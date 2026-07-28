"""Intent normalization and pre-execution guardrails for the AI copilot."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


EXECUTE = "EXECUTE"
CLARIFY = "CLARIFY"
ANSWER_ONLY = "ANSWER_ONLY"
BLOCK = "BLOCK"

DISTRACTING_CATEGORIES = {
    "music_control",
    "trip_plan",
    "attractions",
    "diagnosis",
    "weather",
    "location_management",
}

ALLOWED_WHILE_DANGEROUS = {
    "safety",
    "fatigue_assist",
    "navigation",
    "context_query",
    "chitchat",
}


@dataclass
class NormalizedIntent:
    id: str
    category: str
    agent: str
    priority: int
    description: str = ""
    params: dict[str, Any] = field(default_factory=dict)
    confidence: float = 0.0
    mode: str = EXECUTE
    missing_slots: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class GuardDecision:
    allowed: bool
    mode: str = EXECUTE
    reason: str = ""
    message: str = ""
    missing_slots: list[str] = field(default_factory=list)


def normalize_intent(intent) -> NormalizedIntent:
    """Convert rule/LLM intent objects into a single execution contract."""
    metadata = dict(getattr(intent, "metadata", {}) or {})
    params = dict(getattr(intent, "params", {}) or {})
    confidence = float(getattr(intent, "confidence", 0.0) or 0.0)
    category = getattr(intent, "category", "chitchat") or "chitchat"

    missing_slots = _missing_required_slots(category, params)
    mode = metadata.get("mode") or metadata.get("decision_mode") or EXECUTE
    if missing_slots:
        mode = CLARIFY
    elif confidence and confidence < _min_confidence(category):
        mode = ANSWER_ONLY

    return NormalizedIntent(
        id=getattr(intent, "id", "intent"),
        category=category,
        agent=getattr(intent, "agent", "react_agent"),
        priority=int(getattr(intent, "priority", 9) or 9),
        description=getattr(intent, "description", "") or "",
        params=params,
        confidence=confidence,
        mode=mode,
        missing_slots=missing_slots,
        metadata=metadata,
    )


def guard_intent(intent: NormalizedIntent, driver_state: dict | None = None) -> GuardDecision:
    """Apply slot validation and driving-safety policy before tool execution."""
    driver_state = driver_state or {}
    safety_level = _safety_level(driver_state)

    if intent.missing_slots:
        return GuardDecision(
            allowed=False,
            mode=CLARIFY,
            reason="missing_required_slots",
            message=_clarification_message(intent),
            missing_slots=intent.missing_slots,
        )

    if intent.mode == ANSWER_ONLY:
        return GuardDecision(
            allowed=False,
            mode=ANSWER_ONLY,
            reason="low_confidence",
            message="我还不确定你是否要我执行操作，可以再说具体一点。",
        )

    if safety_level == "dangerous" and intent.category not in ALLOWED_WHILE_DANGEROUS:
        return GuardDecision(
            allowed=False,
            mode=BLOCK,
            reason="blocked_by_dangerous_driving_state",
            message="当前驾驶状态风险较高，我先不执行这类容易分心的操作。请先注意前方道路。",
        )

    if safety_level in {"distracted", "high", "medium"} and intent.category in DISTRACTING_CATEGORIES:
        return GuardDecision(
            allowed=False,
            mode=BLOCK,
            reason="blocked_by_distracted_driving_state",
            message="检测到你当前可能分心，我先不执行这类操作。需要的话请在安全状态下再发起。",
        )

    return GuardDecision(allowed=True, mode=EXECUTE)


def _missing_required_slots(category: str, params: dict[str, Any]) -> list[str]:
    if category == "navigation" and not params.get("destination"):
        return ["destination"]
    if category == "weather" and not (params.get("city") or params.get("lat") or params.get("lon")):
        return ["city_or_location"]
    if category == "trip_plan" and not params.get("city"):
        return ["city"]
    if category == "location_management":
        if params.get("action") == "save" and not params.get("address"):
            return ["address"]
        if not params.get("label"):
            return ["label"]
    if category == "music_control" and not (params.get("action") or params.get("singer") or params.get("song") or params.get("volume_action") or "volume" in params):
        return ["music_action_or_query"]
    if category == "ac_control" and not (params.get("action") or "temperature" in params):
        return ["ac_action_or_temperature"]
    return []


def _clarification_message(intent: NormalizedIntent) -> str:
    category = intent.category
    if category == "navigation":
        return "你想导航到哪里？"
    if category == "weather":
        return "你想查哪个城市的天气？"
    if category == "trip_plan":
        return "你想规划哪个城市或目的地的行程？"
    if category == "location_management":
        if "address" in intent.missing_slots:
            return "请告诉我要保存的具体地址。"
        return "你想设置家还是公司的地址？"
    if category == "music_control":
        return "你想播放、暂停、调音量，还是搜索哪首歌？"
    if category == "ac_control":
        return "你想打开、关闭空调，还是调到多少度？"
    return "我需要再确认一下你的具体需求。"


def _min_confidence(category: str) -> float:
    if category in {"ac_control", "music_control", "navigation", "location_management"}:
        return 0.72
    if category in {"trip_plan", "attractions", "diagnosis"}:
        return 0.78
    return 0.65


def _safety_level(driver_state: dict[str, Any]) -> str:
    for key in ("severity", "risk", "safety_level"):
        value = str(driver_state.get(key, "") or "").lower()
        if value:
            if value in {"dangerous", "high", "severe"}:
                return "dangerous"
            if value in {"distracted", "medium", "moderate"}:
                return "distracted"
            if value in {"safe", "normal", "low"}:
                return "normal"
    if driver_state.get("distracted"):
        return "distracted"
    return "normal"
