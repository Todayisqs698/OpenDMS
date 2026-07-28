# BACKEND_STRUCTURE — EdgeGuard 后端结构文档

> **版本**: 1.0.0 | **最后更新**: 2026-07-26

---

## 1. 项目目录结构

```
EdgeGuard/
├── backend/                              # FastAPI 后端 (port 8000)
│   ├── main.py                           # 主入口 — 50+ API 端点 + WebSocket + 生命周期
│   └── app/
│       ├── __init__.py
│       ├── camera.py                     # 摄像头引擎 — MediaPipe 实时感知 + JPEG 推流
│       ├── core/
│       │   ├── __init__.py
│       │   └── database.py               # SQLite 持久化 — 告警/交互/会话
│       └── ws/
│           ├── __init__.py
│           └── manager.py                # WebSocket 连接管理 + 广播
│
├── modules/                              # AI + 感知核心模块
│   ├── ai/                               # AI 决策层 (21 模块)
│   │   ├── agent_core.py                 # Agent Core — GoalStack + Planner + Reflection
│   │   ├── agent_graph.py                # LangGraph ReAct Agent 循环
│   │   ├── agent_tools.py                # Agent 工具注册
│   │   ├── orchestrator.py               # 多 Agent 编排引擎
│   │   ├── intention_agent.py            # 意图分解 Agent
│   │   ├── deepseek_client.py            # DeepSeek LLM 客户端 (OpenAI SDK)
│   │   ├── tools.py                      # 8 个 Function Calling 工具定义
│   │   ├── safety_gate.py                # 安全门控 — 风险级别 → 工具白名单
│   │   ├── memory.py                     # Agent 工作记忆 + 会话记忆
│   │   ├── edge_cloud_router.py          # 边缘-云端混合路由器
│   │   ├── local_decision_engine.py      # 本地决策引擎 (离线关键词 + 5类告警)
│   │   ├── fallback_handler.py           # 8 种离线降级场景
│   │   ├── driver_state_machine.py       # 7 维驾驶员状态向量 + 趋势预测
│   │   ├── fatigue_predictor.py          # 疲劳趋势预测
│   │   ├── safe_executor.py              # Agent 执行异常兜底
│   │   ├── langgraph_orchestrator.py     # LangGraph 编排器
│   │   ├── location_store.py             # GPS 位置单例存储
│   │   ├── navigation_service.py         # 导航路线规划 (OSRM + Nominatim)
│   │   ├── multimodal_collector.py       # 多模态数据收集器
│   │   ├── vehicle_knowledge_base.py     # RAG 车辆知识库
│   │   ├── interaction_agent.py          # 交互理解 Agent (旧版)
│   │   ├── prompts/                      # Prompt 模板库
│   │   │   ├── __init__.py               # 公共 API (render, get_template, search)
│   │   │   ├── registry.py               # 模板注册中心
│   │   │   ├── template.py               # PromptTemplate 数据类
│   │   │   ├── agent_templates.py        # Agent 类 Prompt
│   │   │   ├── analysis_templates.py     # 分析类 Prompt
│   │   │   └── safety_templates.py       # 安全类 Prompt
│   │   └── agents/                       # 6 个子 Agent
│   │       ├── __init__.py
│   │       ├── safety_agent.py           # 安全 Agent — 眼动+头部姿态 → 风险分级
│   │       ├── interaction_agent.py      # 交互 Agent — 手势+语音 → 意图解析
│   │       ├── environment_agent.py      # 环境 Agent — 天气+时段 → 驾驶建议
│   │       ├── analyze_agent.py          # 分析 Agent — 驾驶行为分析
│   │       ├── diagnose_agent.py         # 诊断 Agent — 故障诊断
│   │       └── recommend_agent.py        # 推荐 Agent — 导航/天气/景点/行程
│   │
│   ├── vision/                           # 视觉感知层 (全本地推理)
│   │   ├── face_tracker.py               # MediaPipe 468 点面部追踪 + PnP 头部姿态
│   │   ├── hand_gesture.py               # 手势识别 — MediaPipe Tasks API + 几何规则 + TFLite
│   │   ├── gesture_classifier.py         # TFLite 手势分类器封装
│   │   └── gesture/
│   │       └── keypoint_classifier.py    # 21 点关键点分类器
│   │
│   ├── audio/                            # 语音感知层
│   │   ├── speech_recognizer.py          # Whisper 语音转写
│   │   ├── audio_pipeline.py             # 音频采集管线 (VAD + 降噪 + 回调)
│   │   └── recorder.py                   # 麦克风录音器
│   │
│   ├── actions/
│   │   └── action_handler.py             # 动作执行器
│   │
│   └── system/
│       ├── __init__.py
│       └── interaction_logger.py         # 交互日志记录
│
├── data/
│   ├── edgeguard.db                      # SQLite 主数据库
│   ├── agent_memory.json                 # Agent 持久记忆 (JSON)
│   ├── knowledge/
│   │   ├── vehicle_manual.txt            # 车辆手册文本 (RAG 语料)
│   │   └── faiss_index/                  # FAISS 向量索引 + metadata
│   └── music/                            # 本地音乐文件目录
│
├── app.py                                # 独立摄像头 + AI 主循环 (可脱离前端运行)
├── requirements.txt                      # Python 依赖
└── .env.example                          # 环境变量模板
```

