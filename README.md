# EdgeGuard — 边缘智能驾驶安全多模态交互系统

> 车载中控大屏 HMI + 多模态 AI Agent。安全功能全本地推理，断网可用；复杂语义走云端大模型。手势、语音、面部追踪三通道融合，ReAct Agent 自主决策闭环。

## 效果展示

| 主驾驶舱 | AI 副驾对话 |
|----------|------------|
| ![主界面](picture/屏幕截图%202026-07-28%20142155.png) | ![AI对话](picture/屏幕截图%202026-07-28%20142603.png) |

| 行程规划 | 安全监测 |
|----------|---------|
| ![行程规划](picture/屏幕截图%202026-07-28%20142631.png) | ![安全监测](picture/屏幕截图%202026-07-28%20142721.png) |

| 导航与地图 |
|-----------|
| ![导航地图](picture/屏幕截图%202026-07-28%20143030.png) |

---

## 系统架构

```
┌──────────────────────────────────────────────────────────────┐
│                  🖥️  Vue 3 HMI 中控大屏 (:8005)               │
│   AppSidebar │ MapArea │ AiPanel │ BottomBar                 │
│   SafetyPanel │ TripPlanView │ ClimateControl │ StatsPanel   │
└────────────┬────────────────────────────────┬────────────────┘
             │   REST API + WebSocket          │
┌────────────▼────────────────────────────────▼────────────────┐
│                 ⚡ FastAPI 后端 (:8000)                        │
│  Camera Engine │ WS Manager │ TTS │ AC │ Music │ Navigation  │
└────────────┬────────────────────────────────┬────────────────┘
             │                                │
┌────────────▼──────────┐     ┌───────────────▼────────────────┐
│  👁️ 视觉感知 (全本地)  │     │  🧠 AI 决策引擎                │
│  MediaPipe Face 468点 │     │  DeepSeek LLM API             │
│  PnP 头部姿态估计     │     │  ┌──────────────────────────┐  │
│  手势识别 16 种手势   │     │  │ IntentionAgent → 意图分解 │  │
│  PERCLOS 疲劳检测     │     │  │ ControlExecutor → 直调API │  │
│  OpenCV 摄像头管线    │     │  │ ReAct Agent → 思考-行动   │  │
└───────────────────────┘     │  │ RecommendAgent → 推荐     │  │
                              │  │ DiagnoseAgent → 故障诊断  │  │
┌───────────────────────┐     │  │ TripPlanner → 行程规划    │  │
│  🎤 语音 (本地优先)    │     │  │ Safety Gate → 安全门控   │  │
│  Whisper 语音识别      │     │  └──────────────────────────┘  │
│  edge-tts 语音合成     │     │  Critic → 行程校验             │
│  WebRTC VAD + 降噪    │     └───────────────────────────────┘
└───────────────────────┘
```

---

## 核心功能

### 🛡️ 安全守护

- **面部追踪**：MediaPipe 468 点 Face Landmarker + PnP 头部姿态估计
- **四级风险分级**：normal → warning → danger → critical，实时 PERCLOS 疲劳检测
- **分心告警**：视线偏离超时 → 三级闪烁 + 语音提醒
- **安全门控**：Agent 执行前基于风险等级自动过滤工具白名单

### 🚗 语音 & 手势车控

- **空调控制**：开关、温度(16-30°C)、模式(制冷/制热/自动/送风)、风速
- **音乐控制**：搜索、播放、暂停、切歌、音量，支持网易云 API + 本地 MP3
- **复合指令**："调低音量并播放周杰伦" → 同时执行音量调节 + 搜索播放
- **手势识别**：16 种手势指令，纯几何规则 + TFLite 模型双引擎

### 🧭 AI 副驾 & 行程规划

- **多意图理解**：一句"打开空调、导航到西湖、今天天气怎么样"拆为 3 个独立意图
- **结构化行程规划**：自然语言丢进去 → 高德 POI 搜景点搜酒店 → LLM 编排逐日时间线
- **智能约束提取**：自动识别人数、节奏、预算、必去/避讳、喜好标签
- **行程面板**：Day 切换、酒店/景点/餐食时间线、预算总计、天气卡片
- **免费导航**：OSRM 路线规划 + Nominatim 地理编码 + 高德瓦片地图，全免费

### 📊 驾驶分析

- **实时 Dashboard**：摄像头画面 + 视线方向 + 手势 + 安全等级
- **驾驶统计**：时长、分心次数、告警记录、注意力评分
- **数据库持久化**：告警、交互、驾驶会话全部写入 SQLite

