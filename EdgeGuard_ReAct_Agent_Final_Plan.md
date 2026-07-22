# EdgeGuard ReAct Agent 语音交互 — 最终改造方案

> 基于 Coze 生成方案与现有架构的整合评估
> 日期：2026-07-22

---

## 一、背景与问题诊断

### 1.1 用户期望

用户希望 EdgeGuard 的语音交互具备真正的 **Thought-Action-Observation** 智能体能力：

- **规划与推理**：Agent 将高层目标分解为子任务（如"规划天津一日游"→查天气→搜景点→检查车况→综合建议）
- **工具调用**：Agent 识别信息缺口，主动调用外部工具补全信息（天气API、景点搜索、知识库）
- **动态修正**：用户反馈作为新约束，Agent 据此调整行为（如"这家酒店超出预算"→重新推荐）
- **思维链可见**：用户能实时看到 Agent 的思考过程（Thought→Action→Observation 逐步展示）

### 1.2 当前问题（6 个根因）

| # | 问题 | 影响 |
|---|------|------|
| P1 | VoicePanel 调用 `/api/agent/orchestrate`，空调/音乐走 ControlExecutor 短路（<100ms，无 LLM） | 用户感知不到 Agent 的推理过程 |
| P2 | AgentThinkingPanel 连接 `ws://host/ws/agent_panel`，后端只有 `/ws/{client_id}` | 思维链面板永远 404，无法渲染 |
| P3 | `/api/agent/orchestrate` 路由无 WebSocket callbacks | 即使修复 WebSocket，也无 thinking steps 可推送 |
| P4 | `orchestrator.py` 调用 `react_agent.chat()` 不传 callbacks | ReAgent 推理中间步骤丢失 |
| P5 | `manual_react_loop` 只推送安全等级，不推送 LLM 思考内容 | AgentThinkingPanel 无内容可显示 |
| P6 | VoicePanel 与 AgentThinkingPanel 零联动 | 两个组件之间无交互 |

### 1.3 当前数据流（断裂状态）

```
VoicePanel.vue
  └─ POST /api/agent/orchestrate
       └─ IntentionAgent.analyze()
            └─ RULE_BASED_PATTERNS 匹配空调/音乐
                 └─ ControlExecutor.execute()  (< 100ms, 无 LLM)
                      └─ 返回 reply_text，无 thinking steps

AgentThinkingPanel.vue
  └─ WebSocket ws://host/ws/agent_panel  ← 404! 端点不存在
```

---

## 二、理论参考：第十三章智能旅行助手

> 来源：《HelloAgents — 智能体系统设计与实现》第十三章

第十三章以"智能旅行助手"为完整案例，系统展示了 ReAct 智能体从原型到生产应用的构建过程。以下提取与 EdgeGuard 改造直接相关的设计思想。

### 2.1 ReAct 循环的核心能力模型

第十三章通过一个完整的运行案例（北京天气+景点推荐），展示了 ReAct 智能体的四项基本能力：

| 能力 | 定义 | EdgeGuard 映射 |
|------|------|-----------------|
| **任务分解** | 将"查天气并推荐景点"分解为：查天气→根据天气搜景点→整合建议 | IntentionAgent 分解复合意图，ReActAgent 分步执行 |
| **工具调用** | 识别信息缺口→调用 `get_weather(city="北京")`→获得 Observation | DeepSeek function calling → `control_ac` / `get_weather` / `search_attractions` |
| **上下文理解** | 将天气 Observation（Sunny, 26°C）作为景点推荐的上下文 | `manual_react_loop` 的 state.messages 携带完整历史 |
| **结果合成** | 收集所有信息后用 `Finish[最终答案]` 输出自然语言回复 | `respond_node` 生成最终回复 |

**运行案例分析**（第十三章 1.3.4 节）：

```
用户输入: 查询北京天气，推荐旅游景点

循环 1: Thought: 先获取北京天气 → Action: get_weather(city="北京")
       Observation: 北京当前天气:Sunny，气温26摄氏度

循环 2: Thought: 知道天气晴朗28°C，搜索适合晴天的景点
       Action: get_attraction(city="北京", weather="Sunny")
       Observation: 推荐颐和园（湖景）和长城（历史）

循环 3: Thought: 已有足够信息，给出最终建议
       Action: Finish[今天北京晴朗26°C，推荐颐和园或长城]
```

**对 EdgeGuard 的启示**：这个案例证明了 ReAct 循环在**车载场景完全适用**。EdgeGuard 的"规划天津一日游"可以类比为：查天津天气→根据天气搜景点→检查车况知识库→综合生成行程建议。

### 2.2 工具设计方法论

第十三章提供了两种工具实现范式：

**范式 A：直接 API 调用（get_weather）**

