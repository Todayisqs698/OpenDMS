# EdgeGuard — 边缘智能驾驶安全多模态交互系统

> 基于边缘-云端混合架构的车载多模态 AI 交互系统。安全功能全本地推理，断网可用；复杂语义理解走云端大模型。手势、语音、面部追踪三通道融合，ReAct Agent 自主决策闭环。

## 系统架构

```
┌──────────────────────────────────────────────────────────────┐
│                     🖥️  Vue 3 HMI 中控大屏                     │
│   AppSidebar │ SafetyPanel │ MapArea │ AiPanel │ BottomBar   │
│   ClimateControl │ GestureControl │ TripPlanView │ Stats     │
└────────────┬────────────────────────────────┬────────────────┘
             │   REST API + WebSocket          │
┌────────────▼────────────────────────────────▼────────────────┐
│                    ⚡ FastAPI 后端 (port 8000)                 │
│  Camera Engine │ WS Manager │ TTS │ GPS │ AC │ Music │ Nav   │
└────────────┬────────────────────────────────┬────────────────┘
             │                                │
┌────────────▼──────────┐     ┌───────────────▼────────────────┐
│   🧠 AI 决策层 (本地)  │     │   ☁️ AI 决策层 (云端)           │
│  LocalDecisionEngine  │     │  DeepSeek LLM API              │
│  DriverStateMachine   │     │  Multi-Agent Orchestrator      │
│  Safety Gate          │     │  ┌──────────────────────────┐  │
│  RAG (FAISS)          │     │  │ IntentionAgent → 意图分解 │  │
│  手势/语音关键词匹配   │     │  │ SafetyAgent → 安全评估    │  │
│  Edge-Cloud Router    │     │  │ InteractionAgent → 交互   │  │
└───────────────────────┘     │  │ EnvironmentAgent → 环境   │  │
                              │  │ DiagnoseAgent → 故障诊断  │  │
┌───────────────────────┐     │  │ AnalyzeAgent → 行为分析   │  │
│  👁️ 视觉感知 (全本地)  │     │  │ RecommendAgent → 推荐    │  │
│  MediaPipe 468点面部  │     │  │ ControlExecutor → 直接API │  │
│  PnP 头部姿态估计     │     │  └──────────────────────────┘  │
│  手势识别 (16 种手势)  │     │  LangGraph ReAct Agent Loop    │
│  PERCLOS 疲劳检测     │     │  Agent Core (GoalStack+反思)   │
└───────────────────────┘     └───────────────────────────────┘

┌───────────────────────┐
│  🎤 语音 (本地优先)    │
│  Whisper 语音识别      │
│  edge-tts 语音合成     │
│  WebRTC VAD + 降噪    │
└───────────────────────┘
```

## 核心特性

### 🛡️ 安全守护
- **面部追踪**：MediaPipe 468 点 Face Landmarker + PnP 头部姿态估计
- **四级风险分级**：normal → warning → danger → critical，实时 PERCLOS 疲劳检测 + 眨眼率
- **分心告警**：视线偏离超时 → 三级闪烁 + 语音提醒，支持 8 种离线降级场景
- **安全门控 (Safety Gate)**：ReAct Agent 执行前，基于风险等级自动过滤工具白名单

### 🎯 多模态交互
- **手势识别**：16 种手势指令，纯几何规则分类器（零依赖）+ TFLite 模型双引擎
- **语音指令**：20+ 本地关键词 + Whisper 完整转写 → DeepSeek 语义理解
- **主动观察**：LLM 分析驾驶员视线模式，适时给出温和提醒（"您看了很久窗外，需要停车休息吗？"）

### 🧠 多 Agent 编排
- **IntentionAgent** 分解用户输入为多个意图（控制/查询/诊断/推荐）
- **Orchestrator** 按优先级调度子 Agent，安全预检始终最先执行
- **ControlExecutor** 空调/音乐直调 API（<100ms，不走 LLM）
- **ReAct Agent** 完整感知-思考-行动循环，支持工具调用、记忆、反思
- **Agent Core** GoalStack 目标栈 + TaskPlanner + ReflectionEngine + SessionMemory

