"""
EdgeGuard Backend — FastAPI + WebSocket + 摄像头引擎

启动: cd backend && uvicorn main:app --reload --port 8000
"""
import sys, os
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
# 数据库持久化
from backend.app.core.database import insert_alert_record, insert_interaction_record, init_db, create_drive_session, finish_drive_session, set_current_session_id, query_alerts, query_interactions, get_session_summary
from modules.ai.agent_core import EdgeGuardAgent
from modules.ai.agent_graph import ReActAgent

logger = logging.getLogger(__name__)

# ── 全局状态 ──
_loop = None
_current_session_id: int = 0


def get_session_id() -> int:
    """获取当前驾驶会话 ID，供 handler 使用"""
    return _current_session_id

# ── 全局 Agent 实例 ──
_edgeguard_agent: EdgeGuardAgent | None = None
_react_agent: ReActAgent | None = None

# 保存事件循环引用，便于在线程中调度 WS 广播
_loop = None

# ── 全局 GPS 状态（由 NavPanel 上报，供 start_navigation 使用）──
_current_gps: dict = {}  # {"lat": float, "lon": float, "updated_at": float}

# ── 本地音乐目录 ──
_MUSIC_DIR = os.path.join(_project_root, "data", "music")
os.makedirs(_MUSIC_DIR, exist_ok=True)

def get_agent() -> EdgeGuardAgent:
    global _edgeguard_agent
    if _edgeguard_agent is None:
        _edgeguard_agent = EdgeGuardAgent(memory_path=os.path.join(_project_root, "data", "agent_memory.json"))
    return _edgeguard_agent

def get_react_agent() -> ReActAgent:
    global _react_agent
    if _react_agent is None:
        _react_agent = ReActAgent()
    return _react_agent

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


def _scan_local_music(query: str = "") -> list:
    """扫描 data/music/ 目录的本地音频文件"""
    results = []
    if not os.path.isdir(_MUSIC_DIR):
        return results
    for fname in sorted(os.listdir(_MUSIC_DIR)):
        if not fname.lower().endswith(('.mp3', '.wav', '.flac', '.m4a', '.ogg')):
            continue
        name = os.path.splitext(fname)[0]
        artist, title = "本地音乐", name
        if " - " in name:
            parts = name.split(" - ", 1)
            artist, title = parts[0].strip(), parts[1].strip()
        if query and query.lower() not in name.lower():
            continue
        from urllib.parse import quote
        results.append({
            "id": hash(fname) % 1000000,
            "name": title,
            "artist": artist,
            "album": "",
            "duration": 0,
            "url": f"/static/music/{quote(fname)}",
            "source": "local",
        })
    return results


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期：启动摄像头引擎 + 周期环境广播"""
    global _loop
    _loop = asyncio.get_event_loop()
    ws_manager.set_event_loop(_loop)  # 注入事件循环供 camera 线程 WS 广播
    from app.camera import start, stop
    import asyncio as _aio

    start(ws_manager)
    logger.info("摄像头引擎已启动")

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
    stop()
    logger.info("摄像头引擎已停止")


app = FastAPI(title="EdgeGuard API", version="1.0.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
app.mount("/static/music", StaticFiles(directory=_MUSIC_DIR), name="music_static")


@app.get("/api/health")
def health():
    return {"status": "ok", "system": "EdgeGuard"}


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
    from modules.ai.langgraph_orchestrator import Orchestrator
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
    orchestrator = Orchestrator()

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
    Agent 主入口 — 真正的感知-思考-行动循环。
    替代旧版 /api/interaction/query，支持规划/工具调用/记忆/反思。
    """
    agent = get_agent()

    # 构建 driver_state
    driver_state = {
        "risk": req.driver_risk,
        "fatigue": req.driver_fatigue,
        "distracted": req.driver_distracted,
    }

    # 如果有摄像头状态，也加入感知
    cam_state = get_camera_state()
    if cam_state:
        driver_state.update(cam_state)

    # 执行 Agent Loop
    result = agent.handle_user_input(text=req.text, gesture=req.gesture, driver_state=driver_state)

    if result is None:
        return {"status": "ok", "result": {"reply_text": "无待处理目标", "actions": []}}

    return {
        "status": "ok",
        "result": {
            "reply_text": result.get("reply", ""),
            "goal_id": result.get("goal_id"),
            "goal_description": result.get("goal_description"),
            "status": result.get("status"),
            "actions": result.get("actions", []),
            "allow_execute": result.get("status") == "success",
            "isFinal": True,
        }
    }


@app.get("/api/agent/thinking")
async def agent_thinking():
    """获取 Agent 思维链，供前端可视化"""
    agent = get_agent()
    return {"status": "ok", "chain": agent.get_thinking_chain(), "goals": [g.__dict__ for g in agent.goals._goals[:5]]}


