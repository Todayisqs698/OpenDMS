# APP_FLOW — EdgeGuard 应用流程文档

> **版本**: 1.0.0 | **最后更新**: 2026-07-26

---

## 1. 路由与屏幕清单

| 路径 | 页面名称 | 组件 | 说明 |
|------|---------|------|------|
| `/` | DashboardView | `src/views/DashboardView.vue` | 主仪表盘 — 五大面板布局 |
| `/report` | ReportView | `src/views/ReportView.vue` (懒加载) | 驾驶报告页 |

### 1.1 前端路由 (Vue Router)

```
/ (DashboardView)
  ├── AppSidebar         — 左侧导航栏（页面切换）
  ├── TopBar             — 顶栏（状态 + 天气 + 时间）
  ├── SafetyPanel        — 安全告警面板（左上）
  ├── StatsPanel         — 驾驶统计面板（左下）
  ├── MapArea            — 地图区域（中央 Leaflet）
  ├── AiPanel            — AI 对话面板（右侧）
  ├── BottomBar          — 底部快捷栏
  ├── ClimateControl     — 空调控制（抽屉/弹窗）
  ├── GestureControl     — 手势可视化（弹窗）
  ├── AgentResultPanel   — Agent 结构化结果展示（导航/天气/景点/行程）
  ├── TripPlanView       — 行程规划展示
  ├── AttentionRing      — 注意力环（摄像头画面叠加）
  ├── QuickBtn           — 快捷按钮（空调/音乐/导航等）
  └── SettingsPanel      — 设置面板

/report (ReportView)
  └── 驾驶报告内容（LLM 生成）
```

---

## 2. 应用启动流程

```
┌─────────────────────────────────────────────────────────────┐
│                    应用启动 (Cold Start)                      │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  1. 后端启动 (uvicorn backend.main:app --port 8000)         │
│     ├── 初始化 FastAPI 应用 + CORS 中间件                     │
│     ├── 挂载 /static/music 静态文件目录                       │
│     ├── lifespan: 启动摄像头引擎 (camera.py)                  │
│     │   ├── 初始化 FaceTracker (MediaPipe)                   │
│     │   ├── 初始化 HandGestureDetector                       │
│     │   ├── 初始化 AudioPipeline (语音管线)                   │
│     │   ├── 启动 5 类独立告警计时器                           │
│     │   └── 开始摄像头采集循环 (30 FPS 目标)                  │
│     ├── lifespan: 初始化数据库 (init_db)                      │
│     ├── lifespan: 创建驾驶会话 (create_drive_session)         │
│     ├── lifespan: 启动周期性环境广播 (每 30s)                  │
│     └── lifespan (shutdown): 结束驾驶会话 + 停止摄像头        │
│                                                             │
│  2. 前端启动 (cd frontend && npm run dev, port 8005)         │
│     ├── Vite 开发服务器启动                                   │
│     ├── 代理 /api → localhost:8000                           │
│     ├── 代理 /ws → ws://localhost:8000                       │
│     ├── 加载 Vue 3 App + Element Plus + Router               │
│     ├── 路由解析 → DashboardView                             │
│     └── 初始化 WebSocket 连接                                │
│                                                             │
│  3. 用户浏览器访问 http://localhost:8005                      │
│     ├── DashboardView 挂载                                   │
│     ├── useTelemetry composable 启动摄像头轮询                │
│     │   └── GET /api/camera/frame (每 200ms)                 │
│     ├── useAgentWS composable 连接 WebSocket                 │
│     │   ├── ws://localhost:8000/ws/agent_panel               │
│     │   └── ws://localhost:8000/ws/agent_result              │
│     ├── 获取环境数据 GET /api/environment                     │
│     ├── 获取仪表盘状态 GET /api/dashboard/state              │
│     └── 渲染五大面板布局                                     │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

---

## 3. 核心用户流程

### 3.1 安全告警流程

```
触发器: 摄像头检测到异常状态
│
├── 多人检测 (crowd): face_count ≥ 2
│   └── 计时器累加 → 超过阈值 → check_crowd() → severe 告警
│
├── 无人检测 (absence): !face_ok
│   └── 计时器累加 → 超过阈值 → check_absence() → severe 告警
│
├── 疲劳检测 (fatigue): PERCLOS > 0.15
│   └── 计时器累加 → 超过阈值 → check_fatigue() → danger 告警
│       ├── 计算 fatigue_score (0-100)
│       └── 疲劳等级: normal / warning / danger
│
├── 头部偏离 (head): gaze != center
│   └── 计时器累加 → 超过阈值 → check_head_deviation() → warning/danger
│
└── 视线偏离 (gaze): gaze != center
    └── 计时器累加 → 超过阈值 → check_gaze_deviation() → warning/danger

