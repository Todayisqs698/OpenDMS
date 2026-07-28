# IMPLEMENTATION_PLAN — EdgeGuard 实施计划

> **版本**: 1.0.0 (MVP 已完成) | **最后更新**: 2026-07-26

本文档记录从零构建 EdgeGuard 的完整步骤序列。每一步粒度足够细，AI 无需猜测。

---

## 阶段 0: 项目初始化

### 步骤 0.1: 创建项目目录
```bash
mkdir -p EdgeGuard
cd EdgeGuard
git init
```

### 步骤 0.2: 创建 .gitignore
- 忽略 `*.pyc`, `__pycache__/`, `.env`, `node_modules/`, `dist/`, `.vite/`, `data/logs/`, `*.mp4`, `.vscode/`, `.idea/`, `backend/data/`, `tools/netease-cloud-music-api/`, `data/knowledge/faiss_index/`

### 步骤 0.3: 创建 .env.example
- 定义所有环境变量模板: `DEEPSEEK_API_KEY`, `LLM_PROVIDER`, `OPENAI_API_KEY`, `HF_ENDPOINT`, `AMAP_API_KEY`, `ANTHROPIC_API_KEY`, `OPENWEATHER_API_KEY`, `EMBEDDING_API_BASE`, `EMBEDDING_API_KEY`, `EMBEDDING_MODEL`

### 步骤 0.4: 创建 .env (用户本地)
- 复制 `.env.example` → `.env`，填入实际 API Key

### 步骤 0.5: 初始化前后端目录
```bash
mkdir -p backend/app/core backend/app/ws
mkdir -p frontend/src/{views,components/hmi,composables,lib,router,styles}
mkdir -p modules/{ai/{agents,prompts},vision/gesture/models,audio,actions,system}
mkdir -p data/{knowledge/faiss_index,music}
```

---

## 阶段 1: 后端基础架构

### 步骤 1.1: 安装 Python 依赖
```bash
pip install -r requirements.txt
```
依赖清单见 `specs/TECH_STACK.md` 第 2 节。

### 步骤 1.2: 创建 requirements.txt
- opencv-python>=4.8.0, mediapipe>=0.10.30, numpy>=1.24.0
- sounddevice>=0.5.2, webrtcvad>=2.0.7, openai-whisper>=20240930, noisereduce>=3.0.0, edge-tts>=6.1.0
- openai>=1.30.0, langchain>=0.3.0, langgraph>=0.2.0
- faiss-cpu>=1.10.0, sentence-transformers>=3.0.0
- fastapi>=0.110.0, uvicorn[standard]>=0.29.0, websockets>=12.0, httpx>=0.28.0
- python-dotenv>=1.0.0, requests>=2.31.0

### 步骤 1.3: 创建 FastAPI 应用入口 `backend/main.py`
- 导入 FastAPI, CORSMiddleware, WebSocket
- 设置 CORS `allow_origins=["*"]`
- 添加 lifespan: 启动摄像头引擎 + 初始化数据库 + 创建驾驶会话 + 启动周期环境广播
- lifespan shutdown: 结束驾驶会话 + 停止摄像头
- 挂载 `/static/music` 静态文件目录

### 步骤 1.4: 实现健康检查端点
- `GET /api/health` → `{"status": "ok", "system": "EdgeGuard"}`

### 步骤 1.5: 创建数据库模块 `backend/app/core/database.py`
- 实现 `get_db_connection()`: SQLite 连接 + `row_factory = sqlite3.Row`
- 实现 `init_db()`: 创建 `drive_sessions`, `alerts`, `interactions` 三张表 (CREATE TABLE IF NOT EXISTS)
- 实现 `create_drive_session()` → int session_id
- 实现 `finish_drive_session(session_id, avg_fatigue_score)`
- 实现 `insert_alert_record(session_id, risk_level, alert_msg, perclos, blink_rate, fatigue_score)`
- 实现 `insert_interaction_record(session_id, user_query, ai_response)`
- 实现 `query_alerts(session_id, limit)` → list[dict]
- 实现 `query_interactions(session_id, limit)` → list[dict]
- 实现 `get_session_summary(session_id)` → dict | None
- 实现 `set_current_session_id(sid)` / `get_current_session_id()` → int

