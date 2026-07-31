"""
在讲稿 DOCX 的指定位置插入代码片段。
使用 doc_insert_html_content 在每个章节末尾插入带 <pre> 标签的代码块。
"""

import subprocess
import json

EDSDK = r"D:\Workbuddy\resources\app.asar.unpacked\resources\builtin-skills\tencent-local-office-edit\edsdk.py"
FILE_ID = "cd300950-e4c1-4152-9afa-348f849c3ea2"
PYTHON = "python3"
CWD = r"C:\Users\SQS\Desktop\edgeguard"

def insert_html(file_id, idx, html):
    """插入 HTML 内容，返回新的 idx"""
    payload = {"html_text": html}
    args = [PYTHON, EDSDK, "call", "doc_insert_html_content",
            f"file_id={file_id}", f"idx={idx}",
            "--json", json.dumps(payload)]
    result = subprocess.run(args, capture_output=True, text=True, timeout=30, cwd=CWD)
    if result.returncode != 0:
        print(f"ERROR at idx={idx}: {result.stderr}")
        return None
    try:
        resp = json.loads(result.stdout)
        return resp.get("last_edit_index", idx)
    except:
        return idx

def code_block(title, code):
    """生成带标题的代码块 HTML"""
    # 转义 HTML 特殊字符
    code = code.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    return f"""<h4>{title}</h4><pre><code>{code}</code></pre>"""

# ===== 插入顺序：从文档末尾往前插，避免 idx 偏移 =====

# 插入位置：每个章节的 end_index（即该章节最后一段的 end_index）

# 由于 doc_insert_html_content 会在指定 idx 处插入内容，
# 我们需要在章节最后一个段落的末尾处插入。
# 从文档结构可知各章节结束的 end_index：