# ── ReAct Agent Chat 路由（流式 WebSocket 推送）──

class AgentChatRequest(BaseModel):
    text: str = ""
    gesture: str = ""
    driver_state: dict = {}


@app.post("/api/agent/chat")
async def agent_chat(req: AgentChatRequest):
    """
    ReAct Agent 主入口 — 真正的感知-思考-行动循环。
    支持流式 WebSocket 推送 Agent 执行过程。
    """
    agent = get_react_agent()

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

    callbacks = [sync_push]

    def sync_chat():
        agent_result = agent.chat(text=req.text, driver_state=driver_state, callbacks=callbacks)

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

        # 结构化推送：将 recommend_agent 的导航/天气结果推送到 AgentResultPanel
        for r in response.results:
            if not r.success:
                continue
            rec_data = r.data or {}
            if r.intent_category == "navigation" and rec_data.get("nav_data"):
                nav = rec_data["nav_data"]
                sync_push("navigation", {
                    "destination": nav.get("destination", ""),
                    "distance_km": nav.get("distance_km", 0),
                    "duration_min": nav.get("duration_min", 0),
                    "route_summary": nav.get("route_summary", ""),
                    "origin": nav.get("origin", "当前位置"),
                    "map_url": nav.get("map_url", ""),
                    "amap_nav_url": nav.get("amap_nav_url", ""),
                })
            elif r.intent_category == "weather":
                weather = rec_data.get("weather", {})
                sync_push("weather_query", {
                    "city": weather.get("desc", ""),
                    "weather_desc": weather.get("desc", ""),
                    "temperature": weather.get("temperature"),
                    "driving_context": rec_data.get("reply", ""),
                })
            elif r.intent_category == "trip_plan":
                trip = rec_data.get("trip_plan", {})
                if trip:
                    sync_push("trip_plan", {
                        "city": trip.get("city", ""),
                        "days": trip.get("days", 1),
                        "summary": trip.get("summary", ""),
                        "budget": trip.get("budget", {}),
                        "itinerary": trip.get("itinerary", []),
                    })
            elif r.intent_category == "attractions":
                attrs = rec_data.get("attractions", [])
                if attrs:
                    sync_push("attractions", {
                        "city": rec_data.get("city", ""),
                        "attractions": attrs,
                    })

        # 推送最终回复
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
        _current_gps.update({"lat": lat, "lon": lon, "updated_at": _time.time()})
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

    lat, lon = req.lat, req.lon
    if lat is None or lon is None:
        lat, lon = get_location_store().get_coords()
    svc = get_navigation_service()

    def _run():
        return svc.plan(lat, lon, destination)

    try:
        result = _run_with_timeout(_run, timeout=8.0)
    except Exception:
        result = {
            "success": False, "destination": destination,
            "route_summary": "导航服务暂不可用，请检查网络连接",
            "distance_km": 0, "duration_min": 0, "steps": [], "geometry": [],
            "source": "error",
        }

    # 推送结构化导航数据到前端
    try:
        asyncio.run_coroutine_threadsafe(
            ws_manager.broadcast({"type": "navigation", "data": result}),
            _loop,
        )
    except Exception:
        pass

    return result


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
    _current_gps.update({"lat": lat, "lon": lon, "updated_at": _time.time()})
    logger.info(f"📍 GPS 已更新: lat={lat}, lon={lon}")
    return {"status": "ok"}


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


# ── 音乐播放状态管理 ──

import httpx

_MUSIC_API_BASE = "http://localhost:3000"

_music_state = {
    "playing": False,
    "current_song": {"id": 0, "name": "", "artist": "", "album": "", "url": "", "cover": "", "duration": 0},
    "playlist": [],
    "playlist_index": -1,
    "volume": 80,
}


@app.get("/api/music/state")
def get_music_state():
    """返回当前音乐播放状态"""
    return {"status": "ok", "data": _music_state}


class MusicSearchRequest(BaseModel):
    keyword: str = ""


