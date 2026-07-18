# EdgeGuard：边缘智能驾驶安全多模态交互系统

> 第5组 | 大模型应用开发实训 | 2026-07-17

---

## 一、项目概述

基于**边缘-云端混合架构**的车载多模态AI交互系统。通过摄像头和麦克风实时采集驾驶员眼动、手势、语音和环境数据，由 LangGraph 编排的三智能体协作引擎进行融合决策，实现分心预警、疲劳监测、语音手势交互和车辆知识问答。核心安全功能全部本地推理，断网可用。

---

## 二、技术架构

```
┌─────────────────────────────────────────────────┐
│                   感知层 (全本地)                 │
│  MediaPipe面部追踪 │ Whisper语音 │ 手势识别      │
│  → 468点面部关键点 + EAR眨眼 + 头部姿态(PnP)     │
│  → 15+手势几何分类器 + 20+语音关键词匹配         │
│  → 延迟 <50ms，断网可用                          │
├─────────────────────────────────────────────────┤
│                  决策层 (边缘-云端混合)            │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐      │
│  │SafetyAgent│  │InteractA.│  │ EnvAgent  │      │
│  │ 安全监测  │  │ 交互理解  │  │ 环境分析  │      │
│  │ 本地优先  │  │ 混合路由  │  │ 混合路由  │      │
│  └─────┬────┘  └────┬─────┘  └─────┬─────┘      │
│        └─────────────┼─────────────┘             │
│              LangGraph 状态图编排                 │
│         边缘-云端路由器 (实时网络感知)             │
│         离线降级处理 (网络中断自动切换)            │
├─────────────────────────────────────────────────┤
│                  交互层                           │
│  Vue3中控大屏 ← WebSocket → FastAPI后端          │
│  AI主动播报(TTS) │ 驾驶报告(LLM生成) │ 语音对话   │
└─────────────────────────────────────────────────┘
```

### 感知层（全本地，不依赖网络）

| 模态 | 技术 | 状态 |
|------|------|:---:|
| 眼动追踪 | MediaPipe Face Landmarker（468点）+ 虹膜定位 | ✅ |
| 眨眼检测 | 自适应EAR基线校准（前60帧中位数采样） | ✅ |
| 头部姿态 | MediaPipe + OpenCV PnP解算（pitch/yaw/roll） | ✅ |
| 手势识别 | MediaPipe Hand Landmarker + 几何规则（15+手势） | ✅ |
| 语音识别 | Whisper 转写管线 | ⚡ 半成品 |

### 决策层（边缘-云端混合路由）

| 决策类型 | 路由 | 技术 | 状态 |
|----------|:---:|------|:---:|
| 分心检测 | 本地 | 视线yaw+虹膜双判断 + 5帧防抖 + 三级告警 | ✅ |
| 手势指令映射 | 本地 | 几何分类器直接输出 | ✅ |
| 语音关键词匹配 | 本地 | 20+关键词意图识别 | ✅ |
| 复杂语义理解 | 云端 | DeepSeek API | ✅ |
| 车辆知识问答 | 混合 | FAISS检索 + DeepSeek生成（RAG） | ✅ |
| 环境分析 | 混合 | wttr.in天气 + DeepSeek LLM | ✅ |
| Agent编排 | 混合 | LangGraph StateGraph（条件路由+短路） | ✅ |
| 疲劳趋势预测 | 本地 | 四级分级+PERCLOS+眨眼率+多维融合，趋势建模待完善 | ⚡ 框架完成 |

### 手势/语音 → 动作反馈链路

```
摄像头/麦克风采集 → 手势几何分类 / 语音关键词匹配
                         ↓
              local_decision_engine: 映射为 action_code
              (15手势 + 20语音 → confirm/cancel/PlayMusic/TurnOnAC/Navigate/...)
                         ↓
              action_handler: action_code → TTS语音反馈
              ("好的，我将为您打开空调")
                         ↓
              WebSocket 推送决策结果 → 前端面板更新
```

当前覆盖的指令类型：
- 空调控制：开/关/温度调节
- 音乐播放：播放/停止/切歌/音量
- 导航指令：导航到目的地
- 安全确认：注意力恢复确认（"我在看路"）
- 车窗/灯光：开/关控制
- 知识问答：故障咨询 → RAG 检索兜底



---

## 三、AI 调用清单

### DeepSeek LLM 直接调用：5 处

| # | 模块 | 触发方式 | 功能 |
|---|------|---------|------|
| 1 | `/api/drive/insight` | 前端定时请求 | AI主动观察驾驶员状态，LLM生成口语化提醒 |
| 2 | `/api/drive/report` | 用户点击按钮 | 驾驶数据 → LLM生成结构化报告（总结+建议） |
| 3 | `InteractionAgent`（语音理解） | 语音输入 | 简单指令本地关键词匹配，复杂语义调DeepSeek |
| 4 | `EnvironmentAgent`（环境分析） | 环境数据更新 | 天气+时段 → LLM风险分析+驾驶建议+预警 |
| 5 | `vehicle_knowledge_base.py`（RAG） | 用户提问 | FAISS Embedding检索 + DeepSeek生成口语化回答 |