---

## 2. 数据库模式 (SQLite)

### 2.1 数据库文件

| 文件 | 位置 | 用途 |
|------|------|------|
| `edgeguard.db` | `data/edgeguard.db` | 主数据库 |
| `user_memory.db` | `backend/data/user_memory.db` | Agent 用户记忆 (预留) |
| `interactions.db` | `backend/data/logs/interactions.db` | 旧版交互日志 (已迁移) |

### 2.2 表: `drive_sessions` — 驾驶会话

```sql
CREATE TABLE IF NOT EXISTS drive_sessions (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    start_time      TEXT    NOT NULL,              -- ISO 8601: "2026-07-26 14:30:00"
    end_time        TEXT,                          -- NULL 表示会话进行中
    avg_fatigue_score REAL,                        -- 平均疲劳分数 (0-100)
    remark          TEXT                           -- 备注
);
```

| 列 | 类型 | 约束 | 说明 |
|----|------|------|------|
| `id` | INTEGER | PK, AUTOINCREMENT | 会话 ID |
| `start_time` | TEXT | NOT NULL | 会话开始时间 |
| `end_time` | TEXT | NULLABLE | 会话结束时间，NULL = 进行中 |
| `avg_fatigue_score` | REAL | NULLABLE | 全程平均疲劳分数 |
| `remark` | TEXT | NULLABLE | 备注信息 |

### 2.3 表: `alerts` — 安全告警记录

```sql
CREATE TABLE IF NOT EXISTS alerts (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id      INTEGER,                      -- FK → drive_sessions.id
    risk_level      TEXT    NOT NULL,              -- "normal" | "warning" | "danger" | "critical"
    alert_msg       TEXT,                          -- 告警详情 (如 "[crowd] 多人 — 警告！检测到...")
    perclos         REAL,                          -- PERCLOS 值 (0.0-1.0)
    blink_rate      REAL,                          -- 眨眼率 (次/分钟)
    fatigue_score   REAL,                          -- 疲劳分数 (0-100)
    created_at      TEXT    NOT NULL,              -- ISO 8601
    FOREIGN KEY (session_id) REFERENCES drive_sessions(id)
);

-- 常用查询索引
CREATE INDEX IF NOT EXISTS idx_alerts_session ON alerts(session_id);
CREATE INDEX IF NOT EXISTS idx_alerts_level ON alerts(risk_level);
```

| 列 | 类型 | 约束 | 说明 |
|----|------|------|------|
| `id` | INTEGER | PK, AUTOINCREMENT | 告警 ID |
| `session_id` | INTEGER | FK | 所属会话 |
| `risk_level` | TEXT | NOT NULL | 风险等级 |
| `alert_msg` | TEXT | NULLABLE | 告警详情 (类别 + 标签 + TTS 文本) |
| `perclos` | REAL | NULLABLE | 触发时的 PERCLOS 值 |
| `blink_rate` | REAL | NULLABLE | 触发时的眨眼率 |
| `fatigue_score` | REAL | NULLABLE | 触发时的疲劳分数 |
| `created_at` | TEXT | NOT NULL | 告警时间 |

### 2.4 表: `interactions` — 用户交互记录

```sql
CREATE TABLE IF NOT EXISTS interactions (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id      INTEGER,                      -- FK → drive_sessions.id
    user_query      TEXT,                          -- 用户输入 (语音转写文本)
    ai_response     TEXT,                          -- AI 回复文本
    created_at      TEXT    NOT NULL,              -- ISO 8601
    FOREIGN KEY (session_id) REFERENCES drive_sessions(id)
);

CREATE INDEX IF NOT EXISTS idx_interactions_session ON interactions(session_id);
```