```python
def get_weather(city: str) -> str:
    """通过 wttr.in 查询实时天气 → 返回自然语言描述"""
    url = f"https://wttr.in/{city}?format=j1"
    response = requests.get(url)
    data = response.json()
    current = data['current_condition'][0]
    return f"{city}当前天气:{current['weatherDesc'][0]['value']}，气温{current['temp_C']}摄氏度"
```

EdgeGuard 已有等价实现：`modules/ai/tools.py` 中的 `get_weather` 通过高德 API 查询。

**范式 B：搜索+LLM 摘要（get_attraction）**

```python
def get_attraction(city: str, weather: str) -> str:
    """Tavily 搜索 → LLM 生成推荐理由"""
    tavily = TavilyClient(api_key)
    query = f"'{city}' 在'{weather}'天气下最值得去的旅游景点推荐"
    response = tavily.search(query=query, include_answer=True)
    return response["answer"]  # Tavily 内置 LLM 摘要
```

EdgeGuard 的 `search_attractions` 对应此范式，但用**高德 POI + 天气过滤**替代 Tavily，更适合中国本土化场景。

### 2.3 通用 LLM 客户端抽象

第十三章设计了 `OpenAICompatibleClient`，核心思想是**服务商无关的 LLM 调用**：

```python
class OpenAICompatibleClient:
    def __init__(self, model, api_key, base_url):
        self.client = OpenAI(api_key=api_key, base_url=base_url)

    def generate(self, prompt, system_prompt):
        messages = [
            {'role': 'system', 'content': system_prompt},
            {'role': 'user', 'content': prompt}
        ]
        response = self.client.chat.completions.create(model=self.model, messages=messages)
        return response.choices[0].message.content
```

EdgeGuard 已有等价实现：`modules/ai/deepseek_client.py` 的 `chat_with_tools()` 方法，支持 DeepSeek API + function calling。两者的关键区别是 EdgeGuard 使用**结构化 function calling** 而非文本正则解析，可靠性更高。

### 2.4 指令模板（Prompt Engineering）设计原则

第十三章强调了 Prompt 作为"智能体说明书"的关键作用，提出了三点设计原则：

| 原则 | 第十三章做法 | EdgeGuard 采纳 |
|------|-------------|---------------|
| **角色锚定** | "你是一个智能旅行助手" | "你是一个车载智能助手" |
| **工具清单** | 列出可用工具名+参数+描述 | 列出 8 个工具（含参数类型和约束） |
| **输出格式约束** | Thought/Action/Finish 严格格式 + 单步输出 | 同样约束 + 增加 Finish 文本长度限制（≤25字/句，适配 TTS） |
| **安全规则** | 无（旅行助手无安全约束） | 车载场景增加安全规则（驾驶中限制工具范围） |

### 2.5 Web 应用数据流转模型

第十三章提出了四层数据流转模型，这对理解 EdgeGuard 的数据流很有参考价值：

```
用户输入 → HTTP 请求 → 后端 Pydantic 验证 → Agent 处理 → 外部 API → 聚合 → HTTP 响应 → 前端渲染
```

EdgeGuard 的数据流转对应关系：

| 第十三章层 | EdgeGuard 对应 | 现有实现 |
|-----------|---------------|---------|
| 前端表单 | VoicePanel 输入框 | 已有 |
| HTTP 请求 | POST `/api/agent/chat` | 已有 |
| Pydantic 验证 | `AgentChatRequest(text, gesture, driver_state)` | 已有 |
| Agent 处理 | ReActAgent `manual_react_loop` | 已有 |
| 外部 API | 高德天气/POI + 网易云音乐 + DeepSeek | 已有 |
| 聚合 | `respond_node` 生成最终回复 | 已有 |
| 前端渲染 | AgentStepCard 思维链 + VoicePanel 消息列表 | **待改造** |

**关键发现**：EdgeGuard 的后端四层（HTTP→验证→Agent→外部API）已基本完善，**缺失的核心环节是 Agent 处理过程的可视化**（思维链推送 + 前端渲染），这正是本次改造的重点。

### 2.6 从 EdgeGuard 视角的差异总结

| 维度 | 第十三章（HelloAgents） | EdgeGuard | 差异影响 |
|------|------------------------|-----------|---------|
| **场景** | 旅行助手（桌面端） | 车载助手（嵌入式） | EdgeGuard 有安全门控，延迟敏感 |
| **工具调用** | 文本正则解析 `Action: func(arg="val")` | DeepSeek function calling（结构化） | EdgeGuard 更可靠，但需 LLM 支持 tool_choice |
| **数据模型** | Pydantic 全链路（前端 TS → 后端 Python） | 后端 Pydantic + 前端 JS 动态类型 | 前端缺少类型安全 |
| **记忆** | 无（单轮） | 3 层记忆（Working + Task + LongTerm） | EdgeGuard 有多轮上下文能力 |
| **安全** | 无 | 4 级安全门控 + 工具白名单 | EdgeGuard 更适合车载场景 |