### 步骤 1.6: 创建 WebSocket 管理器 `backend/app/ws/manager.py`
- 实现 `WSManager` 类
  - `connect(websocket, client_id)`: 接受连接 + 元数据注册 + 离线消息推送
  - `disconnect(client_id)`: 移除连接 + 保留缓冲
  - `broadcast(data)`: 广播所有在线客户端
  - `broadcast_sync(data)`: 线程安全同步广播 (供 camera 线程使用)
  - `send_to(client_id, data)`: 单播
  - `send_environment(env_data)`: 类型化推送
  - `send_driver_state(state)`: 类型化推送
  - `send_alert(alert)`: 类型化推送
  - `send_ai_decision(decision)`: 类型化推送
  - `_heartbeat_loop()`: 每 30s ping + 死连接清理
  - `_cleanup_loop()`: 每 45s 超时客户端清理 + 缓冲截断
  - `get_status()`: 连接统计
- 全局单例: `ws_manager = WSManager()`
- 配置常量: `HEARTBEAT_INTERVAL=30`, `CLIENT_TIMEOUT=90`, `MAX_BUFFER_SIZE=100`

---

## 阶段 2: LLM 客户端与 AI 基础

### 步骤 2.1: 创建 DeepSeek 客户端 `modules/ai/deepseek_client.py`
- 定义 `MultimodalInput` dataclass: gaze_data, gesture_data, speech_data, timestamp, duration, context
- 定义 `AIResponse` dataclass: action_code, recommendation_text, confidence, reasoning, timestamp
- 实现 `DeepSeekClient` 类:
  - `__init__`: 从环境变量读取 API Key, 初始化 OpenAI 客户端 (base_url="https://api.deepseek.com")
  - `is_available` property: Key 是否已配置
  - `create_multimodal_prompt()`: 构造多模态融合 prompt
  - `chat()`: 调用 chat.completions.create
- 全局单例: `deepseek_client = DeepSeekClient()`

### 步骤 2.2: 创建 Prompt 模板库 `modules/ai/prompts/`
- `template.py`: `PromptTemplate` dataclass (id, name, category, description, content, fallback_content, variables, version)
- `registry.py`: `PromptRegistry` 类 — 注册/查询/搜索模板
- `agent_templates.py`: Agent 系统提示词 + 工具选择 prompt
- `analysis_templates.py`: 驾驶报告 + 主动观察 prompt (analysis.drive_report, analysis.drive_insight)
- `safety_templates.py`: 安全评估 + 疲劳检测 prompt
- `__init__.py`: 公共 API — `render(template_id, **kwargs)`, `get_template(id)`, `search(keyword)`, `list_by_category(cat)`, `get_all_dicts()`, `export_markdown()`, `stats()`

### 步骤 2.3: 创建 Edge-Cloud 路由器 `modules/ai/edge_cloud_router.py`
- 实现路由决策逻辑: 复杂度评估 + 网络检测 + 离线模式
- 路由结果: "local" | "cloud" | "hybrid"
- 网络检测: `socket.create_connection(("api.deepseek.com", 443), timeout=2)`
- 离线模式自动切换: 网络断开 → `offline_mode = True`
- 全局单例: `get_router()`

### 步骤 2.4: 创建本地决策引擎 `modules/ai/local_decision_engine.py`
- 实现 `decide_locally(input)`: 手势/语音关键词/安全规则匹配
- 实现 5 类独立决策函数:
  - `check_crowd(duration, face_count)`: 多人检测
  - `check_absence(duration)`: 无人检测
  - `check_fatigue(duration)`: 疲劳检测
  - `check_head_deviation(gaze, duration)`: 头部偏离
  - `check_gaze_deviation(gaze, duration)`: 视线偏离
- 返回格式: `{ action_code, recommendation_text, alert, severity, alert_category, alert_label }`

### 步骤 2.5: 创建离线降级处理 `modules/ai/fallback_handler.py`
- 8 种离线降级场景的模板响应
- `handle_fallback(input)` → 返回预设的安全回复

---

## 阶段 3: 视觉感知层

### 步骤 3.1: 创建面部追踪器 `modules/vision/face_tracker.py`
- 实现 `FaceTracker` 类:
  - 初始化 MediaPipe Face Landmarker (468 点)
  - `refresh(frame)`: 处理一帧，更新所有检测结果
  - `is_face_detected()` → bool
  - `head_pose()` → { pitch, yaw, roll } (PnP 算法)
  - `gaze_state` property → "center"|"left"|"right"|"up"|"down"|"lost"|...
  - `is_blinking()` → bool
  - `ear` property → float (眼睛纵横比)
  - `ear_threshold` → float
  - `BLINK_RATIO` → float
  - `perclos` property → float (0.0-1.0)
  - `blink_count` property → int
  - `face_landmarks` property → 468 个 NormalizedLandmark