### Agent 编排：3 Agent + LangGraph

| Agent | 输入 | 决策 | 输出 | 调LLM |
|-------|------|------|------|:---:|
| SafetyAgent | 眼动+PERCLOS+头部姿态 | 风险分级(normal/distracted/dangerous) | 风险等级+告警 | 否 |
| InteractionAgent | 手势+语音 | 意图分类+安全拦截+RAG检索 | action_code+回复 | 是 |
| EnvironmentAgent | 时间+天气API | 环境分析+驾驶建议+预警 | 上下文+alerts | 是 |

编排策略：
- SafetyAgent 第一个执行，有 VETO 短路权
- 判定危险 → 直接 END，跳过后端所有 Agent
- 正常 → Interaction + Environment 并行分析
- 所有 Agent 走 safe_executor 异常兜底

### 边缘-云端智能路由

| 决策类型 | 路由 | 延迟 |
|----------|------|------|
| 分心/疲劳检测 | 本地 | <50ms |
| 手势指令 | 本地 | <30ms |
| 语音关键词 | 本地 | <5ms |
| 复杂语义理解 | 云端 DeepSeek | 1-3s |
| 知识问答 | 混合(FAISS+LLM) | 0.1-2s |
| AI主动播报 | 云端 DeepSeek | 1-2s |

断网行为：自动标记离线 → 本地规则+模板兜底 → 每10秒检测网络 → 恢复自动切回

---

## 四、离线可用范围

| 断网仍可用 | 断网暂不可用 |
|-----------|------------|
| 面部追踪 + 眨眼检测 + 视线方向 | AI 主动播报（依赖 LLM） |
| 分心告警（三级闪烁+文字提示） | 驾驶报告生成 |
| 手势识别（15+手势指令） | 复杂语义问答 |
| 语音关键词指令（20+指令） | RAG 知识检索（降级为模板库兜底） |
| 离线模板库兜底（8种场景） | 天气数据获取 |

---

## 五、各模块完成情况

### 组长— ✅ 已完成

| 模块 | 说明 |
|------|------|
| `langgraph_orchestrator.py` | LangGraph状态图+条件路由+降级顺序模式 |
| `edge_cloud_router.py` | 本地/混合/云端三路分发+网络感知+超时切换 |
| `local_decision_engine.py` | 15+手势+20+关键词+视线分级(mild/moderate/severe) |
| `fallback_handler.py` | 离线模板库+关键词兜底+网络恢复自动切回 |
| `driver_state_machine.py` | 驾驶员状态流转 |
| `safe_executor.py` | Agent异常统一兜底 |
| `face_tracker.py` | 468点+自适应EAR基线+5帧防抖+PnP头部姿态 |
| `hand_gesture.py` | 几何规则手势识别器 |
| `backend/main.py` | FastAPI+WebSocket+摄像头引擎+LLM播报+驾驶报告 |
| `backend/app/camera.py` | 摄像头采集+HUD叠加+JPEG推流 |
| `frontend/` 项目骨架 | Vue3+Vite+VueRouter+ElementPlus+ECharts |
| `app.py` | 主流程串联 |

### B 岗（交互+知识库）— ✅ 已提交，待合并

| 模块 | 行数 |
|------|------|
| `modules/ai/interaction_agent.py` — 意图分类+安全拦截+RAG对接 | 583 |
| `modules/ai/vehicle_knowledge_base.py` — FAISS索引+语义检索+LLM生成 | 403 |
| `frontend/src/AiDecisionPanel.vue` — AI决策链路可视化 | 560 |
| `frontend/src/VoiceInteractionBar.vue` — 语音输入+对话历史+TTS | 550 |

### C 岗（环境+导航）— ✅ 已提交，待合并

| 模块 | 行数 |
|------|------|
| `modules/ai/agents/environment_agent.py` — wttr.in天气+DeepSeek LLM+降级规则引擎 | 383 |
| `frontend/src/components/NavPanel.vue` — 天气+时钟+驾驶建议+预警 | 275 |

### A 岗（安全+告警）— ✅ 已提交，待合并

| 模块 | 行数 | 说明 |
|------|------|------|
| `safety_agent.py` | 186 | ✅ 四级风险分级(normal/attn_declining/distracted/dangerous)，PERCLOS计算+眨眼率+多维度融合判定，含自测用例 |
| `fatigue_predictor.py` | 47 | ⚡ 框架完成，`FatiguePredictor`类+滑动窗口，趋势计算逻辑待补 |
| `frontend/DashboardView.vue` | — | ⚡ 新增四级风险WebSocket模拟工况(4秒循环)，需整合到组长最新框架 |
| `frontend/AiPanel.vue` | 116改动 | ✅ 适配后端risk_level/alert_msg/PERCLOS/疲劳分数等字段 |
| `GaugePanel.vue` | — | ⚡ 待填充仪表盘可视化 |
| `AlertPanel.vue` | — | ⚡ 待接入三级告警动画 |