---

## 三、Coze 方案评估

对 `EdgeGuard_ReAct_Agent_Design.md` 的逐项评估：

### 3.1 采纳（4 项）

| 来自 Coze 的设计 | 理由 |
|------------------|------|
| **AGENT_SYSTEM_PROMPT 模板** | 质量远超现有硬编码 prompt。包含角色锚定、7 工具详细说明、输出格式约束、示例对话、安全规则。直接替换现有 system prompt |
| **search_attractions 工具** | 新增能力。高德 POI 搜索 + 天气联动过滤 + LLM 生成推荐理由。填补了现有工具集的空白 |
| **多级降级策略** | 比现有"5s 超时降级"更健壮。覆盖 LLM 超时重试、格式错误自动修正、未知工具告知 LLM 自行纠正、总超时强制 Finish |
| **AgentStepCard.vue + useAgentWebSocket.js** | 前端组件质量高。步骤卡片带类型着色（思考/调用/结果/错误）、耗时显示、自动滚动。替换现有 AgentThinkingPanel |

### 3.2 适配（2 项）

| Coze 设计 | 调整方式 |
|-----------|---------|
| 全新 `react_agent.py` + 文本正则解析 | **不新建文件**。复用现有 `agent_graph.py` 的 `manual_react_loop`（LangGraph StateGraph + DeepSeek function calling），保留 function calling 作为主路径 |
| 全新 `AgentWebSocketHandler` 类 | **不新建文件**。直接在 `main.py` 中新增 WebSocket 端点，复用现有 `ws_manager` 广播机制 |

### 3.3 不采纳（3 项）

| Coze 设计 | 不采纳理由 |
|-----------|-----------|
| 全新 `tool_registry.py` | 现有 `tools.py` 已有 `TOOL_SCHEMAS` + `TOOL_EXECUTOR` 注册机制，直接扩展即可 |
| 全新 `interaction_agent.py` | EdgeGuard 用 IntentionAgent + Orchestrator 模式，不需要额外加一层 InteractionAgent |
| 全新 `prompts.py` 文件 | 现有 `modules/ai/prompts/` 模板库已完善，新 prompt 注册到模板库中 |

---

## 四、整合后的目标架构

### 4.1 数据流（修复后）

```
VoicePanel.vue
  ├─ 简单指令？── SimpleIntentRouter.match()
  │                 ├─ 命中 → 直接执行 control_ac/control_music (<100ms)
  │                 └─ 未命中 ↓
  └─ POST /api/agent/chat
       └─ ReActAgent.chat(callbacks=[sync_push])
            └─ manual_react_loop(state, callbacks)
                 ├─ perceive_node  → ws: agent_think（安全等级 + 上下文感知）
                 ├─ agent_node     → ws: agent_think（LLM 推理文本）
                 ├─ tool_node      → ws: agent_tool_call + agent_tool_result
                 ├─ agent_node     → ws: agent_think（观察后继续推理）
                 └─ respond        → ws: agent_final + return reply_text

AgentThinkingPanel.vue
  └─ WebSocket /ws/agent_panel  ← 新增端点
       └─ 监听 agent_think / agent_tool_call / agent_tool_result / agent_final
            └─ AgentStepCard 实时渲染
```

### 4.2 架构图

```
┌─────────────────────────────────────────────────────────────┐
│                    EdgeGuard 语音交互架构                      │
│                                                               │
│  ┌───────────────────────────────────────────────────────┐   │
│  │                   路由层 (VoicePanel)                │   │
│  │  SimpleIntentRouter ──命中──▶ 直接执行 (<100ms)       │   │
│  │       │ 未命中                                         │   │
│  │       ▼                                                │   │
│  │  POST /api/agent/chat ─────▶ ReAct Agent               │   │
│  └───────────────────────────────────────────────────────┘   │
│                          │                                    │
│                          ▼                                    │
│  ┌───────────────────────────────────────────────────────┐   │
│  │              ReAct Agent (agent_graph.py)              │   │
│  │                                                        │   │
│  │  AGENT_SYSTEM_PROMPT (Coze 设计)                       │   │
│  │       │                                                │   │
│  │       ▼                                                │   │
│  │  manual_react_loop                                     │   │
│  │    perceive → safety_gate → agent(思考) → tool(执行)   │   │
│  │         → agent(观察) → ... → respond(回复)           │   │
│  │       │                                                │   │
│  │       ├─ callbacks → WebSocket 推送每一步               │   │
│  │       └─ DeepSeek function calling (结构化工具调用)    │   │
│  └───────────────────────────────────────────────────────┘   │
│                          │                                    │
│                          ▼                                    │
│  ┌───────────────────────────────────────────────────────┐   │
│  │                工具层 (tools.py)                      │   │
│  │                                                        │   │
│  │  现有: control_ac / control_music / get_weather        │   │
│  │        search_knowledge / speak / alert_driver        │   │
│  │        ask_clarification                               │   │
│  │  新增: search_attractions (高德POI + 天气联动)         │   │
│  └───────────────────────────────────────────────────────┘   │
│                                                               │
│  ┌───────────────────────────────────────────────────────┐   │
│  │              WebSocket 推送层                         │   │
│  │  /ws/agent_panel (新增端点)                            │   │
│  │  agent_think / agent_tool_call / agent_tool_result    │   │
│  │  agent_final / agent_error                             │   │
│  └───────────────────────────────────────────────────────┘   │
│                          │                                    │
│                          ▼                                    │
│  ┌───────────────────────────────────────────────────────┐   │
│  │              前端渲染层 (Vue3)                         │   │
│  │  AgentStepCard.vue + useAgentWebSocket.js (Coze 设计) │   │
│  │  类型着色 + 自动滚动 + 耗时显示 + 折叠详情            │   │
│  └───────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
```