| 列 | 类型 | 约束 | 说明 |
|----|------|------|------|
| `id` | INTEGER | PK, AUTOINCREMENT | 交互 ID |
| `session_id` | INTEGER | FK | 所属会话 |
| `user_query` | TEXT | NULLABLE | 用户语音/文本输入 |
| `ai_response` | TEXT | NULLABLE | AI 回复文本 |
| `created_at` | TEXT | NOT NULL | 交互时间 |

---

## 3. API 端点合约

### 3.1 健康检查

```
GET /api/health
→ 200 { "status": "ok", "system": "EdgeGuard" }
```

### 3.2 摄像头

```
GET /api/camera/frame?landmarks=1
→ 200 image/jpeg
  Headers:
    X-Gaze: center|left|right|up|down|...
    X-Gesture: gesture_name|""
    X-Action: action_code
    X-Severity: normal|warning|danger|critical
    X-Alert: 0|1
    X-Duration: float (偏离持续时间)
    X-Perclos: float
    X-BlinkRate: float
    X-FatigueScore: int
    X-FatigueLevel: normal|warning|danger
    X-AlertCategory: crowd|absence|fatigue|head|gaze
    X-Speech: 语音转写文本
→ 503 (摄像头未启动，返回占位图)
```

### 3.3 系统状态

```
GET /api/status
→ 200 {
  "status": "ok",
  "offline_mode": false,
  "llm_online": true,
  "active_engine": "DeepSeek-V3 (API)",
  "cloud_latency": { "avg": 0, "min": 0, "max": 0, "count": 0 },
  "agents": { "safety": true, "interaction": true, "environment": true },
  "perception_available": true,
  "driver_state": { "state": "...", "risk_score": 0, "trend": "...", "vector": [...] }
}
```

### 3.4 AI 分析

```
POST /api/analyze
  Body: {
    trigger: "speech" | "gaze" | "gesture" | "multi",
    gaze_state: "center",
    gaze_duration: 0.0,
    gesture: "",
    gesture_confidence: 0.0,
    speech_text: "",
    context_type: "user_input" | "distraction_detected" | "camera_stream"
  }
→ 200 {
    "status": "ok",
    "route": "local" | "cloud" | "hybrid",
    "offline": false,
    "result": { action_code, recommendation_text, alert, severity, ... },
    "interaction_result": { ... } | null
  }
```

### 3.5 Agent Chat (ReAct)

```
POST /api/agent/chat
  Body: {
    text: "打开空调",
    gesture: "",
    driver_state: { gaze, duration, perclos, blink_rate, ... }
  }
→ 200 {
    "status": "ok",
    "result": {
      "reply_text": "已为您开启空调，温度设置为24°C",
      "steps": 3,
      "safety_level": "normal",
      "status": "success"
    }
  }
→ 500 { "status": "error", "message": "..." }

副作用:
  - WebSocket 流式推送: agent_perceive, agent_safety_gate, agent_reasoning,
    agent_tool_call, agent_final
  - 持久化: INSERT INTO interactions
  - 告警持久化: 非 normal 风险 → INSERT INTO alerts
```

### 3.6 Agent Orchestrate (多 Agent)

```
POST /api/agent/orchestrate
  Body: {
    text: "帮我规划杭州3天行程并看天气",
    gesture: "",
    driver_state: { ... }
  }
→ 200 {
    "status": "ok",
    "result": {
      "reply_text": "已为您规划杭州3天行程...",
      "intent_plan": "trip_plan → weather → attractions",
      "results": [
        {
          "intent_id": "intent_1",
          "intent_category": "trip_plan",
          "agent": "recommend_agent",
          "success": true,
          "reply": "...",
          "actions": ["show_trip_plan"],
          "error": null,
          "duration_ms": 1234.5
        },
        ...
      ],
      "actions": ["show_trip_plan", "show_weather"],
      "needs_clarification": false,
      "total_duration_ms": 2500.0,
      "route": "cloud"
    }
  }

副作用:
  - WebSocket 推送: agent_navigation, agent_weather_query, agent_trip_plan, agent_attractions
```

### 3.7 Agent Query (Agent Core)