### 步骤 3.2: 创建手势识别器 `modules/vision/hand_gesture.py`
- 实现 `HandGestureDetector` 类:
  - 加载 MediaPipe HandLandmarker (.task 文件)
  - 加载 TFLite KeyPointClassifier
  - `process(rgb_frame)` → (gesture_name, confidence)
  - 支持 15+ 手势: Open, Close, Thumbs Up, Thumbs Down, OK, Peace, Pointer, Quiet Coyote 等
  - `is_available` property
  - `labels` property (手势名称列表)
  - 几何规则分类器作为主引擎 (零延迟)
  - TFLite 作为辅助验证
  - 防抖: `_stable_count` 连续 N 帧一致才确认

### 步骤 3.3: 创建 TFLite 分类器封装 `modules/vision/gesture_classifier.py`
- `GestureClassifier` 类: 加载/推理 TFLite 模型
- `get_available_gestures()` → list[str]

---

## 阶段 4: 语音感知层

### 步骤 4.1: 创建语音识别器 `modules/audio/speech_recognizer.py`
- `transcribe(audio_bytes)` → text: str
- 使用 Whisper base 模型
- 首次调用自动下载模型

### 步骤 4.2: 创建音频管线 `modules/audio/audio_pipeline.py`
- `AudioPipeline` 类:
  - `start()`: 启动音频采集线程 (sounddevice + WebRTC VAD + noisereduce)
  - `stop()`: 停止采集
  - `pause()` / `resume()`: TTS 播报时暂停/恢复
  - `get_result()` → { text, timestamp } | None
  - 独立线程运行，不阻塞视觉管线

### 步骤 4.3: 创建麦克风录音器 `modules/audio/recorder.py`
- `Recorder` 类: 简化的麦克风采集 (用于 app.py 语音线程)
- `record_stream()` → generator of { wav: bytes }

---

## 阶段 5: Agent 系统

### 步骤 5.1: 创建安全门控 `modules/ai/safety_gate.py`
- `apply_safety_gate(driver_state)` → SafetyGateState
- 四级风险 → 工具白名单:
  - normal → 全工具开放
  - attn_declining → 受限 (无音乐/导航)
  - distracted → 受限 (仅 speak/alert/AC)
  - dangerous → 仅告警 (speak/alert_driver)

### 步骤 5.2: 创建工具定义 `modules/ai/tools.py`
- 定义 8 个 Function Calling 工具:
  1. `speak(text)` — TTS 播报
  2. `control_ac(command, temperature, mode, fanSpeed)` — 空调控制
  3. `control_music(command, keyword)` — 音乐控制
  4. `search_knowledge(query)` — RAG 知识检索
  5. `get_weather(city, lat, lon)` — 天气查询
  6. `alert_driver(message, severity)` — 驾驶员告警
  7. `ask_clarification(question)` — 反问澄清
  8. `search_attractions(city, keyword)` — POI 检索
  9. `start_navigation(destination)` — 导航规划
  10. `plan_trip(city, days)` — 行程规划
- `TOOL_SCHEMAS`: OpenAI Function Calling JSON Schema 列表
- `execute_tool(name, args)` → result

### 步骤 5.3: 创建记忆系统 `modules/ai/memory.py`
- `AgentMemory` 类:
  - WorkingMemory: 最近 N 轮对话 (deque)
  - SessionMemory: 用户偏好持久化 (JSON)
  - `add_user_message(text)`
  - `add_assistant_message(text)`
  - `get_context()` → str (拼接最近对话)
  - `save()` / `load()`: JSON 序列化

### 步骤 5.4: 创建驾驶员状态机 `modules/ai/driver_state_machine.py`
- `DriverStateMachine` 类:
  - 7 维状态向量: gaze_direction, head_pitch, head_yaw, perclos, blink_rate, fatigue_score, risk_level
  - `update(sensor_data)` → current_state
  - `get_state()` → str
  - `get_risk_score()` → float (0-100)
  - `get_trend()` → "stable"|"improving"|"declining"
  - `get_vector()` → list[float]
  - 滑动窗口 + 趋势计算

### 步骤 5.5: 创建疲劳预测器 `modules/ai/fatigue_predictor.py`
- `FatiguePredictor` 类:
  - 基于 PERCLOS 历史趋势预测疲劳时间
  - `predict(perclos_history)` → { estimated_time_to_danger, confidence }