---

## 项目结构

```
EdgeGuard/
├── backend/                         # FastAPI 后端 (:8000)
│   ├── main.py                      # 主入口 — 50+ API 端点 + WebSocket
│   └── app/
│       ├── camera.py                # 摄像头引擎 — MediaPipe + JPEG 推流
│       ├── core/database.py         # SQLite — 告警/交互/会话
│       ├── ws/manager.py            # WebSocket 连接管理
│       └── routes/                  # 音乐/设置等独立路由
│
├── frontend/                        # Vue 3 中控大屏 (:8005)
│   └── src/
│       ├── views/
│       │   ├── DashboardView.vue    # 主仪表盘布局
│       │   └── ReportView.vue       # 驾驶报告页
│       ├── components/hmi/          # HMI 组件 (14 个)
│       │   ├── MapArea.vue          # Leaflet 地图 + 摄像头画中画
│       │   ├── AiPanel.vue          # AI 对话面板 + 语音输入
│       │   ├── BottomBar.vue        # 底部快捷栏 (空调/媒体/手势)
│       │   ├── TripPlanView.vue     # 行程规划面板
│       │   ├── SafetyPanel.vue      # 安全监测面板
│       │   ├── ClimateControl.vue   # 空调控制面板
│       │   ├── GestureControl.vue   # 手势可视化
│       │   ├── AppSidebar.vue       # 左侧导航栏
│       │   ├── TopBar.vue           # 顶栏
│       │   ├── StatsPanel.vue       # 驾驶统计
│       │   ├── SettingsPanel.vue    # 设置
│       │   ├── AgentResultPanel.vue # Agent 结果卡片
│       │   ├── AttentionRing.vue    # 注意力环
│       │   └── QuickBtn.vue         # 快捷按钮
│       ├── composables/
│       │   ├── useTelemetry.ts      # 摄像头轮询
│       │   └── useAgentWS.ts        # Agent WebSocket 结果流
│       ├── lib/edgeguard.ts         # 类型定义 + API 端点
│       └── styles/globals.css       # Tailwind CSS4 全局样式
│
├── modules/                         # AI + 感知核心
│   ├── ai/                          # AI 决策层
│   │   ├── agent_graph.py           # ReAct Agent 循环
│   │   ├── orchestrator.py          # 多 Agent 编排引擎
│   │   ├── intention_agent.py       # 意图分解 (规则+LLM双通道)
│   │   ├── intent_guard.py          # 安全门控 + 槽位验证
│   │   ├── tools.py                 # Function Calling 工具 (14 个)
│   │   ├── deepseek_client.py       # DeepSeek LLM 客户端
│   │   ├── memory.py                # Agent 长短期记忆
│   │   ├── navigation_service.py    # OSRM + Nominatim 导航
│   │   ├── location_store.py        # GPS 位置持久化
│   │   ├── structured_results.py    # 结构化结果推送
│   │   ├── edge_cloud_router.py     # 边缘-云端混合路由
│   │   ├── local_decision_engine.py # 本地关键词决策
│   │   ├── fallback_handler.py      # 离线降级
│   │   ├── prompts/                 # Prompt 模板库
│   │   ├── agents/                  # 子 Agent
│   │   │   ├── recommend_agent.py   # 推荐 (导航/天气/景点/行程)
│   │   │   ├── interaction_agent.py # 交互
│   │   │   ├── environment_agent.py # 环境感知
│   │   │   ├── analyze_agent.py     # 驾驶分析
│   │   │   └── diagnose_agent.py    # 故障诊断
│   │   └── trip_planner/            # 行程规划引擎
│   │       ├── agent.py             # TripPlanner Agent + LLM编排
│   │       ├── critic.py            # 校验器 (6 个确定性检查)
│   │       ├── schemas.py           # TripRequest + 约束提取
│   │       ├── task_manager.py      # 异步任务管理
│   │       └── xhs_service.py       # 小红书数据增强
│   ├── vision/                      # 视觉感知 (全本地)
│   │   ├── face_tracker.py          # MediaPipe 面部追踪
│   │   ├── hand_gesture.py          # 手势识别
│   │   └── gesture_classifier.py    # TFLite 手势分类器
│   └── audio/                       # 语音感知
│       ├── speech_recognizer.py     # Whisper 语音转写
│       └── audio_pipeline.py        # 音频采集管线
│
├── data/
│   ├── edgeguard.db                 # SQLite 数据库
│   └── music/                       # 本地音乐文件
│
├── picture/                         # 项目截图
├── requirements.txt                 # Python 依赖
├── start.bat                        # 一键启动脚本
├── .env.example                     # 环境变量模板
└── README.md
```