---

## 五、具体改动清单

### 5.1 后端改动（7 项）

#### B1: 新增 WebSocket 端点 `/ws/agent_panel`

- **文件**: `backend/main.py`
- **改什么**: 新增 `@app.websocket("/ws/agent_panel")` 路由，内部使用固定 ID `"agent_panel"` 注册到 `ws_manager`
- **为什么**: AgentThinkingPanel 连接此端点才能接收 thinking steps

```python
@app.websocket("/ws/agent_panel")
async def websocket_agent_panel(websocket: WebSocket):
    await ws_manager.connect(websocket, "agent_panel")
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        ws_manager.disconnect("agent_panel")
```

#### B2: 替换 AGENT_SYSTEM_PROMPT

- **文件**: `modules/ai/prompts/agent_templates.py`
- **改什么**: 将现有 `agent.system.base` 模板替换为 Coze 设计的完整 SYSTEM_PROMPT（包含角色锚定、7 工具详细说明、输出格式约束 `Thought:/Action:/Finish[]`、安全规则、示例对话）
- **为什么**: Coze 的 Prompt 质量远超现有版本，包含清晰的工具参数说明和输出格式约束

**关键设计要点**：

| 设计点 | 说明 |
|--------|------|
| 角色锚定 | "车载旅行助手"而非通用助手，约束回复风格为语音友好（≤25字/句） |
| 工具参数内联 | `key=value` 格式而非 JSON，减少 token 消耗 |
| 单步输出 | 每次只输出一对 Thought-Action，便于逐步推送 |
| Finish 约束 | ≤3 句话、每句 ≤25 字，适配 TTS 播报节奏 |
| 天气联动 | 明确指示天气影响景点推荐策略（雨天室内、高温避开正午） |

#### B3: 新增 search_attractions 工具

- **文件**: `modules/ai/tools.py`（扩展）+ 新增 `modules/ai/tools/search_attractions.py`
- **改什么**: 注册第 8 个工具 `search_attractions`，使用高德地图 POI 搜索 + 天气过滤 + LLM 生成推荐理由
- **为什么**: 填补工具集空白，支持"规划天津一日游"等旅行场景

**工具接口**：

```python
# 工具参数
{
    "name": "search_attractions",
    "description": "搜索城市热门景点，根据天气和偏好智能推荐",
    "parameters": {
        "city": {"type": "string", "required": True},
        "weather": {"type": "string", "required": False},
        "count": {"type": "integer", "default": 5},
        "preference": {"type": "string", "enum": ["历史文化","亲子","户外","美食","拍照打卡"]}
    }
}

# 天气联动策略
┌─────────────────┐     ┌──────────────────┐     ┌─────────────────┐
│   天气判断       │────▶│   景点过滤       │────▶│   排序策略       │
├─────────────────┤     ├──────────────────┤     ├─────────────────┤
│ 雨/雪/雷暴      │     │ 剔除纯户外景点   │     │ 室内优先        │
│ 高温 ≥35°C      │     │ 标注避暑提示     │     │ 户外排后+标注   │
│ 晴/多云/微风    │     │ 不过滤           │     │ 户外优先        │
└─────────────────┘     └──────────────────┘     └─────────────────┘
```

#### B4: manual_react_loop 推送 LLM 思考内容（⬆️ Phase 1 关键步骤）

