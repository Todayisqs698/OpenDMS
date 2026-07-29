"""
EdgeGuard Backend — FastAPI + WebSocket + 摄像头引擎

启动: cd backend && uvicorn main:app --reload --port 8000
"""
from __future__ import annotations

import sys, os
import json
import time
import asyncio
import logging
from contextlib import asynccontextmanager
from typing import Optional

# 项目根目录加入 path，让 backend 代码能 import modules
_project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _project_root not in sys.path:
    sys.path.append(_project_root)

# backend 目录本身加入 path 最前，确保 `import app` 解析到 backend/app/
_backend_dir = os.path.dirname(os.path.abspath(__file__))
if _backend_dir not in sys.path:
    sys.path.insert(0, _backend_dir)

from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from app.ws.manager import ws_manager
from app.routes.music import router as music_router
from app.routes.settings import router as settings_router
# 数据库持久化
from backend.app.core.database import insert_alert_record, insert_interaction_record, init_db, create_drive_session, finish_drive_session, set_current_session_id, query_alerts, query_interactions, get_session_summary
from modules.ai.agent_graph import ReActAgent
from modules.ai.structured_results import push_structured_results, iter_structured_result_events

logger = logging.getLogger(__name__)

# ── 全局状态 ──
_loop = None
_current_session_id: int = 0


def get_session_id() -> int:
    """获取当前驾驶会话 ID，供 handler 使用"""
    return _current_session_id

# ── 全局 Agent 实例 ──
_react_agent: ReActAgent | None = None
_legacy_multimodal_orchestrator = None

# 保存事件循环引用，便于在线程中调度 WS 广播
_loop = None

# ── 全局 GPS 状态（由 NavPanel 上报，供 start_navigation 使用）──
_current_gps: dict = {}  # {"lat": float, "lon": float, "updated_at": float}

# ── 本地音乐目录 ──
_MUSIC_DIR = os.path.join(_project_root, "data", "music")
os.makedirs(_MUSIC_DIR, exist_ok=True)

def get_react_agent() -> ReActAgent:
    global _react_agent
    if _react_agent is None:
        _react_agent = ReActAgent()
    return _react_agent


def _get_legacy_multimodal_orchestrator():
    """Deprecated multimodal camera/event orchestrator kept for /api/analyze compatibility."""
    global _legacy_multimodal_orchestrator
    if _legacy_multimodal_orchestrator is None:
        from modules.ai.langgraph_orchestrator import Orchestrator
        _legacy_multimodal_orchestrator = Orchestrator()
    return _legacy_multimodal_orchestrator


def _resolve_agent_safety_level(response, driver_state: dict) -> str:
    """Use the orchestrator's actual route/result before falling back to raw sensor state."""
    if response and getattr(response, "route", "") == "safety_shortcut":
        return "dangerous"

    if response:
        for result in getattr(response, "results", []) or []:
            if getattr(result, "intent_category", "") == "safety":
                for action in getattr(result, "actions", []) or []:
                    level = action.get("level") if isinstance(action, dict) else None
                    if level:
                        return level

    return (driver_state or {}).get("severity", "normal")


def _emit_orchestrator_steps(response, driver_state: dict, sync_push):
    """Emit coarse-grained agent_step events for the unified orchestrator path."""
    safety_level = _resolve_agent_safety_level(response, driver_state)
    sync_push("step", {
        "id": "perceive",
        "label": f"感知驾驶状态：{safety_level}",
        "status": "done",
        "stage": "perceive",
    })

    if response.route == "safety_shortcut":
        sync_push("step", {
            "id": "safety_gate",
            "label": "安全门控：危险状态，已短路告警",
            "status": "done",
            "stage": "safety",
        })
        return

    intents = response.intent_plan.get("intents", []) if response.intent_plan else []
    if intents:
        labels = [f"{i.get('category')}→{i.get('agent')}" for i in intents]
        sync_push("step", {
            "id": "intent_plan",
            "label": "意图规划：" + "、".join(labels),
            "status": "done",
            "stage": "intent",
        })

    for result in response.results:
        status = "done" if result.success else "error"
        sync_push("step", {
            "id": f"dispatch_{result.intent_id}",
            "label": f"{result.agent_name} 处理 {result.intent_category}",
            "status": status,
            "stage": "dispatch",
        })


def _run_unified_agent_sync(text: str, driver_state: dict, sync_push=None, callbacks: dict = None,
                            route: str = "auto") -> dict:
    """Run the canonical chat path and return the legacy chat-shaped result.

    route 参数控制执行路径：
      auto     → 自动分类（由 route_classifier 决定）
      quick    → 跳过 LLM，本地关键词匹配 + ControlExecutor 直达工具
      react    → ReAct 推理（LLM 工具调用）
      multi    → 多Agent 编排（Orchestrator）
      readonly → 只读模式（强制安全门控，禁用写操作工具）
    """
    # ── 安全前置门：危险驾驶状态强制走 multi（SafetyAgent VETO）──
    # 即使前端显式发送 route='quick'，危险状态下也必须经过 SafetyAgent 审查
    from modules.ai.route_classifier import is_dangerous_driver_state
    if route != "readonly" and is_dangerous_driver_state(driver_state):
        logger.warning(
            "Safety override: dangerous driver state detected "
            "(severity=%s, fatigue_score=%s), forcing 'multi' route (was '%s')",
            (driver_state or {}).get("severity"),
            (driver_state or {}).get("fatigue_score"),
            route,
        )
        push = sync_push or (lambda *a: None)
        push("step", {
            "id": "safety_override",
            "label": "安全前置门：检测到危险驾驶状态，强制走安全编排",
            "status": "done",
            "stage": "safety",
        })
        route = "multi"

    # auto 路由：先分类，再分发
    if route == "auto":
        from modules.ai.route_classifier import classify_route
        route = classify_route(text, driver_state)
        logger.info("Auto route classified as: %s (text=%s)", route, text[:50])

    if route == "quick":
        return _run_quick_route_sync(text, driver_state, sync_push)
    elif route == "multi":
        return _run_orchestrator_agent_sync(text, driver_state, sync_push=sync_push, callbacks=callbacks)
    elif route == "readonly":
        return _run_readonly_route_sync(text, driver_state, sync_push)
    else:  # "react" or fallback
        return _run_tool_calling_agent_sync(text, driver_state, sync_push)


def _run_tool_calling_agent_sync(text: str, driver_state: dict, sync_push=None) -> dict:
    """Run ReAct function-calling directly, bypassing keyword intent routing."""
    def noop_push(event_type: str, data: dict):
        return None

    push = sync_push or noop_push
    push("step", {
        "id": "agent_mode",
        "label": "决策模式：LLM 工具调用",
        "status": "done",
        "stage": "agent",
    })

    def react_callback(event_type: str, data: dict):
        if event_type == "think":
            push("step", {
                "id": f"think_{time.time_ns()}",
                "label": data.get("thought", "推理中"),
                "status": "done",
                "stage": "agent",
            })
        elif event_type == "tool_call":
            push("step", {
                "id": f"tool_call_{time.time_ns()}",
                "label": f"调用工具：{data.get('tool', '')}",
                "status": "running",
                "stage": "tool",
                "tool": data.get("tool", ""),
                "args": data.get("args", {}),
            })
        elif event_type == "tool_result":
            push("step", {
                "id": f"tool_result_{time.time_ns()}",
                "label": f"工具完成：{data.get('tool', '')}",
                "status": "done",
                "stage": "tool",
                "tool": data.get("tool", ""),
                "result": data.get("result", ""),
            })
        elif event_type in {"navigation", "attractions", "weather_query", "trip_plan"}:
            push(event_type, data)
        elif event_type == "error":
            push("step", {
                "id": f"agent_error_{time.time_ns()}",
                "label": data.get("message", "Agent 执行异常"),
                "status": "error",
                "stage": "agent",
            })

    result = get_react_agent().chat(text, driver_state or {}, callbacks=[react_callback])
    reply = result.get("reply", "")
    push("final", {"text": reply})
    return {
        "reply": reply,
        "steps": result.get("steps", 0),
        "status": result.get("status", "success"),
        "safety_level": result.get("safety_level", "normal"),
        "route": "tool_calling",
        "intent_plan": {
            "mode": "tool_calling",
            "intents": [],
            "needs_clarification": False,
            "overall_summary": "LLM 直接选择工具执行",
        },
    }