### 步骤 5.6: 创建 ReAct Agent `modules/ai/agent_graph.py`
- 使用 LangGraph StateGraph (降级: 手动 while 循环)
- 节点:
  - `perceive_node`: 读取 DriverStateMachine + 用户输入
  - `safety_gate_node`: 评估风险 → 过滤工具
  - `agent_node`: LLM 推理 → 决定工具调用
  - `tool_node`: 执行工具 → 返回结果
  - `safety_response_node`: 紧急告警 → 直接回复
  - `respond_node`: 生成最终回复
- 边:
  - START → perceive → safety_gate → [dangerous?]
    - 是 → safety_response → END
    - 否 → agent → [tool_calls?]
      - 是 → tool → agent (循环)
      - 否 → respond → END
- `ReActAgent` 类:
  - `chat(text, driver_state, callbacks)` → AgentResult
  - `update_sensor_data(sensor_data)`: 全局函数 (供 app.py 调用)
  - `get_driver_state()`: 全局函数 (供 API 端点调用)

### 步骤 5.7: 创建 Agent Core `modules/ai/agent_core.py`
- 数据模型: `Perception`, `Goal`, `GoalStack`, `TaskPlan`, `ToolCall`
- `EdgeGuardAgent` 类:
  - `handle_user_input(text, gesture, driver_state)` → AgentResult
  - GoalStack: 优先队列 (自主目标 / 用户目标 / 系统目标)
  - TaskPlanner: 目标 → 子任务分解 + 依赖排序
  - ToolRegistry: 动态工具注册/选择
  - ReflectionEngine: 结果验证 + 自动重试
  - `get_thinking_chain()` → list[str]
- `ControlExecutor` 类: 空调/音乐直调 API (< 100ms)

### 步骤 5.8: 创建 6 个子 Agent `modules/ai/agents/`
- `safety_agent.py`: `SafetyAgent` — 眼动+PERCLOS → 风险分级
- `interaction_agent.py`: `InteractionAgent` — 手势+语音 → 意图解析
- `environment_agent.py`: `EnvironmentAgent` — 天气+时段 → 驾驶建议
  - 天气 API: OpenWeatherMap → wttr.in 降级
  - 强制规则模式 (`_llm_disabled = True`): 不走 LLM，避免离线卡死
  - 输出: weather, temperature, humidity, wind_speed, driving_context, risk_score, alerts
- `analyze_agent.py`: `AnalyzeAgent` — 驾驶行为分析
- `diagnose_agent.py`: `DiagnoseAgent` — 故障诊断
- `recommend_agent.py`: `RecommendAgent` — 导航/天气/景点/行程推荐

### 步骤 5.9: 创建编排器 `modules/ai/orchestrator.py`
- `OrchestratorResponse` dataclass
- `ExecutionResult` dataclass
- `Orchestrator` 类:
  - `process(text, driver_state)` → OrchestratorResponse
  - 流程: IntentionAgent → 安全预检 → 调度子 Agent → 聚合结果
- 全局单例: `get_orchestrator()`

### 步骤 5.10: 创建意图分解 `modules/ai/intention_agent.py`
- `IntentionAgent` 类:
  - `decompose(text)` → list[Intent]
  - 意图分类: control / query / diagnose / recommend / trip_plan / weather / navigation

### 步骤 5.11: 创建导航服务 `modules/ai/navigation_service.py`
- `NavigationService` 类:
  - `plan(lat, lon, destination)` → route result
  - Nominatim 地理编码 (地址→坐标)
  - OSRM 路线规划 (坐标→路线)
  - 超时 8s → 返回 error
- 全局单例: `get_navigation_service()`

### 步骤 5.12: 创建位置存储 `modules/ai/location_store.py`
- `LocationStore` 单例:
  - `update(lat, lon, city)` → snapshot
  - `get_coords()` → (lat, lon) | (None, None)
  - `get_city()` → str | None

### 步骤 5.13: 创建车辆知识库 `modules/ai/vehicle_knowledge_base.py`
- `retrieve_knowledge(query, top_k)` → { docs, scores }
- FAISS 向量检索 + sentence-transformers 编码
- 默认语料: `data/knowledge/vehicle_manual.txt`

---

## 阶段 6: 后端 API 端点

### 步骤 6.1: 摄像头与状态端点
- `GET /api/camera/frame`: 返回 JPEG + 状态响应头 (X-Gaze, X-Gesture, X-Action, X-Alert, X-Perclos, X-BlinkRate, X-FatigueScore, X-FatigueLevel, X-Speech ...)
- `GET /api/status`: AI 模块状态 + 网络状态 + 驾驶员状态