insertions = [
    # (idx, title, code)
    # 4.1 面部疲劳 - 在 "2287" (4.1 最后一段末尾)
    (2287, "代码示例：PERCLOS 与多维特征提取 (fatigue_predictor.py)",
     '''def _extract_features(eye_frames: list[dict]) -> dict:
    """从眼动帧序列提取 7 维状态向量。"""
    if not eye_frames:
        return {
            "perclos": 0.0, "blink_rate": 12.0,
            "avg_eye_open": 0.35, "yaw_var": 0.0,
            "pitch_var": 0.0, "gaze_off_freq": 0,
            "alert_delay": -1.0,
        }

    total = len(eye_frames)
    close_count = 0
    blink_times = 0
    ear_values = []
    yaw_values, pitch_values = [], []
    gaze_off_count = 0
    last_ear_low = False

    for frame in eye_frames:
        ear = frame.get("ear", 0.5)
        ear_values.append(ear)
        if ear < EAR_THRESHOLD:  # 阈值 0.22
            close_count += 1
            if not last_ear_low:
                blink_times += 1
                last_ear_low = True
        else:
            last_ear_low = False
        yaw_values.append(frame.get("yaw", 0))
        pitch_values.append(frame.get("pitch", 0))
        if frame.get("gaze", "center") != "center":
            gaze_off_count += 1

    perclos = round(close_count / total, 3)
    blink_rate = round(blink_times * (60.0 / max(total, 1)), 1)
    avg_eye_open = round(sum(ear_values) / total, 3)'''),

    # 4.3 手势识别 - 在 "3134"
    (3134, "代码示例：16种手势几何分类与动作映射 (gesture_classifier.py)",
     '''GESTURE_ACTION_MAP = {
    "open_palm":   {"action_code": "open_ac",    "label": "open AC"},
    "fist":        {"action_code": "close_ac",   "label": "close AC"},
    "thumbs_up":   {"action_code": "confirm",    "label": "confirm / play"},
    "thumbs_down": {"action_code": "cancel",     "label": "cancel / pause"},
    "index_point": {"action_code": "attention",  "label": "driver status"},
    "peace":       {"action_code": "greeting",   "label": "wake assistant"},
    "ok_sign":     {"action_code": "confirm_ac", "label": "confirm AC set"},
    "three_fingers":{"action_code": "mode_3",    "label": "switch mode"},
    "four_fingers": {"action_code": "mode_4",    "label": "navigate home"},
    "pinch":       {"action_code": "zoom_in",    "label": "zoom in / up"},
    "swipe_left":  {"action_code": "prev_track", "label": "previous track"},
    "swipe_right": {"action_code": "next_track", "label": "next track"},
    "palm_up":     {"action_code": "volume_up",  "label": "volume up"},
    "palm_down":   {"action_code": "volume_down","label": "volume down"},
    "call_me":     {"action_code": "call",       "label": "answer call"},
    "rock_on":     {"action_code": "mute",       "label": "mute / DND"},
}'''),

    # 4.4 语音交互 - 在 "3634"
    (3634, "代码示例：语音交互全链路 API 端点 (main.py)",
     '''@app.post("/api/voice/transcribe")
async def voice_transcribe(file: UploadFile):
    """Whisper 语音转写 — 支持 20+ 语种实时识别"""
    audio = await file.read()
    result = whisper_model.transcribe(audio)
    return {"text": result["text"], "language": result["language"]}

@app.post("/api/voice/process")
async def voice_process(req: VoiceRequest):
    """语音指令全链路：识别 → 意图理解 → 智能执行 → TTS 合成"""
    text = req.text or (await voice_transcribe(req.audio))["text"]
    intent = await intention_agent.analyze(text)
    result = await agent_orchestrator.execute(intent)
    tts_audio = await tts_engine.synthesize(result["reply"])
    return {"text": text, "intent": intent, "result": result,
            "tts_audio": tts_audio}'''),

    # 5.1 LangGraph 快速层 - 在 "4201"
    (4201, "代码示例：LangGraph 多智能体图构建 (multi_agent_graph.py)",
     '''def _init_graph(self) -> None:
    """构建 Safety → Intention → Fan-out → EvidenceAudit → Aggregate"""
    builder = StateGraph(MultiAgentState)

    # 7 个 Agent 节点 + 1 个聚合节点
    builder.add_node("safety", lambda s: _safety_node(s, self._safety_agent))
    builder.add_node("intention", lambda s: _intention_node(s, self._intention_agent))
    builder.add_node("interaction", lambda s: _interaction_node(s, self._interaction_agent))
    builder.add_node("diagnose", lambda s: _diagnose_node(s, self._diagnose_agent))
    builder.add_node("analyze", lambda s: _analyze_node(s, self._analyze_agent))
    builder.add_node("recommend", lambda s: _recommend_node(s, self._recommend_agent))
    builder.add_node("evidence_audit", lambda s: _evidence_audit_node(s, self._evidence_audit_agent))
    builder.add_node("aggregate", _aggregate_node)

    builder.set_entry_point("safety")

    # Safety → VETO 短路 / Intention
    builder.add_conditional_edges("safety", _route_after_safety,
        {"aggregate": "aggregate", "intention": "intention"})

    # Intention → Fan-out 到 4 个执行 Agent（并行）
    builder.add_edge("intention", "interaction")
    builder.add_edge("intention", "diagnose")
    builder.add_edge("intention", "analyze")
    builder.add_edge("intention", "recommend")

    # 执行 Agent → EvidenceAudit → Aggregate → END
    for agent in ["interaction", "diagnose", "analyze", "recommend"]:
        builder.add_edge(agent, "evidence_audit")
    builder.add_edge("evidence_audit", "aggregate")
    builder.add_edge("aggregate", END)

    self._graph = builder.compile()'''),

    # 5.3 SafetyAgent VETO - 在 "5094"
    (5094, "代码示例：四级风险状态机与 VETO 短路 (safety_agent.py)",
     '''# 四级递进式风险判定
if is_fatigue_danger or (heavy_gaze and is_fatigue_tired):
    risk_level = "dangerous"
    alert_text = "重度疲劳，建议立即靠边停车休息"
    self.consecutive_warnings += 1

elif (heavy_gaze or heavy_head) and not is_fatigue_tired:
    risk_level = "distracted"
    alert_text = "视线/头部偏离道路，请注视前方道路"
    self.consecutive_warnings += 1

elif is_fatigue_tired or slight_gaze or slight_head:
    risk_level = "attn_declining"
    alert_text = "注意力下降，建议短暂休整"
    self.consecutive_warnings += 1

else:
    risk_level = "normal"
    alert_text = ""
    self.consecutive_warnings = 0

# VETO 否决：dangerous 状态拦截所有非安全指令
if risk_level == "dangerous" and not is_safety_critical(request):
    return {"veto": True, "reason": alert_text,
            "fallback": "建议导航至最近服务区休息"}'''),

    # 5.4 边云路由 - 在 "5530"
    (5530, "代码示例：边云三路径智能路由 (edge_cloud_router.py)",
     '''# 路由策略分类
LOCAL_ONLY = {"distract", "fatigue_warning", "confirm",
              "cancel", "PlayMusic", "TurnOnAC", "TurnOffAC"}
HYBRID = {"semantic_query", "knowledge_qa", "weather_query",
          "navigation_query", "vehicle_question"}
CLOUD_FIRST = {"context_reasoning", "multi_turn_dialogue",
               "emotion_analysis", "driving_advice"}

class EdgeCloudRouter:
    def route(self, context: dict) -> str:
        """Returns: "local" | "cloud" | "hybrid" """
        # 离线模式 → 全部本地
        if self.offline_mode:
            return "local"

        action = context.get("action_code", "")
        trigger = context.get("trigger", "")

        # 安全/手势/动作指令 → 本地 (<50ms)
        if action in LOCAL_ONLY or trigger in ("gaze", "gesture"):
            return "local"

        # 知识/语义查询 → 混合（本地预处理 + 云端生成）
        if action in HYBRID or trigger == "query":
            return "hybrid"

        return "local"  # 默认本地，安全优先'''),

    # 5.5 RAG 知识库 - 在 "6013"
    (6013, "代码示例：FAISS 向量检索与 RAG 问答链 (vehicle_knowledge_base.py)",
     '''def search(self, query: str, top_k: int = 3) -> list[dict]:
    """语义检索 — FAISS IndexFlatL2 + 384维 Embedding"""
    query_vec = self.embedding_fn([query])  # SentenceTransformer
    distances, indices = self.index.search(
        query_vec.astype(np.float32), top_k)
    results = []
    for i, idx in enumerate(indices[0]):
        if idx >= 0:
            doc = self.documents[idx]
            results.append({
                "content": doc["content"],
                "source": f"KB:{doc.get('source', 'manual')}",
                "section": doc.get("section", ""),
                "score": float(distances[0][i])
            })
    return results

def ask(self, question: str) -> dict:
    """RAG 问答：检索 Top-3 → 拼接上下文 → LLM 生成"""
    docs = self.search(question, top_k=3)
    context = "\\n---\\n".join(
        f"[{d['source']} {d['section']}] {d['content']}"
        for d in docs)
    prompt = f"基于以下知识回答：\\n{context}\\n\\n问题：{question}"
    reply = self.llm.chat(prompt)
    return {"answer": reply, "sources": docs}'''),

    # 3.3 技术选型/模型分派 - 在 "1735"
    (1735, "代码示例：Agent 到模型的分派与双降级链 (model_factory.py)",
     '''# Agent → 模型映射（轻量路由）
AGENT_MODEL = {
    "safety":         create_fast_model,      # 豆包 Lite / DeepSeek Chat 降级
    "intention":      create_fast_model,
    "interaction":    create_fast_model,
    "diagnose":       create_reasoning_model, # DeepSeek Reasoner / 豆包 Lite 降级
    "analyze":        create_reasoning_model,
    "recommend":      create_reasoning_model,
    "evidence_audit": create_fast_model,
    "orchestrator":   create_reasoning_model,
}

# 模块级缓存，避免重复创建 OpenAI 连接池
_client_cache: dict[str, ModelClient] = {}

def get_model_for_agent(agent_name: str) -> ModelClient:
    """按 Agent 角色获取对应模型实例（带缓存）"""
    if agent_name in _client_cache:
        return _client_cache[agent_name]
    factory = AGENT_MODEL.get(agent_name, create_fast_model)
    client = factory()
    _client_cache[agent_name] = client
    return client'''),

    # 6.2 API - 在 "6892"
    (6892, "代码示例：核心 API — 统一 Agent 入口 /api/agent/chat (main.py)",
     '''@app.post("/api/agent/chat")
async def agent_chat(req: AgentChatRequest):
    """
    统一 Agent 主入口 — 支持 auto/quick/react/multi 四种路由模式。
    SafetyAgent 前置拦截，Pydantic Schema 校验输出。
    """
    driver_state = dict(req.driver_state)
    cam_state = get_camera_state()
    if cam_state:
        driver_state.update(cam_state)

    result = await _main_loop.run_in_executor(
        None, lambda: _run_unified_agent_sync(
            req.text, driver_state, route=req.route))

    return {
        "status": "ok",
        "result": {
            "reply_text": result.get("reply", ""),
            "steps": result.get("steps", 0),
            "safety_level": result.get("safety_level", "normal"),
            "route": result.get("route", "orchestrator"),
            "intent_plan": result.get("intent_plan", {}),
        }
    }'''),

    # 7.1 创新总结 - 在 "8010" (7.1 最后一段)
    (8010, "代码示例：系统启动入口 — 一键部署 (start.bat / docker-compose)",
     '''# docker-compose.yml ��� 容器化一键部署
services:
  backend:
    build:
      context: .
      dockerfile: Dockerfile.backend
    ports: ["8000:8000"]
    volumes: ["./data:/app/data", "./modules:/app/modules"]
  frontend:
    build:
      context: .
      dockerfile: Dockerfile.frontend
    ports: ["3000:3000"]
    depends_on: [backend]

# start.bat — 本地开发一键拉起
# pip install -r requirements.txt
# uvicorn backend.main:app --host 0.0.0.0 --port 8000
# cd frontend && npm install && npm run dev'''),
]

# 从后往前插入（后面的 idx 不受前面插入影响，因为我们在章节末尾插，后面的 idx 不受影响）
# 实际上 doc_insert_html_content 是插入到 idx 位置，后面的内容自动后移。
# 所以如果按从前到后的顺序插入，前面插入后后面 idx 会变。
# 但这里我们使用的是文档结构的 end_index，这些是在插入前就确定的。
# 按从后往前的顺序插入可以避免 idx 偏移问题。

# 按 idx 从大到小排序
insertions.sort(key=lambda x: x[0], reverse=True)

print(f"共 {len(insertions)} 个代码片段待插入\n")

for i, (idx, title, code) in enumerate(insertions):
    print(f"[{i+1}/{len(insertions)}] 插入: {title} @ idx={idx}")
    html = code_block(title, code)
    new_idx = insert_html(FILE_ID, idx, html)
    if new_idx is None:
        print(f"  FAILED!")
    else:
        print(f"  OK, new_idx={new_idx}")

print("\n=== 全部完成! ===")
