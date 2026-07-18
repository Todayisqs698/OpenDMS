# EdgeGuard：边缘智能驾驶安全多模态交互系统

> 第5组 | 大模型应用开发实训 | 2026-07-17
>
> 基于边缘-云端混合架构的车载多模态AI交互系统。核心安全功能全本地推理，断网可用。

## 项目结构

```
EdgeGuard/
├── app.py                          # 主入口：摄像头采集 + 感知 + AI决策 + WebSocket推流
│
├── modules/
│   ├── ai/                         # AI 决策层
│   │   ├── agents/                 # 三智能体
│   │   │   ├── safety_agent.py     # 安全Agent — 眼动+头部姿态 → 四级风险分级 [A岗]
│   │   │   ├── interaction_agent.py# 交互Agent — 手势+语音 → 意图解析+RAG [B岗]
│   │   │   └── environment_agent.py# 环境Agent — 天气+时段 → 驾驶建议 [C岗]
│   │   ├── interaction_agent.py    # 交互Agent完整实现(583行) [B岗]
│   │   ├── vehicle_knowledge_base.py # RAG车辆知识库 — FAISS检索+LLM生成 [B岗]
│   │   ├── deepseek_client.py      # DeepSeek LLM 客户端
│   │   ├── langgraph_orchestrator.py # LangGraph 三Agent编排引擎
│   │   ├── edge_cloud_router.py    # 边缘-云端混合路由器
│   │   ├── local_decision_engine.py # 本地决策引擎(手势+语音关键词)
│   │   ├── fallback_handler.py     # 离线降级处理
│   │   ├── driver_state_machine.py # 驾驶员状态机
│   │   ├── fatigue_predictor.py    # 疲劳趋势预测 [A岗 — 接口已定义，逻辑待补]
│   │   ├── safe_executor.py        # Agent异常统一兜底
│   │   └── multimodal_collector.py # 多模态数据采集器
│   │
│   ├── vision/                     # 视觉感知层(全本地)
│   │   ├── face_tracker.py         # MediaPipe面部追踪(468点) + PnP头部姿态
│   │   ├── hand_gesture.py         # 手势识别(几何规则，15+手势)
│   │   ├── face_landmarker_v2_with_blendshapes.task  # MediaPipe模型文件
│   │   └── hand_landmarker.task    # 手部关键点模型文件
│   │
│   ├── audio/                      # 语音感知层
│   │   ├── recorder.py             # 音频录制
│   │   └── speech_recognizer.py    # Whisper语音识别
│   │
│   ├── actions/
│   │   └── action_handler.py       # 动作执行器 [C岗]
│   │
│   └── system/
│       └── interaction_logger.py   # 交互日志记录 [C岗]
│
├── backend/                        # FastAPI 后端
│   ├── main.py                     # API端点 + WebSocket (⚠️ 待整合A/B/C端点)
│   └── app/
│       ├── camera.py               # 摄像头引擎 + JPEG推流
│       └── ws/
│           └── manager.py          # WebSocket连接管理 [C岗]
│
├── frontend/                       # Vue3 中控大屏
│   └── src/
│       ├── App.vue                 # 根组件
│       ├── main.js                 # 入口
│       ├── router/index.js         # 路由
│       ├── AiDecisionPanel.vue     # AI决策链路可视化 [B岗 — 560行]
│       ├── VoiceInteractionBar.vue # 语音交互栏 [B岗 — 550行]
│       ├── views/
│       │   └── DashboardView.vue   # 主仪表盘 (⚠️ A/mater版本待整合)
│       └── components/
│           ├── AiPanel.vue         # AI决策面板 [A岗 — 121行]
│           ├── NavPanel.vue        # 导航/天气面板 [C岗 — 400行]
│           ├── AlertPanel.vue      # 安全告警面板 (⚠️ 待完善三级动画)
│           ├── GaugePanel.vue      # 仪表盘面板 (⚠️ 待ECharts可视化)
│           └── VoicePanel.vue      # 语音状态面板
│
├── data/
│   └── knowledge/
│       └── vehicle_manual.txt      # 车辆知识库文档 [B岗]
│
├── scripts/                        # 辅助脚本
│   ├── demo_auto.py                # 自动化演示
│   ├── demo_camera_speech.py       # 摄像头+语音演示
│   ├── demo_full.py                # 完整演示
│   └── test_perception.py          # 感知层测试
│
├── _archive/                       # 归档(旧方案代码，供参考)
│   ├── backend_old/                # 12345工单系统后端
│   ├── vision_old/                 # dlib旧视觉方案
│   └── system_old/                 # 旧系统模块
│
├── requirements.txt                # Python依赖
├── setup.bat                       # Windows环境安装脚本
└── start.bat                       # Windows启动脚本
```

## 技术栈

| 层级 | 选型 |
|------|------|
| 视觉 | OpenCV + MediaPipe Face Landmarker (468点) + PnP |
| 语音 | Whisper (本地转写) + edge-tts (TTS播报) |
| AI编排 | LangGraph StateGraph (条件路由+并行+短路) |
| 大模型 | DeepSeek Chat API / 离线模板降级 |
| 向量检索 | FAISS + HuggingFace Embeddings (RAG) |
| 后端 | FastAPI + WebSocket + uvicorn |
| 前端 | Vue 3.4 + Vite + Element Plus + ECharts |

## 快速开始

```bash
# 1. 安装 Python 依赖
pip install -r requirements.txt

# 2. 配置 API Key
cp .env.example .env
# 编辑 .env，填入 DEEPSEEK_API_KEY=sk-xxx

# 3. 启动后端
cd backend
uvicorn main:app --reload --host 0.0.0.0 --port 8000

# 4. 启动前端（新终端）
cd frontend
npm install && npm run dev

# 5. 启动摄像头 AI 引擎（新终端）
python app.py              # 需要摄像头
python app.py --dry-run    # 干跑模式（测试AI链路）

# 打开浏览器: http://localhost:5173
```

## 离线能力

| 断网仍可用 | 断网暂不可用 |
|-----------|------------|
| 面部追踪 + 眨眼检测 + 视线方向 | AI 主动播报 |
| 分心告警（三级闪烁+文字提示） | 驾驶报告生成 |
| 手势识别（15+手势指令） | 复杂语义问答 |
| 语音关键词指令（20+指令） | RAG 知识检索 |
| 离线模板库兜底（8种场景） | 天气数据获取 |

## 待完成

| 事项 | 详情 |
|------|------|
| ⚠️ `backend/main.py` | A/B/C/master 四版API端点待手工拼合 |
| ⚠️ `DashboardView.vue` | A版风险模拟 + master版摄像头大屏 待整合 |
| 🔲 `fatigue_predictor.py` | 7维状态向量+滑动窗口趋势建模 [A岗] |
| 🔲 `GaugePanel.vue` | ECharts仪表盘可视化 |
| 🔲 `AlertPanel.vue` | 三级告警动画+语音联动 |
| 🔲 Whisper集成 | speech_recognizer.py已完整，未接入app.py实时流程 |

## 参考声明

本项目感知层的底层视觉/语音管线参考了 [In-Vehicle-Multimodal-Interaction-System](https://github.com/1Reminding/In-Vehicle-Multimodal-Interaction-System) 的架构设计。边缘计算决策层、LangGraph Agent 编排层、RAG 知识库、Vue3 前端为自主开发。