### 步骤 6.2: AI 分析端点
- `POST /api/analyze`: 多模态数据 → 边缘-云端路由 → 决策结果 → WS 广播
- `POST /api/interaction/query`: 语音/手势 → InteractionAgent → 交互结果

### 步骤 6.3: Agent 端点
- `POST /api/agent/chat`: ReAct Agent 主入口 (流式 WS 推送)
- `POST /api/agent/query`: Agent Core 查询
- `POST /api/agent/orchestrate`: 多 Agent 编排
- `GET /api/agent/thinking`: Agent 思维链可视化

### 步骤 6.4: 驾驶端点
- `POST /api/drive/insight`: LLM 主动观察 → speak/none
- `POST /api/drive/report`: LLM 驾驶报告生成
- `GET /api/environment` + `POST /api/environment`: 天气 + 驾驶建议
- `POST /api/navigation/route`: 导航路线规划

### 步骤 6.5: 车载控制端点
- `GET /api/ac/state` + `POST /api/ac/command`: 空调状态与控制
- Music 端点: `GET /api/music/state`, `POST /api/music/search`, `POST /api/music/play`, `POST /api/music/pause`, `POST /api/music/next`, `POST /api/music/prev`, `POST /api/music/volume`
- `GET /api/tts`: TTS 语音合成

### 步骤 6.6: 语音端点
- `POST /api/voice/process`: 语音文本 → 意图分析 → 动作+回复
- `POST /api/voice/transcribe`: WAV bytes → Whisper 转写
- `GET /api/voice/state`: 语音模块状态

### 步骤 6.7: 位置端点
- `POST /api/location`: 上报 GPS 位置
- `POST /api/gps/update` + `GET /api/gps/current`: GPS 坐标

### 步骤 6.8: 数据查询端点
- `GET /api/alerts`: 告警记录查询
- `GET /api/interactions`: 交互记录查询
- `GET /api/session/summary`: 驾驶会话摘要
- `GET /api/dashboard/state`: Dashboard 聚合数据

### 步骤 6.9: Prompt 端点
- `GET /api/prompts`: 模板库列表
- `GET /api/prompts/{template_id}`: 模板详情
- `GET /api/prompts/export/markdown`: Markdown 导出

### 步骤 6.10: WebSocket 端点
- `/ws/{client_id}`: 通用 WebSocket
- `/ws/agent_panel`: Agent 思维链推送
- `/ws/agent_result`: Agent 结构化结果推送
- `/ws/navpanel`: 导航 + 环境数据推送

---

## 阶段 7: 摄像头引擎

### 步骤 7.1: 创建摄像头引擎 `backend/app/camera.py`
- `start(ws_manager)`: 启动摄像头采集线程
- `stop()`: 停止采集
- `_loop(ws_manager)`: 主循环
  - 打开摄像头 (cv2.VideoCapture(0, CAP_DSHOW))
  - FaceTracker 初始化
  - HandGestureDetector 初始化
  - AudioPipeline 初始化
  - 5 类独立告警计时器: crowd, absence, fatigue, head, gaze
  - PERCLOS + 眨眼率实时计算
  - 手势识别 (每 3 帧)
  - 5 类独立决策 (优先级: crowd > absence > fatigue > head > gaze)
  - 手势决策独立评估
  - 主动安全干预 (severe/moderate → WS 广播 + 数据库持久化)
  - HUD 绘制: 状态栏 + 告警条 + FPS
  - JPEG 编码 + 状态更新
- `get_frame()`: 获取最新 JPEG 帧
- `get_state()`: 获取最新感知状态

---

## 阶段 8: 独立 AI 引擎 (app.py)

### 步骤 8.1: 创建 app.py
- `EdgeGuardApp` 类:
  - `__init__(dry_run)`: 初始化 AI 决策层 + 感知层
  - `on_multimodal_event(input)`: 多模态回调 → 路由 → 编排 → 响应
  - `run_dry()`: 干跑模式 (4 个测试场景)
  - `run()`: 正常模式 (摄像头 + AI + WebSocket 推流)
  - `_init_speech_thread()`: 语音实时转写线程
  - `_handle_result(result)`: 处理决策结果
- `__main__`: `--dry-run` 参数切换模式

---

## 阶段 9: 前端初始化

### 步骤 9.1: 创建 Vue 3 项目
```bash
cd frontend
npm init -y
npm install vue@^3.4.0 vue-router@^4.3.0
npm install -D vite@^5.4.0 @vitejs/plugin-vue@^5.0.0
```