```
POST /api/agent/query
  Body: { text, gesture, driver_risk, driver_fatigue, driver_distracted }
→ 200 {
    "status": "ok",
    "result": {
      "reply_text": "...",
      "goal_id": "goal_1",
      "goal_description": "开启空调",
      "status": "success",
      "actions": ["TurnOnAC"],
      "allow_execute": true,
      "isFinal": true
    }
  }
```

### 3.8 语音处理

```
POST /api/voice/process
  Body: { text: "打开空调" }
→ 200 {
    "status": "ok",
    "reply": "空调已开启",
    "action_code": "TurnOnAC",
    "tts_text": "空调已开启",
    "route": "local" | "interaction" | "fallback"
  }

POST /api/voice/transcribe
  Body: <WAV bytes>
→ 200 { "status": "ok", "text": "打开空调" }
→ 200 { "status": "error", "text": "", "error": "音频数据太短" }

GET /api/voice/state
→ 200 { "status": "ok", "modules": { "whisper": true, "tts": true }, "active_listening": false }
```

### 3.9 TTS 语音合成

```
GET /api/tts?text=你好
→ 200 audio/mpeg  (edge-tts, zh-CN-XiaoxiaoNeural)
→ 200 audio/wav   (pyttsx3 降级)
→ 200 { "error": "TTS 引擎均不可用: ..." }
```

### 3.10 驾驶洞察与报告

```
POST /api/drive/insight
  Body: { gaze_pattern, gesture, duration_sec, attention }
→ 200 {
    "status": "ok",
    "speak": true | false,
    "text": "您看了很久窗外，需要停车休息吗？" | ""
  }

POST /api/drive/report
  Body: { duration_min, distractions, severe, attention_score, avg_gaze }
→ 200 { "status": "ok", "summary": "...", "advice": "...", "route": "cloud" }
→ 200 { "status": "error", "message": "生成失败: ..." }
```

### 3.11 环境与天气

```
GET /api/environment?city=北京&lat=39.9&lon=116.4
POST /api/environment  { city, lat, lon }
GET /api/weather?lat=39.9&lon=116.4
→ 200 {
    "status": "ok",
    "data": {
      "weather": "Clouds",
      "weather_icon": "cloud",
      "weather_emoji": "☁️",
      "weather_desc": "多云",
      "temperature": 22.5,
      "humidity": 65,
      "wind_speed": 12,
      "visibility": 10000,
      "driving_context": "多云天气，能见度良好，适合驾驶",
      "risk_score": 0.1,
      "alerts": [],
      "reasoning": "天气+时段规则评估",
      "city": "北京",
      "lat": 39.9, "lon": 116.4,
      "location_source": "gps" | "city_lookup" | "offline",
      "timestamp": "2026-07-26T14:30:00"
    }
  }
```

### 3.12 导航

```
POST /api/navigation/route
  Body: { destination: "杭州", lat: 39.9, lon: 116.4 }
→ 200 {
    "success": true,
    "destination": "杭州",
    "distance_km": 1200.5,
    "duration_min": 720,
    "route_summary": "经G2京沪高速，全程约1200公里",
    "steps": [...],
    "geometry": [[lat, lon], ...],
    "source": "osrm",
    "origin": "当前位置",
    "map_url": "...",
    "waypoints": [...]
  }
→ 200 { "success": false, "route_summary": "请提供目的地", ... }
→ 200 { "success": false, "route_summary": "导航服务暂不可用", ... }  (超时 8s)
```

### 3.13 空调控制

```
GET /api/ac/state
→ 200 { "status": "ok", "data": { "power": false, "temperature": 24, "mode": "auto", "fanSpeed": 2 } }

POST /api/ac/command
  Body: {
    command: "TurnOnAC" | "TurnOffAC" | "temp_up" | "temp_down" | "set",
    temperature: 24 | "up" | "down",
    mode: "cool" | "heat" | "auto" | "fan",
    fanSpeed: 1-5,
    delta: 1
  }
→ 200 { "status": "ok", "data": { ... } }

验证规则:
  - temperature: min 16, max 30
  - fanSpeed: min 1, max 5
  - mode: 仅 "cool" | "heat" | "auto" | "fan"
```

### 3.14 音乐控制