@app.post("/api/music/search")
async def music_search(req: MusicSearchRequest):
    """搜索歌曲：优先本地文件，失败时降级网易云API"""
    # 1. 先扫本地
    local = _scan_local_music(req.keyword)
    if local:
        return {"status": "ok", "songs": local}
    # 2. 本地无结果，尝试网易云API
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                f"{_MUSIC_API_BASE}/cloudsearch",
                params={"keywords": req.keyword},
            )
            data = resp.json()
            songs = []
            result_songs = data.get("result", {}).get("songs", [])
            for s in result_songs[:10]:
                artists_list = s.get("ar") or s.get("artists", [])
                artists = ", ".join(a.get("name", "") for a in artists_list)
                album = s.get("al") or s.get("album") or {}
                songs.append({
                    "id": s.get("id", 0),
                    "name": s.get("name", ""),
                    "artist": artists,
                    "album": album.get("name", ""),
                    "duration": s.get("duration", 0),
                    "cover": (album.get("picUrl") or "") + "?param=300y300",
                })
            return {"status": "ok", "songs": songs}
    except Exception:
        pass
    # 3. 兜底：本地+在线都不可用时返回演示曲目
    demo_all = [
        {"id": 1, "name": "传奇", "artist": "王菲", "album": "传奇", "duration": 262, "cover": "", "source": "demo"},
        {"id": 2, "name": "红豆", "artist": "王菲", "album": "唱游", "duration": 253, "cover": "", "source": "demo"},
        {"id": 3, "name": "匆匆那年", "artist": "王菲", "album": "匆匆那年", "duration": 241, "cover": "", "source": "demo"},
        {"id": 4, "name": "因为爱情", "artist": "王菲 & 陈奕迅", "album": "将爱", "duration": 228, "cover": "", "source": "demo"},
        {"id": 5, "name": "如愿", "artist": "王菲", "album": "如愿", "duration": 275, "cover": "", "source": "demo"},
        {"id": 6, "name": "晴天", "artist": "周杰伦", "album": "叶惠美", "duration": 269, "cover": "", "source": "demo"},
        {"id": 7, "name": "七里香", "artist": "周杰伦", "album": "七里香", "duration": 299, "cover": "", "source": "demo"},
        {"id": 8, "name": "夜曲", "artist": "周杰伦", "album": "十一月的萧邦", "duration": 226, "cover": "", "source": "demo"},
    ]
    q = req.keyword.strip().lower()
    if q:
        demo_all = [d for d in demo_all if q in d["name"].lower() or q in d["artist"].lower()]
    return {"status": "ok", "songs": demo_all, "hint": "演示曲目（启动 localhost:3000 或放入 MP3 到 data/music/ 获取真实播放）"}


class MusicPlayRequest(BaseModel):
    song_id: int = 0


@app.post("/api/music/play")
async def music_play(req: MusicPlayRequest):
    """播放指定歌曲：优先本地文件，否则演示曲目，最后尝试网易云API"""
    global _music_state
    # 演示曲目映射
    _demo_map = {
        1: {"name": "传奇", "artist": "王菲", "album": "传奇", "duration": 262},
        2: {"name": "红豆", "artist": "王菲", "album": "唱游", "duration": 253},
        3: {"name": "匆匆那年", "artist": "王菲", "album": "匆匆那年", "duration": 241},
        4: {"name": "因为爱情", "artist": "王菲 & 陈奕迅", "album": "将爱", "duration": 228},
        5: {"name": "如愿", "artist": "王菲", "album": "如愿", "duration": 275},
        6: {"name": "晴天", "artist": "周杰伦", "album": "叶惠美", "duration": 269},
        7: {"name": "七里香", "artist": "周杰伦", "album": "七里香", "duration": 299},
        8: {"name": "夜曲", "artist": "周杰伦", "album": "十一月的萧邦", "duration": 226},
    }
    try:
        # 1. 本地文件
        local_songs = _scan_local_music("")
        local_match = next((s for s in local_songs if s["id"] == req.song_id), None)
        if local_match and local_match.get("url"):
            _music_state["current_song"] = {
                "id": req.song_id, "name": local_match["name"],
                "artist": local_match["artist"], "album": "",
                "url": local_match["url"], "cover": "", "duration": 0,
            }
            _music_state["playing"] = True
            return {"status": "ok", "data": _music_state}

        # 2. 演示曲目（无真实音频，仅展示"播放中"状态）
        if req.song_id in _demo_map:
            song = _demo_map[req.song_id]
            _music_state["current_song"] = {
                "id": req.song_id, "name": song["name"],
                "artist": song["artist"], "album": song["album"],
                "url": "", "cover": "", "duration": song["duration"],
            }
            _music_state["playing"] = True
            return {"status": "ok", "data": _music_state, "hint": "演示模式：无真实音频，启动 localhost:3000 获取在线播放"}

        # 否则尝试网易云API
        async with httpx.AsyncClient(timeout=10) as client:
            # 获取播放URL
            url_resp = await client.get(
                f"{_MUSIC_API_BASE}/song/url/v1",
                params={"id": req.song_id, "level": "exhigh"},
            )
            url_data = url_resp.json()
            urls = url_data.get("data", [])
            play_url = urls[0].get("url", "") if urls else ""

            # 获取歌曲详情（名称、封面等）
            detail_resp = await client.get(
                f"{_MUSIC_API_BASE}/song/detail",
                params={"ids": str(req.song_id)},
            )
            detail_data = detail_resp.json()
            songs = detail_data.get("songs", [])
            song_info = songs[0] if songs else {}

            artists = ", ".join(a.get("name", "") for a in (song_info.get("ar") or song_info.get("artists", [])))
            album = song_info.get("al") or song_info.get("album") or {}
            cover_url = (album.get("picUrl") or "") + "?param=300y300"
            duration = song_info.get("duration", 0)

            # 更新播放列表索引
            idx = -1
            for i, item in enumerate(_music_state["playlist"]):
                if item.get("id") == req.song_id:
                    idx = i
                    break
            if idx == -1:
                _music_state["playlist"].append({
                    "id": req.song_id,
                    "name": song_info.get("name", ""),
                    "artist": artists,
                    "album": album.get("name", ""),
                    "cover": cover_url,
                    "duration": duration,
                })
                _music_state["playlist_index"] = len(_music_state["playlist"]) - 1
            else:
                _music_state["playlist_index"] = idx

            _music_state["current_song"] = {
                "id": req.song_id,
                "name": song_info.get("name", ""),
                "artist": artists,
                "album": album.get("name", ""),
                "url": play_url,
                "cover": cover_url,
                "duration": duration,
            }
            _music_state["playing"] = True

            return {"status": "ok", "data": _music_state}
    except Exception as e:
        return {"status": "error", "message": str(e)[:200]}