---

## 六、技术栈

| 层级 | 选型 |
|------|------|
| 视觉 | OpenCV + MediaPipe Face Landmarker (468点) + PnP头部姿态 |
| 语音 | Whisper（本地转写） + pyttsx3（TTS播报） |
| AI编排 | LangGraph StateGraph（条件路由+并行+短路） |
| 大模型 | DeepSeek Chat API（主） / 离线模板降级 |
| 向量检索 | FAISS + HuggingFace Embeddings（RAG知识库） |
| 后端 | FastAPI + WebSocket + uvicorn |
| 前端 | Vue 3.4 + Vite 5 + Element Plus + ECharts + Canvas |
| 数据 | SQLite（交互日志+用户配置） |

### 自主开发声明

感知层视觉管线参考了开源方案架构，以下模块为自主设计与开发：

| 模块 | 状态 |
|------|:---:|
| 边缘-云端混合路由器（网络感知、自动降级、三路分发） | ✅ |
| LangGraph 多智能体编排引擎（条件路由+优先级仲裁） | ✅ |
| 本地决策引擎（多模态融合+严重度分级） | ✅ |
| RAG 车辆知识库（FAISS + Embeddings + LLM生成） | ✅ |
| 驾驶员状态机 | ✅ |
| MediaPipe 面部追踪器（自适应EAR基线+视线防抖+PnP姿态） | ✅ |
| FastAPI + WebSocket 实时通信架构 | ✅ |
| Vue3 车载中控可视化大屏 | ✅ |
| 疲劳趋势预测模型（多维状态向量+滑动窗口） | 🔲 开发中 |

---

## 七、时间线

| 日期 | 节点 | 状态 |
|------|------|:---:|
| 7/14 | 选题确认 + 方案书 + 环境搭建 | ✅ |
| 7/15 | 组长核心模块完成（编排器+路由器+面部追踪+大屏） | ✅ |
| 7/16-17 | B/C提交代码；组长AI深度应用(LLM播报+驾驶报告+TTS) | ✅ |
| 7/19 | 各自模块基本完成（截止日） | ⏳ |
| 7/21 | **第一次联调**：Agent接口对接，边缘路由走通 | ⏳ |
| 7/23 | 模块交付，整合LangGraph编排 | ⏳ |
| 7/25 | **第二次联调**：完整流程走通 | ⏳ |
| 7/27 | PPT + 录屏 | ⏳ |
| 7/28-30 | 缓冲修bug + 最终检查 | ⏳ |

---

## 八、量化数据

| 指标 | 数值 |
|------|------|
| 总代码行数（不含node_modules/venv） | ~9,400+ |
| Python 模块 | 25 |
| Vue 组件 | 10 |
| Agent 数量 | 3 |
| LLM 直接调用点 | 5 |
| RAG 管线 | 1 |
| 手势映射指令 | 15 |
| 语音关键词匹配 | 20+ |
| 知识库兜底条目 | 10+ |
| 离线模板场景 | 8 |
| 告警严重度分级 | 3 (mild/moderate/severe) |
| 面部关键点 | 468 (MediaPipe) |
| REST API 端点 | 6 |

---

## 九、待完成 / 待整合

### 代码未完成

| 事项 | 详情 | 负责人 |
|------|------|:---:|
| `fatigue_predictor.py` | 文件不存在，7维状态向量+滑动窗口时序建模待开发 | A |
| `safety_agent.py` | 仅基础 if-else（46行），待接入 PERCLOS+疲劳预测+头部姿态融合 | A |
| `GaugePanel.vue` | 仅展示字符串（16行壳），待填充仪表盘可视化 | A |
| `AlertPanel.vue` | 仅 if-else 显示（14行壳），待接入三级告警动画+语音联动 | A |
| Whisper 语音管线 | `speech_recognizer.py` 模块完整，未接入摄像头实时流程 | 组长 |

### 分支待合并

| 事项 | 详情 |
|------|------|
| B 的 4 个文件 | `interaction_agent.py`(583行)+`vehicle_knowledge_base.py`(403行)+`AiDecisionPanel.vue`(560行)+`VoiceInteractionBar.vue`(550行) 在 member-b 分支 |
| C 的 2 个文件 | `environment_agent.py`(383行)+`NavPanel.vue`(275行) 在 member-c 分支 |
| 合并冲突 | `backend/main.py` B和C各加了API端点有冲突；B写了独立 DashboardView.vue 需整合到框架；VoiceInteractionBar 绝对URL需改Vite代理 |