```
GET  /api/music/state
POST /api/music/search   { keyword: "周杰伦" }
POST /api/music/play     { song_id: 123 }
POST /api/music/pause    (切换播放/暂停)
POST /api/music/next
POST /api/music/prev
POST /api/music/volume   { volume: 80 }

搜索降级策略:
  1. 本地文件 → data/music/*.mp3
  2. 网易云 API → localhost:3000/cloudsearch
  3. 演示曲目 → 内置 8 首演示歌曲

播放降级策略:
  1. 本地文件 url → 直接播放
  2. 演示曲目 → 仅展示"播放中"状态，无真实音频
  3. 网易云 API url → 在线播放
```

### 3.15 位置

```
POST /api/location   { lat: 39.9, lon: 116.4, city: "北京" }
POST /api/gps/update?lat=39.9&lon=116.4
GET  /api/gps/current
→ 200 { "status": "ok", "data": { "lat": 39.9, "lon": 116.4, "updated_at": 1234567890.0 } }
→ 200 { "status": "no_gps", "message": "暂无 GPS 数据" }
```

### 3.16 数据查询

```
GET /api/alerts?limit=50&session_id=1
→ 200 { "status": "ok", "total": 5, "data": [{ id, session_id, risk_level, alert_msg, perclos, blink_rate, fatigue_score, created_at }, ...] }

GET /api/interactions?limit=100&session_id=1
→ 200 { "status": "ok", "total": 10, "data": [{ id, session_id, user_query, ai_response, created_at }, ...] }

GET /api/session/summary?session_id=1
→ 200 {
    "status": "ok",
    "data": {
      "session_id": 1,
      "start_time": "2026-07-26 14:30:00",
      "end_time": "2026-07-26 15:45:00",
      "total_alerts": 5,
      "avg_fatigue_score": 23.5,
      "level_breakdown": { "normal": 2, "warning": 2, "danger": 1 }
    }
  }
→ 200 { "status": "ok", "data": null, "message": "暂无驾驶会话" }
```

### 3.17 Dashboard 聚合

```
GET /api/dashboard/state?need=all|environment|driver_state|modules
→ 200 {
    "status": "ok",
    "ts": 1234567890.0,
    "environment": { ... },       // need=all|environment
    "driver_state": { ... },      // need=all|driver_state
    "offline": false,             // need=all|modules
    "modules": { ... }            // need=all|modules
  }
```

### 3.18 Prompt 模板库

```
GET /api/prompts?category=safety&search=疲劳
→ 200 {
    "status": "ok",
    "total": 3,
    "categories": ["agent", "analysis", "safety"],
    "templates": [{ id, name, category, description, variables, version }, ...]
  }

GET /api/prompts/{template_id}
→ 200 {
    "status": "ok",
    "template": { ... },
    "content": "完整模板文本...",
    "fallback_content": "降级版本...",
    "preview": "渲染预览..."
  }

GET /api/prompts/export/markdown
→ 200 text/markdown
```

### 3.19 手势可用性

```
GET /api/gesture/available
→ 200 {
    "available": true,
    "geometry_available": true,
    "gestures": ["Open", "Close", "Thumbs Up", "Thumbs Down", "OK", "Peace", "Pointer", "Quiet Coyote", ...]
  }
```

---

## 4. WebSocket 端点

### 4.1 端点列表

| 路径 | 客户端 ID | 推送内容 |
|------|----------|---------|
| `/ws/{client_id}` | 自定义 | 通用双向通信 |
| `/ws/agent_panel` | `agent_panel` | Agent 思维链 (perceive→safety_gate→agent→tool→result) |
| `/ws/agent_result` | `agent_result` | Agent 结构化结果 (导航/天气/景点/行程) |
| `/ws/navpanel` | `navpanel` | 环境数据 (每 30s) + 导航结果 |

### 4.2 消息格式

```json
{
  "type": "agent_perceive",
  "data": {
    "phase": "perceive",
    "detail": "视线 center · 疲劳 normal · PERCLOS 0.03",
    "status": "done",
    "durationMs": 120
  }
}
```

### 4.3 连接管理

```
连接:
  1. 客户端发起 WebSocket 连接
  2. WSManager.connect(websocket, client_id)
     - 接受连接
     - 注册元数据 (connected_at, last_active)
     - 推送离线缓冲消息 (如有)

心跳:
  - 服务端每 30s 发送 { type: "ping", timestamp }
  - 客户端无需响应 (被动检测)

超时:
  - 客户端 90s 无活动 → 自动断开
  - 消息缓冲: 最多保留 100 条/客户端，总量超过 500 条截断至 200 条

断开:
  - WSManager.disconnect(client_id)
  - 保留消息缓冲 (重连后恢复)
  - 日志: "客户端断开: {client_id} (当前在线: N)"
```