### 步骤 9.2: 安装前端依赖
```bash
npm install element-plus@^2.7.0
npm install echarts@^5.5.0 leaflet@^1.9.4
npm install tailwindcss@^4.3.3 @tailwindcss/postcss@^4.3.3 postcss@^8.5.22
npm install @lucide/vue@^1.26.0 clsx@^2.1.1 tailwind-merge@^3.6.0 tw-animate-css@^1.4.0
npm install @fontsource/geist-sans@^5.3.0 @fontsource/geist-mono@^5.3.0
```

### 步骤 9.3: 配置 Vite
- `vite.config.js`: Vue 插件 + `@` 别名 + 代理 `/api` → `localhost:8000`, `/ws` → `ws://localhost:8000` + port 8005

### 步骤 9.4: 创建入口文件 `frontend/src/main.js`
- createApp → use(ElementPlus) → use(router) → mount('#app')
- 导入 `element-plus/dist/index.css` + `./styles/globals.css`

### 步骤 9.5: 创建全局样式 `frontend/src/styles/globals.css`
- `@import 'tailwindcss'`
- `@custom-variant dark`
- `@theme inline`: 定义所有 CSS 变量 (颜色/字体/圆角/图表)
- `:root` + `.dark`: 完整浅色/暗色主题变量
- `@layer base`: 全局 border-color, background, color
- HMI 动画: `@keyframes hmi-breathe`, `@keyframes hmi-pulse-ring`
- Leaflet 瓦片修复: `.leaflet-tile { max-width: none !important; }`

### 步骤 9.6: 创建路由 `frontend/src/router/index.js`
- `/` → DashboardView
- `/report` → ReportView (懒加载)

### 步骤 9.7: 创建类型定义 `frontend/src/lib/edgeguard.ts`
- 所有 API 端点常量 (`ENDPOINTS`)
- TypeScript 类型: SafetyLevel, SafetyGateState, Telemetry, SafetyAlert, DrivingStats, NavInfo, ChatMessage, AgentTraceStep, AgentResult, HvacState, ACState, GestureCommand, MusicState, SongInfo, WSMessage 等
- Mock 数据: initialTelemetry, initialAlerts, initialStats, initialChat, mockNav, quickReplies, mockAgentTrace
- 手势指令表: gestureCommands

### 步骤 9.8: 创建工具函数 `frontend/src/lib/utils.ts`
- `cn(...inputs)`: clsx + tailwind-merge 合并

---

## 阶段 10: 前端 Composables

### 步骤 10.1: 创建摄像头遥测 `frontend/src/composables/useTelemetry.ts`
- 响应式状态: telemetry, alerts, stats, driverState
- `startPolling()`: setInterval 每 200ms GET /api/camera/frame
- 解析响应头: X-Gaze, X-Gesture, X-Action, X-Alert, X-Severity, X-Perclos, X-BlinkRate, X-FatigueScore 等
- `stopPolling()`: clearInterval
- 告警列表维护 (最近 20 条)

### 步骤 10.2: 创建 Agent WebSocket `frontend/src/composables/useAgentWS.ts`
- WebSocket 连接: `/ws/agent_panel` + `/ws/agent_result`
- 响应式状态: messages, traceSteps, agentResults, isConnected
- `sendMessage(text)`: POST /api/agent/chat
- `handleWSMessage(msg)`: 按 type 分发处理
  - agent_perceive → traceSteps 更新
  - agent_safety_gate → traceSteps 更新
  - agent_reasoning → traceSteps 更新
  - agent_tool_call → traceSteps 更新
  - agent_final → messages 添加 AI 回复
  - agent_navigation → agentResults 添加导航卡片
  - agent_weather_query → agentResults 添加天气卡片
  - agent_trip_plan → 行程数据
  - agent_attractions → 景点数据
- 自动重连: 断开后 3s 重试
- 心跳: 接收 ping → 忽略 (服务端被动检测)

---

## 阶段 11: 前端组件 — 布局

### 步骤 11.1: 创建 App.vue
- `<router-view />`

### 步骤 11.2: 创建 DashboardView `frontend/src/views/DashboardView.vue`
- 五大面板布局: AppSidebar (左) + TopBar (顶) + 中央区域 (SafetyPanel + MapArea + AiPanel) + BottomBar (底)
- 响应式网格: `grid grid-cols-[64px_1fr_360px] grid-rows-[48px_1fr_auto]`
- 挂载时: 启动 useTelemetry 轮询 + useAgentWS 连接 + 获取环境数据 + 获取仪表盘状态