def _emit_multi_agent_steps(response, driver_state: dict, sync_push):
    """Emit step events for the LangGraph multi-agent topology."""
    safety_level = _resolve_agent_safety_level(response, driver_state)
    sync_push("step", {
        "id": "perceive",
        "label": f"感知驾驶状态：{safety_level}",
        "status": "done",
        "stage": "perceive",
    })

    if response.route == "safety_shortcut":
        sync_push("step", {
            "id": "safety_veto",
            "label": "SafetyAgent VETO：危险状态，已短路告警",
            "status": "done",
            "stage": "safety",
        })
        return

    sync_push("step", {
        "id": "safety_check",
        "label": "SafetyAgent 安全检查通过",
        "status": "done",
        "stage": "safety",
    })

    intents = response.intent_plan.get("intents", []) if response.intent_plan else []
    if intents:
        labels = [f"{i.get('category')}→{i.get('agent')}" for i in intents]
        sync_push("step", {
            "id": "intention_route",
            "label": "IntentionAgent 路由：" + "、".join(labels),
            "status": "done",
            "stage": "intent",
        })

    agents_used = getattr(response, "agents_used", [])
    for result in response.results:
        status = "done" if result.success else "error"
        sync_push("step", {
            "id": f"agent_{result.agent_name}",
            "label": f"{result.agent_name} 执行 {result.intent_category}",
            "status": status,
            "stage": "dispatch",
        })

    audit = getattr(response, "audit_result", {}) or {}
    audit_issues = audit.get("issues", []) if isinstance(audit, dict) else []
    if audit_issues:
        sync_push("step", {
            "id": "evidence_audit",
            "label": f"EvidenceAudit 发现 {len(audit_issues)} 个问题",
            "status": "done",
            "stage": "audit",
        })
    elif agents_used and "evidence_audit" in agents_used:
        sync_push("step", {
            "id": "evidence_audit",
            "label": "EvidenceAudit 审计通过",
            "status": "done",
            "stage": "audit",
        })


def _run_orchestrator_agent_sync(text: str, driver_state: dict, sync_push=None, callbacks: dict = None) -> dict:
    """Run the LangGraph multi-agent topology and return the legacy chat-shaped result."""
    from modules.ai.multi_agent_graph import get_multi_agent_orchestrator

    def noop_push(event_type: str, data: dict):
        return None

    push = sync_push or noop_push

    push("step", {
        "id": "agent_mode",
        "label": "决策模式：LangGraph 六Agent编排",
        "status": "done",
        "stage": "agent",
    })

    orch = get_multi_agent_orchestrator()
    response = orch.process(text=text, driver_state=driver_state, callbacks=callbacks)
    safety_level = _resolve_agent_safety_level(response, driver_state)
    _emit_multi_agent_steps(response, driver_state, push)

    agent_result = {
        "reply": response.overall_reply,
        "steps": len(response.results),
        "status": "emergency" if response.route == "safety_shortcut"
                   else ("audit_blocked" if getattr(response, "audit_blocked", False) else "success"),
        "safety_level": safety_level,
        "route": response.route,
        "intent_plan": response.intent_plan,
        "orchestrator_response": response,
        "agents_used": getattr(response, "agents_used", []),
        "audit_result": getattr(response, "audit_result", {}),
        "audit_blocked": getattr(response, "audit_blocked", False),
        "evidence": getattr(response, "evidence", []),
    }

    push_structured_results(response, push)
    push("final", {"text": response.overall_reply})
    return agent_result


# action_code → ControlExecutor 的 category + params 映射
_ACTION_CODE_MAP = {
    "TurnOnAC": ("ac_control", {"action": "TurnOnAC"}),
    "TurnOffAC": ("ac_control", {"action": "TurnOffAC"}),
    "PlayMusic": ("music_control", {"action": "play"}),
    "StopMusic": ("music_control", {"action": "pause"}),
    "volume_up": ("music_control", {"volume_action": "up"}),
    "volume_down": ("music_control", {"volume_action": "down"}),
}


def _run_quick_route_sync(text: str, driver_state: dict, sync_push=None) -> dict:
    """快速指令路由：跳过 LLM，本地关键词匹配后直接调 ControlExecutor。<100ms。"""
    from modules.ai.local_decision_engine import _handle_speech

    def noop_push(event_type: str, data: dict):
        return None

    push = sync_push or noop_push
    push("step", {
        "id": "agent_mode",
        "label": "决策模式：快速指令（本地匹配）",
        "status": "done",
        "stage": "agent",
    })

    # 本地关键词匹配
    result = _handle_speech({"text": text})
    action_code = result.get("action_code", "unknown")
    decision_mode = result.get("decision_mode", "")

    push("step", {
        "id": "local_match",
        "label": f"本地匹配：{action_code}（置信度 {result.get('confidence', 0):.0%}）",
        "status": "done",
        "stage": "perceive",
    })

    # 未命中可执行指令 → 降级到 ReAct
    if action_code == "unknown" or action_code == "semantic_query" or decision_mode == "CLARIFY":
        push("step", {
            "id": "fallback_react",
            "label": "本地未命中，降级到 ReAct 推理",
            "status": "done",
            "stage": "agent",
        })
        return _run_tool_calling_agent_sync(text, driver_state, sync_push)

    # 查映射表，找到可执行的控制类别
    mapped = _ACTION_CODE_MAP.get(action_code)
    if not mapped:
        # 不在映射表中的指令（如车窗、灯光）→ 降级到 ReAct
        push("step", {
            "id": "fallback_react",
            "label": f"指令 {action_code} 无快速执行器，降级到 ReAct",
            "status": "done",
            "stage": "agent",
        })
        return _run_tool_calling_agent_sync(text, driver_state, sync_push)

    category, params = mapped

    # 从用户文本中提取歌手名（用于音乐搜索）
    if category == "music_control" and params.get("action") == "play":
        import re
        normalized = re.sub(r"\s+", "", text)
        singer_match = re.search(
            r"(播放|放一下|来一首|听一下)(.*?)(的歌|歌曲|音乐|$)", normalized
        )
        if singer_match:
            singer = singer_match.group(2)
            if singer and singer not in ("音乐", "歌", "歌曲"):
                params["singer"] = singer

    # 调用 ControlExecutor 执行
    push("step", {
        "id": f"exec_{category}",
        "label": f"执行控制：{category}",
        "status": "running",
        "stage": "tool",
        "tool": category,
        "args": params,
    })

    orch = _get_orchestrator()
    exec_result = orch.control_executor.execute(category, params, text)

    push("step", {
        "id": f"exec_{category}_done",
        "label": f"控制完成：{exec_result.reply_text}",
        "status": "done",
        "stage": "tool",
        "tool": category,
        "result": exec_result.reply_text,
    })

    reply = exec_result.reply_text
    push("final", {"text": reply})
    return {
        "reply": reply,
        "steps": 2,
        "status": "success",
        "safety_level": "normal",
        "route": "quick",
        "intent_plan": {
            "mode": "quick",
            "intents": [{"category": category, "action": action_code}],
            "needs_clarification": False,
            "overall_summary": f"本地快速匹配 → {action_code}",
        },
    }


def _run_readonly_route_sync(text: str, driver_state: dict, sync_push=None) -> dict:
    """只读模式路由：强制安全等级为 readonly，仅允许查询和告警工具。"""
    def noop_push(event_type: str, data: dict):
        return None

    push = sync_push or noop_push
    push("step", {
        "id": "agent_mode",
        "label": "决策模式：安全模式（只读）",
        "status": "done",
        "stage": "agent",
    })

    # 强制设置安全等级为 readonly
    forced_ds = dict(driver_state or {})
    forced_ds["_force_safety"] = "readonly"

    # 复用 ReAct 推理，但通过 _force_safety 标志限制工具集
    def react_callback(event_type: str, data: dict):
        if event_type == "think":
            push("step", {
                "id": f"think_{time.time_ns()}",
                "label": data.get("thought", "推理中"),
                "status": "done",
                "stage": "agent",
            })
        elif event_type == "tool_call":
            push("step", {
                "id": f"tool_call_{time.time_ns()}",
                "label": f"调用工具：{data.get('tool', '')}",
                "status": "running",
                "stage": "tool",
                "tool": data.get("tool", ""),
                "args": data.get("args", {}),
            })
        elif event_type == "tool_result":
            push("step", {
                "id": f"tool_result_{time.time_ns()}",
                "label": f"工具完成：{data.get('tool', '')}",
                "status": "done",
                "stage": "tool",
                "tool": data.get("tool", ""),
                "result": data.get("result", ""),
            })
        elif event_type in {"navigation", "attractions", "weather_query", "trip_plan"}:
            push(event_type, data)
        elif event_type == "error":
            push("step", {
                "id": f"agent_error_{time.time_ns()}",
                "label": data.get("message", "Agent 执行异常"),
                "status": "error",
                "stage": "agent",
            })

    result = get_react_agent().chat(text, forced_ds, callbacks=[react_callback])
    reply = result.get("reply", "")
    push("final", {"text": reply})
    return {
        "reply": reply,
        "steps": result.get("steps", 0),
        "status": result.get("status", "success"),
        "safety_level": "readonly",
        "route": "readonly",
        "intent_plan": {
            "mode": "readonly",
            "intents": [],
            "needs_clarification": False,
            "overall_summary": "只读模式：仅允许查询和告警",
        },
    }

