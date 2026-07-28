# EdgeGuard vs DrivePilot-Cockpit 深度对比分析

> 分析日期：2026-07-27
> 分析对象：本仓库 EdgeGuard vs [WaitsKid/DrivePilot-Cockpit](https://github.com/WaitsKid/DrivePilot-Cockpit)
> 目的：定位 EdgeGuard 使用效果差距的根因，给出可执行的改进路径

---

## 一、核心结论（TL;DR）

EdgeGuard 的使用体验比 DrivePilot 差，**不是单个功能的实现问题，而是系统工程层面的结构性差距**。两者在以下五个维度存在根本差异：

| 维度 | DrivePilot | EdgeGuard | 差距性质 |
|------|-----------|-----------|---------|
| 架构清晰度 | 三端分离（Qt/DMS/Agent） | 单体后端 49 端点堆叠 | 结构性 |
| DMS 疲劳检测 | 训练 MobileNetV2（F1=0.99） | 规则启发式 7 维向量 | 根本性 |
| Agent 工具执行 | Qt 端校验+执行，安全边界清晰 | Python 后端直接执行，LLM 可越权 | 设计性 |
| 功能聚焦度 | 3 个子项目，职责单一 | 5+ 子项目混入，精力分散 | 策略性 |
| 工程稳定性 | 12 篇文档驱动，设计决策有据 | 线上 bug 驱动，Lessons Learned 沉重 | 过程性 |

---

## 二、两个项目概览

### 2.1 DrivePilot-Cockpit

**定位**：Qt Quick 智能座舱模拟系统，面向课程设计和毕业设计展示。

**三端架构**：

```
Qt Quick 客户端 (C++/QML)
    ↕ REST + WebSocket
DMS 后端 (FastAPI + OpenCV + ONNX)     ← 疲劳检测
    ↕ WebSocket
Agent 后端 (FastAPI + Kimi Tool Calling) ← AI 编排
```

**技术栈**：Qt 6.9.1 / QML / C++ / FastAPI / YuNet / MobileNetV2 / ONNX Runtime / Kimi / 讯飞 ASR / 高德地图

**验证结果**（公共测试集）：

| 模型 | Macro F1 | ONNX CPU P95 |
|------|---------|-------------|
| 眼睛状态 MobileNetV2 | 0.9908 | 3.120 ms |
| 哈欠状态 MobileNetV2 | 0.9814 | 4.032 ms |

**文档体系**：12 篇结构化文档（需求规格、架构设计、功能模型、接口协议、部署运行、用户手册、测试质量、安全隐私、工作流、项目复盘）。

### 2.2 EdgeGuard

**定位**：车载智能中控系统（DMS + AI Agent + 车机 HMI）。

**技术栈**：Vue 3 / Vite / FastAPI / MediaPipe / DeepSeek / 高德地图 / 网易云 API / LangGraph

**代码规模**：

| 目录 | 行数 | 文件数 |
|------|------|--------|
| `backend/` | 2,451 | 7 |
| `modules/` (Python) | 15,100 | 54 |
| ├ `modules/ai/` | 13,227 | 44 |
| `frontend/src/` | 3,726 | 24 |

**子项目混入**：`TripStar-main/`、`helloagents-trip-planner/`、`mobile/`（uni-app）、`design/`（Next.js）、`tools/netease-cloud-music-api/`。

---

## 三、架构对比

### 3.1 分层架构

**DrivePilot 的架构决策**（有明确文档记录）：

| 决策 | 原因 |
|------|------|
| 模型推理放 Python | PyTorch/OpenCV/ONNX 生态成熟；Qt 不承担模型生命周期 |
| Agent 编排放 Python | 云模型 Key 不进入 Qt；会话/工具循环/重试更易维护 |
| Qt 执行工具 | LLM 不直接操作 QML，只提出工具调用，Qt 校验后执行并回传真实结果 |
| 不向 Qt 发摄像头画面 | 降低隐私风险和序列化开销 |

**EdgeGuard 的架构现状**：

```
Vue3 前端 (浏览器)
    ↕ HTTP + WebSocket
FastAPI 单体后端 (main.py, 49 端点)
    ├── ReActAgent (LangGraph + 手动降级)
    ├── Orchestrator (意图识别 + 多 Agent 编排)
    ├── ControlExecutor (空调/音乐直接调 API)
    ├── 摄像头引擎 (MediaPipe + OpenCV)
    ├── DMS 状态机 (规则启发式)
    ├── 行程规划器 (XHS 爬虫 + Amap + LLM)
    └── 网易云音乐代理 (:3000)
```

**关键差异**：

- **DrivePilot 三个独立服务**各自有清晰的输入输出契约，DMS 和 Agent 互不干扰
- **EdgeGuard 一个进程扛所有**，49 个端点挤在 `main.py` 一个文件里，摄像头推理、Agent 循环、音乐播放、地图导航全耦合

### 3.2 接口设计

| 维度 | DrivePilot | EdgeGuard |
|------|-----------|-----------|
| DMS 接口 | REST + WebSocket，仅传数字状态和告警事件 | 摄像头画面经 WebSocket 传到前端 |
| Agent 接口 | WebSocket 会话，工具调用/结果有 `call_id` 关联 | `/api/agent/chat` + `/ws/agent_panel` + `/ws/agent_result` 三路并行 |
| 工具执行 | Qt 端校验+执行，Agent 只发 JSON Schema 参数 | Python 后端直接执行，前端只接收结构化推送 |
| 安全边界 | 工具白名单 + Qt 侧参数校验 + 超时 + 最大步数 | 工具白名单 + safety_gate 节点，但 LLM 可直接调后端 API |

---

## 四、核心功能对比

### 4.1 DMS 疲劳检测（差距最大的模块）

| 维度 | DrivePilot | EdgeGuard |
|------|-----------|-----------|
| 人脸检测 | YuNet（轻量 ONNX 模型） | MediaPipe Face Landmarker → Haar Cascade → noop（3 级降级） |
| 闭眼检测 | MobileNetV2 二分类（Closed/Open），F1=0.9862 | EAR 阈值 0.26（几何特征，非学习） |
| 哈欠检测 | MobileNetV2 二分类（yawn/no_yawn），F1=0.9907 | 无独立哈欠模型 |
| 疲劳算法 | PERCLOS + 连续闭眼时长 + 哈欠事件去重 + 4 级状态机 | 7 维规则向量（PERCLOS + 眨眼频率 + 头部姿态 + 视线偏移 + 告警延迟） |
| 状态机 | 活力→正常→略微疲劳→严重疲劳，升级/恢复防抖 | 阈值 WARN=40 / DANGER=70 + 线性回归趋势 |
| 推理延迟 | ONNX CPU P95 = 3-4 ms | MediaPipe detect_for_video（未公开基准） |
| 可验证性 | 公共测试集 Macro F1=0.99，ONNX/PyTorch 一致性 <5e-7 | 无量化评估，无测试集 |

**根因分析**：

DrivePilot 走了**完整的 ML 工程链路**：数据增强 → MobileNetV2 迁移学习 → 测试集评估 → 阈值校准 → ONNX 导出 → 一致性检查。这套流程保证了模型在公共测试集上的准确率可量化、可复现。

EdgeGuard 的 DMS 是**纯规则启发式**——用 EAR 几何阈值判断闭眼、用头部姿态方差判断疲劳趋势。这种方法在理想光照和正面朝向时勉强可用，但在侧脸、戴眼镜、光照变化时会严重误判。7 维向量虽然维度多，但每个维度都是手工阈值，没有训练数据支撑，无法量化准确率。

### 4.2 AI Agent

| 维度 | DrivePilot | EdgeGuard |
|------|-----------|-----------|
| LLM | Kimi（Moonshot） | DeepSeek |
| 工具调用 | Kimi 原生 Tool Calling | DeepSeek function calling → 文本格式解析（Thought:/Action:）降级 |
| 执行循环 | 模型→工具调用→Qt执行→结果回传→模型继续 | LangGraph StateGraph → 手动 ReAct 循环降级 |
| 工具执行位置 | **Qt 客户端**（C++ 校验+执行） | **Python 后端**（直接调 API） |
| 工具数量 | 精选白名单 | 10 个工具 + QUICK_PATTERNS 11 条规则 |
| 会话管理 | WebSocket 会话 + `call_id` 关联 | WorkingMemory（最近 6 条）+ last_tool_results 缓存 |
| 最大步数 | 有限制 | max_steps=5 + `_force_finish_response()` |
| 离线模式 | 无 Key 时本地 demo_agent | 无 Key 时 fallback_handler |

**关键差异：工具执行位置**

这是两个项目最根本的设计分歧：

```
DrivePilot:  LLM → "调用 set_ac_temperature(22)" → Qt 校验+执行 → 回传真实结果
EdgeGuard:   LLM → control_music("play") → Python 后端直接 POST /api/music/play → 回传结果
```

DrivePilot 把工具执行放在 Qt 客户端，好处是：
1. **安全边界清晰**——LLM 永远无法直接操作后端 API
2. **参数校验在执行端**——Qt 知道当前空调状态，可以拒绝非法操作
3. **结果真实**——Qt 执行后回传的是真实的车控结果，不是后端 API 的返回值

EdgeGuard 把工具执行放在 Python 后端，坏处是：
1. LLM 可以直接调后端任何 API，安全边界模糊
2. 后端 `control_music` 工具返回 `success=True` 但实际音乐没播放（因为网易云 API 没启动）——**工具层报成功但实际失败**，这正是你遇到的"播放音乐无法控制"问题的根因
3. 前端只能被动接收结构化推送，无法参与工具执行校验

### 4.3 HMI 界面

| 维度 | DrivePilot | EdgeGuard |
|------|-----------|-----------|
| UI 框架 | Qt Quick / QML（原生渲染） | Vue 3 + Vite（浏览器） |
| 页面数 | 首页/应用中心/空调/控制中心/车辆设置/车辆健康/音乐/天气/地图/联系人/视频/计算器/画图/AI助手 | Dashboard（六区式）+ Report |
| 组件数 | 10+ Controller 类 | 14 个 HMI 组件 |
| 语音识别 | 讯飞 WebSocket 流式 ASR | 浏览器 Web Speech API |
| TTS | 本地 TTS 引擎 | speechSynthesis（浏览器） |
| 离线能力 | Qt 可编译为独立 exe | 依赖浏览器 |

**关键差异：渲染层**

DrivePilot 用 Qt Quick 做车载 HMI 是**行业标准选择**——QML 的 GPU 加速渲染、固定画布设计、窗口等比适配，在车机场景下体验远优于浏览器方案。EdgeGuard 用 Vue3 在浏览器跑 HMI，虽然开发快，但在以下场景会有问题：
- 浏览器标签页失焦时 WebSocket 可能断连
- speechSynthesis 在不同浏览器行为不一致
- 动画帧率受浏览器调度影响

### 4.4 导航与地图

| 维度 | DrivePilot | EdgeGuard |
|------|-----------|-----------|
| 地图服务 | 高德地图（WebEngine + JS API） | 高德静态地图 + Leaflet（瓦片源常被屏蔽） |
| 路线规划 | 高德原生导航 | OSRM + Nominatim（免费） + 高德深链 |
| 起点获取 | 高德 API | 浏览器 GPS → 高德 IP 定位 → 默认上海回退 |
| 语义地点 | 未实现 | 家/公司（saved_locations 表，上一轮刚修复） |

EdgeGuard 在导航上的复杂度远高于 DrivePilot（OSRM + Nominatim + 离线地标表 + 高德深链 + 语义地点解析），但**复杂度没有转化为体验提升**——OpenStreetMap 瓦片被屏蔽、GPS 超时、语义地点未定义导致 1201km 荒谬路线。

---

## 五、SWOT 分析

### 5.1 EdgeGuard

| | 正面 | 负面 |
|---|------|------|
| **内部** | **优势**：多级降级贯穿全栈；行程规划带预算计算；语义地点可持久化 | **劣势**：DMS 无训练模型；后端单体耦合；工具执行无安全边界；子项目过多分散精力 |
| **外部** | **机会**：行程规划+景点推荐是差异化能力；浏览器架构易于远程访问 | **威胁**：DrivePilot 的 ML 工程链路形成质量壁垒；Qt 方案更符合车规级预期 |

### 5.2 DrivePilot

| | 正面 | 负面 |
|---|------|------|
| **内部** | **优势**：DMS 模型 F1=0.99；三端分离架构清晰；12 篇文档驱动；Qt 原生渲染 | **劣势**：无行程规划；无景点推荐；无语义地点；功能范围较窄 |
| **外部** | **机会**：作品集展示定位清晰，易于评审理解 | **威胁**：功能覆盖面不如 EdgeGuard |

---

## 六、EdgeGuard 体验差的根因定位

### 6.1 根因一：DMS 缺乏训练模型

**现象**：疲劳检测不准确，告警时机不合理。

**根因**：没有走 ML 工程链路（数据→训练→评估→部署），用几何阈值替代学习模型。MediaPipe 虽然能检测 468 个面部关键点，但 EdgeGuard 只用了 EAR（眼睛纵横比）一个几何特征做闭眼判定，没有训练专门的闭眼/睁眼分类器。

**DrivePilot 的做法**：用 MobileNetV2 迁移学习训练了独立的闭眼分类模型和哈欠分类模型，在公共测试集上 F1=0.99，ONNX 推理仅 3ms。

### 6.2 根因二：工具执行层报假成功

**现象**：命令"播放音乐"，AI 回复"已开始播放"，但实际没声音。

**根因**：`control_music` 工具在 Python 后端执行，调用 `/api/music/play`，后端返回 `status: needs_audio`（网易云 API 没启动），但工具层把 `needs_audio` 当成功返回了 `success=True`。LLM 看到成功就回复"已播放"，用户感知到的是"AI 说播放了但没声音"。

**DrivePilot 的做法**：工具在 Qt 端执行，Qt 知道当前音乐播放器的真实状态（有没有音频源、有没有在播放），回传给 LLM 的是真实结果。如果没音频源，LLM 会收到"播放失败：无音频源"，从而如实告诉用户。

### 6.3 根因三：Agent 上下文断裂

**现象**：导航到"家"不知道家在哪；上一轮推荐了景点，下一轮问"刚才那个景点"AI 失忆。

**根因**：导航请求走 `RecommendAgent`，不经过 `ReActAgent.chat()`，导致 `WorkingMemory` 从未被写入。LLM 每轮都是"失忆"状态。

**DrivePilot 的做法**：所有请求都走同一个 WebSocket 会话 + `AgentRunner`，会话历史统一管理，不存在路径绕过记忆的问题。

### 6.4 根因四：后端单体导致耦合 bug

**现象**：修一个功能（如音乐控制）要同时改 `tools.py`、`orchestrator.py`、`intention_agent.py`、`backend/main.py` 四个文件，且改动互相影响。

**根因**：49 个端点 + Agent 循环 + 摄像头引擎 + DMS 状态机全在 `main.py` 一个文件里，修改任何一处都可能影响其他功能。`modules/ai/` 有 44 个文件 13,227 行，`agent_core.py`（蓝图）和 `agent_graph.py`（实现）存在重叠。

**DrivePilot 的做法**：DMS 和 Agent 是两个独立的 FastAPI 服务，各有自己的 `scripts/run_server.py` 和端口（8765 / 8770），互不影响。

### 6.5 根因五：功能过多但每个都不精

**现象**：行程规划、XHS 爬虫、网易云代理、移动端、设计稿——每个都有但都不完整。

**根因**：项目包含了 5+ 个子项目（`TripStar-main`、`helloagents-trip-planner`、`mobile`、`design`、`tools/netease-cloud-music-api`），精力分散在太多方向。XHS 爬虫因反爬机制不稳定，反而引入了复杂的降级逻辑（XHS → Amap+LLM），增加了系统复杂度但没有提升核心体验。

**DrivePilot 的做法**：只做三件事（HMI + DMS + Agent），每件都做到位。

---

## 七、改进路径（优先级排序）

### P0：拆分后端服务

把单体 `main.py` 拆成三个独立服务：

```
dms-backend/      ← 摄像头 + MediaPipe + 疲劳状态机  (:8765)
agent-backend/    ← ReActAgent + 工具执行 + WebSocket   (:8770)
control-backend/  ← 空调/音乐/导航 REST API             (:8000)
```

前端分别连三个服务，任一服务崩溃不影响其他。

### P1：训练 DMS 模型

参考 DrivePilot 的 ML 链路：

1. 收集闭眼/睁眼数据集（如 CEW 数据集）
2. MobileNetV2 迁移学习训练二分类
3. 导出 ONNX，用 ONNX Runtime CPU 推理
4. 在公共测试集上评估 F1
5. 替换当前 EAR 阈值方案

### P2：工具执行移到前端

把工具执行从 Python 后端移到 Vue 前端：

```
当前: LLM → control_music() → Python POST /api/music/play → 返回
改为: LLM → 发出工具调用 → 前端校验+执行 → 回传真实结果 → LLM 继续
```

好处：前端知道真实播放状态，不会报假成功。

### P3：精简功能范围

- 删除 `TripStar-main/`（参考实现，不需要在主仓库）
- 删除 `design/`（Next.js 设计稿，与 Vue 前端无关）
- 删除 `mobile/`（uni-app 移动端，与车机场景冲突）
- 把 `tools/netease-cloud-music-api/` 改为外部依赖而非子目录
- 考虑用本地音频文件替代网易云 API（消除外部服务依赖）

### P4：补充工程文档

参考 DrivePilot 的 12 篇文档体系，至少补齐：

- 架构设计文档（为什么这么分）
- 接口协议文档（每个端点的输入输出）
- 测试与质量文档（有哪些测试，覆盖率多少）
- 安全与隐私文档（密钥管理、摄像头数据边界）

---

## 八、总结

EdgeGuard 的功能覆盖面比 DrivePilot 更广（行程规划、景点推荐、语义地点、XHS 数据源），但在**核心体验质量**上存在结构性差距：

1. **DMS 没有训练模型**——疲劳检测是规则启发式，准确率无法保证
2. **工具执行在 Python 层**——安全边界模糊，容易报假成功
3. **后端单体耦合**——49 端点挤在一个文件，改动牵一发动全身
4. **上下文记忆断裂**——多 Agent 路径绕过 WorkingMemory
5. **功能过多不精**——5+ 子项目分散精力

DrivePilot 虽然功能少，但每个功能都做到了"可验证、可复现、可维护"——DMS 有 F1 指标、Agent 有安全边界、架构有文档支撑。这种**工程纪律**是 EdgeGuard 当前最需要补的。

建议按 P0→P4 顺序改进，优先拆分后端和训练 DMS 模型——这两项能带来最直接的体验提升。