成功路径:
  1. 告警触发 → severity = "severe" | "moderate"
  2. 冷却检查 (15s 间隔)
  3. WebSocket 广播: { type: "safety_alert", severity, tts_text }
  4. TTS 语音播报: "警告！检测到危险驾驶状态，请立即注视前方！"
  5. 数据库持久化: INSERT INTO alerts (session_id, risk_level, alert_msg, perclos, ...)
  6. 前端 SafetyPanel 显示告警卡片 + 红色闪烁边框动画

错误/降级:
  - 数据库写入失败 → 仅日志记录，不影响实时告警
  - TTS 引擎不可用 → 静默，仅视觉告警
  - WebSocket 断开 → 前端轮询 /api/camera/frame 响应头获取状态

恢复路径:
  - 异常状态消除 (视线回正 / 面部重新检测到)
  - 防抖: 回正需持续 1 秒才清零计时器
  - severity → "normal" → 告警解除 → 前端绿色状态
```

### 3.2 手势交互流程

```
触发器: 摄像头检测到手势 (每 3 帧一次)
│
├── HandGestureDetector.process(rgb_frame)
│   ├── MediaPipe HandLandmarker 提取 21 个手部关键点
│   ├── 几何规则分类器: 手指角度 + 关键点相对位置
│   └── TFLite KeyPointClassifier (辅助)
│
└── 输出: (gesture_name, confidence)

成功路径:
  1. gesture_name 非空 → decide_locally({ trigger: "gesture", data: { gesture, confidence } })
  2. 本地决策引擎匹配 action_code
  3. 安全门控检查: severe 告警阻塞手势指令
  4. 非 severe → 执行手势指令
     ├── Open → TurnOnAC → POST /api/ac/command { command: "TurnOnAC" }
     ├── Close → TurnOffAC → POST /api/ac/command { command: "TurnOffAC" }
     ├── Thumbs Up / OK → confirm → 确认当前操作
     ├── Thumbs Down / Peace → cancel → 取消当前操作
     ├── Pointer → attention → 标记注意力点
     └── Quiet Coyote → mute → 静音
  5. 前端 GestureControl 面板更新: 显示手势名称 + 执行状态
  6. 动作保持 0.8 秒（确保前端轮询能捕获）

错误路径:
  - 手势识别置信度 < 0.7 → 不执行
  - 未知手势 → decide_locally 返回 action_code="unknown" → 忽略
  - 安全告警 severe → 阻塞手势，优先安全
  - 手势识别器未加载 → gesture_available = False → 跳过

边界情况:
  - 同一手势持续出现 → 防抖: 仅首次触发动作
  - 手势快速切换 → 保持上一次动作 0.8s
  - 无手部可见 → gesture_name = ""
```

### 3.3 语音交互流程

```
触发器: 用户语音输入
│
├── 方式 A: 浏览器麦克风 → POST /api/voice/transcribe (WAV bytes)
├── 方式 B: 后端音频管线 → AudioPipeline (microphone + VAD + 降噪)
│
└── Whisper 转写 → text

成功路径 (后端 /api/voice/process):
  1. 接收 text → 本地关键词匹配 (decide_locally)
  2. 匹配成功 → action_code + reply_text → 直接返回
  3. 无匹配 → InteractionAgent.analyze() → DeepSeek LLM 语义理解
     ├── 意图分类: 控制 / 查询 / 诊断 / 推荐
     ├── 实体提取: 温度值 / 歌曲名 / 目的地
     └── 安全评估: 驾驶员状态 → 决定是否执行
  4. 返回: { action_code, reply, tts_text, route }
  5. TTS 语音合成: GET /api/tts?text=...
     ├── edge-tts (zh-CN-XiaoxiaoNeural) → MP3
     └── pyttsx3 降级 → WAV
  6. WebSocket 广播: { type: "interaction_result", data }

错误/降级:
  - Whisper 未安装 → 仅本地关键词可用
  - DeepSeek API 不可用 (离线) → 本地关键词 + fallback_handler
  - 语音识别为空 → 返回 error
  - TTS 引擎均不可用 → 返回 error (仅文本回复)
  - 音频太短 (< 1000 bytes) → 返回 error

Agent 完整路径 (POST /api/agent/chat):
  1. 创建 ReActAgent 实例
  2. agent.chat(text, driver_state, callbacks)
     ├── perceive_node: 读取传感器状态 + 用户输入
     ├── safety_gate: 评估 risk_level → 过滤工具白名单
     ├── [risk=dangerous] → safety_response → END
     ├── agent_node: LLM 推理 → 决定工具调用
     ├── [需要工具] → tool_node → 执行 → 回到 agent_node
     └── respond → 生成最终回复
  3. 流式 WebSocket 推送 (callbacks 每步推送)
     ├── { type: "agent_perceive", data }
     ├── { type: "agent_safety_gate", data }
     ├── { type: "agent_reasoning", data }
     ├── { type: "agent_tool_call", data }
     └── { type: "agent_final", data }
  4. 持久化: INSERT INTO interactions (session_id, user_query, ai_response)
  5. 告警持久化: 非 normal 风险 → INSERT INTO alerts