def get_camera_state() -> dict:
    """获取摄像头实时状态（安全包装，摄像头未启动时返回 None）"""
    try:
        from app.camera import get_state
        state = get_state()
        return state if state else None
    except Exception:
        return None


def _run_with_timeout(fn, timeout: float):
    """
    在独立线程中执行 fn，并用 future.result(timeout) 实现整体超时。
    兼容 Windows 事件循环；不依赖 asyncio.to_thread。
    """
    from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutTimeout
    ex = ThreadPoolExecutor(max_workers=1)
    try:
        fut = ex.submit(fn)
        return fut.result(timeout=timeout)
    except FutTimeout:
        logger.warning(f"端点逻辑超时（>{timeout}s），返回兜底")
        raise
    finally:
        ex.shutdown(wait=False)


def _fallback_environment(city: str, lat, lon) -> dict:
    """环境/天气离线兜底（任何异常、超时都走这里）"""
    return {
        "weather": "unknown", "weather_icon": "unknown",
        "weather_emoji": "❓", "weather_desc": "天气数据不可用（离线）",
        "temperature": None, "humidity": None, "wind_speed": None,
        "visibility": None, "driving_context": "路况未知，请谨慎驾驶",
        "risk_score": 0.0, "alerts": [], "reasoning": "离线规则模式",
        "city": city or "未知", "lat": lat, "lon": lon,
        "location_source": "offline",
        "timestamp": __import__("datetime").datetime.now().isoformat(),
    }


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期：启动摄像头引擎 + 周期环境广播"""
    global _loop
    _loop = asyncio.get_event_loop()
    ws_manager.set_event_loop(_loop)  # 注入事件循环供 camera 线程 WS 广播
    import asyncio as _aio

    try:
        from app.camera import start, stop
        start(ws_manager)
        logger.info("摄像头引擎已启动")
    except ImportError:
        logger.info("摄像头模块不可用（无 OpenCV/MediaPipe），跳过")
        start, stop = None, None
    except Exception as e:
        logger.warning(f"摄像头引擎启动失败: {e}")

    # ── 初始化数据库表（确保 alerts 等表存在）──
    try:
        init_db()
        _current_session_id = create_drive_session()
        set_current_session_id(_current_session_id)
        logger.info("数据库表初始化完成，驾驶会话已创建 session_id=%s", _current_session_id)
    except Exception as e:
        logger.warning(f"数据库初始化失败: {e}")

    # ── 周期性环境数据广播（每 30s 推送到 NavPanel WebSocket）──
    async def _periodic_env_broadcast():
        from modules.ai.agents.environment_agent import EnvironmentAgent
        from modules.ai.location_store import get_location_store
        env_agent = EnvironmentAgent()
        loc = get_location_store()
        while True:
            try:
                await _aio.sleep(30)
                lat, lon = loc.get_coords()
                params = {}
                if lat is not None and lon is not None:
                    params["lat"] = lat
                    params["lon"] = lon
                city = loc.get_city()
                if city:
                    params["city"] = city
                result = env_agent.analyze(params)
                await ws_manager.send_environment(result)
                logger.debug("环境数据已广播: city=%s, temp=%s", result.get("city"), result.get("temperature"))
            except Exception as e:
                logger.warning("环境广播失败: %s", e)

    env_task = _aio.create_task(_periodic_env_broadcast())

    yield

    # ── 关闭前结束驾驶会话 ──
    try:
        if _current_session_id > 0:
            finish_drive_session(_current_session_id)
            logger.info("驾驶会话已结束 session_id=%s", _current_session_id)
    except Exception as e:
        logger.warning(f"结束驾驶会话失败: {e}")

    env_task.cancel()
    if stop:
        stop()
        logger.info("摄像头引擎已停止")


app = FastAPI(title="EdgeGuard API", version="1.0.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
app.include_router(music_router)
app.include_router(settings_router)
app.mount("/static/music", StaticFiles(directory=_MUSIC_DIR), name="music_static")


@app.get("/api/health")
def health():
    """健康检查 — 确认模型工厂就绪状态"""
    model_status = {"fast_model": "ok", "reasoning_model": "ok"}
    try:
        from modules.ai.model_factory import create_fast_model, create_reasoning_model
    except ImportError as e:
        logger.warning("model_factory 导入失败: %s", e)
        return {"status": "ok", "system": "EdgeGuard",
                "fast_model": "error", "reasoning_model": "error",
                "import_error": str(e)}
    try:
        create_fast_model()
    except Exception as e:
        model_status["fast_model"] = "error"
        logger.warning("fast_model 创建失败: %s", e)
    try:
        create_reasoning_model()
    except Exception as e:
        model_status["reasoning_model"] = "error"
        logger.warning("reasoning_model 创建失败: %s", e)
    return {"status": "ok", "system": "EdgeGuard", **model_status}


@app.get("/api/tts")
async def tts(text: str = ""):
    """语音合成 — 优先 edge_tts 神经网络语音，降级 pyttsx3 本地引擎"""
    if not text:
        return {"error": "no text"}
    import tempfile, os

    # Level 1: edge_tts（神经网络语音，质量最高）
    try:
        import edge_tts
        tmp = tempfile.NamedTemporaryFile(suffix=".mp3", delete=False)
        tmp.close()
        communicate = edge_tts.Communicate(text, "zh-CN-XiaoxiaoNeural")
        await communicate.save(tmp.name)
        from fastapi.responses import FileResponse
        return FileResponse(tmp.name, media_type="audio/mpeg",
                           headers={"Cache-Control": "no-cache"})
    except Exception as e:
        logger.warning(f"edge_tts 失败，降级到 pyttsx3: {e}")

    # Level 2: pyttsx3（本地引擎，离线可用）
    try:
        import pyttsx3
        tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
        tmp.close()
        engine = pyttsx3.init()
        engine.setProperty('rate', 160)
        engine.setProperty('volume', 0.9)
        engine.save_to_file(text, tmp.name)
        engine.runAndWait()
        from fastapi.responses import FileResponse
        return FileResponse(tmp.name, media_type="audio/wav",
                           headers={"Cache-Control": "no-cache"})
    except Exception as e:
        return {"error": f"TTS 引擎均不可用: {str(e)[:100]}"}


@app.get("/api/camera/frame")
def camera_frame(landmarks: str = "1"):
    """返回最新摄像头帧（JPEG）+ 状态在响应头。landmarks=0 关闭面部标记"""
    from app.camera import get_frame, get_state, set_landmarks
    from fastapi.responses import Response
    from urllib.parse import quote

    def _safe(v: str) -> str:
        """确保 header 值不含非 Latin-1 字符（URL 编码中文等）"""
        try:
            v.encode("latin-1")
            return v
        except UnicodeEncodeError:
            return quote(v, safe="")

    set_landmarks(landmarks != "0")
    frame = get_frame()
    if frame is None:
        # 摄像头未启动时返回占位图而非 503，避免前端轮询报错
        import os as _os
        placeholder = _os.path.join(_project_root, "frontend", "public", "images", "driver-cam.png")
        if _os.path.isfile(placeholder):
            with open(placeholder, "rb") as f:
                return Response(content=f.read(), media_type="image/png")
        return Response(status_code=503)

    headers = {
        "Cache-Control": "no-cache, no-store, must-revalidate",
        "Access-Control-Expose-Headers": (
            "X-Gaze, X-Gesture, X-Action, X-Alert, X-Severity, X-Duration, "
            "X-GestureHint, X-GestureAction, X-Confidence, X-Perclos, X-BlinkRate, "
            "X-FatigueScore, X-FatigueLevel, X-AlertCategory, X-AlertLabel, "
            "X-DurCrowd, X-DurAbsence, X-DurFatigue, X-DurHead, X-DurGaze, "
            "X-Speech"
        ),
    }
    state = get_state()
    if state:
        headers["X-Gaze"] = _safe(state.get("gaze", ""))
        headers["X-Gesture"] = _safe(state.get("gesture", ""))
        headers["X-Action"] = _safe(state.get("action_code", ""))
        headers["X-Severity"] = _safe(state.get("severity", "normal"))
        headers["X-Duration"] = str(state.get("duration", 0))
        headers["X-Alert"] = "1" if state.get("alert") else "0"
        headers["X-GestureHint"] = _safe(state.get("gesture_hint", ""))
        headers["X-GestureAction"] = _safe(state.get("gesture_action", ""))
        headers["X-Confidence"] = str(state.get("confidence", 0.8))
        headers["X-Perclos"] = str(state.get("perclos", 0))
        headers["X-BlinkRate"] = str(state.get("blink_rate", 0))
        headers["X-FatigueScore"] = str(state.get("fatigue_score", 0))
        headers["X-FatigueLevel"] = _safe(state.get("fatigue_level", "normal"))
        headers["X-AlertCategory"] = _safe(state.get("alert_category", ""))
        headers["X-AlertLabel"] = _safe(state.get("alert_label", ""))
        headers["X-DurCrowd"] = str(state.get("dur_crowd", 0))
        headers["X-DurAbsence"] = str(state.get("dur_absence", 0))
        headers["X-DurFatigue"] = str(state.get("dur_fatigue", 0))
        headers["X-DurHead"] = str(state.get("dur_head", 0))
        headers["X-DurGaze"] = str(state.get("dur_gaze", 0))
        headers["X-Speech"] = _safe(state.get("speech", ""))

    return Response(content=frame, media_type="image/jpeg", headers=headers)


@app.get("/api/status")
def status():
    """AI 模块加载状态 + 网络状态 + 驾驶员状态（5 秒整体超时）"""
    from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutTimeout
    from modules.ai.edge_cloud_router import get_router
    from modules.ai.deepseek_client import deepseek_client

    def _collect():
        router = get_router()
        try:
            import socket
            socket.create_connection(("api.deepseek.com", 443), timeout=2)
            if router.offline_mode:
                router.offline_mode = False
        except Exception:
            router.offline_mode = True
        return {
            "status": "ok",
            "offline_mode": router.is_offline(),
            "llm_online": deepseek_client.is_available,
            "active_engine": "DeepSeek-V3 (API)" if deepseek_client.is_available else "LocalDecisionEngine (Fallback)",
            "cloud_latency": router.get_cloud_latency_stats(),
            "agents": {
                "safety": _check_agent("safety"),
                "interaction": _check_agent("interaction"),
                "environment": _check_agent("environment"),
            },
            "perception_available": _check_perception(),
            "driver_state": _get_driver_state_safe(),
        }

    with ThreadPoolExecutor(max_workers=1) as ex:
        try:
            return ex.submit(_collect).result(timeout=5.0)
        except FutTimeout:
            return {
                "status": "ok",
                "offline_mode": False,
                "llm_online": True,
                "active_engine": "DeepSeek-V3 (API)",
                "cloud_latency": {"avg": 0, "min": 0, "max": 0, "count": 0},
                "agents": {"safety": True, "interaction": True, "environment": True},
                "perception_available": False,
                "driver_state": {},
            }


def _get_driver_state_safe() -> dict:
    """安全读取 DriverStateMachine 当前状态"""
    try:
        from modules.ai.agent_graph import get_driver_state
        return get_driver_state()
    except Exception:
        return {}


class AnalyzeRequest(BaseModel):
    trigger: str = "speech"
    gaze_state: str = "center"
    gaze_duration: float = 0.0
    gesture: str = ""
    gesture_confidence: float = 0.0
    speech_text: str = ""
    context_type: str = "user_input"


class InsightRequest(BaseModel):
    gaze_pattern: str = ""       # 最近视线模式描述
    gesture: str = ""            # 当前手势
    duration_sec: float = 0      # 当前偏离/专注持续时间
    attention: int = 100         # 注意力评分


@app.post("/api/drive/insight")
def drive_insight(req: InsightRequest):
    """LLM 主动观察：判断是否有值得说的话"""
    from modules.ai.deepseek_client import deepseek_client
    from modules.ai.prompts import render

    has_gesture = req.gaze_pattern and '手势' in req.gaze_pattern

    # 使用模板库渲染 prompt（模板 ID: analysis.drive_insight）
    trigger_hint = "检测到手势，请自然确认一下。" if has_gesture else ""
    try:
        prompt = render(
            "analysis.drive_insight",
            gaze_pattern=req.gaze_pattern,
            attention=req.attention,
            max_chars=15,
            trigger_hint=trigger_hint,
        )
    except Exception:
        # 模板库不可用时降级
        prompt = f"观察: {req.gaze_pattern}，注意力: {req.attention}分。{trigger_hint}一切正常回NONE。"

    try:
        r = deepseek_client.client.chat.completions.create(
            model="deepseek-v4-flash",
            messages=[{"role": "system", "content": "你是驾驶伙伴，语气温和亲切。有手势时自然确认一下。其他情况观察驾驶员，值得说就15字内，否则回NONE。"},
                      {"role": "user", "content": prompt}],
            max_tokens=512, temperature=0.6
        )
        reply = r.choices[0].message.content.strip()
        if reply.upper() == "NONE" or len(reply) < 3:
            return {"status": "ok", "speak": False, "text": ""}
        return {"status": "ok", "speak": True, "text": reply}
    except Exception as e:
        return {"status": "error", "speak": False, "text": ""}


class DriveReportRequest(BaseModel):
    duration_min: float = 0
    distractions: int = 0
    severe: int = 0
    attention_score: int = 100
    avg_gaze: str = "center"


@app.post("/api/drive/report")
def drive_report(req: DriveReportRequest):
    """LLM 生成驾驶报告 + 疲劳趋势分析"""
    from modules.ai.deepseek_client import deepseek_client
    from modules.ai.prompts import render

    # 使用模板库渲染 prompt（模板 ID: analysis.drive_report）
    try:
        prompt = render(
            "analysis.drive_report",
            duration_min=req.duration_min,
            distractions=req.distractions,
            severe=req.severe,
            attention_score=req.attention_score,
            avg_gaze=req.avg_gaze,
            max_words=50,
        )
    except Exception:
        prompt = f"驾驶时长{req.duration_min:.0f}分钟，分心{req.distractions}次。请生成总结和建议。"

    try:
        r = deepseek_client.client.chat.completions.create(
            model="deepseek-v4-flash",
            messages=[
                {"role": "system", "content": "你是驾驶行为分析师，回答简洁实用。"},
                {"role": "user", "content": prompt}
            ],
            max_tokens=4096, temperature=0.7
        )
        parts = r.choices[0].message.content.strip().split("|")
        return {
            "status": "ok",
            "summary": parts[0].strip() if len(parts) > 0 else "",
            "advice": parts[1].strip() if len(parts) > 1 else "",
            "route": "cloud"
        }
    except Exception as e:
        return {"status": "error", "message": f"生成失败: {str(e)[:100]}"}


@app.post("/api/analyze")
async def analyze(req: AnalyzeRequest):
    """AI 分析：传入多模态数据，返回决策结果"""
    from modules.ai.deepseek_client import MultimodalInput
    from modules.ai.edge_cloud_router import get_router
    from modules.ai.local_decision_engine import decide_locally
    from modules.ai.fallback_handler import handle_fallback
    import time

    # 更新 DriverStateMachine（供 Agent perceive_node 使用）
    try:
        from modules.ai.agent_graph import update_sensor_data
        update_sensor_data({
            "gaze_direction": req.gaze_state,
        })
    except Exception:
        pass

    router = get_router()
    orchestrator = _get_legacy_multimodal_orchestrator()

    multimodal_input = MultimodalInput(
        gaze_data={"state": req.gaze_state, "duration": req.gaze_duration},
        gesture_data={"gesture": req.gesture, "confidence": req.gesture_confidence},
        speech_data={"text": req.speech_text, "intent": "command" if req.speech_text else ""},
        timestamp=time.time(), duration=0.1,
        context={"type": req.context_type, "trigger": req.trigger},
    )

    route = router.route({"trigger": req.trigger, "type": req.context_type, "text": req.speech_text})

    if route == "local":
        result = decide_locally({
            "trigger": req.trigger,
            "data": {"state": req.gaze_state, "duration": req.gaze_duration,
                     "gesture": req.gesture, "confidence": req.gesture_confidence,
                     "text": req.speech_text}
        })
    elif router.is_offline():
        result = handle_fallback({"action_code": "", "text": req.speech_text})
    else:
        result = orchestrator.process(multimodal_input)

    if isinstance(result, dict):
        result.setdefault("legacy", route != "local")
        if route != "local":
            result.setdefault("replacement", "/api/agent/chat for user text requests")

    await ws_manager.broadcast({"type": "ai_decision", "data": result})
    await ws_manager.broadcast({"type": "driver_state", "data": {
        "gaze": req.gaze_state, "gesture": req.gesture,
        "speech": req.speech_text, "route": route,
    }})

    # 若包含语音/手势输入，额外由 InteractionAgent 产出标准化交互结果
    interaction_result = None
    if req.speech_text or req.gesture:
        try:
            from modules.ai.agents.interaction_agent import InteractionAgent
            agent = InteractionAgent()
            interaction_result = agent.analyze({
                "gesture": {"gesture": req.gesture,
                            "confidence": req.gesture_confidence},
                "speech": {"text": req.speech_text},
                "driver_state": {
                    "risk": "safe" if route == "local" else "distract",
                    "fatigue": False, "distracted": route != "local",
                },
            })
            interaction_result["route"] = route
        except Exception as e:
            logger.warning(f"交互分析失败: {e}")

    if interaction_result:
        await ws_manager.broadcast({"type": "interaction_result",
                                    "data": interaction_result})

    return {"status": "ok", "route": route, "offline": router.is_offline(),
            "result": result, "interaction_result": interaction_result}


class InteractionQuery(BaseModel):
    text: str = ""
    gesture: str = ""
    gesture_confidence: float = 0.0
    driver_risk: str = "safe"       # safe / distract / fatigue
    driver_fatigue: bool = False
    driver_distracted: bool = False


@app.post("/api/interaction/query")
def interaction_query(req: InteractionQuery):
    """
    交互理解：语音/手势 → 意图分类 + 安全拦截 + RAG。
    返回标准化结果并通过 WS 广播 interaction_result（供 AiDecisionPanel）。
    """
    from modules.ai.interaction_agent import InteractionAgent
    from modules.ai.edge_cloud_router import get_router

    agent = InteractionAgent()
    result = agent.analyze({
        "gesture": {"gesture": req.gesture, "confidence": req.gesture_confidence},
        "speech": {"text": req.text},
        "driver_state": {
            "risk": req.driver_risk,
            "fatigue": req.driver_fatigue,
            "distracted": req.driver_distracted,
        },
    })

    # 补充路由信息
    router = get_router()
    result["source"] = "interaction_agent"
    result["route"] = router.route({
        "trigger": "speech" if req.text else "gesture",
        "action_code": result.get("action_code", ""),
        "type": "user_input",
        "text": req.text,
    })

    # 广播给前端 / 移动端
    try:
        asyncio.run_coroutine_threadsafe(
            ws_manager.broadcast({"type": "interaction_result", "data": result}),
            _loop,
        )
    except Exception:
        pass

    return {"status": "ok", "result": result}


# ── Agentic Loop 路由 ──

class AgentQueryRequest(BaseModel):
    text: str = ""
    gesture: str = ""
    driver_risk: str = "safe"
    driver_fatigue: bool = False
    driver_distracted: bool = False


@app.post("/api/agent/query")
async def agent_query(req: AgentQueryRequest):
    """
    Deprecated compatibility endpoint.
    新代码请使用 /api/agent/chat；此端点委托统一 Orchestrator 路径。
    """
    driver_state = {
        "risk": req.driver_risk,
        "fatigue": req.driver_fatigue,
        "distracted": req.driver_distracted,
    }

    # 如果有摄像头状态，也加入感知
    cam_state = get_camera_state()
    if cam_state:
        driver_state.update(cam_state)

    result = await asyncio.get_running_loop().run_in_executor(
        None,
        lambda: _run_unified_agent_sync(req.text or f"手势指令: {req.gesture}", driver_state),
    )
    response = result.get("orchestrator_response")

    return {
        "status": "ok",
        "deprecated": True,
        "replacement": "/api/agent/chat",
        "result": {
            "reply_text": result.get("reply", ""),
            "status": result.get("status"),
            "actions": response.actions if response else [],
            "allow_execute": result.get("status") == "success",
            "isFinal": True,
            "route": result.get("route", "orchestrator"),
            "intent_plan": result.get("intent_plan", {}),
        }
    }


@app.get("/api/agent/thinking")
async def agent_thinking():
    """Deprecated: thinking steps are now streamed as agent_step events."""
    return {
        "status": "ok",
        "deprecated": True,
        "replacement": "/ws/agent_panel agent_step events",
        "chain": [],
        "goals": [],
    }


# ── ReAct Agent Chat 路由（流式 WebSocket 推送）──

class AgentChatRequest(BaseModel):
    text: str = ""
    gesture: str = ""
    driver_state: dict = {}
    route: str = "auto"  # auto | quick | react | multi | readonly


def _sse_event(event_type: str, data: dict) -> str:
    payload = json.dumps({"type": event_type, "data": data}, ensure_ascii=False)
    return f"event: {event_type}\ndata: {payload}\n\n"


@app.post("/api/agent/chat")
async def agent_chat(req: AgentChatRequest, stream: bool = False):
    """
    统一 Agent 主入口。
    默认由 AgentOrchestrator 自动判断快速规则、并行意图、ReAct 子流程和安全短路。
    """
    if stream:
        driver_state = dict(req.driver_state)
        cam_state = get_camera_state()
        if cam_state:
            driver_state.update(cam_state)
        loop = asyncio.get_running_loop()
        event_queue: asyncio.Queue = asyncio.Queue()

        def queue_push(event_type: str, data: dict):
            loop.call_soon_threadsafe(event_queue.put_nowait, {"type": f"agent_{event_type}", "data": data})

        def sync_run():
            try:
                agent_result = _run_unified_agent_sync(
                    req.text, driver_state, queue_push,
                    callbacks={
                        "on_intent": lambda plan: queue_push("intent", plan),
                        "on_step": lambda step: queue_push("step", step),
                        "on_result": lambda result: queue_push("result", result),
                    },
                    route=req.route,
                )
                queue_push("final", {"text": agent_result.get("reply", "")})
                # 推送结构化结果（orchestrator 路径）
                orch_response = agent_result.get("orchestrator_response")
                if orch_response:
                    for event_type, data in iter_structured_result_events(orch_response):
                        queue_push(event_type, data)
            finally:
                loop.call_soon_threadsafe(event_queue.put_nowait, None)

        loop.run_in_executor(None, sync_run)

        async def sse_gen():
            while True:
                item = await event_queue.get()
                if item is None:
                    break
                yield _sse_event(item["type"], item["data"])

        return StreamingResponse(sse_gen(), media_type="text/event-stream")

    # 合并摄像头状态
    driver_state = dict(req.driver_state)
    cam_state = get_camera_state()
    if cam_state:
        driver_state.update(cam_state)

    # 定义 callbacks 用于流式推送
    _main_loop = asyncio.get_running_loop()  # 捕获主线程 event loop

    def sync_push(event_type: str, data: dict):
        """同步版 WebSocket 推送（在 run_in_executor 线程中调用）"""
        try:
            asyncio.run_coroutine_threadsafe(
                ws_manager.broadcast({"type": f"agent_{event_type}", "data": data}),
                _main_loop,
            )
        except Exception:
            pass

    def sync_chat():
        agent_result = _run_unified_agent_sync(
            req.text,
            driver_state,
            sync_push,
            callbacks={
                "on_intent": lambda plan: sync_push("intent", plan),
                "on_step": lambda step: sync_push("step", step),
                "on_result": lambda result: sync_push("result", result),
            },
            route=req.route,
        )

        sid = _current_session_id
        reply_text = agent_result.get("reply", "")

        # ── 交互记录持久化（每次对话都记）──
        try:
            if sid > 0:
                insert_interaction_record(
                    session_id=sid,
                    user_query=req.text,
                    ai_response=reply_text,
                )
        except Exception as e:
            logger.warning("交互记录写入失败: %s", e)

        # ── 告警持久化：非 normal 风险写入 alerts 表 ──
        try:
            risk_level = agent_result.get("safety_level", "normal")
            if risk_level != "normal":
                # 从摄像头状态取真实感知数据
                drivers = driver_state or {}
                insert_alert_record(
                    session_id=sid,
                    risk_level=risk_level,
                    alert_msg=reply_text,
                    perclos=float(drivers.get("perclos", 0)),
                    blink_rate=float(drivers.get("blink_rate", 0)),
                    fatigue_score=float(drivers.get("fatigue_score", 0)),
                )
                logger.info("agent 告警已持久化: risk_level=%s, sid=%s", risk_level, sid)
        except Exception as e:
            logger.warning("告警数据库写入异常: %s", e)

        return agent_result

    try:
        result = await _main_loop.run_in_executor(None, sync_chat)
    except Exception as e:
        logger.error(f"Agent chat error: {e}")
        await ws_manager.broadcast({"type": "agent_error", "data": {"message": str(e)}})
        return {"status": "error", "message": str(e)}

    return {
        "status": "ok",
        "result": {
            "reply_text": result.get("reply", ""),
            "steps": result.get("steps", 0),
            "safety_level": result.get("safety_level", "normal"),
            "status": result.get("status", ""),
            "route": result.get("route", "orchestrator"),
            "intent_plan": result.get("intent_plan", {}),
        }
    }


# ── Agent Orchestrator 路由（多 Agent 编排）──

class OrchestratorRequest(BaseModel):
    text: str = ""
    gesture: str = ""
    driver_state: dict = {}


_orchestrator_instance = None


def _get_orchestrator():
    """懒加载编排器"""
    global _orchestrator_instance
    if _orchestrator_instance is None:
        from modules.ai.orchestrator import get_orchestrator
        _orchestrator_instance = get_orchestrator()
    return _orchestrator_instance


@app.post("/api/agent/orchestrate")
async def agent_orchestrate(req: OrchestratorRequest):
    """
    多 Agent 编排主入口 — 意图分解 → 调度子 Agent → 聚合结果。

    流程：
      1. IntentionAgent 分解用户输入为多个意图
      2. 安全预检（dangerous 直接短路告警）
      3. 按优先级调度各子 Agent（control_executor / react_agent / diagnose_agent / ...）
      4. 聚合结果，返回统一响应

    返回：
      - overall_reply: 给用户的自然语言总结
      - intents: 识别到的意图列表
      - results: 每个意图的执行结果
      - actions: 聚合后的动作列表（供前端执行）
    """
    orch = _get_orchestrator()

    # 合并摄像头状态
    driver_state = dict(req.driver_state)
    cam_state = get_camera_state()
    if cam_state:
        driver_state.update(cam_state)

    _main_loop = asyncio.get_running_loop()

    # WebSocket 推送回调（与 /api/agent/chat 一致的结构化推送）
    def sync_push(event_type: str, data: dict):
        try:
            asyncio.run_coroutine_threadsafe(
                ws_manager.broadcast({"type": f"agent_{event_type}", "data": data}),
                _main_loop,
            )
        except Exception:
            pass

    def sync_run():
        response = orch.process(text=req.text, driver_state=driver_state)
        push_structured_results(response, sync_push)
        sync_push("final", {"text": response.overall_reply})
        return response

    try:
        response = await _main_loop.run_in_executor(None, sync_run)
    except Exception as e:
        logger.error(f"Orchestrator error: {e}")
        return {"status": "error", "message": str(e)}

    return {
        "status": "ok",
        "result": {
            "reply_text": response.overall_reply,
            "intent_plan": response.intent_plan,
            "results": [
                {
                    "intent_id": r.intent_id,
                    "intent_category": r.intent_category,
                    "agent": r.agent_name,
                    "success": r.success,
                    "reply": r.reply_text,
                    "actions": r.actions,
                    "error": r.error,
                    "duration_ms": round(r.duration_ms, 2),
                }
                for r in response.results
            ],
            "actions": response.actions,
            "needs_clarification": response.needs_clarification,
            "clarification_question": response.clarification_question,
            "total_duration_ms": round(response.total_duration_ms, 2),
            "route": response.route,
        }
    }


@app.get("/api/environment")
async def environment(city: str = "", lat: float = None, lon: float = None):
    """环境信息：实时天气 + 时间上下文 + 驾驶风险（OpenWeatherMap / wttr.in 免费 API）"""
    from modules.ai.agents.environment_agent import EnvironmentAgent

    # 存储 GPS 坐标供 start_navigation 使用
    if lat is not None and lon is not None:
        import time as _time
        from modules.ai.location_store import get_location_store
        _current_gps.update({"lat": lat, "lon": lon, "updated_at": _time.time()})
        get_location_store().update(lat=lat, lon=lon, source="gps")
        logger.info(f"📍 GPS 已更新: lat={lat}, lon={lon}")

    agent = EnvironmentAgent()
    params = {}
    if city:
        params["city"] = city
    if lat is not None and lon is not None:
        params["lat"] = lat
        params["lon"] = lon

    result = await asyncio.get_running_loop().run_in_executor(None, agent.analyze, params)

    return {"status": "ok", "data": result}


# ── 导航路线规划 ──

class NavRouteRequest(BaseModel):
    destination: str = ""
    lat: Optional[float] = None
    lon: Optional[float] = None


@app.post("/api/navigation/route")
def nav_route(req: NavRouteRequest):
    """规划从当前位置到目的地的驾车路线。免费 API，零依赖。"""
    from modules.ai.navigation_service import get_navigation_service
    from modules.ai.location_store import get_location_store

    destination = (req.destination or "").strip()
    if not destination:
        return {
            "success": False, "destination": "",
            "route_summary": "请提供目的地",
            "distance_km": 0, "duration_min": 0, "steps": [], "geometry": [],
            "source": "error",
        }

    # 起点获取：前端传入 → LocationStore → 默认上海市中心（与 tools.py 一致）
    # 注意：浏览器 GPS 和 LocationStore 返回 WGS-84；上海回退坐标是 GCJ-02，
    # 需转成 WGS-84 再传给 plan()，否则 plan() 内部会二次偏转换导致起点偏移。
    lat, lon = req.lat, req.lon
    gps_source = "request"
    if lat is None or lon is None:
        lat, lon = get_location_store().get_coords()
        gps_source = "location_store"
    if lat is None or lon is None:
        # 桌面浏览器无 GPS 硬件，回退到上海市中心
        # 31.2304, 121.4737 是 GCJ-02 坐标，转成 WGS-84 后传给 plan()
        from modules.ai.navigation_service import _gcj02_to_wgs84
        lat, lon = _gcj02_to_wgs84(31.2304, 121.4737)
        gps_source = "fallback_shanghai"
    svc = get_navigation_service()

    def _run():
        return svc.plan(lat, lon, destination)

    try:
        result = _run_with_timeout(_run, timeout=12.0)
    except Exception:
        result = {
            "success": False, "destination": destination,
            "route_summary": "导航服务暂不可用，请检查网络连接",
            "distance_km": 0, "duration_min": 0, "steps": [], "geometry": [],
            "source": "error",
        }

    # 回填起点信息（与 tools.py start_navigation 一致）
    result["origin_source"] = gps_source
    if gps_source == "fallback_shanghai":
        result.setdefault("origin", "上海市中心（未获取到真实定位）")
    result.setdefault("origin_coords", [lat, lon])

    # 推送结构化导航数据到前端
    try:
        asyncio.run_coroutine_threadsafe(
            ws_manager.broadcast({"type": "navigation", "data": result}),
            _loop,
        )
    except Exception:
        pass

    return result


# ── 地理编码代理（前端地图标注目的地用）──

@app.get("/api/map/geocode")
def map_geocode(address: str = ""):
    """将地址/地名转换为经纬度坐标，使用高德地理编码 API。"""
    import httpx

    address = (address or "").strip()
    if not address:
        return {"success": False, "error": "地址不能为空", "lat": None, "lng": None}

    amap_key = os.getenv("AMAP_API_KEY", "")
    if not amap_key:
        return {"success": False, "error": "高德 API Key 未配置", "lat": None, "lng": None}

    try:
        resp = httpx.get(
            "https://restapi.amap.com/v3/geocode/geo",
            params={"address": address, "key": amap_key},
            timeout=5.0,
        )
        data = resp.json()
        if data.get("status") == "1" and data.get("geocodes"):
            location = data["geocodes"][0].get("location", "")
            if "," in location:
                lng, lat = location.split(",")
                return {
                    "success": True,
                    "lat": float(lat),
                    "lng": float(lng),
                    "formatted": data["geocodes"][0].get("formatted_address", address),
                }
        return {"success": False, "error": "未找到匹配地点", "lat": None, "lng": None}
    except Exception as e:
        return {"success": False, "error": f"地理编码失败: {e}", "lat": None, "lng": None}


# ── GPS 位置上报 ──

class LocationRequest(BaseModel):
    lat: Optional[float] = None
    lon: Optional[float] = None
    city: Optional[str] = None


class EnvironmentRequest(BaseModel):
    city: Optional[str] = None
    lat: Optional[float] = None
    lon: Optional[float] = None


@app.post("/api/environment")
def environment_post(req: EnvironmentRequest):
    """
    环境分析（POST 版本，支持 GPS 坐标自动反查城市）。
    NavPanel 前端通过此端点根据 GPS 坐标获取天气+驾驶建议。
    """
    from modules.ai.agents.environment_agent import EnvironmentAgent
    from modules.ai.location_store import get_location_store

    loc = get_location_store()
    lat = req.lat
    lon = req.lon
    if lat is None or lon is None:
        glat, glon = loc.get_coords()
        if glat is not None:
            lat, lon = glat, glon

    def _run():
        # 强制规则模式：避免无网/Key 无效时 LLM 构造卡死
        EnvironmentAgent._llm_disabled = True
        agent = EnvironmentAgent()
        return agent.analyze({"city": req.city, "lat": lat, "lon": lon})

    try:
        result = _run_with_timeout(_run, timeout=8.0)
    except Exception:
        result = _fallback_environment(req.city or loc.get_city(), lat, lon)

    if result.get("city") and not loc.get_city():
        loc.update(city=result["city"], source="gps_resolved")

    return {"status": "ok", "data": result}


@app.get("/api/weather")
def weather(lat: Optional[float] = None, lon: Optional[float] = None,
            city: Optional[str] = None):
    """天气快捷接口（GET，便于前端轮询）。"""
    from modules.ai.agents.environment_agent import EnvironmentAgent
    from modules.ai.location_store import get_location_store

    if lat is None or lon is None:
        glat, glon = get_location_store().get_coords()
        lat, lon = glat, glon

    def _run():
        EnvironmentAgent._llm_disabled = True
        agent = EnvironmentAgent()
        return agent.analyze({"city": city, "lat": lat, "lon": lon})

    try:
        result = _run_with_timeout(_run, timeout=8.0)
    except Exception:
        result = _fallback_environment(city, lat, lon)
    return {"status": "ok", "data": result}


@app.get("/api/gesture/available")
async def gesture_available():
    """Return gesture availability: geometry-based always works, TFLite may be degraded."""
    from modules.vision.gesture_classifier import GestureClassifier
    from modules.vision.hand_gesture import HandGestureDetector
    hgd = HandGestureDetector()
    return {
        "available": hgd.is_available,
        "geometry_available": True,  # always available — no model needed
        "gestures": GestureClassifier.get_available_gestures()
    }


@app.post("/api/gps/update")
async def update_gps(lat: float, lon: float):
    """前端上报 GPS 坐标，供导航工具使用"""
    import time as _time
    from modules.ai.location_store import get_location_store
    _current_gps.update({"lat": lat, "lon": lon, "updated_at": _time.time()})
    snap = get_location_store().update(lat=lat, lon=lon, source="gps")
    logger.info(f"📍 GPS 已更新: lat={lat}, lon={lon}")
    return {"status": "ok", "location": snap}


@app.get("/api/gps/current")
async def current_gps():
    """获取当前 GPS 坐标"""
    if not _current_gps or "lat" not in _current_gps:
        return {"status": "no_gps", "message": "暂无 GPS 数据"}
    return {"status": "ok", "data": _current_gps}


@app.websocket("/ws/{client_id}")
async def websocket_endpoint(websocket: WebSocket, client_id: str):
    await ws_manager.connect(websocket, client_id)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        ws_manager.disconnect(client_id)


@app.websocket("/ws/agent_panel")
async def websocket_agent_panel(websocket: WebSocket):
    """Agent 思维链专用 WebSocket 端点 — 推送 ReAct Agent 执行过程"""
    await ws_manager.connect(websocket, "agent_panel")
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        ws_manager.disconnect("agent_panel")


@app.websocket("/ws/agent_result")
async def websocket_agent_result(websocket: WebSocket):
    """Agent 结果展示 WebSocket 端点 — 推送景点/天气/导航/行程等结构化结果"""
    await ws_manager.connect(websocket, "agent_result")
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        ws_manager.disconnect("agent_result")


def _check_agent(name: str) -> bool:
    try:
        if name == "safety":
            from modules.ai.agents.safety_agent import SafetyAgent; SafetyAgent()
        elif name == "interaction":
            from modules.ai.agents.interaction_agent import InteractionAgent; InteractionAgent()
        elif name == "environment":
            from modules.ai.agents.environment_agent import EnvironmentAgent; EnvironmentAgent()
        return True
    except Exception:
        return False


def _check_perception() -> bool:
    try:
        import cv2, dlib, whisper
        return True
    except ImportError:
        return False


# ── 空调状态管理 ──

_ac_state = {"power": False, "temperature": 24, "mode": "auto", "fanSpeed": 2}


@app.get("/api/ac/state")
def get_ac_state():
    """返回当前空调状态"""
    return {"status": "ok", "data": _ac_state}


class ACCommandRequest(BaseModel):
    command: str = ""
    temperature: int | str | None = None
    mode: str | None = None
    fanSpeed: int | None = None
    delta: int | None = None


@app.post("/api/ac/command")
def ac_command(req: ACCommandRequest):
    """接收空调控制命令，更新状态并返回新状态"""
    global _ac_state

    cmd = req.command
    if cmd == "TurnOnAC":
        _ac_state["power"] = True
    elif cmd == "TurnOffAC":
        _ac_state["power"] = False
    elif cmd == "temp_up":
        _ac_state["temperature"] = min(_ac_state["temperature"] + 1, 30)
    elif cmd == "temp_down":
        _ac_state["temperature"] = max(_ac_state["temperature"] - 1, 16)
    elif cmd == "set":
        if req.temperature is not None:
            if isinstance(req.temperature, str):
                # 支持 "up"/"down" + delta 幅度
                delta = getattr(req, 'delta', 1) or 1
                if not isinstance(delta, (int, float)):
                    try: delta = int(delta)
                    except: delta = 1
                if req.temperature == "up":
                    _ac_state["temperature"] = min(_ac_state["temperature"] + delta, 30)
                elif req.temperature == "down":
                    _ac_state["temperature"] = max(_ac_state["temperature"] - delta, 16)
            else:
                _ac_state["temperature"] = max(16, min(int(req.temperature), 30))
        if req.mode is not None:
            _ac_state["mode"] = req.mode
        if req.fanSpeed is not None:
            _ac_state["fanSpeed"] = max(1, min(req.fanSpeed, 5))

    return {"status": "ok", "data": _ac_state}


@app.get("/api/prompts")
def prompts_list(category: str = "", search: str = ""):
    """
    Prompt 模板库查询接口。
    支持按 category 过滤和关键词搜索。
    返回所有已注册模板的元数据（不含模板正文，避免 token 泄漏）。
    """
    from modules.ai.prompts import get_all_dicts, search as search_templates, list_by_category, stats as prompt_stats

    if search:
        results = [t.to_dict() for t in search_templates(search)]
    elif category:
        results = [t.to_dict() for t in list_by_category(category)]
    else:
        results = get_all_dicts()

    return {
        "status": "ok",
        "total": len(results),
        "categories": prompt_stats()["categories"],
        "templates": results,
    }


@app.get("/api/prompts/{template_id}")
def prompts_detail(template_id: str):
    """
    获取单个模板的完整信息（含正文）。
    """
    from modules.ai.prompts import get_template

    tpl = get_template(template_id)
    if tpl is None:
        return {"status": "error", "message": f"模板不存在: {template_id}"}

    return {
        "status": "ok",
        "template": tpl.to_dict(),
        "content": tpl.content,
        "fallback_content": tpl.fallback_content,
        "preview": tpl.preview(),
    }


@app.get("/api/prompts/export/markdown")
def prompts_export_md():
    """导出 Prompt 模板库为 Markdown 文档"""
    from modules.ai.prompts import export_markdown
    from fastapi.responses import PlainTextResponse
    return PlainTextResponse(export_markdown(), media_type="text/markdown")


# ── 导航路线规划（免费 API：Nominatim + OSRM，无需 Key）──

@app.post("/api/location")
def update_location(req: LocationRequest):
    """接收前端/移动端上报的 GPS 位置，写入全局位置存储。"""
    from modules.ai.location_store import get_location_store

    store = get_location_store()
    snap = store.update(lat=req.lat, lon=req.lon, city=req.city)
    logger.info(f"GPS 位置更新: lat={snap.get('lat')}, lon={snap.get('lon')}, city={snap.get('city')}")
    return {"status": "ok", "location": snap}


# ── 导航面板 WebSocket ──

@app.websocket("/ws/navpanel")
async def websocket_navpanel(websocket: WebSocket):
    """导航面板专用 WebSocket：推送环境数据 + 导航结果。"""
    await ws_manager.connect(websocket, "navpanel")
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        ws_manager.disconnect("navpanel")


# ── 语音处理端点 ──

class VoiceRequest(BaseModel):
    text: str = ""


@app.post("/api/voice/process")
def voice_process(req: VoiceRequest):
    """
    接收用户语音文本 → 分析意图 → 返回动作+回复+TTS 文本
    """
    text = (req.text or "").strip()
    if not text:
        return {
            "status": "error", "reply": "请告诉我您要做什么",
            "action_code": "", "tts_text": ""
        }

    if os.getenv("VOICE_PROCESS_MODE", "tool_calling").strip().lower() != "legacy":
        driver_state = get_camera_state() or {}
        result = _run_tool_calling_agent_sync(text, driver_state)
        reply = result.get("reply", "")
        return {
            "status": "ok",
            "reply": reply,
            "action_code": "",
            "tts_text": reply,
            "route": "tool_calling",
        }

    reply = ""
    action_code = ""
    route = "local"

    # 1. 本地关键词匹配
    from modules.ai.local_decision_engine import decide_locally
    local = decide_locally({"trigger": "speech", "data": {"text": text}})

    if local and local.get("decision_mode") == "EXECUTE" and local.get("action_code") and local.get("action_code") != "unknown":
        action_code = local.get("action_code")
        reply = local.get("recommendation_text") or "已执行"
        route = "local"
    else:
        # 2. 调 InteractionAgent（需 LLM 时）
        try:
            from modules.ai.agents.interaction_agent import InteractionAgent
            agent = InteractionAgent()
            result = agent.analyze({
                "gesture": {"gesture": "", "confidence": 0},
                "speech": {"text": text, "intent": "", "emotion": "neutral"},
                "driver_state": {"risk": "safe", "fatigue": False, "distracted": False},
            })
            action_code = result.get("action_code", "unknown")
            reply = result.get("recommendation_text", "已理解您的指令")
            route = "interaction"
        except Exception as e:
            # 3. 兜底：用 RAG 知识库
            try:
                from modules.ai.vehicle_knowledge_base import retrieve_knowledge
                r = retrieve_knowledge(text, top_k=2)
                docs = r.get("docs", [])
                if docs:
                    reply = docs[0].get("content", "已收到")[:100]
                else:
                    reply = "已收到您的指令"
            except Exception:
                reply = "已收到您的指令"

    return {
        "status": "ok",
        "reply": reply,
        "action_code": action_code,
        "tts_text": reply,
        "route": route,
    }


@app.get("/api/voice/state")
def voice_state():
    """语音模块加载状态"""
    whisper_ok = False
    whisper_err = ""
    tts = True
    try:
        from modules.audio.speech_recognizer import transcribe
        whisper_ok = True
    except Exception as e:
        whisper_err = f"{type(e).__name__}: {e}"
    return {
        "status": "ok",
        "modules": {"whisper": whisper_ok, "tts": tts},
        "active_listening": False,
        "whisper_error": whisper_err,
    }


@app.post("/api/voice/transcribe")
async def voice_transcribe(request: Request):
    """接收浏览器麦克风录制的 WAV 音频，返回 Whisper 转写文本"""
    try:
        audio_bytes = await request.body()
        if len(audio_bytes) < 1000:
            return {"status": "error", "text": "", "error": "音频数据太短"}
        from modules.audio.speech_recognizer import transcribe
        text = transcribe(audio_bytes)
        return {"status": "ok", "text": text}
    except Exception as e:
        return {"status": "error", "text": "", "error": str(e)[:200]}


# ── Dashboard 聚合端点 ──

@app.get("/api/dashboard/state")
def dashboard_state(need: str = "all"):
    """
    返回仪表盘所有需要的状态：
    - environment: 当前位置+天气+驾驶建议
    - driver_state: 摄像头感知的视线/手势/告警
    - modules: 各 AI 模块加载状态
    - offline: 是否离线
    """
    from modules.ai.location_store import get_location_store
    from modules.ai.edge_cloud_router import get_router

    result = {"status": "ok", "ts": time.time()}

    if need in ("all", "environment"):
        loc = get_location_store()
        lat, lon = loc.get_coords()
        if lat is None or lon is None:
            lat, lon = 39.9042, 116.4074
        try:
            from modules.ai.agents.environment_agent import EnvironmentAgent
            EnvironmentAgent._llm_disabled = True
            agent = EnvironmentAgent()
            env = agent.analyze({"lat": lat, "lon": lon})
            result["environment"] = env
        except Exception as e:
            result["environment"] = _fallback_environment(loc.get_city() or "北京", lat, lon)

    if need in ("all", "driver_state"):
        try:
            cam_state = get_camera_state()
            result["driver_state"] = cam_state or {
                "gaze": "center", "gesture": "", "action_code": "normal",
                "alert": "", "severity": "normal", "duration": 0,
                "confidence": 0.8, "gesture_hint": "",
            }
        except Exception:
            result["driver_state"] = {
                "gaze": "center", "gesture": "", "action_code": "normal",
                "alert": "", "severity": "normal", "duration": 0,
                "confidence": 0.0, "gesture_hint": "",
            }

    if need in ("all", "modules"):
        router = get_router()
        result["offline"] = router.is_offline()
        result["modules"] = {
            "safety": _check_agent("safety"),
            "interaction": _check_agent("interaction"),
            "environment": _check_agent("environment"),
            "perception": _check_perception(),
        }

    return result


# ========== 数据库持久化查询 API ==========

@app.get("/api/alerts")
def api_alerts(limit: int = 50, session_id: int = 0):
    """获取告警记录列表（支持按会话过滤）"""
    try:
        rows = query_alerts(session_id=session_id, limit=limit)
        return {"status": "ok", "total": len(rows), "data": rows}
    except Exception as e:
        return {"status": "error", "message": str(e)}


@app.get("/api/session/summary")
def api_session_summary(session_id: int = 0):
    """获取当前驾驶会话摘要（时长、告警统计、疲劳分）"""
    try:
        summary = get_session_summary(session_id=session_id)
        if summary is None:
            return {"status": "ok", "data": None, "message": "暂无驾驶会话"}
        return {"status": "ok", "data": summary}
    except Exception as e:
        return {"status": "error", "message": str(e)}


@app.get("/api/interactions")
def api_interactions(limit: int = 100, session_id: int = 0):
    """获取语音交互记录"""
    try:
        rows = query_interactions(session_id=session_id, limit=limit)
        return {"status": "ok", "total": len(rows), "data": rows}
    except Exception as e:
        return {"status": "error", "message": str(e)}


# ========== 异步旅行规划任务 (P2: 移植自 TripStar) ==========

class AsyncTripRequest(BaseModel):
    """异步旅行规划请求体"""
    city: str
    days: int = 2
    preference: str = ""
    origin: str = ""
    waypoints: list[str] = []
    forbidden_cities: list[str] = []


@app.post("/api/trip/async")
async def trip_async(req: AsyncTripRequest):
    """提交异步旅行规划任务，立即返回 task_id，不阻塞请求。

    前端可通过以下方式获取进度:
    - WebSocket: /ws/trip/{task_id} (实时推送)
    - HTTP 轮询: GET /api/trip/status/{task_id}
    """
    from modules.ai.trip_planner.task_manager import create_trip_task

    task_id = create_trip_task(
        city=req.city,
        days=req.days,
        preference=req.preference or None,
        origin=req.origin,
        waypoints=req.waypoints or None,
        forbidden_cities=req.forbidden_cities or None,
    )
    logger.info("异步旅行任务已创建: task_id=%s city=%s days=%s", task_id, req.city, req.days)
    return {
        "task_id": task_id,
        "status": "processing",
        "ws_url": f"/ws/trip/{task_id}",
        "poll_url": f"/api/trip/status/{task_id}",
        "message": "任务已提交，可通过 WebSocket 或轮询获取进度",
    }


@app.get("/api/trip/status/{task_id}")
async def trip_status(task_id: str):
    """HTTP 轮询获取任务状态（WebSocket 不可用时的降级方案）。"""
    from modules.ai.trip_planner.task_manager import get_task_status

    status = get_task_status(task_id)
    if status is None:
        return {"status": "error", "message": f"任务 {task_id} 不存在"}
    return {"status": "ok", "data": status}


@app.websocket("/ws/trip/{task_id}")
async def websocket_trip_task(websocket: WebSocket, task_id: str):
    """WebSocket 实时推送旅行规划任务进度。

    连接后立即发送当前状态快照，后续每次状态更新自动推送。
    任务完成或失败后自动关闭连接。
    """
    from modules.ai.trip_planner.task_manager import (
        get_task,
        subscribe_to_task,
        unsubscribe_from_task,
    )

    await websocket.accept()

    task = get_task(task_id)
    if task is None:
        await websocket.send_json({
            "task_id": task_id,
            "status": "failed",
            "stage": "failed",
            "progress": 100,
            "message": "任务不存在",
            "error": "任务不存在",
        })
        await websocket.close(code=1008)
        return

    # 订阅后续更新
    queue = subscribe_to_task(task_id)
    if queue is None:
        await websocket.send_json({
            "task_id": task_id,
            "status": "failed",
            "message": "订阅失败",
        })
        await websocket.close(code=1008)
        return

    # 先发送当前状态快照
    from modules.ai.trip_planner.task_manager import _build_task_event
    snapshot = _build_task_event(task_id, task)
    await websocket.send_json(snapshot)

    # 如果任务已结束，直接关闭
    if snapshot.get("status") in ("completed", "failed"):
        try:
            await websocket.close()
        except Exception:
            pass
        unsubscribe_from_task(task_id, queue)
        return

    # 循环推送后续更新
    try:
        while True:
            try:
                event = await asyncio.wait_for(queue.get(), timeout=120.0)
                await websocket.send_json(event)
                if event.get("status") in ("completed", "failed"):
                    break
            except asyncio.TimeoutError:
                # 发送心跳保持连接
                await websocket.send_json({"type": "ping", "task_id": task_id})
    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.warning("WebSocket trip task %s 异常: %s", task_id, e)
    finally:
        unsubscribe_from_task(task_id, queue)
        try:
            await websocket.close()
        except Exception:
            pass


# ========== 前端静态文件（手机/平板直接访问后端即可） ==========
_frontend_dist = os.path.join(_project_root, "frontend", "dist")
if os.path.isdir(_frontend_dist):
    app.mount("/", StaticFiles(directory=_frontend_dist, html=True), name="frontend")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