- **文件**: `modules/ai/agent_graph.py`
- **改什么**: 在 `manual_react_loop` 中，对 agent_node 返回的两种情况分别处理：
  1. **有 `tool_calls`**（function calling 模式）：从 `tool_calls[0].function.arguments` 中提取参数，合成 `thought` 文本（如"Agent 决定调用 get_weather，参数 city=天津"）
  2. **有 `content`**（文本回复模式）：直接推送 `content`
- **为什么**: DeepSeek function calling 模式下 `msg.content` 经常为 `null`，真正信息在 `msg.tool_calls` 里。如果不合成 thought，前端思维链会在 agent_node 步骤显示空白

**选型决策（方案 A/B/C）**：

| 方案 | 做法 | 代价 | 决定 |
|------|------|------|------|
| A | 放弃 function calling，纯用文本 Thought-Action 正则解析 | 可靠性下降，但思维链天然完整 | ❌ |
| **B** | **保留 function calling，在 tool_node 执行后合成 thought 文本** | **思维链不够自然，但代价最小** | **✅ 采纳** |
| C | 额外调一次 LLM 生成自然语言 thought | 每步多一次 LLM 调用，延迟翻倍 | ❌ |

```python
# agent_graph.py manual_react_loop 中 agent_node 调用后

def _extract_thought_from_message(msg):
    """从 LLM 返回消息中提取 thought 文本（兼容 function calling 和纯文本）"""
    # 优先取 content（文本回复模式）
    content = msg.get("content", "")
    if content:
        return content

    # function calling 模式：合成 thought 描述
    tool_calls = msg.get("tool_calls", [])
    if tool_calls:
        tc = tool_calls[0]
        func_name = tc.get("function", {}).get("name", "unknown")
        try:
            args = json.loads(tc.get("function", {}).get("arguments", "{}"))
            arg_str = ", ".join(f"{k}={v}" for k, v in args.items())
        except (json.JSONDecodeError, AttributeError):
            arg_str = tc.get("function", {}).get("arguments", "")
        return f"Agent 决定调用 {func_name}，参数 {arg_str}"

    return ""

# 在 agent_node 返回后推送
messages = state.get("messages", [])
if messages:
    last_msg = messages[-1]
    thought = _extract_thought_from_message(last_msg)
    if thought:
        _notify("think", {"thought": thought})

# 同时推送 tool_call 事件（如果有工具调用）
if last_msg.get("tool_calls"):
    for tc in last_msg["tool_calls"]:
        func_name = tc["function"]["name"]
        args = tc["function"]["arguments"]
        _notify("tool_call", {"tool_name": func_name, "params": args})
```

> **注意**：由于采用方案 B（合成 thought），Coze 的 AGENT_SYSTEM_PROMPT 中的 `Thought:/Action:` 格式约束**不再需要**。System prompt 只需角色锚定 + 工具说明 + Finish 约束，不要求 LLM 输出 Thought-Action 文本对。LLM 通过 function calling 结构化返回工具调用，后端自动合成 thought 推送给前端。

#### B5: `/api/agent/chat` 路由已有 sync_push 保持不变

- **文件**: `backend/main.py`（第 416-464 行）
- **现状**: `/api/agent/chat` 路由已有完整的 `sync_push` callback 实现，通过 `asyncio.run_coroutine_threadsafe` 调用 `ws_manager.broadcast()`
- **改动**: 无需修改，保持现有逻辑

#### B6: VoicePanel 改为调用 `/api/agent/chat`

- **文件**: `frontend/src/components/VoicePanel.vue`
- **改什么**: `sendText()` 主请求从 `/api/agent/orchestrate` 改为 `/api/agent/chat`
- **为什么**: `/api/agent/chat` 是 ReActAgent 统一入口，天然产生 thinking steps

#### B7: 前端组件替换

- **文件**: 新增 `frontend/src/components/AgentStepCard.vue` + `frontend/src/composables/useAgentWebSocket.js`
- **改什么**: 替换现有 `AgentThinkingPanel.vue`
- **为什么**: Coze 设计的组件支持类型着色、耗时显示、自动滚动、可折叠详情，视觉效果更好

### 5.2 前端改动（4 项）

| 编号 | 文件 | 改什么 |
|------|------|--------|
| F1 | `VoicePanel.vue` | `sendText()` 调用 `/api/agent/chat`，请求体 `{ text, driver_state }`，适配响应格式 |
| F2 | `AgentStepCard.vue` | 新增组件：步骤卡片（思考/调用/结果/错误四种类型着色 + 耗时显示 + 动画入场） |
| F3 | `useAgentWebSocket.js` | 新增 composable：WebSocket 连接管理 + 消息分发 + 步骤列表状态 |
| F4 | `DashboardView.vue` | VoicePanel 新增 `@agent-start` 事件 → AgentThinkingPanel.clearSteps()；AgentThinkingPanel 连接地址改为 `/ws/agent_panel` |

### 4.3 改动文件汇总