### 步骤 11.3: 创建 AppSidebar `frontend/src/components/hmi/AppSidebar.vue`
- 垂直导航: 仪表盘 / 驾驶报告 / 设置
- Lucide 图标: LayoutDashboard, FileText, Settings
- 激活态: `bg-accent text-accent-foreground`
- 底部: 离线状态指示器 + 系统版本

### 步骤 11.4: 创建 TopBar `frontend/src/components/hmi/TopBar.vue`
- 左侧: 时间显示
- 中央: 天气图标 + 温度 + 城市 (来自环境广播)
- 右侧: 系统状态 (在线/离线/Agent 模式)

### 步骤 11.5: 创建 BottomBar `frontend/src/components/hmi/BottomBar.vue`
- 快捷操作按钮: 空调、音乐、导航、语音
- QuickBtn 组件 × 4

---

## 阶段 12: 前端组件 — 安全与监控

### 步骤 12.1: 创建 SafetyPanel `frontend/src/components/hmi/SafetyPanel.vue`
- 告警卡片列表 (最近 10 条)
- 告警级别颜色: danger → border-danger 红色, warning → border-warn 黄色, normal → border-safe 绿色
- 空状态: "✅ 驾驶状态良好"
- 告警脉冲动画 (danger 级别)

### 步骤 12.2: 创建 StatsPanel `frontend/src/components/hmi/StatsPanel.vue`
- 驾驶统计: 时长、分心次数、严重告警、注意力评分
- ECharts 图表: 疲劳趋势折线图 (12 个时间点)
- 数据来源: useTelemetry + GET /api/session/summary

### 步骤 12.3: 创建 AttentionRing `frontend/src/components/hmi/AttentionRing.vue`
- SVG 圆环进度条
- 颜色: 80-100 safe, 50-79 warn, <50 danger
- 动画: `animate-hmi-breathe` (正常), `animate-hmi-pulse` (告警)

---

## 阶段 13: 前端组件 — AI 交互

### 步骤 13.1: 创建 AiPanel `frontend/src/components/hmi/AiPanel.vue`
- 对话消息列表 (user/assistant)
- Agent 追踪链 (可折叠): 每步显示 phase, detail, status, durationMs
- 输入区域: Element Plus el-input + 发送按钮 + 语音按钮
- 快捷回复: 4 个预设按钮 (来自 quickReplies)
- 路由选择器: auto / quick / react / multi / readonly
- 自动滚动到底部

### 步骤 13.2: 创建 AgentResultPanel `frontend/src/components/hmi/AgentResultPanel.vue`
- 结构化结果卡片:
  - 导航卡片: 目的地、距离、预计时间、路线摘要
  - 天气卡片: 城市、温度、天气描述、驾驶建议
  - 景点卡片: 名称、评分、地址
- 空状态: "等待 Agent 结果..."

### 步骤 13.3: 创建 TripPlanView `frontend/src/components/hmi/TripPlanView.vue`
- 行程概览: 城市、天数、预算
- 每日行程: 时间线展示 (上午/下午/晚上)
- 来源: WebSocket agent_trip_plan 消息

---

## 阶段 14: 前端组件 — 车载控制

### 步骤 14.1: 创建 ClimateControl `frontend/src/components/hmi/ClimateControl.vue`
- Element Plus el-drawer 抽屉容器
- 温度显示: 大号数字 (text-3xl) + ↑↓ 调节按钮
- 模式选择: 制冷/制热/自动/送风 (el-radio-group)
- 风速滑块: 1-5 档 (el-slider)
- 开关按钮: 拟物化大圆形按钮
- API: GET /api/ac/state, POST /api/ac/command

### 步骤 14.2: 创建 GestureControl `frontend/src/components/hmi/GestureControl.vue`
- 手势可视化: 当前检测到的手势名称 + 图标
- 手势指令表: gestureCommands 列表 (手势 / 动作 / 含义 / 分类)
- 最近手势检测历史
- 数据来源: useTelemetry (X-Gesture 响应头)

### 步骤 14.3: 创建 QuickBtn `frontend/src/components/hmi/QuickBtn.vue`
- Props: icon, label, active, disabled
- 大号触控区域: min 44×44px
- 状态: default / active / disabled

---

## 阶段 15: 前端组件 — 地图与导航

### 步骤 15.1: 创建 MapArea `frontend/src/components/hmi/MapArea.vue`
- Leaflet 地图初始化 + 瓦片层
- 当前位置标记 (L.marker)
- 路线折线 (L.polyline)
- 天气叠加条 (半透明)
- 导航信息条: 距离、预计时间、下个转弯
- 响应式: 容器尺寸变化时 `map.invalidateSize()`
- Leaflet CSS 修复: `.leaflet-tile { max-width: none !important; }`