@app.post("/api/music/pause")
def music_pause():
    """切换播放/暂停状态"""
    global _music_state
    _music_state["playing"] = not _music_state["playing"]
    return {"status": "ok", "data": _music_state}


@app.post("/api/music/next")
async def music_next():
    """播放列表下一首"""
    global _music_state
    pl = _music_state["playlist"]
    if not pl:
        return {"status": "ok", "data": _music_state}
    _music_state["playlist_index"] = (_music_state["playlist_index"] + 1) % len(pl)
    next_song = pl[_music_state["playlist_index"]]
    # 自动获取播放URL
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            url_resp = await client.get(
                f"{_MUSIC_API_BASE}/song/url/v1",
                params={"id": next_song["id"], "level": "exhigh"},
            )
            url_data = url_resp.json()
            urls = url_data.get("data", [])
            play_url = urls[0].get("url", "") if urls else ""
            next_song["url"] = play_url
    except Exception:
        pass

    _music_state["current_song"] = {
        "id": next_song.get("id", 0),
        "name": next_song.get("name", ""),
        "artist": next_song.get("artist", ""),
        "album": next_song.get("album", ""),
        "url": next_song.get("url", ""),
        "cover": next_song.get("cover", ""),
        "duration": next_song.get("duration", 0),
    }
    _music_state["playing"] = True
    return {"status": "ok", "data": _music_state}


@app.post("/api/music/prev")
async def music_prev():
    """播放列表上一首"""
    global _music_state
    pl = _music_state["playlist"]
    if not pl:
        return {"status": "ok", "data": _music_state}
    _music_state["playlist_index"] = (_music_state["playlist_index"] - 1) % len(pl)
    prev_song = pl[_music_state["playlist_index"]]
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            url_resp = await client.get(
                f"{_MUSIC_API_BASE}/song/url/v1",
                params={"id": prev_song["id"], "level": "exhigh"},
            )
            url_data = url_resp.json()
            urls = url_data.get("data", [])
            play_url = urls[0].get("url", "") if urls else ""
            prev_song["url"] = play_url
    except Exception:
        pass

    _music_state["current_song"] = {
        "id": prev_song.get("id", 0),
        "name": prev_song.get("name", ""),
        "artist": prev_song.get("artist", ""),
        "album": prev_song.get("album", ""),
        "url": prev_song.get("url", ""),
        "cover": prev_song.get("cover", ""),
        "duration": prev_song.get("duration", 0),
    }
    _music_state["playing"] = True
    return {"status": "ok", "data": _music_state}


class MusicVolumeRequest(BaseModel):
    volume: int = 80


@app.post("/api/music/volume")
def music_volume(req: MusicVolumeRequest):
    """设置音量 (0-100)"""
    global _music_state
    _music_state["volume"] = max(0, min(int(req.volume), 100))
    return {"status": "ok", "data": _music_state}


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

    reply = ""
    action_code = ""
    route = "local"

    # 1. 本地关键词匹配
    from modules.ai.local_decision_engine import decide_locally
    local = decide_locally({"trigger": "speech", "data": {"text": text}})

    if local and local.get("action_code") and local.get("action_code") != "unknown":
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


# ========== 前端静态文件（手机/平板直接访问后端即可） ==========
_frontend_dist = os.path.join(_project_root, "frontend", "dist")
if os.path.isdir(_frontend_dist):
    app.mount("/", StaticFiles(directory=_frontend_dist, html=True), name="frontend")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
