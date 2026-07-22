# EdgeGuard ReAct Agent 语音交互模块 — 完整设计方案

> 基于 Thought-Action-Observation 范式重构语音交互层
> 适配现有 FastAPI + DeepSeek + LangGraph + Vue3 架构

---

## 目录

1. [AGENT_SYSTEM_PROMPT 模板](#1-agent_system_prompt-模板)
2. [search_attractions 工具设计](#2-search_attractions-工具设计)
3. [Agent 主循环实现](#3-agent-主循环实现)
4. [WebSocket 实时推送方案](#4-websocket-实时推送方案)
5. [与现有架构整合方案](#5-与现有架构整合方案)

---

## 1. AGENT_SYSTEM_PROMPT 模板

### 1.1 完整 Prompt

```python
AGENT_SYSTEM_PROMPT = """你是 EdgeGuard 车载智能助手，专注于驾驶场景下的语音交互。

## 角色定位
- 你是一个车载旅行规划与安全助手，正在通过语音与驾驶员对话
- **安全第一**：任何涉及驾驶安全的决策必须优先处理
- **语音友好**：所有回复必须简短、口语化、适合 TTS 播报（每句 ≤ 25 字）
- **主动高效**：能一步完成的不分两步，能自己查的不问用户

## 可用工具

你可以调用以下工具来完成任务。每次只能调用一个工具。

### 1. get_weather
- 用途：查询指定城市的天气
- 参数：city (string, 必填) — 城市名称
- 示例：get_weather(city="天津")

### 2. search_attractions
- 用途：搜索城市热门景点，根据天气和偏好智能推荐
- 参数：
  - city (string, 必填) — 目标城市
  - weather (string, 可选) — 当前天气，用于过滤室内/户外
  - count (int, 可选, 默认5) — 推荐数量
  - preference (string, 可选) — 偏好类型："历史文化"/"亲子"/"户外"/"美食"/"拍照打卡"
- 示例：search_attractions(city="天津", weather="晴", count=5, preference="历史文化")

### 3. search_knowledge
- 用途：查询车辆知识库（RAG），获取车辆手册、故障排查、保养建议
- 参数：query (string, 必填) — 查询问题
- 示例：search_knowledge(query="出行前需要检查什么")

### 4. control_ac
- 用途：控制车载空调
- 参数：
  - action (string, 必填) — "on"/"off"/"set_temp"/"set_mode"
  - temperature (int, 可选) — 目标温度（16-32）
  - mode (string, 可选) — "cool"/"heat"/"auto"/"defog"
- 示例：control_ac(action="set_temp", temperature=24)

### 5. control_music
- 用途：控制车载音乐播放
- 参数：
  - action (string, 必填) — "play"/"pause"/"next"/"prev"/"set_genre"
  - query (string, 可选) — 歌曲名或歌手名
  - genre (string, 可选) — "pop"/"rock"/"classical"/"jazz"/"chill"
- 示例：control_music(action="play", query="周杰伦 晴天")

### 6. speak
- 用途：通过 TTS 向驾驶员播报语音消息
- 参数：text (string, 必填) — 播报文本（≤ 100 字）
- 示例：speak(text="前方3公里有服务区，建议休息")

### 7. alert_driver
- 用途：触发安全告警（疲劳/分心/危险驾驶）
- 参数：
  - level (string, 必填) — "info"/"warning"/"critical"
  - message (string, 必填) — 告警内容
- 示例：alert_driver(level="warning", message="您已连续驾驶2小时，建议休息")

## 输出格式

你必须严格按照以下格式输出，每次只输出一对 Thought-Action：

Thought: <你的思考过程，分析当前状态和下一步行动>
Action: <工具名>(参数1=值1, 参数2=值2)

当你获得足够信息可以给出最终回答时，使用 Finish：

Thought: <总结思考>
Action: Finish[最终回复文本]

## 约束规则

1. **每次只输出一对 Thought-Action**，不要一次输出多步
2. **Action 参数必须在一行内写完**，不要换行
3. **Finish 的回复 ≤ 3 句话**，每句 ≤ 25 字，适合语音播报
4. **不要输出 JSON 格式**，严格按 Thought/Action 文本格式
5. **安全相关操作（alert_driver）优先级最高**，发现危险立即告警
6. **不要编造工具返回值**，等待 Observation 后再决定下一步
7. **如果用户意图明确且无需工具**（如"打开空调"），直接 Finish 回复
8. **天气影响行程建议**：下雨优先室内景点，高温避开正午户外

## 示例对话

用户："帮我规划明天去天津玩一天的行程"

Thought: 用户想规划天津一日游。需要先查明天天津天气，再搜景点，最后综合建议。先查天气。
Action: get_weather(city="天津")

（等待 Observation 返回后继续）

Thought: 明天天津晴转多云28°C，适合出行。接下来搜天津热门景点，偏好户外和历史文化。
Action: search_attractions(city="天津", weather="晴转多云", count=5, preference="户外")

（等待 Observation 返回后继续）

Thought: 景点有了，还需检查车况确保安全。
Action: search_knowledge(query="出行前车辆检查项目")

（等待 Observation 返回后继续）

Thought: 天气好、车况正常、景点已选好。综合规划路线：上午户外趁凉快，中午室内休息，下午傍晚景点。
Action: Finish[明天天津晴转多云28°C，建议早7点出发走京沪高速。上午五大道加意式风情区，中午古文化街吃饭，下午天津之眼加海河游船。车况正常油量充足，导航到五大道吗？]
"""
```

### 1.2 Prompt 设计要点说明

| 设计点 | 说明 |
|--------|------|
| 角色锚定 | "车载旅行助手"而非通用助手，约束回复风格为语音友好 |
| 安全第一 | alert_driver 优先级最高，天气影响安全建议 |
| 工具参数内联 | 用 `key=value` 格式而非 JSON，减少 token 消耗 |
| 单步输出 | 每次只输出一对 Thought-Action，便于逐步推送给前端 |
| Finish 约束 | ≤ 3 句话、每句 ≤ 25 字，适配 TTS 播报节奏 |
| 天气联动 | 明确指示天气影响景点推荐策略 |

---

## 2. search_attractions 工具设计

### 2.1 方案选型：高德地图 POI 搜索

| 维度 | 高德地图 POI | 互联网搜索 API |
|------|-------------|---------------|
| 数据结构化 | ✅ 返回结构化 POI 数据 | ❌ 需额外解析 |
| 地理位置 | ✅ 精确经纬度+距离 | ⚠️ 需二次地理编码 |
| 分类标签 | ✅ 内置 POI 类型体系 | ❌ 无标准分类 |
| 实时性 | ✅ 营业时间/评分 | ✅ 更新快 |
| 调用成本 | 免费额度 5000次/天 | 多数收费 |
| 推荐理由 | ❌ 需 LLM 生成 | ✅ 可抓取评论 |

**推荐方案：高德 POI 为主 + LLM 生成推荐理由**

- 用高德获取结构化景点数据（名称、类型、评分、位置）
- 用 LLM 根据天气和偏好生成推荐理由
- 这样既有可靠的结构化数据，又有个性化的推荐文案

### 2.2 工具实现代码

```python
# modules/ai/tools/search_attractions.py

import httpx
import json
import os
from typing import Optional
from deepseek_client import DeepSeekClient

# 高德地图 API 配置
AMAP_KEY = os.getenv("AMAP_API_KEY", "")
AMAP_POI_URL = "https://restapi.amap.com/v5/place/text"

# 景点类型映射（高德 POI 类型码 → 友好标签）
POI_TYPE_MAP = {
    "风景名胜": "景点",
    "风景名胜;风景名胜相关": "景点",
    "风景名胜;旅游景点": "景点",
    "科教文化服务;博物馆": "博物馆",
    "科教文化服务;科技馆": "科技馆",
    "购物服务;商场": "商场",
    "餐饮服务": "美食",
    "体育休闲服务;娱乐场所": "娱乐",
    "商务住宅;度假村": "度假",
}

# 偏好 → 高德 POI 搜索关键词映射
PREFERENCE_KEYWORDS = {
    "历史文化": "历史文化景点 古迹 博物馆",
    "亲子": "亲子乐园 动物园 儿童公园",
    "户外": "公园 山景 湖景 自然风景区",
    "美食": "美食街 特色餐饮 小吃",
    "拍照打卡": "网红景点 地标建筑 观景台",
}

# 天气 → 偏好过滤规则
WEATHER_INDOOR_TYPES = {"博物馆", "科技馆", "商场", "娱乐"}
WEATHER_OUTDOOR_TYPES = {"景点", "公园", "山景", "湖景", "度假", "娱乐"}

BAD_WEATHER_KEYWORDS = ["雨", "雪", "暴雨", "大风", "雷暴", "冰雹"]
HOT_WEATHER_KEYWORDS = ["高温", "酷热", "35°C", "36°C", "37°C", "38°C", "39°C", "40°C"]


def is_bad_weather(weather: str) -> bool:
    """判断是否为恶劣天气（需要优先推荐室内）"""
    return any(kw in weather for kw in BAD_WEATHER_KEYWORDS)


def is_hot_weather(weather: str) -> bool:
    """判断是否为高温天气（避开正午户外）"""
    return any(kw in weather for kw in HOT_WEATHER_KEYWORDS)


async def search_amap_poi(
    city: str,
    keyword: str = "旅游景点",
    count: int = 10,
) -> list[dict]:
    """调用高德地图 POI 搜索"""
    params = {
        "key": AMAP_KEY,
        "keywords": keyword,
        "region": city,
        "city_limit": "true",
        "page_size": str(min(count, 25)),
        "show_fields": "business,photos",
        "offset": "1",
    }

    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(AMAP_POI_URL, params=params)
        data = resp.json()

    if data.get("status") != "1":
        return []

    pois = data.get("pois", [])
    results = []
    for poi in pois:
        # 解析 POI 类型
        type_str = poi.get("type", "")
        type_tag = "景点"  # 默认
        for key, tag in POI_TYPE_MAP.items():
            if key in type_str:
                type_tag = tag
                break

        results.append({
            "name": poi.get("name", ""),
            "type_tag": type_tag,
            "address": poi.get("address", ""),
            "rating": poi.get("biz_ext", {}).get("rating", "暂无"),
            "location": poi.get("location", ""),  # 经纬度
            "photos": poi.get("photos", []),
        })

    return results


def filter_by_weather(pois: list[dict], weather: str) -> list[dict]:
    """根据天气过滤景点"""
    if not weather:
        return pois

    if is_bad_weather(weather):
        # 恶劣天气：优先室内
        return sorted(pois, key=lambda p: (
            0 if p["type_tag"] in WEATHER_INDOOR_TYPES else 1
        ))
    elif is_hot_weather(weather):
        # 高温天气：标注户外景点需避开正午
        for poi in pois:
            if poi["type_tag"] in WEATHER_OUTDOOR_TYPES:
                poi["weather_note"] = "建议清晨或傍晚前往，避开正午高温"
        return pois
    else:
        # 好天气：优先户外
        return sorted(pois, key=lambda p: (
            0 if p["type_tag"] in WEATHER_OUTDOOR_TYPES else 1
        ))


async def generate_recommendation_reason(
    poi: dict,
    weather: str,
    preference: str,
    llm_client: DeepSeekClient,
) -> str:
    """用 LLM 为单个景点生成推荐理由（≤ 20 字）"""
    prompt = (
        f"为景点「{poi['name']}」写一句推荐理由（≤ 20 字），"
        f"天气：{weather or '未知'}，用户偏好：{preference or '综合'}。"
        f"只输出推荐语，不要引号和前缀。"
    )
    try:
        reason = await llm_client.chat(prompt, max_tokens=50)
        return reason.strip()
    except Exception:
        return f"{poi['type_tag']}好去处"


async def search_attractions(
    city: str,
    weather: Optional[str] = None,
    count: int = 5,
    preference: Optional[str] = None,
    llm_client: Optional[DeepSeekClient] = None,
) -> str:
    """
    search_attractions 工具主函数

    Args:
        city: 目标城市
        weather: 当前天气（用于过滤）
        count: 推荐数量
        preference: 偏好类型
        llm_client: LLM 客户端（用于生成推荐理由）

    Returns:
        格式化的景点推荐文本
    """
    # 1. 确定搜索关键词
    keyword = PREFERENCE_KEYWORDS.get(preference, "旅游景点 热门景点")

    # 2. 调用高德 POI 搜索（多搜一些用于过滤）
    pois = await search_amap_poi(city, keyword=keyword, count=count * 2)

    if not pois:
        return f"未找到{city}的相关景点，建议换个关键词试试。"

    # 3. 天气过滤
    pois = filter_by_weather(pois, weather)

    # 4. 取前 N 个
    pois = pois[:count]

    # 5. 生成推荐理由（如果有 LLM）
    if llm_client:
        for poi in pois:
            poi["reason"] = await generate_recommendation_reason(
                poi, weather, preference, llm_client
            )
    else:
        for poi in pois:
            poi["reason"] = f"{poi['type_tag']}好去处"

    # 6. 格式化输出
    lines = []
    for i, poi in enumerate(pois, 1):
        line = f"{i}. {poi['name']}（{poi['type_tag']}）— {poi['reason']}"
        if poi.get("weather_note"):
            line += f" ⚠️{poi['weather_note']}"
        lines.append(line)

    return "\n".join(lines)
```

### 2.3 天气联动策略

```
┌─────────────────┐     ┌──────────────────┐     ┌─────────────────┐
│   天气判断       │────▶│   景点过滤       │────▶│   排序策略       │
├─────────────────┤     ├──────────────────┤     ├─────────────────┤
│ 雨/雪/雷暴      │     │ 剔除纯户外景点   │     │ 室内优先        │
│ 高温 ≥35°C      │     │ 标注避暑提示     │     │ 户外排后+标注   │
│ 晴/多云/微风    │     │ 不过滤           │     │ 户外优先        │
│ 无天气信息       │     │ 不过滤           │     │ 按评分排序      │
└─────────────────┘     └──────────────────┘     └─────────────────┘
```

---

## 3. Agent 主循环实现

### 3.1 核心代码

```python
# modules/ai/agents/react_agent.py

import re
import asyncio
import time
import logging
from typing import AsyncGenerator, Optional, Callable
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

# ============================================
# 数据结构
# ============================================

@dataclass
class AgentStep:
    """Agent 单步执行结果"""
    step_index: int
    thought: str = ""
    action: str = ""          # 工具名
    action_params: dict = {}  # 解析后的参数
    observation: str = ""
    is_finish: bool = False
    finish_text: str = ""
    error: str = ""
    elapsed_ms: int = 0


@dataclass
class AgentResult:
    """Agent 完整执行结果"""
    success: bool
    final_text: str = ""
    steps: list[AgentStep] = field(default_factory=list)
    total_elapsed_ms: int = 0
    error: str = ""


# ============================================
# Thought/Action 解析器
# ============================================

# 匹配格式:
#   Thought: xxx
#   Action: tool_name(param1=value1, param2=value2)
#   Action: Finish[最终回复文本]
THOUGHT_PATTERN = re.compile(r"Thought:\s*(.+?)(?=\nAction:|\Z)", re.DOTALL)
ACTION_PATTERN = re.compile(r"Action:\s*(.+?)(?:\n|\Z)", re.DOTALL)

# 匹配 Action 中的工具名和参数
# 格式: tool_name(key1=value1, key2="value with spaces")
TOOL_CALL_PATTERN = re.compile(
    r'^(\w+)\((.+)\)$', re.DOTALL
)

# 匹配 Finish
FINISH_PATTERN = re.compile(r'^Finish\[(.+)\]$', re.DOTALL)


def parse_thought_action(llm_output: str) -> tuple[str, str]:
    """
    从 LLM 输出中解析 Thought 和 Action

    Returns:
        (thought_text, action_text)
    """
    thought_match = THOUGHT_PATTERN.search(llm_output)
    action_match = ACTION_PATTERN.search(llm_output)

    thought = thought_match.group(1).strip() if thought_match else ""
    action = action_match.group(1).strip() if action_match else ""

    return thought, action


def parse_action(action_text: str) -> tuple[str, dict, bool, str]:
    """
    解析 Action 文本

    Returns:
        (tool_name, params_dict, is_finish, finish_text)
    """
    # 检查是否为 Finish
    finish_match = FINISH_PATTERN.match(action_text)
    if finish_match:
        return "Finish", {}, True, finish_match.group(1).strip()

    # 解析工具调用
    tool_match = TOOL_CALL_PATTERN.match(action_text)
    if not tool_match:
        return "", {}, False, ""

    tool_name = tool_match.group(1)
    params_str = tool_match.group(2)

    # 解析参数 key=value 对
    params = _parse_params(params_str)
    return tool_name, params, False, ""


def _parse_params(params_str: str) -> dict:
    """
    解析 key=value 参数串
    支持: key="value with spaces", key=123, key=value
    """
    params = {}
    # 匹配 key=value 对，value 可以是引号内或无引号
    param_pattern = re.compile(
        r'(\w+)\s*=\s*(?:"([^"]*?)"|\'([^\']*?)\'|([^,\s]+))'
    )
    for match in param_pattern.finditer(params_str):
        key = match.group(1)
        value = match.group(2) or match.group(3) or match.group(4)

        # 尝试类型转换
        if value.isdigit():
            value = int(value)
        elif value.lower() in ("true", "false"):
            value = value.lower() == "true"
        elif value.lower() == "none":
            value = None

        params[key] = value

    return params


# ============================================
# Agent 主循环
# ============================================

# 工具注册表
TOOL_REGISTRY: dict[str, Callable] = {}

# 最大迭代次数（防止死循环）
MAX_ITERATIONS = 8

# 单次 LLM 调用超时（秒）
LLM_TIMEOUT = 15

# 整体超时（秒）
TOTAL_TIMEOUT = 60


def register_tool(name: str, func: Callable):
    """注册工具到全局注册表"""
    TOOL_REGISTRY[name] = func


class ReActAgent:
    """
    ReAct Agent 主循环

    执行流程:
    1. 构建 messages（system prompt + 用户输入 + 历史 Observation）
    2. 调用 LLM 获取 Thought + Action
    3. 解析 Action，执行工具
    4. 将 Observation 追加到 messages
    5. 重复 2-4 直到 Finish 或达到限制
    """

    def __init__(
        self,
        system_prompt: str,
        llm_client,
        tool_registry: dict[str, Callable],
        on_step: Optional[Callable[[AgentStep], None]] = None,
        max_iterations: int = MAX_ITERATIONS,
        total_timeout: int = TOTAL_TIMEOUT,
    ):
        self.system_prompt = system_prompt
        self.llm_client = llm_client
        self.tools = tool_registry
        self.on_step = on_step  # 每步回调（用于 WebSocket 推送）
        self.max_iterations = max_iterations
        self.total_timeout = total_timeout

    async def run(self, user_input: str) -> AgentResult:
        """
        执行 Agent 主循环

        Args:
            user_input: 用户输入文本

        Returns:
            AgentResult
        """
        start_time = time.time()
        messages = [
            {"role": "system", "content": self.system_prompt},
            {"role": "user", "content": user_input},
        ]
        steps = []

        for i in range(self.max_iterations):
            # 检查总超时
            elapsed = time.time() - start_time
            if elapsed > self.total_timeout:
                return AgentResult(
                    success=False,
                    steps=steps,
                    total_elapsed_ms=int(elapsed * 1000),
                    error="Agent 执行超时",
                    final_text="抱歉，处理时间过长，请稍后再试。",
                )

            step = AgentStep(step_index=i + 1)
            step_start = time.time()

            try:
                # ---- Step 1: 调用 LLM ----
                llm_output = await asyncio.wait_for(
                    self.llm_client.chat_messages(messages),
                    timeout=LLM_TIMEOUT,
                )

                # ---- Step 2: 解析 Thought/Action ----
                step.thought, action_text = parse_thought_action(llm_output)
                step.action = action_text

                if not action_text:
                    # 格式错误：降级处理
                    step.error = "LLM 输出格式异常，自动降级"
                    logger.warning(f"Step {i+1}: 无法解析 Action: {llm_output[:200]}")
                    # 追加修正提示，让 LLM 重新输出
                    messages.append({"role": "assistant", "content": llm_output})
                    messages.append({
                        "role": "user",
                        "content": "请严格按照 Thought/Action 格式输出。"
                    })
                    step.elapsed_ms = int((time.time() - step_start) * 1000)
                    steps.append(step)
                    if self.on_step:
                        self.on_step(step)
                    continue

                # ---- Step 3: 解析工具调用 ----
                tool_name, params, is_finish, finish_text = parse_action(action_text)
                step.action = tool_name
                step.action_params = params

                # 通知前端当前步骤
                if self.on_step:
                    self.on_step(step)

                # ---- Step 4: 处理 Finish ----
                if is_finish:
                    step.is_finish = True
                    step.finish_text = finish_text
                    step.elapsed_ms = int((time.time() - step_start) * 1000)
                    steps.append(step)
                    if self.on_step:
                        self.on_step(step)

                    total_elapsed = int((time.time() - start_time) * 1000)
                    return AgentResult(
                        success=True,
                        final_text=finish_text,
                        steps=steps,
                        total_elapsed_ms=total_elapsed,
                    )

                # ---- Step 5: 执行工具 ----
                if tool_name not in self.tools:
                    step.observation = f"错误：工具 '{tool_name}' 不存在。可用工具：{list(self.tools.keys())}"
                    step.error = f"未知工具: {tool_name}"
                else:
                    try:
                        tool_func = self.tools[tool_name]
                        if asyncio.iscoroutinefunction(tool_func):
                            result = await tool_func(**params)
                        else:
                            result = tool_func(**params)
                        step.observation = str(result)
                    except Exception as e:
                        step.observation = f"工具执行失败：{str(e)}"
                        step.error = str(e)
                        logger.error(f"Step {i+1}: 工具 {tool_name} 执行失败: {e}")

                step.elapsed_ms = int((time.time() - step_start) * 1000)
                steps.append(step)

                # 通知前端 Observation
                if self.on_step:
                    self.on_step(step)

                # ---- Step 6: 追加到 messages ----
                messages.append({"role": "assistant", "content": llm_output})
                messages.append({
                    "role": "user",
                    "content": f"Observation: {step.observation}"
                })

            except asyncio.TimeoutError:
                step.error = "LLM 调用超时"
                step.elapsed_ms = int((time.time() - step_start) * 1000)
                steps.append(step)
                if self.on_step:
                    self.on_step(step)
                logger.error(f"Step {i+1}: LLM 调用超时")
                continue

            except Exception as e:
                step.error = str(e)
                step.elapsed_ms = int((time.time() - step_start) * 1000)
                steps.append(step)
                if self.on_step:
                    self.on_step(step)
                logger.error(f"Step {i+1}: 未预期异常: {e}")
                continue

        # 达到最大迭代次数
        total_elapsed = int((time.time() - start_time) * 1000)
        return AgentResult(
            success=False,
            steps=steps,
            total_elapsed_ms=total_elapsed,
            error=f"达到最大迭代次数 {self.max_iterations}",
            final_text="抱歉，这个问题我需要分步处理，目前还在分析中。请稍后再试。",
        )


# ============================================
# 流式执行（支持 WebSocket 逐步推送）
# ============================================

    async def run_stream(self, user_input: str) -> AsyncGenerator[AgentStep, None]:
        """
        流式执行 Agent，每完成一步 yield 一个 AgentStep
        用于 WebSocket 实时推送
        """
        start_time = time.time()
        messages = [
            {"role": "system", "content": self.system_prompt},
            {"role": "user", "content": user_input},
        ]

        for i in range(self.max_iterations):
            elapsed = time.time() - start_time
            if elapsed > self.total_timeout:
                error_step = AgentStep(
                    step_index=i + 1,
                    error="Agent 执行超时",
                    is_finish=True,
                    finish_text="抱歉，处理时间过长，请稍后再试。",
                )
                yield error_step
                return

            step = AgentStep(step_index=i + 1)
            step_start = time.time()

            try:
                llm_output = await asyncio.wait_for(
                    self.llm_client.chat_messages(messages),
                    timeout=LLM_TIMEOUT,
                )

                step.thought, action_text = parse_thought_action(llm_output)
                step.action = action_text

                if not action_text:
                    step.error = "LLM 输出格式异常"
                    messages.append({"role": "assistant", "content": llm_output})
                    messages.append({
                        "role": "user",
                        "content": "请严格按照 Thought/Action 格式输出。"
                    })
                    step.elapsed_ms = int((time.time() - step_start) * 1000)
                    yield step
                    continue

                tool_name, params, is_finish, finish_text = parse_action(action_text)
                step.action = tool_name
                step.action_params = params

                if is_finish:
                    step.is_finish = True
                    step.finish_text = finish_text
                    step.elapsed_ms = int((time.time() - step_start) * 1000)
                    yield step
                    return

                # 执行工具
                if tool_name not in self.tools:
                    step.observation = f"错误：工具 '{tool_name}' 不存在"
                else:
                    try:
                        tool_func = self.tools[tool_name]
                        if asyncio.iscoroutinefunction(tool_func):
                            result = await tool_func(**params)
                        else:
                            result = tool_func(**params)
                        step.observation = str(result)
                    except Exception as e:
                        step.observation = f"工具执行失败：{e}"
                        step.error = str(e)

                step.elapsed_ms = int((time.time() - step_start) * 1000)
                yield step

                # 追加到 messages
                messages.append({"role": "assistant", "content": llm_output})
                messages.append({
                    "role": "user",
                    "content": f"Observation: {step.observation}"
                })

            except asyncio.TimeoutError:
                step.error = "LLM 调用超时"
                step.elapsed_ms = int((time.time() - step_start) * 1000)
                yield step

            except Exception as e:
                step.error = str(e)
                step.elapsed_ms = int((time.time() - step_start) * 1000)
                yield step

        # 达到最大迭代
        yield AgentStep(
            step_index=self.max_iterations + 1,
            error="达到最大迭代次数",
            is_finish=True,
            finish_text="抱歉，这个问题处理较复杂，请稍后再试。",
        )
```

### 3.2 工具注册与初始化

```python
# modules/ai/agents/tool_registry.py

from modules.ai.tools.search_attractions import search_attractions
from modules.ai.tools.get_weather import get_weather
from modules.ai.tools.search_knowledge import search_knowledge
from modules.ai.tools.control_ac import control_ac
from modules.ai.tools.control_music import control_music
from modules.ai.tools.speak import speak
from modules.ai.tools.alert_driver import alert_driver
from modules.ai.deepseek_client import DeepSeekClient


def build_tool_registry(llm_client: DeepSeekClient) -> dict:
    """构建工具注册表"""
    return {
        "get_weather": get_weather,
        "search_attractions": lambda **kw: search_attractions(
            llm_client=llm_client, **kw
        ),
        "search_knowledge": search_knowledge,
        "control_ac": control_ac,
        "control_music": control_music,
        "speak": speak,
        "alert_driver": alert_driver,
    }
```

### 3.3 降级策略

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
└──────────────────────┘
```

---

## 4. WebSocket 实时推送方案

### 4.1 消息 JSON Schema

```python
# 所有消息统一格式
{
    "type": "agent_step",           # 消息类型
    "session_id": "uuid-xxx",       # 会话ID
    "data": { ... }                 # 具体数据
}

# type 枚举:
# - "agent_step_start"   → Agent 开始处理
# - "agent_thought"      → Thought 输出
# - "agent_action"       → Action 输出（工具调用）
# - "agent_observation"  → Observation 返回
# - "agent_finish"       → 最终结果
# - "agent_error"        → 错误
# - "agent_step_end"     → 单步结束
```

#### 各类型详细 Schema

```python
# 1. agent_step_start — Agent 开始处理用户输入
{
    "type": "agent_step_start",
    "session_id": "a1b2c3d4",
    "data": {
        "user_input": "帮我规划明天去天津玩一天的行程",
        "timestamp": 1720000000000
    }
}

# 2. agent_thought — Thought 输出
{
    "type": "agent_thought",
    "session_id": "a1b2c3d4",
    "data": {
        "step": 1,
        "thought": "用户想规划天津一日游。需要先查明天天津天气。",
        "timestamp": 1720000000100
    }
}

# 3. agent_action — Action 输出（正在调用工具）
{
    "type": "agent_action",
    "session_id": "a1b2c3d4",
    "data": {
        "step": 1,
        "tool_name": "get_weather",
        "params": {"city": "天津"},
        "status": "calling",        # calling | completed | failed
        "timestamp": 1720000000200
    }
}

# 4. agent_observation — 工具返回结果
{
    "type": "agent_observation",
    "session_id": "a1b2c3d4",
    "data": {
        "step": 1,
        "tool_name": "get_weather",
        "observation": "天津明天晴转多云，28°C，微风，适合出行",
        "elapsed_ms": 850,
        "timestamp": 1720000001050
    }
}

# 5. agent_finish — 最终结果
{
    "type": "agent_finish",
    "session_id": "a1b2c3d4",
    "data": {
        "final_text": "明天天津晴转多云28°C，建议早7点出发走京沪高速。上午五大道加意式风情区，中午古文化街吃饭，下午天津之眼加海河游船。",
        "total_steps": 4,
        "total_elapsed_ms": 5200,
        "timestamp": 1720000005200
    }
}

# 6. agent_error — 错误
{
    "type": "agent_error",
    "session_id": "a1b2c3d4",
    "data": {
        "step": 2,
        "error": "工具 search_attractions 调用超时",
        "recoverable": true,
        "timestamp": 1720000003000
    }
}
```

### 4.2 后端 WebSocket 处理

```python
# backend/app/ws/agent_ws.py

import json
import uuid
import asyncio
from fastapi import WebSocket, WebSocketDisconnect
from modules.ai.agents.react_agent import ReActAgent, AgentStep
from modules.ai.agents.tool_registry import build_tool_registry
from modules.ai.prompts import AGENT_SYSTEM_PROMPT


class AgentWebSocketHandler:
    """Agent WebSocket 处理器"""

    def __init__(self, llm_client):
        self.llm_client = llm_client
        self.tool_registry = build_tool_registry(llm_client)

    async def handle(self, websocket: WebSocket):
        """处理 WebSocket 连接"""
        await websocket.accept()
        session_id = str(uuid.uuid4())[:8]

        try:
            while True:
                # 接收用户消息
                raw = await websocket.receive_text()
                msg = json.loads(raw)
                user_input = msg.get("text", "")

                if not user_input:
                    continue

                # 发送开始信号
                await self._send(websocket, {
                    "type": "agent_step_start",
                    "session_id": session_id,
                    "data": {
                        "user_input": user_input,
                        "timestamp": self._now_ms(),
                    }
                })

                # 创建 Agent（带流式回调）
                agent = ReActAgent(
                    system_prompt=AGENT_SYSTEM_PROMPT,
                    llm_client=self.llm_client,
                    tool_registry=self.tool_registry,
                )

                # 流式执行并推送每一步
                final_text = ""
                async for step in agent.run_stream(user_input):
                    await self._push_step(websocket, session_id, step)
                    if step.is_finish:
                        final_text = step.finish_text

                # 发送完成信号
                await self._send(websocket, {
                    "type": "agent_finish",
                    "session_id": session_id,
                    "data": {
                        "final_text": final_text,
                        "timestamp": self._now_ms(),
                    }
                })

                # TTS 播报最终结果
                if final_text and "speak" in self.tool_registry:
                    try:
                        await self.tool_registry["speak"](text=final_text)
                    except Exception:
                        pass

        except WebSocketDisconnect:
            pass
        except Exception as e:
            try:
                await self._send(websocket, {
                    "type": "agent_error",
                    "session_id": session_id,
                    "data": {"error": str(e), "timestamp": self._now_ms()}
                })
            except Exception:
                pass

    async def _push_step(self, ws: WebSocket, session_id: str, step: AgentStep):
        """推送单步数据到前端"""
        # 推送 Thought
        if step.thought:
            await self._send(ws, {
                "type": "agent_thought",
                "session_id": session_id,
                "data": {
                    "step": step.step_index,
                    "thought": step.thought,
                    "timestamp": self._now_ms(),
                }
            })

        # 推送 Action
        if step.action and not step.is_finish:
            await self._send(ws, {
                "type": "agent_action",
                "session_id": session_id,
                "data": {
                    "step": step.step_index,
                    "tool_name": step.action,
                    "params": step.action_params,
                    "status": "calling",
                    "timestamp": self._now_ms(),
                }
            })

        # 推送 Observation
        if step.observation:
            await self._send(ws, {
                "type": "agent_observation",
                "session_id": session_id,
                "data": {
                    "step": step.step_index,
                    "tool_name": step.action,
                    "observation": step.observation,
                    "elapsed_ms": step.elapsed_ms,
                    "timestamp": self._now_ms(),
                }
            })

        # 推送错误
        if step.error:
            await self._send(ws, {
                "type": "agent_error",
                "session_id": session_id,
                "data": {
                    "step": step.step_index,
                    "error": step.error,
                    "recoverable": True,
                    "timestamp": self._now_ms(),
                }
            })

    async def _send(self, ws: WebSocket, data: dict):
        """发送 JSON 消息"""
        try:
            await ws.send_json(data)
        except Exception:
            pass

    def _now_ms(self) -> int:
        import time
        return int(time.time() * 1000)
```

### 4.3 前端 Vue3 渲染方案

#### 4.3.1 WebSocket 连接管理

```javascript
// frontend/src/composables/useAgentWebSocket.js

import { ref, onUnmounted } from 'vue'

export function useAgentWebSocket() {
  const steps = ref([])          // 所有步骤
  const isProcessing = ref(false) // 是否正在处理
  const finalText = ref('')      // 最终结果
  const error = ref('')
  let ws = null

  function connect(url) {
    ws = new WebSocket(url)

    ws.onmessage = (event) => {
      const msg = JSON.parse(event.data)
      handleMessage(msg)
    }

    ws.onclose = () => {
      isProcessing.value = false
    }

    return ws
  }

  function handleMessage(msg) {
    switch (msg.type) {
      case 'agent_step_start':
        steps.value = []
        finalText.value = ''
        error.value = ''
        isProcessing.value = true
        break

      case 'agent_thought':
        steps.value.push({
          type: 'thought',
          step: msg.data.step,
          content: msg.data.thought,
          timestamp: msg.data.timestamp,
        })
        break

      case 'agent_action':
        steps.value.push({
          type: 'action',
          step: msg.data.step,
          toolName: msg.data.tool_name,
          params: msg.data.params,
          status: msg.data.status,
          timestamp: msg.data.timestamp,
        })
        break

      case 'agent_observation':
        steps.value.push({
          type: 'observation',
          step: msg.data.step,
          toolName: msg.data.tool_name,
          content: msg.data.observation,
          elapsedMs: msg.data.elapsed_ms,
          timestamp: msg.data.timestamp,
        })
        break

      case 'agent_finish':
        finalText.value = msg.data.final_text
        isProcessing.value = false
        break

      case 'agent_error':
        error.value = msg.data.error
        steps.value.push({
          type: 'error',
          step: msg.data.step,
          content: msg.data.error,
          timestamp: msg.data.timestamp,
        })
        break
    }
  }

  function send(text) {
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({ text }))
    }
  }

  onUnmounted(() => {
    if (ws) ws.close()
  })

  return { steps, isProcessing, finalText, error, connect, send }
}
```

#### 4.3.2 步骤卡片组件

```vue
<!-- frontend/src/components/AgentStepCard.vue -->
<template>
  <div class="agent-step-card" :class="[`step-${step.type}`]">
    <!-- 状态图标 -->
    <div class="step-icon">
      <el-icon v-if="step.type === 'thought'" class="icon-thinking">
        <Loading />
      </el-icon>
      <el-icon v-else-if="step.type === 'action'" class="icon-action">
        <SetUp />
      </el-icon>
      <el-icon v-else-if="step.type === 'observation'" class="icon-obs">
        <Check />
      </el-icon>
      <el-icon v-else-if="step.type === 'error'" class="icon-error">
        <WarningFilled />
      </el-icon>
    </div>

    <!-- 内容区 -->
    <div class="step-content">
      <!-- Thought -->
      <template v-if="step.type === 'thought'">
        <div class="step-label">思考</div>
        <div class="step-text">{{ step.content }}</div>
      </template>

      <!-- Action -->
      <template v-else-if="step.type === 'action'">
        <div class="step-label">调用工具</div>
        <div class="step-tool">
          <el-tag type="primary" size="small">{{ step.toolName }}</el-tag>
          <span class="step-params">{{ formatParams(step.params) }}</span>
        </div>
      </template>

      <!-- Observation -->
      <template v-else-if="step.type === 'observation'">
        <div class="step-label">
          结果
          <span class="step-time">{{ step.elapsedMs }}ms</span>
        </div>
        <div class="step-text observation-text">{{ step.content }}</div>
      </template>

      <!-- Error -->
      <template v-else-if="step.type === 'error'">
        <div class="step-label error-label">异常</div>
        <div class="step-text error-text">{{ step.content }}</div>
      </template>
    </div>

    <!-- 步骤编号 -->
    <div class="step-number">#{{ step.step }}</div>
  </div>
</template>

<script setup>
import { Loading, SetUp, Check, WarningFilled } from '@element-plus/icons-vue'

const props = defineProps({
  step: { type: Object, required: true }
})

function formatParams(params) {
  if (!params || Object.keys(params).length === 0) return ''
  return Object.entries(params)
    .map(([k, v]) => `${k}="${v}"`)
    .join(', ')
}
</script>

<style scoped>
.agent-step-card {
  display: flex;
  align-items: flex-start;
  gap: 12px;
  padding: 12px 16px;
  border-radius: 8px;
  margin-bottom: 8px;
  background: rgba(255, 255, 255, 0.05);
  border-left: 3px solid transparent;
  animation: slideIn 0.3s ease-out;
}

.step-thought { border-left-color: #409EFF; }
.step-action  { border-left-color: #E6A23C; }
.step-observation { border-left-color: #67C23A; }
.step-error   { border-left-color: #F56C6C; }

.step-icon {
  font-size: 18px;
  margin-top: 2px;
}
.icon-thinking { color: #409EFF; animation: spin 1.5s linear infinite; }
.icon-action   { color: #E6A23C; }
.icon-obs      { color: #67C23A; }
.icon-error    { color: #F56C6C; }

.step-content { flex: 1; min-width: 0; }

.step-label {
  font-size: 11px;
  color: rgba(255, 255, 255, 0.4);
  margin-bottom: 4px;
  text-transform: uppercase;
  letter-spacing: 1px;
}

.step-text {
  font-size: 14px;
  color: rgba(255, 255, 255, 0.85);
  line-height: 1.5;
}

.step-tool {
  display: flex;
  align-items: center;
  gap: 8px;
}

.step-params {
  font-size: 12px;
  color: rgba(255, 255, 255, 0.5);
  font-family: 'Courier New', monospace;
}

.step-time {
  font-size: 10px;
  color: rgba(255, 255, 255, 0.3);
  margin-left: 8px;
}

.step-number {
  font-size: 11px;
  color: rgba(255, 255, 255, 0.2);
  font-weight: bold;
}

.observation-text {
  white-space: pre-wrap;
  font-size: 13px;
}

.error-text { color: #F56C6C; }

@keyframes slideIn {
  from { opacity: 0; transform: translateY(10px); }
  to   { opacity: 1; transform: translateY(0); }
}

@keyframes spin {
  from { transform: rotate(0deg); }
  to   { transform: rotate(360deg); }
}
</style>
```

#### 4.3.3 主面板集成

```vue
<!-- frontend/src/components/AgentPanel.vue -->
<template>
  <div class="agent-panel">
    <!-- 步骤流 -->
    <div class="steps-container" ref="stepsContainer">
      <AgentStepCard
        v-for="(step, idx) in steps"
        :key="idx"
        :step="step"
      />

      <!-- 加载指示器 -->
      <div v-if="isProcessing" class="processing-indicator">
        <el-icon class="is-loading"><Loading /></el-icon>
        <span>Agent 思考中...</span>
      </div>
    </div>

    <!-- 最终结果 -->
    <div v-if="finalText" class="final-result">
      <div class="result-label">最终建议</div>
      <div class="result-text">{{ finalText }}</div>
    </div>
  </div>
</template>

<script setup>
import { ref, watch, nextTick } from 'vue'
import { Loading } from '@element-plus/icons-vue'
import AgentStepCard from './AgentStepCard.vue'
import { useAgentWebSocket } from '../composables/useAgentWebSocket'

const { steps, isProcessing, finalText, connect, send } = useAgentWebSocket()
const stepsContainer = ref(null)

// 自动滚动到底部
watch(steps, () => {
  nextTick(() => {
    if (stepsContainer.value) {
      stepsContainer.value.scrollTop = stepsContainer.value.scrollHeight
    }
  })
}, { deep: true })

// 连接 WebSocket
connect('ws://localhost:8000/ws/agent')

// 暴露发送方法
function sendQuery(text) {
  send(text)
}

defineExpose({ sendQuery })
</script>
```

---

## 5. 与现有架构整合方案

### 5.1 现有架构分析

```
当前架构:
┌─────────────────────────────────────────────┐
│              LangGraph Orchestrator          │
│  ┌──────────┐ ┌──────────┐ ┌──────────────┐ │
│  │ Safety   │ │Interaction│ │ Environment  │ │
│  │ Agent    │ │ Agent    │ │ Agent        │ │
│  │(眼动/头部)│ │(手势+语音)│ │(天气+时段)   │ │
│  └──────────┘ └──────────┘ └──────────────┘ │
└─────────────────────────────────────────────┘
```

### 5.2 推荐方案：替换 Interaction Agent 内部的 ReAct 循环

**不建议**将 ReAct 循环作为 Orchestrator 的统一入口，原因：

1. **Safety Agent 不应走 ReAct**：安全告警需要毫秒级响应，不能等 LLM 思考
2. **Environment Agent 是被动触发**：天气/时段变化不需要多步推理
3. **只有 Interaction Agent 需要多步推理**：语音指令的复杂场景才需要 Thought-Action-Observation

### 5.3 整合架构图

```
┌─────────────────────────────────────────────────────────────┐
│                    LangGraph Orchestrator                     │
│                                                               │
│  ┌──────────────┐     ┌──────────────────────────────────┐   │
│  │ Safety Agent │     │       Interaction Agent           │   │
│  │ (不变)       │     │  ┌────────────────────────────┐  │   │
│  │              │     │  │   ReAct Agent (新)         │  │   │
│  │ 眼动→告警    │     │  │                            │  │   │
│  │ 头部→分级    │     │  │  Thought → Action → Obs    │  │   │
│  │              │     │  │  ↓ 循环直到 Finish         │  │   │
│  └──────┬───────┘     │  │                            │  │   │
│         │             │  │  工具: weather/attractions/ │  │   │
│         │             │  │  knowledge/ac/music/speak/  │  │   │
│         │             │  │  alert                     │  │   │
│         │             │  └────────────────────────────┘  │   │
│         │             │                                   │   │
│         │             │  简单指令 → 直接路由（不走ReAct）  │   │
│         │             └──────────────────────────────────┘   │
│         │                                                     │
│  ┌──────┴──────────────────────────────────────────────┐     │
│  │              路由决策逻辑                              │     │
│  │                                                       │     │
│  │  安全事件 → Safety Agent (立即响应)                    │     │
│  │  简单指令 → 直接执行 (开空调/放音乐)                   │     │
│  │  复杂查询 → ReAct Agent (规划行程/多步推理)           │     │
│  │  环境变化 → Environment Agent (天气提醒)              │     │
│  └───────────────────────────────────────────────────────┘     │
│                                                               │
│  ┌──────────────┐                                             │
│  │ Environment  │                                             │
│  │ Agent        │                                             │
│  │ (不变)       │                                             │
│  └──────────────┘                                             │
└─────────────────────────────────────────────────────────────┘
```

### 5.4 Interaction Agent 内部改造

```python
# modules/ai/interaction_agent.py 改造要点

class InteractionAgent:
    def __init__(self, llm_client, ws_manager):
        self.llm_client = llm_client
        self.ws_manager = ws_manager
        self.react_agent = None  # 延迟初始化
        self.simple_router = SimpleIntentRouter()  # 简单指令路由器

    async def handle_voice_input(self, text: str, context: dict):
        """处理语音输入"""

        # 1. 简单指令快速路由（不走 LLM）
        simple_result = self.simple_router.match(text)
        if simple_result:
            await self._execute_simple(simple_result)
            return

        # 2. 复杂查询 → ReAct Agent
        await self._run_react_agent(text, context)

    async def _run_react_agent(self, text: str, context: dict):
        """运行 ReAct Agent（带 WebSocket 推送）"""
        from modules.ai.agents.react_agent import ReActAgent
        from modules.ai.agents.tool_registry import build_tool_registry
        from modules.ai.prompts import AGENT_SYSTEM_PROMPT

        # 创建工具注册表
        tools = build_tool_registry(self.llm_client)

        # 创建 Agent，绑定 WebSocket 推送回调
        async def push_to_frontend(step):
            """每步回调 → WebSocket 推送"""
            await self.ws_manager.broadcast_agent_step(step)

        self.react_agent = ReActAgent(
            system_prompt=AGENT_SYSTEM_PROMPT,
            llm_client=self.llm_client,
            tool_registry=tools,
            on_step=push_to_frontend,
        )

        # 执行
        result = await self.react_agent.run(text)

        # TTS 播报最终结果
        if result.success and result.final_text:
            await tools["speak"](text=result.final_text)

        return result


class SimpleIntentRouter:
    """简单指令路由器（不走 LLM，关键词匹配）"""

    PATTERNS = {
        "control_ac": [
            (r"打开空调", {"action": "on"}),
            (r"关闭空调", {"action": "off"}),
            (r"温度调到(\d+)", lambda m: {"action": "set_temp", "temperature": int(m.group(1))}),
            (r"太热了", {"action": "set_temp", "temperature": 22}),
            (r"太冷了", {"action": "set_temp", "temperature": 26}),
        ],
        "control_music": [
            (r"播放(.+)", lambda m: {"action": "play", "query": m.group(1)}),
            (r"下一首", {"action": "next"}),
            (r"暂停", {"action": "pause"}),
        ],
    }

    def match(self, text: str):
        """匹配简单指令，返回 (tool_name, params) 或 None"""
        import re
        for tool_name, patterns in self.PATTERNS.items():
            for pattern, params in patterns:
                m = re.search(pattern, text)
                if m:
                    if callable(params):
                        return (tool_name, params(m))
                    return (tool_name, params)
        return None
```

### 5.5 整合步骤清单

| 步骤 | 内容 | 影响范围 |
|------|------|----------|
| 1 | 新建 `modules/ai/agents/react_agent.py` | 新增文件 |
| 2 | 新建 `modules/ai/agents/tool_registry.py` | 新增文件 |
| 3 | 新建 `modules/ai/tools/search_attractions.py` | 新增文件 |
| 4 | 新建 `modules/ai/prompts.py`（存放 AGENT_SYSTEM_PROMPT） | 新增文件 |
| 5 | 改造 `interaction_agent.py`：内部集成 ReAct Agent | 修改文件 |
| 6 | 改造 `backend/app/ws/manager.py`：新增 agent 消息类型 | 修改文件 |
| 7 | 新建 `backend/app/ws/agent_ws.py` | 新增文件 |
| 8 | 改造 `backend/main.py`：注册 agent WebSocket 端点 | 修改文件 |
| 9 | 新建前端 `AgentStepCard.vue` + `AgentPanel.vue` | 新增文件 |
| 10 | 新建前端 `useAgentWebSocket.js` composable | 新增文件 |
| 11 | 改造 `VoiceInteractionBar.vue`：接入 Agent 面板 | 修改文件 |
| 12 | `.env` 添加 `AMAP_API_KEY` | 修改文件 |

### 5.6 数据流总览

```
用户语音 → Whisper 转写 → Interaction Agent
                              │
                    ┌─────────┴─────────┐
                    │                   │
              简单指令              复杂查询
                    │                   │
              SimpleRouter          ReAct Agent
                    │                   │
              直接执行            ┌──────┴──────┐
                    │           │  LLM 思考    │
                    │           │  ↓           │
                    │           │  调用工具     │
                    │           │  ↓           │
                    │           │  观察结果     │
                    │           │  ↓ 循环      │
                    │           │  Finish      │
                    │           └──────┬──────┘
                    │                  │
                    │          ┌───────┴───────┐
                    │          │  WebSocket    │
                    │          │  逐步推送     │
                    │          └───────┬───────┘
                    │                  │
                    ▼                  ▼
              执行动作           Vue 前端渲染
                    │           步骤卡片 + 自动滚动
                    ▼                  │
              TTS 播报 ◄───────────────┘
```