| 文件 | 改动类型 | Phase |
|------|---------|-------|
| `backend/main.py` | 修改：新增 WebSocket 端点 | Phase 1 |
| `modules/ai/agent_graph.py` | 修改：推送 thought（方案 B） | **Phase 1**（从 P2 移入） |
| `modules/ai/prompts/agent_templates.py` | 修改：替换 system prompt | Phase 1 |
| `frontend/src/components/AgentStepCard.vue` | **新增** | Phase 1 |
| `frontend/src/composables/useAgentWebSocket.js` | **新增** | Phase 1 |
| `frontend/src/views/DashboardView.vue` | 修改：联动事件 + WebSocket 地址 | Phase 1 |
| `frontend/src/components/VoicePanel.vue` | 修改：三通道路由 + 规则去重 | Phase 2 |
| `modules/ai/tools.py` | 修改：注册 search_attractions | Phase 2 |
| `modules/ai/tools/search_attractions.py` | **新增** | Phase 2 |

**共 9 个文件：3 个新增 + 6 个修改**

---

## 六、延迟分析与降级策略

### 6.1 延迟影响

| 场景 | 改造前 | 改造后 | 说明 |
|------|--------|--------|------|
| "打开空调" | < 100ms | < 100ms | **走快速路由**，不经 LLM |
| "播放周杰伦的歌" | < 200ms | < 200ms | **走快速路由**，不经 LLM |
| "帮我规划天津一日游" | ~5s (Orchestrator) | ~5s (ReAct Agent) | 一样走 LLM，但 now 有思维链展示 |
| "我好困帮我调低空调" | ~3s (Orchestrator) | ~3s (ReAct Agent) | 一样走 LLM，有思维链展示 |
| "今天天气怎么样" | ~2s | ~2s | 无变化 |
| 纯闲聊 | 无路径 | ~1.5s | 新增能力 |

**关键设计**：简单控制指令（开空调、暂停音乐）走 `SimpleIntentRouter` 快速路由，不经 LLM，保持 <100ms 响应。只有复杂查询才走 ReAct Agent。

### 5.2 多级降级策略（采纳 Coze 设计）

```
┌──────────────────────┐
│    LLM 调用失败      │
├──────────────────────┤
│ 超时 (15s)           │──▶ 重试 1 次 ──▶ 仍失败 → 跳过该步，提示用户
│ 格式错误             │──▶ 追加修正 prompt 重试 ──▶ 仍失败 → 直接 Finish 降级回复
│ 工具不存在           │──▶ Observation 告知 LLM ──▶ LLM 自行纠正
│ 工具执行异常         │──▶ Observation 返回错误 ──▶ LLM 决定是否重试
│ 达到最大迭代 (8次)   │──▶ 强制 Finish，返回已收集信息的摘要
│ 总超时 (60s)         │──▶ 强制 Finish，返回"处理中请稍后"
│ /api/agent/chat 不可用 │──▶ VoicePanel 降级到 fallbackLocal 规则匹配
└──────────────────────┘
```

### 6.3 快速路由规则（统一为 VoicePanel 单层）

> **⚠️ 已知问题修复**：当前规则匹配存在三重重复——VoicePanel 的 `detectAcCommand()`（150 行正则）、Coze 方案的 `SimpleIntentRouter`（前端）、IntentionAgent 的 `RULE_BASED_PATTERNS`（后端）。**决策：只保留 VoicePanel 前端一层**，后端 IntentionAgent 的规则通道不再用于语音交互主路径（保留给 Orchestrator 编程调用使用）。

```python
# VoicePanel.vue — 唯一的快速路由层（替代 detectAcCommand + 新增 SimpleIntentRouter）
const QUICK_PATTERNS = [
    // 空调 — 纯开关指令
    { pattern: /打开空调|开空调|空调打开/, type: 'ac', action: 'on' },
    { pattern: /关闭空调|关掉空调|关空调/, type: 'ac', action: 'off' },
    { pattern: /太热了|好热/, type: 'ac', action: 'set_temp', params: { temperature: 22 } },
    { pattern: /太冷了|好冷/, type: 'ac', action: 'set_temp', params: { temperature: 26 } },
    // 音乐 — 纯控制指令（不涉及搜索）
    { pattern: /暂停|停止播放/, type: 'music', action: 'pause' },
    { pattern: /下一首|切歌/, type: 'music', action: 'next' },
    { pattern: /上一首/, type: 'music', action: 'prev' },
]

// 路由逻辑
function quickRoute(text) {
    for (const p of QUICK_PATTERNS) {
        if (p.pattern.test(text)) {
            return { type: p.type, action: p.action, params: p.params || {} }
        }
    }
    return null  // 未命中 → 走 /api/agent/chat
}

// sendText() 中的调用顺序
async function sendText() {
    const quick = quickRoute(text)
    if (quick) {
        // 直接执行 (<100ms)，不经 LLM
        executeQuickAction(quick)
        return
    }
    // 复杂指令 → ReAct Agent
    await callAgentChat(text)
}
```