---

## 技术栈

| 层级 | 选型 |
|------|------|
| 视觉 | OpenCV + MediaPipe Face Landmarker (468 点) + PnP |
| 语音 | Whisper (本地转写) + edge-tts (TTS) + WebRTC VAD |
| AI 编排 | Multi-Agent Orchestrator + ReAct Loop |
| 大模型 | DeepSeek API (deepseek-v4-flash) |
| Agent | Function Calling + GoalStack + ReflectionEngine |
| 后端 | FastAPI + WebSocket + uvicorn |
| 前端 | Vue 3.4 + Vite 5 + Tailwind CSS 4 + Element Plus + Leaflet |
| 数据库 | SQLite (告警/交互/会话持久化) |
| 地图 | OSRM (路线) + 高德 REST API (POI) + Leaflet (展示) |

---

## 快速开始

### 环境要求

- Python 3.10+ (推荐 conda 环境)
- Node.js 18+
- 摄像头（可选）

### 安装

```bash
# 1. 克隆
git clone https://gitlab.omniedu.com/root/monOOoJl27YBk.git
cd monOOoJl27YBk

# 2. Python 依赖
pip install -r requirements.txt

# 3. 前端依赖
cd frontend && npm install && cd ..

# 4. 配置密钥
cp .env.example .env
# 编辑 .env: DEEPSEEK_API_KEY=sk-xxx (必填)
#            AMAP_API_KEY=xxx (可选，行程规划需要)
```

### 运行

```bash
# 方式一：一键启动
双击 start.bat

# 方式二：手动启动
uvicorn backend.main:app --host 0.0.0.0 --port 8000    # 后端
cd frontend && npm run dev                              # 前端 (:8005)
```

浏览器打开 `http://localhost:8005`。无摄像头时安全面板显示模拟数据，AI 对话、导航、空调、行程规划等功能正常使用。

---

## API 端点

### AI & Agent

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/agent/chat` | Agent 主入口（文本输入 → 意图分解 → 执行） |
| POST | `/api/agent/orchestrate` | 多 Agent 编排 |

### 车载控制

| 方法 | 路径 | 说明 |
|------|------|------|
| GET/POST | `/api/ac/state` `/api/ac/command` | 空调状态与控制 |
| GET/POST | `/api/music/*` | 音乐搜索/播放/暂停/切歌/音量 |
| POST | `/api/navigation/route` | 路线规划 |

### 感知

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/camera/frame` | 摄像头 JPEG 帧 |
| GET | `/api/status` | 系统状态 |
| GET | `/api/environment` | 天气 + 驾驶建议 |

### WebSocket

| 路径 | 说明 |
|------|------|
| `/ws/agent_panel` | Agent 思维链 + 结构化结果推送 |
| `/ws/navpanel` | 导航 + 环境数据推送 |

### 持久化

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/alerts` | 告警记录 |
| GET | `/api/interactions` | 交互记录 |
| GET | `/api/session/summary` | 驾驶会话摘要 |

---

## 离线能力

| 断网仍可用 | 断网暂不可用 |
|-----------|-------------|
| 面部追踪 + 疲劳检测 + 视线方向 | AI 主动播报 / 驾驶报告 |
| 分心告警（三级闪烁 + 语音） | 复杂语义问答 |
| 手势识别（16 种手势指令） | 行程规划 |
| 语音关键词指令 | 天气 / 导航 |
| 空调 / 音乐本地控制 | 网易云在线搜索 |

---

## 配置项 (`.env`)

| 变量 | 必填 | 说明 |
|------|------|------|
| `DEEPSEEK_API_KEY` | ✅ | DeepSeek API 密钥 |
| `AMAP_API_KEY` | - | 高德地图（POI 检索 / 天气 / 景点酒店搜索） |
| `LLM_PROVIDER` | - | deepseek / openai / anthropic |
| `OPENAI_API_KEY` | - | OpenAI 备用 |
| `ANTHROPIC_API_KEY` | - | Anthropic 备用 |
| `OPENWEATHER_API_KEY` | - | OpenWeatherMap 备用 |
| `XHS_COOKIE` | - | 小红书 Cookie（景点数据增强，可选） |

---

## 许可证

MIT License
