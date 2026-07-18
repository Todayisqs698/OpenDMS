"""
EdgeGuard Backend — FastAPI + WebSocket + 摄像头引擎

启动: cd backend && uvicorn main:app --reload --port 8000
"""
import sys, os
import logging
from contextlib import asynccontextmanager

# 项目根目录加入 path，让 backend 代码能 import modules
_project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _project_root not in sys.path:
    sys.path.append(_project_root)

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from app.ws.manager import ws_manager

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期：启动/停止摄像头引擎"""
    from app.camera import start, stop
    start(ws_manager)
    logger.info("摄像头引擎已启动")
    yield
    stop()
    logger.info("摄像头引擎已停止")


app = FastAPI(title="EdgeGuard API", version="1.0.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


@app.get("/api/health")
def health():
    return {"status": "ok", "system": "EdgeGuard"}


@app.get("/api/tts")
async def tts(text: str = ""):
    """神经网络语音合成 — 免费微软公开API，接近真人"""
    if not text:
        return {"error": "no text"}
    import edge_tts, tempfile, os
    tmp = tempfile.NamedTemporaryFile(suffix=".mp3", delete=False)
    tmp.close()
    try:
        communicate = edge_tts.Communicate(text, "zh-CN-XiaoxiaoNeural")
        await communicate.save(tmp.name)
        from fastapi.responses import FileResponse
        return FileResponse(tmp.name, media_type="audio/mpeg",
                           headers={"Cache-Control": "no-cache"})
    except Exception as e:
        return {"error": str(e)[:100]}


@app.get("/api/camera/frame")
def camera_frame(landmarks: str = "1"):
    """返回最新摄像头帧（JPEG）+ 状态在响应头。landmarks=0 关闭面部标记"""
    from app.camera import get_frame, get_state, set_landmarks
    from fastapi.responses import Response

    set_landmarks(landmarks != "0")
    frame = get_frame()
    if frame is None:
        return Response(status_code=503)

    headers = {
        "Cache-Control": "no-cache, no-store, must-revalidate",
        "Access-Control-Expose-Headers": "X-Gaze, X-Gesture, X-Action, X-Alert, X-Severity, X-Duration, X-GestureHint, X-Confidence, X-Perclos, X-BlinkRate, X-FatigueScore, X-FatigueLevel",
    }
    state = get_state()
    if state:
        headers["X-Gaze"] = state.get("gaze", "")
        headers["X-Gesture"] = state.get("gesture", "")
        headers["X-Action"] = state.get("action_code", "")
        headers["X-Severity"] = state.get("severity", "normal")
        headers["X-Duration"] = str(state.get("duration", 0))
        headers["X-Alert"] = "1" if state.get("alert") else "0"
        headers["X-GestureHint"] = state.get("gesture_hint", "")
        headers["X-Confidence"] = str(state.get("confidence", 0.8))
        headers["X-Perclos"] = str(state.get("perclos", 0))
        headers["X-BlinkRate"] = str(state.get("blink_rate", 0))
        headers["X-FatigueScore"] = str(state.get("fatigue_score", 0))
        headers["X-FatigueLevel"] = state.get("fatigue_level", "normal")

    return Response(content=frame, media_type="image/jpeg", headers=headers)


@app.get("/api/status")
def status():
    """AI 模块加载状态 + 网络状态"""
    from modules.ai.edge_cloud_router import get_router
    router = get_router()
    # 主动检测网络连通性
    import socket
    try:
        socket.create_connection(("api.deepseek.com", 443), timeout=2)
        if router.offline_mode:
            router.offline_mode = False
    except Exception:
        router.offline_mode = True
    return {
        "status": "ok",
        "offline_mode": router.is_offline(),
        "cloud_latency": router.get_cloud_latency_stats(),
        "agents": {
            "safety": _check_agent("safety"),
            "interaction": _check_agent("interaction"),
            "environment": _check_agent("environment"),
        },
        "perception_available": _check_perception(),
    }


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

    has_gesture = req.gaze_pattern and '手势' in req.gaze_pattern
    if has_gesture:
        prompt = f"""{req.gaze_pattern}。用轻松友好的语气简短确认(10字内)，像朋友一样。"""
    else:
        prompt = f"""你是驾驶伙伴，语气轻松友好像朋友。只观察驾驶员行为不编造路况。
驾驶员状态：观察: {req.gaze_pattern}，注意力: {req.attention}分。
就驾驶员行为说一句提醒或鼓励(15字内)。一切正常就回NONE。</"""

    try:
        r = deepseek_client.client.chat.completions.create(
            model="deepseek-chat",
            messages=[{"role": "system", "content": "你是驾驶伙伴，语气温和亲切。有手势时自然确认一下。其他情况观察驾驶员，值得说就15字内，否则回NONE。"},
                      {"role": "user", "content": prompt}],
            max_tokens=60, temperature=0.6
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

    prompt = f"""你是驾驶行为分析师。根据以下数据生成简短报告（50字内）：

- 驾驶时长: {req.duration_min:.0f}分钟
- 分心次数: {req.distractions}次（严重{req.severe}次）
- 注意力评分: {req.attention_score}分
- 主要视线方向: {req.avg_gaze}

请输出两部分：
1. 驾驶总结（一句话）
2. 建议（一句话）

格式：总结|建议"""

    try:
        r = deepseek_client.client.chat.completions.create(
            model="deepseek-chat",
            messages=[
                {"role": "system", "content": "你是驾驶行为分析师，回答简洁实用。"},
                {"role": "user", "content": prompt}
            ],
            max_tokens=200, temperature=0.7
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

    return {"status": "ok", "route": route, "offline": router.is_offline(), "result": result}


class InteractionRequest(BaseModel):
    text: str = ""
    gesture: str = ""
    gesture_confidence: float = 0
    driver_risk: str = "safe"
    driver_fatigue: bool = False
    driver_distracted: bool = False


@app.post("/api/interaction/query")
async def interaction_query(req: InteractionRequest):
    """语音/手势交互查询：前端对话栏发送用户输入，返回 AI 回复"""
    from modules.ai.deepseek_client import deepseek_client

    try:
        r = deepseek_client.client.chat.completions.create(
            model="deepseek-chat",
            messages=[
                {"role": "system", "content": "你是车载语音助手EdgeGuard，语气友好简洁，像朋友副驾。回复控制在20字内。"},
                {"role": "user", "content": req.text}
            ],
            max_tokens=80, temperature=0.7
        )
        reply = r.choices[0].message.content.strip()
        return {
            "result": {
                "reply_text": reply,
                "allow_execute": True,
                "warning_msg": "",
                "isFinal": True
            }
        }
    except Exception as e:
        return {
            "result": {
                "reply_text": "抱歉，我暂时无法回答。",
                "allow_execute": False,
                "warning_msg": str(e)[:100],
                "isFinal": True
            }
        }


@app.get("/api/environment")
async def environment(city: str = "", lat: float = None, lon: float = None):
    """环境信息：实时天气 + 时间上下文 + 驾驶风险（OpenWeatherMap / wttr.in 免费 API）"""
    from modules.ai.agents.environment_agent import EnvironmentAgent
    import asyncio

    agent = EnvironmentAgent()
    params = {}
    if city:
        params["city"] = city
    if lat is not None and lon is not None:
        params["lat"] = lat
        params["lon"] = lon

    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(None, agent.analyze, params)

    return {"status": "ok", "data": result}


@app.websocket("/ws/{client_id}")
async def websocket_endpoint(websocket: WebSocket, client_id: str):
    await ws_manager.connect(websocket, client_id)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        ws_manager.disconnect(client_id)


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


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