**规则层清理计划**：

| 现有规则 | 改造后 |
|---------|--------|
| `VoicePanel.detectAcCommand()` 150 行正则 | **替换为** `QUICK_PATTERNS` 精简列表 |
| ~~Coze 方案 SimpleIntentRouter~~（不新增） | 由上面的 `QUICK_PATTERNS` 统一替代 |
| `IntentionAgent.RULE_BASED_PATTERNS` 后端 | **保留但不再用于语音交互**，仅 Orchestrator 编程调用使用 |

---

## 七、WebSocket 消息协议（采纳 Coze Schema）

### 7.1 消息格式

所有消息统一格式：

```json
{
    "type": "agent_thought | agent_action | agent_observation | agent_finish | agent_error",
    "data": { ... }
}
```

### 7.2 各类型详细 Schema

```jsonc
// 1. agent_thought — Agent 思考
{
    "type": "agent_thought",
    "data": {
        "step": 1,
        "thought": "用户想规划天津一日游。需要先查明天天津天气。",
        "timestamp": 1720000000100
    }
}

// 2. agent_action — 正在调用工具
{
    "type": "agent_action",
    "data": {
        "step": 1,
        "tool_name": "get_weather",
        "params": {"city": "天津"},
        "status": "calling"
    }
}

// 3. agent_observation — 工具返回结果
{
    "type": "agent_observation",
    "data": {
        "step": 1,
        "tool_name": "get_weather",
        "observation": "天津明天晴转多云，28°C，微风，适合出行",
        "elapsed_ms": 850
    }
}

// 4. agent_finish — 最终结果
{
    "type": "agent_finish",
    "data": {
        "final_text": "明天天津晴转多云28°C，建议早7点出发...",
        "total_steps": 4,
        "total_elapsed_ms": 5200
    }
}

// 5. agent_error — 错误
{
    "type": "agent_error",
    "data": {
        "step": 2,
        "error": "工具 search_attractions 调用超时",
        "recoverable": true
    }
}
```

---

## 八、分阶段实施计划

### Phase 1：打通链路（思维链能显示）— 6 步骤

**目标**：发送复杂指令后，AgentThinkingPanel 能渲染完整的思维链步骤。

| 步骤 | 文件 | 改动 |
|------|------|------|
| 1.1 | `backend/main.py` | 新增 `/ws/agent_panel` WebSocket 端点 |
| **1.2** | **`agent_graph.py`** | **`manual_react_loop` 推送 thought（方案 B：function calling 合成 thought）← 从 Phase 2 移入** |
| 1.3 | `agent_templates.py` | 替换 `agent.system.base`（角色锚定 + 工具说明 + Finish 约束，去掉 Thought/Action 文本格式要求） |
| 1.4 | `AgentStepCard.vue` | 新建步骤卡片组件（Coze 设计） |
| 1.5 | `useAgentWebSocket.js` | 新建 WebSocket composable |
| 1.6 | `DashboardView.vue` | AgentThinkingPanel 连接 `/ws/agent_panel` |

> **关键**：步骤 1.2 是 Phase 1 的核心——没有它，WebSocket 建好了但无数据推送，面板仍然空白。

**验证**：发送"帮我规划明天去天津玩一天的行程"，AgentThinkingPanel 应显示：
> 思考: 用户想规划天津一日游，需要先查天气 → 调用工具: get_weather(city="天津") → 结果: 晴转多云28°C → 思考: 天气好，接下来搜景点 → 调用工具: search_attractions → ... → 最终建议: ...

### Phase 2：统一入口 + 新工具 + 规则去重

**目标**：所有指令有合理路由，简单指令快速响应，复杂指令走 Agent 推理。

| 步骤 | 文件 | 改动 |
|------|------|------|
| 2.1 | `VoicePanel.vue` | `sendText()` 改为三通道：`QUICK_PATTERNS` → `/api/agent/chat`（或 `/api/agent/orchestrate` 诊断类）→ `fallbackLocal` |
| 2.2 | `tools.py` + `search_attractions.py` | 注册 search_attractions 工具 |
| 2.3 | `VoicePanel.vue` | 删除 `detectAcCommand()` 150 行旧代码，由 `QUICK_PATTERNS` 替代（规则去重） |
| 2.4 | `DashboardView.vue` | VoicePanel `@agent-start` 联动 AgentThinkingPanel.clearSteps() |