---

## 阶段 16: 前端组件 — 报告与设置

### 步骤 16.1: 创建 ReportView `frontend/src/views/ReportView.vue`
- 会话摘要数据: GET /api/session/summary, GET /api/alerts, GET /api/interactions
- LLM 报告: POST /api/drive/report → summary + advice
- ECharts 图表: 疲劳趋势 + 告警分类饼图
- 交互记录时间线

### 步骤 16.2: 创建 SettingsPanel `frontend/src/components/hmi/SettingsPanel.vue`
- 主题切换: 暗色/浅色
- 摄像头开关
- 语音开关
- TTS 音量
- 告警灵敏度
- API 配置查看 (遮罩显示)

---

## 阶段 17: 集成与调试

### 步骤 17.1: 端到端测试 — 后端启动
```bash
uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000
# 验证: curl http://localhost:8000/api/health → {"status": "ok"}
```

### 步骤 17.2: 端到端测试 — 前端启动
```bash
cd frontend && npm run dev
# 验证: 浏览器打开 http://localhost:8005 → DashboardView 渲染
```

### 步骤 17.3: 端到端测试 — 摄像头引擎
```bash
python app.py --dry-run  # 干跑模式 → 4 个测试场景通过
python app.py            # 正常模式 → 摄像头画面 + HUD 显示
```

### 步骤 17.4: 端到端测试 — AI 对话链
```bash
curl -X POST http://localhost:8000/api/agent/chat \
  -H "Content-Type: application/json" \
  -d '{"text":"打开空调","driver_state":{}}'
# 验证: 返回 reply_text + safety_level + status
```

### 步骤 17.5: 端到端测试 — WebSocket 连接
- 使用浏览器 DevTools → Network → WS:
  - 连接 `/ws/agent_panel`
  - 发送消息测试
  - 验证心跳 ping 到达

### 步骤 17.6: 端到端测试 — 离线降级
- 断开网络 → 验证 offline_mode 自动激活
- 验证: 安全告警/手势/语音关键词正常工作
- 验证: AI 对话降级到本地模板

### 步骤 17.7: 性能检查
- 摄像头 FPS ≥ 15
- API 响应 p50 < 200ms
- 前端首屏加载 < 2s
- 内存占用 < 500MB (Python + Node)

---

## 阶段 18: 生产构建

### 步骤 18.1: 构建前端
```bash
cd frontend && npm run build
# 输出: frontend/dist/
```

### 步骤 18.2: 验证后端托管前端
- 后端挂载 `frontend/dist/` 为静态文件 (已通过 `app.mount("/", StaticFiles(...))`)
- 访问 `http://localhost:8000` → 前端 SPA 正常渲染

### 步骤 18.3: 创建启动脚本
```bash
# start.sh
#!/bin/bash
# 启动后端 (自动托管前端 dist)
uvicorn backend.main:app --host 0.0.0.0 --port 8000
```

---

## 阶段 19: 规范文档 (当前步骤)

### 步骤 19.1: 创建 specs/PRD.md
### 步骤 19.2: 创建 specs/APP_FLOW.md
### 步骤 19.3: 创建 specs/TECH_STACK.md
### 步骤 19.4: 创建 specs/FRONTEND_GUIDELINES.md
### 步骤 19.5: 创建 specs/BACKEND_STRUCTURE.md
### 步骤 19.6: 创建 specs/IMPLEMENTATION_PLAN.md (本文档)
### 步骤 19.7: 创建 CLAUDE.md
### 步骤 19.8: 创建 progress.txt

---

## 待实现功能 (Backlog)

| 优先级 | 功能 | 预估工作量 |
|--------|------|-----------|
| P1 | 用户认证 (JWT/API Key) | 4h |
| P1 | HTTPS 支持 | 2h |
| P1 | 速率限制 (LLM API) | 2h |
| P1 | 数据库迁移工具 (Alembic 风格) | 3h |
| P2 | 多摄像头支持 | 8h |
| P2 | 驾驶员身份识别 (Face ID) | 16h |
| P2 | 手机端 HMI (PWA) | 16h |
| P2 | CAN 总线接入 (OBD-II) | 40h |
| P3 | 车队管理云平台 | 80h |
| P3 | 多语言支持 (i18n) | 8h |
| P3 | 单元测试 + E2E 测试 | 16h |
| P3 | CI/CD Pipeline | 8h |