### 🚗 车载控制
- **空调**：开关、温度(16-30°C)、模式(制冷/制热/自动/送风)、风速(1-5档)
- **音乐**：本地 MP3 + 网易云 API 搜索播放，播放列表管理
- **导航**：OSRM 免费路线规划 + Leaflet 地图展示 + 高德 POI 检索
- **环境感知**：实时天气 + 时段上下文 → 驾驶风险建议

### 📊 驾驶分析
- **Dashboard 面板**：实时摄像头画面 + 视线方向 + 手势 + 告警状态
- **StatsPanel**：驾驶时长、分心次数、严重告警、注意力评分统计
- **驾驶报告**：LLM 生成行程总结 + 安全建议 + 疲劳趋势
- **数据库持久化**：告警记录、交互记录、驾驶会话 (SQLite)

## 项目结构

```
EdgeGuard/
├── backend/                             # FastAPI 后端 (port 8000)
│   ├── main.py                          # 主入口 — 40+ API 端点 + WebSocket + 生命周期
│   └── app/
│       ├── camera.py                    # 摄像头引擎 — MediaPipe 实时感知 + JPEG 推流
│       ├── core/
│       │   └── database.py              # SQLite 持久化 — 告警/交互/会话记录
│       └── ws/
│           └── manager.py               # WebSocket 连接管理 + 广播
│
├── frontend/                            # Vue 3 中控大屏 (port 5173)
│   └── src/
│       ├── views/
│       │   ├── DashboardView.vue        # 主仪表盘 — 五大面板布局
│       │   └── ReportView.vue           # 驾驶报告页
│       ├── components/hmi/              # HMI 组件库 (14 组件)
│       │   ├── AppSidebar.vue           # 左侧导航栏
│       │   ├── TopBar.vue               # 顶栏 — 状态 + 天气
│       │   ├── SafetyPanel.vue          # 安全告警面板
│       │   ├── StatsPanel.vue           # 驾驶统计面板
│       │   ├── SettingsPanel.vue        # 设置面板
│       │   ├── MapArea.vue              # 地图区域 (Leaflet)
│       │   ├── AiPanel.vue              # AI 对话面板
│       │   ├── BottomBar.vue            # 底部快捷栏
│       │   ├── ClimateControl.vue       # 空调控制
│       │   ├── GestureControl.vue       # 手势可视化
│       │   ├── AgentResultPanel.vue     # Agent 结果展示
│       │   ├── TripPlanView.vue         # 行程规划展示
│       │   ├── AttentionRing.vue        # 注意力环
│       │   └── QuickBtn.vue             # 快捷按钮
│       ├── composables/
│       │   ├── useTelemetry.ts          # 摄像头轮询 + 实时状态 (composable)
│       │   └── useAgentWS.ts            # Agent WebSocket 实时结果 (composable)
│       ├── lib/
│       │   └── edgeguard.ts             # 类型定义 + API 端点 + Mock 数据
│       ├── router/index.js              # Vue Router 路由
│       └── styles/globals.css           # 全局样式 (Tailwind)
│
├── modules/                             # AI + 感知核心模块
│   ├── ai/                              # AI 决策层
│   │   ├── agent_core.py                # Agent Core — GoalStack + Planner + Reflection
│   │   ├── agent_graph.py               # LangGraph ReAct Agent 循环
│   │   ├── orchestrator.py              # 多 Agent 编排引擎
│   │   ├── intention_agent.py           # 意图分解 Agent
│   │   ├── deepseek_client.py           # DeepSeek LLM 客户端
│   │   ├── tools.py                     # 8 个 Function Calling 工具
│   │   ├── safety_gate.py               # 安全门控 — 风险级别 → 工具白名单
│   │   ├── memory.py                    # Agent 记忆系统
│   │   ├── edge_cloud_router.py         # 边缘-云端混合路由器
│   │   ├── local_decision_engine.py     # 本地决策引擎 (离线关键词)
│   │   ├── fallback_handler.py          # 离线降级处理
│   │   ├── driver_state_machine.py      # 7 维驾驶员状态向量
│   │   ├── fatigue_predictor.py         # 疲劳趋势预测
│   │   ├── safe_executor.py             # Agent 异常兜底
│   │   ├── location_store.py            # GPS 位置持久化
│   │   ├── navigation_service.py        # 导航路线规划 (OSRM)
│   │   ├── prompts.py                   # Prompt 模板库
│   │   └── agents/                      # 6 个子 Agent
│   │       ├── safety_agent.py          # 安全 Agent — 眼动+头部姿态 → 风险分级
│   │       ├── interaction_agent.py     # 交互 Agent — 手势+语音 → 意图解析
│   │       ├── environment_agent.py     # 环境 Agent — 天气+时段 → 驾驶建议
│   │       ├── analyze_agent.py         # 分析 Agent — 驾驶行为分析
│   │       ├── diagnose_agent.py        # 诊断 Agent — 故障诊断
│   │       └── recommend_agent.py       # 推荐 Agent — 导航/天气/景点/行程
│   │
│   ├── vision/                          # 视觉感知层 (全本地)
│   │   ├── hand_gesture.py              # 手势识别 — 几何规则引擎 (15+手势)
│   │   ├── gesture_classifier.py        # TFLite 手势分类器
│   │   └── gesture/                     # 手势识别模型
│   │       ├── keypoint_classifier.py   # 关键点分类器
│   │       └── models/                  # TFLite/HDF5 模型文件
│   │
│   └── audio/                           # 语音感知层
│       ├── speech_recognizer.py         # Whisper 语音转写
│       └── audio_pipeline.py            # 音频采集管线 (VAD + 降噪)
│
├── data/
│   ├── edgeguard.db                     # SQLite 数据库
│   ├── agent_memory.json                # Agent 持久记忆
│   └── music/                           # 本地音乐文件目录
│
├── tools/
│   └── netease-cloud-music-api/         # 网易云音乐 API (本地代理)
│
├── requirements.txt                     # Python 依赖
├── .env.example                         # 环境变量模板
└── README.md
```