```

### 3.4 AI 对话流程 (多 Agent 编排)

```
触发器: 用户复杂请求 (POST /api/agent/orchestrate)
  例如: "帮我规划一个去杭州的3天行程，看看那边天气怎么样"

  1. IntentionAgent 意图分解:
     ├── intent_1: { category: "trip_plan", priority: 1 }
     ├── intent_2: { category: "weather", priority: 2 }
     └── intent_3: { category: "recommend", priority: 3 }

  2. 安全预检:
     ├── driver_state.risk == "dangerous" → 短路告警
     └── 正常 → 继续

  3. 按优先级调度:
     ├── TripPlan → RecommendAgent (LLM 行程规划)
     ├── Weather → EnvironmentAgent (天气 API)
     └── Attractions → RecommendAgent (高德 POI)

  4. 结果聚合:
     ├── overall_reply: "杭州3天行程已规划，..."
     ├── actions: [show_trip_plan, show_weather, show_attractions]
     └── WebSocket 推送结构化数据到 AgentResultPanel

  5. 前端 AgentResultPanel 展示:
     ├── 导航卡片 (destination, distance, duration, route)
     ├── 天气卡片 (city, temp, desc, driving_context)
     ├── 行程卡片 (days, itinerary, budget)
     └── 景点卡片 (attractions list)
```

### 3.5 导航与环境流程

```
触发器: 用户请求导航 / 页面加载自动获取环境

导航:
  1. POST /api/navigation/route { destination, lat?, lon? }
  2. Nominatim 地理编码 → 坐标
  3. OSRM 路线规划 → route geometry + steps
  4. WebSocket 广播: { type: "navigation", data }
  5. 前端 MapArea 展示 Leaflet 地图 + 路线折线
  6. 高德 POI 检索 (如有 Key): 充电站/停车场/景点

环境:
  1. GET /api/environment?lat=&lon= (或 POST /api/environment)
  2. EnvironmentAgent.analyze():
     ├── 天气: OpenWeatherMap API → wttr.in 免费 API 降级
     ├── 时段上下文: 早高峰/午间/晚高峰/夜间
     ├── 驾驶风险评估: 天气 + 时段 → risk_score
     └── 驾驶建议生成 (纯规则，不走 LLM)
  3. WebSocket 广播 (每 30s): { type: "environment", data }
  4. 前端 TopBar 显示天气图标 + 温度
  5. 前端 MapArea 叠加天气图层

错误:
  - 无 GPS 坐标 → 使用默认 (北京 39.9, 116.4)
  - 天气 API 超时 (8s) → _fallback_environment 兜底
  - 导航服务超时 (8s) → 返回 error 状态
```

### 3.6 驾驶报告流程

```
触发器: 用户点击导航栏 "驾驶报告" → 路由到 /report
│
├── 1. ReportView 挂载
│   ├── 获取会话摘要: GET /api/session/summary
│   │   └── { session_id, start_time, end_time, total_alerts, level_breakdown }
│   ├── 获取告警列表: GET /api/alerts
│   └── 获取交互记录: GET /api/interactions
│
├── 2. 生成 LLM 报告: POST /api/drive/report
│   ├── 输入: { duration_min, distractions, severe, attention_score, avg_gaze }
│   ├── Prompt 模板: analysis.drive_report
│   ├── DeepSeek LLM 生成
│   └── 输出: { summary, advice, route }
│
└── 3. 渲染报告页面
    ├── 行程概览 (时长/距离)
    ├── 安全评分 + 疲劳趋势图 (ECharts)
    ├── 告警分类统计
    ├── LLM 生成的总结 + 建议
    └── 交互记录时间线

错误:
  - 无驾驶会话 → 显示 "暂无驾驶数据"
  - LLM 不可用 → 仅显示统计数据，无 AI 总结