**验证**：
- "打开空调" → <100ms 快速响应（不走 LLM）
- "播放周杰伦的歌" → <200ms 快速响应（快速路由）
- "我好困帮我调低空调" → ReAct Agent 推理（思考→调空调→关怀回复）
- "帮我规划天津一日游" → ReAct Agent 多步推理 + 思维链展示

### Phase 3：体验打磨

**目标**：降级策略健壮、视觉效果完善、延迟可接受。

| 步骤 | 文件 | 改动 |
|------|------|------|
| 3.1 | `agent_graph.py` | 多级降级策略（超时重试、格式修正、强制 Finish） |
| 3.2 | `AgentStepCard.vue` | tool_result 可折叠（防长结果撑爆面板） |
| 3.3 | `VoicePanel.vue` | `/api/agent/chat` 超时自动降级到 fallbackLocal |
| 3.4 | `agent_graph.py` | 多轮上下文回注（AgentMemory.working 注入 state.messages） |

**验证**：断开 LLM（离线模式）发送"打开空调"→ <100ms 快速响应；恢复在线后发送复合指令→多步推理 + 降级策略生效。

---

## 九、与 Orchestrator 的关系

改造后 Orchestrator **仍然保留并参与语音交互**，用于特定场景：

| 路径 | 入口 | 触发条件 | 用途 |
|------|------|---------|------|
| **快速路由** | VoicePanel `QUICK_PATTERNS` | 纯开关指令（打开/关闭空调、暂停/切歌） | <100ms 直接执行 |
| **ReAct Agent** | VoicePanel → `/api/agent/chat` | 复杂查询（规划行程、天气+景点联动） | 多步推理 + 思维链 |
| **Orchestrator（语音）** | VoicePanel → `/api/agent/orchestrate` | 故障诊断 / 驾驶分析 / 疲劳复合意图 | 多子Agent协同 |
| **Orchestrator（后台）** | 后台定时任务 / API 编程调用 | 疲劳检测触发、外部系统调用 | 非语音交互场景 |
| **Agent WebSocket** | `/ws/agent_panel` | 所有 Agent 路径共用 | 思维链实时推送 |

**语音交互路由决策树**：

```
用户语音输入
  │
  ├─ QUICK_PATTERNS 命中？──▶ 直接执行 (<100ms)
  │
  ├─ 包含故障/诊断关键词？──▶ /api/agent/orchestrate
  │    (IntentionAgent → diagnose_agent → RAG知识库)
  │
  ├─ 包含驾驶分析关键词？──▶ /api/agent/orchestrate
  │    (IntentionAgent → analyze_agent → 驾驶评分)
  │
  └─ 其他 ──▶ /api/agent/chat
       (ReActAgent → tool_calling → 思维链展示)
```

**为什么诊断类仍走 Orchestrator**：
1. `diagnose_agent` 需要 RAG 知识库（`VehicleKnowledgeBase.retrieve_knowledge`），这是独立于 ReAct 工具的知识检索管道
2. `analyze_agent` 需要驾驶数据（时长、分心次数、注意力评分），需要从 `driver_state` 中聚合数据后传入
3. 这两个 Agent 的输入/输出格式与 ReAct 工具不同，硬塞进 `search_knowledge` 工具会丢失结构化输出（评分、等级、改进建议）

Orchestrator 的 IntentionAgent 和 5 个子 Agent 在语音交互中仍然活跃，覆盖故障诊断和驾驶分析两个重要场景。

---

## 十、风险与约束

| 风险 | 缓解措施 |
|------|---------|
| 简单指令延迟增加 | 快速路由拦截，不经 LLM |
| LLM 输出格式不稳定 | function calling 为主路径（结构化），文本解析作为 fallback |
| WebSocket 连接断开 | 自动重连 + 前端降级显示 |
| 高德 API 配额 | 免费额度 5000 次/天，足够开发测试 |
| 多轮对话无上下文 | Phase 3 实现 AgentMemory 上下文回注 |

---

## 十一、附录：参考资料

完整 Coze 生成方案见：`EdgeGuard_ReAct_Agent_Design.md`

第十三章智能旅行助手理论参考见：《HelloAgents — 智能体系统设计与实现》第十三章

Coze 核心采纳部分摘录：

- **AGENT_SYSTEM_PROMPT 模板**（第 23-126 行）：车载助手角色 + 7 工具说明 + Thought/Action/Finish 格式 + 示例对话
- **search_attractions 实现**（第 163-358 行）：高德 POI 搜索 + 天气过滤 + LLM 推荐理由
- **AgentStepCard.vue**（第 1213-1368 行）：步骤卡片组件（类型着色 + 动画 + 耗时）
- **useAgentWebSocket.js**（第 1113-1207 行）：WebSocket composable（消息分发 + 步骤状态）
- **降级策略**（第 840-851 行）：多级错误处理（超时/格式/未知工具/总超时）