## 技术栈

| 层级 | 选型 |
|------|------|
| 视觉感知 | OpenCV + MediaPipe Face Landmarker (468 点) + PnP + TFLite |
| 语音 | Whisper (本地转写) + edge-tts (TTS) + WebRTC VAD |
| AI 编排 | LangGraph StateGraph + Multi-Agent Orchestrator |
| 大模型 | DeepSeek Chat API (deepseek-v4-flash) / 离线模板降级 |
| Agent 模式 | ReAct Loop + GoalStack + ReflectionEngine + Function Calling |
| 向量检索 | FAISS + sentence-transformers (RAG 车辆知识库) |
| 后端 | FastAPI + WebSocket + uvicorn |
| 前端 | Vue 3.4 + Vite 5 + Tailwind CSS 4 + Element Plus + ECharts + Leaflet |
| 数据库 | SQLite (告警/交互/会话持久化) |
| 地图/导航 | OSRM (路线) + 高德 API (POI) + Leaflet (展示) |

## 快速开始

### 环境要求
- Python 3.10+
- Node.js 18+
- 摄像头（可选，干跑模式不需要）

### 安装与运行

```bash
# 1. 克隆仓库
git clone https://github.com/Todayisqs698/OpenDMS.git
cd OpenDMS

# 2. 安装 Python 依赖
pip install -r requirements.txt

# 3. 配置环境变量
cp .env.example .env
# 编辑 .env，填入 DEEPSEEK_API_KEY=sk-xxx
# 可选：AMAP_API_KEY（高德 POI）、OPENWEATHER_API_KEY（天气）

# 4. 安装前端依赖
cd frontend && npm install && cd ..

# 5. 启动后端
uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000

# 6. 启动前端（新终端）
cd frontend && npm run dev

# 7. 打开浏览器: http://localhost:5173
```

### 干跑模式（无需摄像头）

设置 `DEEPSEEK_API_KEY` 后直接启动后端即可。AI 对话、导航、天气、空调控制等功能正常使用。安全面板显示模拟数据。