---

## 5. 存储规则

### 5.1 数据库

- **引擎**: SQLite 3.x (Python 标准库 `sqlite3`)
- **连接**: 每次操作创建新连接 (`get_db_connection()`)，操作完成后关闭
- **行工厂**: `sqlite3.Row` (字典访问)
- **WAL 模式**: 使用默认 journal_mode (未显式设置 WAL)
- **并发**: 单写者，读并发。车载单用户场景足够
- **迁移**: 无迁移工具，使用 `CREATE TABLE IF NOT EXISTS` (幂等初始化)

### 5.2 文件存储

| 路径 | 内容 | 写入策略 |
|------|------|---------|
| `data/edgeguard.db` | SQLite 数据库 | 每次 API 调用时同步写入 |
| `data/agent_memory.json` | Agent 持久记忆 | JSON 序列化 |
| `data/music/*.mp3` | 本地音乐 | 用户手动放入 |
| `data/knowledge/vehicle_manual.txt` | RAG 语料 | 手动编辑 |
| `data/knowledge/faiss_index/` | FAISS 索引 | `vehicle_knowledge_base.py` 构建 |
| `backend/data/logs/` | 交互日志 (JSON) | 旧版，已迁移到 SQLite |

### 5.3 内存状态

以下状态存储在模块级全局变量中，服务重启丢失：

| 变量 | 模块 | 内容 |
|------|------|------|
| `_ac_state` | `backend/main.py` | 空调状态 (power, temperature, mode, fanSpeed) |
| `_music_state` | `backend/main.py` | 音乐播放状态 (playing, current_song, playlist, volume) |
| `_current_gps` | `backend/main.py` | 当前 GPS 坐标 |
| `_current_session_id` | `backend/app/core/database.py` | 当前驾驶会话 ID |
| `_frame` / `_state` | `backend/app/camera.py` | 最新摄像头帧 + 感知状态 |
| `ws_manager.connections` | `backend/app/ws/manager.py` | WebSocket 活跃连接 |
| `_driver_state_machine` | `modules/ai/agent_graph.py` | 驾驶员 7 维状态向量 |
| `LocationStore._instance` | `modules/ai/location_store.py` | GPS 位置单例 |

---

## 6. 认证与安全

### 6.1 当前状态
- **无身份认证**: 单机本地部署，不对外暴露
- **CORS**: `allow_origins=["*"]` (开发阶段)
- **API Key**: DeepSeek/高德/OpenWeather 密钥通过 `.env` 管理
- **`.env`**: 已加入 `.gitignore`，不提交到版本控制

### 6.2 安全建议 (生产部署)
- [ ] 添加 API 鉴权 (JWT / API Key)
- [ ] CORS 限制为前端域名
- [ ] HTTPS (生产环境)
- [ ] 输入验证：所有用户输入需 sanitize
- [ ] 速率限制：LLM API 调用频率控制

---

## 7. 边缘情况处理

| 场景 | 处理 |
|------|------|
| 摄像头热插拔 | 不支持，需重启服务 |
| 多人同时出现在画面中 | 当前仅追踪第一张脸，多人检测计数器 (crowd_face_count >= 2) 触发告警 |
| 夜间/低光照 | MediaPipe 在低光照下精度下降，依赖红外摄像头 (硬件) |
| 驾驶员戴墨镜 | MediaPipe 可能无法检测眼睛特征点 → EAR 计算回退 |
| 驾驶员戴口罩 | MediaPipe Face Landmarker 对下半脸遮挡有鲁棒性，不影响额头/眼睛跟踪 |
| 数据库文件被锁定 | SQLite 默认超时 5s，写入失败 → logger.warning |
| API Key 过期/余额不足 | DeepSeek API 返回 401 → offline_mode 自动激活 |
| 磁盘空间不足 | SQLite 写入失败 → logger.warning，不影响实时功能 |
| 摄像头分辨率异常 | OpenCV 自动适配，frame.shape 动态获取 |
| 手势识别器模型文件缺失 | HandGestureDetector.is_available = False，几何规则仍可用 |
| 两个服务同时写数据库 | SQLite 单写者锁，第二个写入等待或超时 |