```

---

## 4. WebSocket 消息类型

| type | 方向 | 触发时机 | 前端处理组件 |
|------|------|---------|------------|
| `ping` / `pong` | 双向 | 每 30s 心跳 | WSManager (自动) |
| `safety_alert` | 服务端→客户端 | 安全告警触发 | SafetyPanel |
| `driver_state` | 服务端→客户端 | 摄像头每帧状态 | DashboardView |
| `ai_decision` | 服务端→客户端 | AI 分析完成 | AiPanel |
| `interaction_result` | 服务端→客户端 | 语音/手势交互解析完成 | AiPanel |
| `agent_perceive` | 服务端→客户端 | Agent 感知节点 | AiPanel (追踪链) |
| `agent_safety_gate` | 服务端→客户端 | Agent 安全门控 | AiPanel (追踪链) |
| `agent_reasoning` | 服务端→客户端 | Agent LLM 推理 | AiPanel (追踪链) |
| `agent_tool_call` | 服务端→客户端 | Agent 工具调用 | AiPanel (追踪链) |
| `agent_final` | 服务端→客户端 | Agent 执行完成 | AiPanel (追踪链) |
| `agent_error` | 服务端→客户端 | Agent 执行出错 | AiPanel |
| `agent_navigation` | 服务端→客户端 | 导航结果 | AgentResultPanel / MapArea |
| `agent_weather_query` | 服务端→客户端 | 天气查询结果 | AgentResultPanel |
| `agent_trip_plan` | 服务端→客户端 | 行程规划结果 | TripPlanView |
| `agent_attractions` | 服务端→客户端 | 景点推荐结果 | AgentResultPanel |
| `navigation` | 服务端→客户端 | 路线规划完成 | MapArea |
| `environment` | 服务端→客户端 | 每 30s 环境数据 | TopBar / MapArea |

---

## 5. 关键状态转换

### 5.1 驾驶员风险状态机

```
                    ┌─────────┐
        ┌──────────→│ normal  │←──────────┐
        │           └────┬─────┘           │
        │                │                 │
        │  视线偏离>3s    │   回正>1s       │
        │  或 PERCLOS     │                 │
        │  >0.08         │                 │
        │                ▼                 │
        │           ┌─────────┐           │
        │           │ warning │───────────┘
        │           └────┬─────┘
        │                │
        │  视线偏离>5s    │
        │  或 PERCLOS     │
        │  >0.15         │
        │                ▼
        │           ┌─────────┐
        └───────────│ danger  │──→ critical (PERCLOS>0.3 + 持续>10s)
        (恢复)      └─────────┘
```

### 5.2 摄像头连接状态

```
无摄像头 (CAMERA_ENABLED=0) → 跳过引擎 → 前端使用占位图
       │
摄像头启动 → 初始化 FaceTracker + GestureDetector + AudioPipeline
       │
       ├── 成功 → 实时采集 → 前端显示摄像头画面
       │          │
       │          └── 帧丢失 → 跳过该帧 → 继续下一帧
       │
       └── 失败 → 日志 warning → 前端使用占位图 + 模拟数据
```

### 5.3 网络状态转换

```
在线 (api.deepseek.com:443 可达)
  ├── LLM 调用: DeepSeek API
  ├── 导航: OSRM/Nominatim
  └── 天气: OpenWeatherMap / wttr.in
       │
       │ 网络断开 (socket 连接失败)
       ▼
离线 (offline_mode = True)
  ├── LLM 调用: 本地模板 + LocalDecisionEngine
  ├── 导航: 不可用 → error
  ├── 天气: wttr.in 免费 API (离线不可用 → 兜底)
  ├── 安全: 正常工作 (全本地推理)
  ├── 手势: 正常工作 (全本地推理)
  ├── 语音关键词: 正常工作 (本地匹配)
  ├── TTS: pyttsx3 本地引擎
  └── RAG: FAISS 本地检索
       │
       │ 网络恢复 → 自动回切
       ▼
在线 (offline_mode = False)
```

---

## 6. 错误处理矩阵

| 错误场景 | 后端处理 | 前端展示 |
|---------|---------|---------|
| DeepSeek API 超时 (>10s) | 返回 error + 降级到本地决策 | AiPanel: "AI 服务繁忙，已切换到本地模式" |
| DeepSeek API Key 未配置 | deepseek_client.is_available = False | TopBar: "离线模式" 标签 |
| 摄像头不可用 | camera.py 循环不启动 | 占位图 (driver-cam.png) |
| 数据库写入失败 | logger.warning | 静默 (不影响实时功能) |
| WebSocket 连接断开 | 自动重连 (浏览器端) | 重连中动画 |
| TTS 引擎均不可用 | 返回 error JSON | 仅文本回复，无语音 |
| 手势识别器未加载 | HandGestureDetector.is_available = False | GestureControl: "手势不可用" |
| Whisper 未安装 | speech_recognizer 不可用 | 仅本地关键词模式 |
| 音乐 API (localhost:3000) 不可用 | 降级到演示曲目 | 展示演示曲目，提示启动 API |
| 导航服务超时 (8s) | 返回 error JSON | MapArea: "导航服务暂不可用" |
| 天气 API 超时 (8s) | _fallback_environment 兜底 | TopBar: "❓ 天气数据不可用" |