## API 端点一览

### AI & Agent
| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/agent/chat` | ReAct Agent 主入口（流式推送） |
| POST | `/api/agent/query` | Agent Core 查询 |
| POST | `/api/agent/orchestrate` | 多 Agent 编排 |
| GET | `/api/agent/thinking` | Agent 思维链可视化 |
| POST | `/api/analyze` | 多模态分析（视线+手势+语音） |
| POST | `/api/interaction/query` | 交互理解 |

### 感知
| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/camera/frame` | 摄像头 JPEG 帧 + 状态响应头 |
| GET | `/api/status` | 系统/网络/Agent 模块状态 |
| GET | `/api/gesture/available` | 手势识别可用性 |

### 驾驶
| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/drive/insight` | LLM 主动驾驶观察 |
| POST | `/api/drive/report` | LLM 驾驶报告生成 |
| GET/POST | `/api/environment` | 天气 + 驾驶建议 |
| POST | `/api/navigation/route` | 导航路线规划 |

### 车载控制
| 方法 | 路径 | 说明 |
|------|------|------|
| GET/POST | `/api/ac/state` `/api/ac/command` | 空调状态与控制 |
| GET/POST | `/api/music/*` | 音乐搜索/播放/暂停/切歌 |
| GET/POST | `/api/tts` | 语音合成 |

### WebSocket
| 路径 | 说明 |
|------|------|
| `/ws/{client_id}` | 通用 WebSocket |
| `/ws/agent_panel` | Agent 思维链推送 |
| `/ws/agent_result` | Agent 结构化结果推送 |
| `/ws/navpanel` | 导航 + 环境数据推送 |

### 持久化
| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/alerts` | 告警记录查询 |
| GET | `/api/interactions` | 交互记录查询 |
| GET | `/api/session/summary` | 驾驶会话摘要 |

## 离线能力

| ✅ 断网仍可用 | ❌ 断网暂不可用 |
|-------------|--------------|
| 面部追踪 + 眨眼检测 + 视线方向 | AI 主动播报 |
| 分心告警（三级闪烁+语音提醒） | 驾驶报告生成 |
| 手势识别（16 种手势指令） | 复杂语义问答 |
| 语音关键词指令（20+ 指令） | RAG 知识检索 |
| 离线模板库兜底（8 种场景） | 天气数据获取 |
| 空调/音乐本地控制 | 导航路线规划 |
| TTS 本地引擎 (pyttsx3) | 网易云在线搜索 |

## 手势指令集

| 手势 | action_code | 功能 | 分类 |
|------|-------------|------|------|
| 🖐️ Open | `TurnOnAC` | 开空调 | 空调 |
| ✊ Close | `TurnOffAC` | 关空调 | 空调 |
| 👍 Thumbs Up | `confirm` | 确认 | 确认 |
| 👎 Thumbs Down | `cancel` | 取消 | 确认 |
| 👌 OK | `confirm` | 确认 | 确认 |
| ✌️ Peace | `cancel` | 取消 | 确认 |
| 👆 Pointer | `attention` | 注意力检测 | 导航 |
| 🤫 Quiet Coyote | `mute` | 静音 | 媒体 |

## 配置项 (`.env`)

| 变量 | 必填 | 说明 |
|------|------|------|
| `DEEPSEEK_API_KEY` | ✅ | DeepSeek API 密钥 |
| `LLM_PROVIDER` | - | LLM 提供商：deepseek / openai / anthropic |
| `OPENAI_API_KEY` | - | OpenAI API 密钥（备用） |
| `ANTHROPIC_API_KEY` | - | Anthropic API 密钥（备用） |
| `AMAP_API_KEY` | - | 高德地图 API Key（POI 检索/天气） |
| `OPENWEATHER_API_KEY` | - | OpenWeatherMap API Key（天气） |
| `HF_ENDPOINT` | - | HuggingFace 镜像站 |
| `EMBEDDING_API_BASE` | - | Embedding 服务地址（远程降级） |
