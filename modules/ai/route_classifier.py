"""
Route Classifier — 自动路由分类器
根据用户输入文本和驾驶状态决定最优执行路径。

分类规则（优先级从高到低）：
1. 危险驾驶状态 → multi（走 SafetyAgent VETO 短路）
2. 状态查询类 → react（防止误判为播放指令）
3. 知识查询类 → react（需要 LLM 推理）
4. 包含多意图连接词 → multi（多Agent编排）
5. 命中快速指令关键词 → quick（快速指令，跳过 LLM）
6. 默认 → react（ReAct 推理）
"""
import re
import logging

logger = logging.getLogger(__name__)

# 多意图连接词：出现这些词说明用户一句话里有多个需求
MULTI_INTENT_CONJUNCTIONS = [
    "然后", "顺便", "还有", "同时", "并且", "接着", "再", "之后",
    "另外", "此外", "并", "还有",
]

# 快速指令正则（与 local_decision_engine._handle_speech 的 command_patterns 保持一致，并补充短形式）
QUICK_PATTERNS = [
    r"(打开|开启|启动|开一下|开)空调|空调.*(打开|开启|启动|开)",
    r"(关闭|关掉|关一下|关)空调|空调.*(关闭|关掉|关)",
    r"(太热|好热|有点热)",
    r"(太冷|好冷|有点冷)",
    r"(调高|升高|提高).*温度|温度.*(调高|升高|提高)",
    r"(调低|降低|下降).*温度|温度.*(调低|降低|下降)",
    r"(播放|放一下|来一首|听一下|放).*(音乐|歌|歌曲|周杰伦|王菲|林俊杰|陈奕迅|邓紫棋|薛之谦)",
    r"^(播放|放一下|来一首|听一下|放)(音乐|歌)?$",
    r"(暂停|停止|停掉|关掉).*(音乐|播放|歌曲)|^(暂停播放|停止播放|关音乐|停音乐)$",
    r"^(下一首|切歌)$|播放下一首",
    r"^(上一首)$|播放上一首",
    r"(音量|声音).*(调大|加大|大一点|提高)",
    r"(音量|声音).*(调小|减小|小一点|降低)",
    r"(打开|开一下|开).*车窗",
    r"(关闭|关掉|关一下|关).*车窗",
    r"(打开|开一下|开).*灯",
    r"(关闭|关掉|关一下|关).*灯",
]

# 知识查询类关键词（需要 LLM 推理，不走快速路径）
SEMANTIC_QUERY_HINTS = [
    "什么意思", "怎么办", "故障", "为什么", "怎么回事",
    "解释", "区别", "原理", "如何处理",
]

# 状态查询类关键词（用户问"当前是什么状态"，不是操作指令）
# 前缀格式: "在/正在/现在 + 播放/放/播/听 + 什么/哪首/啥 + 歌/音乐/曲子"
STATE_QUERY_PATTERNS = [
    r"(现在|当前|正在|在).*(播放|放|播|听).*(什么|啥|哪|什么歌|哪首)",
    r"(什么|啥|哪).*(歌|音乐|曲子).*(在|正在).*(播放|放|播)",
    r"(播放|放|播)的?(什么|啥|哪首)(歌|音乐|曲子)?$",
    r"(现在|当前).*(歌|音乐|曲子|播放)",
    r"^(什么|啥|哪首)(歌|音乐|曲子)",
    r"(在播|在放|在听)(什么|啥|哪首)?",
]


def is_dangerous_driver_state(driver_state: dict) -> bool:
    """检测驾驶员是否处于危险状态（基于真实传感器字段）。

    摄像头模块产生的 severity 值为 'mild'/'moderate'/'severe'（非 'dangerous'），
    fatigue_level 为 'normal'/'warning'/'danger'，fatigue_score 为 0-100 数值。
    此函数统一判断这些字段，供 route_classifier 和 main.py 安全前置门共用。
    """
    ds = driver_state or {}

    # severity: 摄像头产生 'severe'，SafetyAgent 产生 'dangerous'
    severity = ds.get("severity", "")
    if severity in ("dangerous", "severe"):
        return True

    # risk: 部分前端可能发送
    if ds.get("risk") == "high":
        return True

    # risk_level: SafetyAgent 输出
    if ds.get("risk_level") == "dangerous":
        return True

    # fatigue_level: 摄像头疲劳等级
    if ds.get("fatigue_level") == "danger":
        return True

    # fatigue_score: 数值化疲劳分数 (>=80 为危险)
    try:
        if float(ds.get("fatigue_score", 0)) >= 80:
            return True
    except (TypeError, ValueError):
        pass

    # perclos: 闭眼占比 (>=0.5 为危险)
    try:
        if float(ds.get("perclos", 0)) >= 0.5:
            return True
    except (TypeError, ValueError):
        pass

    return False


def classify_route(text: str, driver_state: dict = None) -> str:
    """
    根据用户输入和驾驶状态自动分类路由。

    Args:
        text: 用户输入文本
        driver_state: 驾驶员状态 dict，含 severity/fatigue_score/perclos 等传感器字段

    Returns:
        'quick' | 'react' | 'multi' | 'readonly'
    """
    if not text or not text.strip():
        return "react"

    ds = driver_state or {}
    normalized = re.sub(r"\s+", "", text.strip())

    # Rule 1: 危险驾驶状态 → 强制走多Agent编排（SafetyAgent VETO 短路）
    # 摄像头 severity='severe'、fatigue_score>=80、fatigue_level='danger' 等均判定为危险
    if is_dangerous_driver_state(ds):
        logger.info(
            "Route classified as 'multi' (dangerous driver state: "
            "severity=%s, fatigue_score=%s, fatigue_level=%s, perclos=%s)",
            ds.get("severity"), ds.get("fatigue_score"),
            ds.get("fatigue_level"), ds.get("perclos"),
        )
        return "multi"

    # Rule 2: 知识查询类 → 走 ReAct（需要 LLM 推理）
    for hint in SEMANTIC_QUERY_HINTS:
        if hint in normalized:
            return "react"

    # Rule 2.5: 状态查询类（"在播什么歌"）→ 走 ReAct，防止被 Rule 4 误判为播放指令
    for pattern in STATE_QUERY_PATTERNS:
        if re.search(pattern, normalized):
            logger.info("Route classified as 'react' (state query: %s)", pattern[:30])
            return "react"

    # Rule 3: 包含多意图连接词 → 多Agent编排（优先于快速匹配，因为多意图需要分解）
    for conj in MULTI_INTENT_CONJUNCTIONS:
        if conj in normalized:
            logger.info("Route classified as 'multi' (conjunction: %s)", conj)
            return "multi"

    # Rule 4: 命中快速指令关键词 → 快速路径
    for pattern in QUICK_PATTERNS:
        if re.search(pattern, normalized):
            logger.info("Route classified as 'quick' (matched keyword: %s)", pattern[:30])
            return "quick"

    # Rule 5: 默认 ReAct 推理
    return "react"
