"""小红书景点数据源 — 移植自 TripStar 的 xhs_service。

通过 Spider_XHS 原生签名引擎直连小红书 API，搜索真实游记笔记，
再用 LLM 提纯为结构化景点数据（名称/游览时长/预约提示/真实评价）。

设计原则:
- Cookie 未配置或签名引擎不可用时，静默降级到高德 POI 数据（不报错）
- 签名引擎采用懒加载，避免 execjs/Node 缺失时整个模块无法导入
- LLM 提纯复用 EdgeGuard 的 deepseek_client
"""
from __future__ import annotations

import json
import logging
import os
import re
from typing import Any

logger = logging.getLogger(__name__)


# ── JSON 容错解析（移植自 TripStar 6 层策略）──────────────────────────

def _sanitize_json_str(json_str: str) -> str:
    """清理大模型输出中常见的 JSON 格式污染。"""
    # 1. 移除 ```json ... ``` 包裹
    json_str = re.sub(r'^```(?:json)?\s*', '', json_str.strip())
    json_str = re.sub(r'```\s*$', '', json_str.strip())
    # 2. 移除 JS 风格注释
    json_str = re.sub(r'//[^\n]*', '', json_str)
    json_str = re.sub(r'/\*.*?\*/', '', json_str, flags=re.DOTALL)
    # 3. 移除控制字符
    json_str = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f]', '', json_str)
    # 4. 修复尾部逗号
    json_str = re.sub(r',\s*([\]\}])', r'\1', json_str)
    # 5. 修复中文引号和全角标点
    json_str = json_str.replace('\u201c', "'").replace('\u201d', "'")
    json_str = json_str.replace('\u2018', "'").replace('\u2019', "'")
    json_str = json_str.replace('\uff1a', ':').replace('\uff0c', ',')
    # 6. 修复算术表达式（如 "total": 30+54+120=204 → "total": 204）
    def _fix_arith(m):
        expr = m.group(1).strip()
        if '=' in expr:
            return m.group(0).replace(m.group(1), expr.split('=')[-1].strip())
        try:
            result = eval(expr, {"__builtins__": {}}, {})
            return m.group(0).replace(m.group(1), str(result))
        except Exception:
            return m.group(0)
    json_str = re.sub(
        r':\s*(\d+(?:\s*[+\-*/]\s*\d+)+(?:\s*=\s*\d+)?)',
        _fix_arith, json_str,
    )
    return json_str


def _fix_unescaped_quotes(json_str: str) -> str:
    """修复 JSON 字符串值内部未转义的双引号。"""
    result = []
    i = 0
    in_string = False
    escape_next = False
    while i < len(json_str):
        ch = json_str[i]
        if escape_next:
            result.append(ch)
            escape_next = False
            i += 1
            continue
        if ch == '\\' and in_string:
            escape_next = True
            result.append(ch)
            i += 1
            continue
        if ch == '"':
            if not in_string:
                in_string = True
                result.append(ch)
            else:
                rest = json_str[i + 1:].lstrip()
                if rest and rest[0] in (',', '}', ']', ':'):
                    in_string = False
                    result.append(ch)
                elif not rest:
                    in_string = False
                    result.append(ch)
                else:
                    result.append("'")
        else:
            result.append(ch)
        i += 1
    return ''.join(result)


def _repair_truncated_json(json_str: str) -> str:
    """修复被 max_tokens 截断的不完整 JSON。"""
    s = json_str.rstrip()
    if not s:
        return s
    # Step 1: 关闭未终止的字符串
    in_str = False
    escape = False
    for ch in s:
        if escape:
            escape = False
            continue
        if ch == '\\':
            escape = True
            continue
        if ch == '"':
            in_str = not in_str
    if in_str:
        s = s.rstrip('\\') + '"'
    # Step 2: 移除尾部不完整碎片
    for _ in range(10):
        stripped = s.rstrip()
        if not stripped:
            break
        last = stripped[-1]
        if last in ('}', ']', '"', '0', '1', '2', '3', '4', '5', '6', '7', '8', '9',
                    'e', 'l', 's'):
            break
        s = stripped[:-1]
    s = re.sub(r',\s*$', '', s)
    # Step 3: 补齐缺失的闭合括号
    stack = []
    in_str2 = False
    esc2 = False
    for ch in s:
        if esc2:
            esc2 = False
            continue
        if ch == '\\' and in_str2:
            esc2 = True
            continue
        if ch == '"':
            in_str2 = not in_str2
            continue
        if in_str2:
            continue
        if ch in ('{', '['):
            stack.append(ch)
        elif ch == '}' and stack and stack[-1] == '{':
            stack.pop()
        elif ch == ']' and stack and stack[-1] == '[':
            stack.pop()
    closing = [']' if c == '[' else '}' for c in reversed(stack)]
    if closing:
        s += '\n' + ''.join(closing)
    return s


def _robust_json_parse(content: str) -> Any:
    """6 层容错 JSON 解析，返回解析结果或 None。

    层级:
    1. 基础清理（去 ```json 包裹、注释、控制字符、尾部逗号、中文标点、算术表达式）
    2. 修复未转义引号
    3. 截断修复
    4. 截断 + 引号组合修复
    5. 暴力正则提取
    6. LLM 自修复（最后手段）
    """
    # 提取 JSON 片段
    if "```json" in content:
        start = content.find("```json") + 7
        end = content.find("```", start)
        json_str = content[start:end].strip() if end > start else content[start:].strip()
    elif "```" in content:
        start = content.find("```") + 3
        end = content.find("```", start)
        json_str = content[start:end].strip() if end > start else content[start:].strip()
    elif "[" in content or "{" in content:
        # 尝试提取数组或对象
        arr_match = re.search(r'\[.*\]', content, re.DOTALL)
        obj_match = re.search(r'\{.*\}', content, re.DOTALL)
        if arr_match:
            json_str = arr_match.group()
        elif obj_match:
            json_str = obj_match.group()
        else:
            json_str = content.strip()
    else:
        json_str = content.strip()

    # 第 1 层: 基础清理
    json_str = _sanitize_json_str(json_str)
    parse_attempts = [("基础清理", json_str)]

    # 第 2 层: 修复未转义引号
    fixed_quotes = _fix_unescaped_quotes(json_str)
    parse_attempts.append(("修复未转义引号", fixed_quotes))

    # 第 3 层: 截断修复
    repaired = _repair_truncated_json(json_str)
    if repaired != json_str:
        parse_attempts.append(("截断修复", repaired))
        # 第 4 层: 截断 + 引号组合
        repaired_fixed = _fix_unescaped_quotes(repaired)
        if repaired_fixed != repaired:
            parse_attempts.append(("截断+引号修复", repaired_fixed))

    # 第 5 层: 暴力正则提取
    match = re.search(r'[\[{][\s\S]*[}\]]', content)
    if match:
        brutal = _sanitize_json_str(match.group())
        brutal = _fix_unescaped_quotes(brutal)
        parse_attempts.append(("正则提取", brutal))
        brutal_repaired = _repair_truncated_json(brutal)
        if brutal_repaired != brutal:
            parse_attempts.append(("正则+截断修复", brutal_repaired))

    # 依次尝试
    for attempt_name, candidate in parse_attempts:
        try:
            return json.loads(candidate)
        except (json.JSONDecodeError, Exception):
            continue

    # 第 6 层: LLM 自修复（最后手段）
    try:
        from modules.ai.model_factory import get_model_for_agent
        client = get_model_for_agent("recommend")
        if client.is_available:
            tail = json_str[-1500:] if len(json_str) > 1500 else json_str
            head = json_str[:500] if len(json_str) > 500 else json_str
            repair_prompt = (
                "以下是一段被截断或格式有误的 JSON，请修复它使其成为合法的 JSON。\n"
                "只输出修复后的完整 JSON，不要输出任何解释文字。\n\n"
                f"开头部分:\n{head}\n\n...(中间省略)...\n\n尾部:\n{tail}"
            )
            resp = client.client.chat.completions.create(
                model=client.chat_model,
                messages=[{"role": "user", "content": repair_prompt}],
                temperature=0.0,
                max_tokens=1500,
            )
            repaired_content = resp.choices[0].message.content or ""
            repaired_content = _sanitize_json_str(repaired_content)
            return json.loads(repaired_content)
    except Exception as e:
        logger.debug("LLM JSON 自修复失败: %s", e)

    return None


# ── Cookie 工具 ──────────────────────────────────────────────────────

def _normalize_xhs_cookie(cookie: str) -> str:
    """兼容 Cookie 请求头字符串和浏览器导出的 JSON Cookie 列表。"""
    normalized = cookie.strip()
    if not normalized:
        return normalized
    if len(normalized) >= 2 and normalized[0] == normalized[-1] and normalized[0] in {"'", '"'}:
        normalized = normalized[1:-1].strip()
    cookie_items = None
    if normalized.startswith("[") and normalized.endswith("]"):
        try:
            cookie_items = json.loads(normalized)
        except json.JSONDecodeError:
            cookie_items = None
    elif normalized.startswith("{") and '"name"' in normalized and '"value"' in normalized:
        try:
            cookie_items = json.loads(f"[{normalized}]")
        except json.JSONDecodeError:
            cookie_items = None
    if isinstance(cookie_items, list):
        pairs = []
        for item in cookie_items:
            if not isinstance(item, dict):
                continue
            name = str(item.get("name", "")).strip()
            value = str(item.get("value", "")).strip()
            if name:
                pairs.append(f"{name}={value}")
        if pairs:
            return "; ".join(pairs)
    return normalized


def _get_xhs_cookie() -> str:
    """动态读取小红书 Cookie。"""
    return os.getenv("XHS_COOKIE", "")


# ── 签名引擎懒加载 ────────────────────────────────────────────────────

_sign_engine = None
_sign_engine_checked = False


def _get_sign_engine():
    """懒加载签名引擎，失败时返回 None（不阻塞主流程）。"""
    global _sign_engine, _sign_engine_checked
    if _sign_engine_checked:
        return _sign_engine
    _sign_engine_checked = True
    try:
        from .xhs_sign.sign_util import (
            generate_request_params,
            generate_x_b3_traceid,
            trans_cookies,
        )
        _sign_engine = {
            "generate_request_params": generate_request_params,
            "generate_x_b3_traceid": generate_x_b3_traceid,
            "trans_cookies": trans_cookies,
        }
        logger.info("XHS 签名引擎加载成功")
    except Exception as e:
        logger.info("XHS 签名引擎不可用（execjs/Node 缺失），将使用降级方案: %s", e)
        _sign_engine = None
    return _sign_engine


# ── 原生小红书 API 客户端 ────────────────────────────────────────────

class XHSCookieExpiredError(Exception):
    """小红书 Cookie 过期致命异常。"""
    pass


class XhsNativeClient:
    """使用 Spider_XHS 签名引擎直连小红书 API 的原生客户端。"""

    BASE_URL = "https://edith.xiaohongshu.com"

    def __init__(self, cookies_str: str):
        self.cookies_str = cookies_str

    def search_notes(self, keyword: str, page: int = 1, sort_type: int = 0,
                     page_size: int = 20) -> dict:
        sort_map = {0: "general", 1: "time_descending", 2: "popularity_descending"}
        sort = sort_map.get(sort_type, "general")
        api = "/api/sns/web/v1/search/notes"
        data = {
            "keyword": keyword, "page": page, "page_size": page_size,
            "search_id": _get_sign_engine()["generate_x_b3_traceid"](21),
            "sort": "general", "note_type": 0, "ext_flags": [],
            "filters": [
                {"tags": [sort], "type": "sort_type"},
                {"tags": ["不限"], "type": "filter_note_type"},
                {"tags": ["不限"], "type": "filter_note_time"},
                {"tags": ["不限"], "type": "filter_note_range"},
                {"tags": ["不限"], "type": "filter_pos_distance"},
            ],
            "geo": "", "image_formats": ["jpg", "webp", "avif"],
        }
        headers, cookies, serialized_data = _get_sign_engine()["generate_request_params"](
            self.cookies_str, api, data, "POST"
        )
        import requests
        response = requests.post(
            self.BASE_URL + api,
            headers=headers,
            data=serialized_data.encode("utf-8"),
            cookies=cookies,
            timeout=15,
        )
        res_json = response.json()
        if not res_json.get("success"):
            code = res_json.get("code", "")
            msg = res_json.get("msg", "")
            if code == 300011 or "异常" in msg:
                raise XHSCookieExpiredError(f"小红书 Cookie 被风控拦截 (code={code}): {msg}")
            raise Exception(f"小红书搜索失败 (code={code}): {msg}")
        return res_json

    def get_note_detail(self, note_id: str, xsec_token: str = "",
                        xsec_source: str = "pc_search") -> dict:
        api = "/api/sns/web/v1/feed"
        data = {
            "source_note_id": note_id,
            "image_formats": ["jpg", "webp", "avif"],
            "extra": {"need_body_topic": "1"},
            "xsec_source": xsec_source,
            "xsec_token": xsec_token,
        }
        headers, cookies, serialized_data = _get_sign_engine()["generate_request_params"](
            self.cookies_str, api, data, "POST"
        )
        import requests
        response = requests.post(
            self.BASE_URL + api,
            headers=headers,
            data=serialized_data,
            cookies=cookies,
            timeout=15,
        )
        res_json = response.json()
        if not res_json.get("success"):
            code = res_json.get("code", "")
            msg = res_json.get("msg", "")
            if code == 300011 or "异常" in msg:
                raise XHSCookieExpiredError(f"小红书 Cookie 被风控拦截 (code={code}): {msg}")
        return res_json


# ── SSR 降级（无需签名） ──────────────────────────────────────────────

def _get_note_detail_ssr(note_id: str) -> dict:
    """通过网页抓取 SSR 状态提取笔记详情（签名 API 不可用时的降级方案）。"""
    import httpx
    url = f"https://www.xiaohongshu.com/explore/{note_id}"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    }
    try:
        resp = httpx.get(url, headers=headers, timeout=8)
        match = re.search(r'window\.__INITIAL_STATE__=({.*?})</script>', resp.text)
        if match:
            state_json = json.loads(match.group(1).replace('undefined', 'null'))
            return state_json.get("note", {}).get("noteDetailMap", {}).get(note_id, {}).get("note", {})
    except Exception as e:
        logger.debug("SSR 详情提取失败 %s: %s", note_id, e)
    return {}


# ── 客户端工厂 ────────────────────────────────────────────────────────

def get_xhs_client() -> XhsNativeClient | None:
    """初始化小红书客户端，未配置 Cookie 或签名引擎不可用时返回 None。"""
    cookie = _get_xhs_cookie()
    if not cookie:
        return None
    if not _get_sign_engine():
        return None
    cookie_str = _normalize_xhs_cookie(cookie)
    return XhsNativeClient(cookie_str)


# ── LLM 提纯 ─────────────────────────────────────────────────────────

def _llm_extract_attractions(combined_text: str, city: str) -> list[dict]:
    """使用 DeepSeek 从游记文本中提纯结构化景点数据。

    返回 list[dict]，每个 dict 包含:
    name, description, visit_duration, reservation_required, reservation_tips
    """
    try:
        from modules.ai.model_factory import get_model_for_agent
        client = get_model_for_agent("recommend")
        if not client.is_available:
            return []
    except Exception:
        return []

    extract_prompt = f"""请从以下真实的小红书打卡游记中，提纯出真实存在的游玩景点。
要求返回严格的 JSON 数组格式，切勿返回除了 JSON 以外的任何冗余文字。
数组中每个对象必须包含以下字段:
"name": 景点名称
"description": 小红书用户的真实评价或避坑指南（一句话）
"visit_duration": 游玩时长（数字，分钟）
"reservation_required": 是否需要提前预约（布尔值 true/false）
"reservation_tips": 预约相关提示（字符串，无则填空字符串）
"category": 景点类型（如：历史古迹/自然风光/博物馆/主题乐园/宗教文化/公园）

游记内容如下:
{combined_text}

JSON 返回示例:
[
  {{"name": "西湖", "description": "免费开放，建议清晨去人少。", "visit_duration": 180, "reservation_required": false, "reservation_tips": "", "category": "自然风光"}},
  {{"name": "灵隐寺", "description": "需要买飞来峰门票才能进。", "visit_duration": 120, "reservation_required": false, "reservation_tips": "", "category": "宗教文化"}}
]
"""
    try:
        response = client.client.chat.completions.create(
            model=client.chat_model,
            messages=[{"role": "user", "content": extract_prompt}],
            temperature=0.1,
            max_tokens=4000,
        )
        content = response.choices[0].message.content or ""
        # 使用 6 层容错 JSON 解析（移植自 TripStar）
        result = _robust_json_parse(content)
        if isinstance(result, list):
            logger.info("XHS LLM 提纯成功: 提取到 %d 个景点", len(result))
            return result
        logger.warning("LLM 提纯结果非数组格式: %s", type(result).__name__ if result else "None")
        return []
    except Exception as e:
        logger.warning("LLM 提纯小红书数据失败: %s", e)
        return []


# ── 高德地理编码 ─────────────────────────────────────────────────────

def _geocode_with_amap(name: str, city: str) -> str:
    """用高德 POI 搜索获取经纬度，返回 "经度,纬度" 格式字符串。"""
    amap_key = os.getenv("AMAP_API_KEY", "")
    if not amap_key:
        return ""
    import httpx
    try:
        resp = httpx.get(
            "https://restapi.amap.com/v3/place/text",
            params={
                "keywords": name, "city": city, "citylimit": "true",
                "offset": 1, "page": 1, "key": amap_key,
            },
            timeout=5,
        )
        data = resp.json()
        if data.get("status") == "1" and data.get("pois"):
            location = data["pois"][0].get("location", "")
            if location:
                return location
    except Exception as e:
        logger.debug("高德地理编码失败 %s: %s", name, e)
    return ""


# ── 核心搜索函数 ──────────────────────────────────────────────────────

def search_xhs_attractions(
    city: str,
    keywords: str = "",
    preference: str | None = None,
    max_notes: int = 4,
) -> list[dict]:
    """搜索小红书笔记并用 LLM 提纯为结构化景点数据。

    Args:
        city: 城市名称
        keywords: 搜索关键词（如"历史古迹"）
        preference: 偏好类型
        max_notes: 最多搜索的笔记数

    Returns:
        list[dict]: 景点列表，格式与高德 search_attractions 兼容:
        [{name, address, location, visit_duration, description, category,
          ticket_price, rating, photo_url, id, source: "xhs", route_city}]
        未配置 Cookie 或搜索失败时返回空列表（不报错）。
    """
    client = get_xhs_client()
    if client is None:
        logger.info("XHS 未配置 Cookie 或签名引擎不可用，跳过小红书数据源")
        return []

    query = f"{city} {keywords or preference or ''} 旅游 景点攻略".strip()
    logger.info("XHS 搜索: query=%s", query)

    try:
        res_json = client.search_notes(keyword=query)
        items = res_json.get("data", {}).get("items", [])[:max_notes]
    except XHSCookieExpiredError as e:
        logger.warning("XHS Cookie 已失效: %s", e)
        return []
    except Exception as e:
        logger.warning("XHS 搜索失败: %s", e)
        return []

    if not items:
        logger.info("XHS 未搜索到相关笔记: query=%s", query)
        return []

    # 收集笔记文本
    combined_text = ""
    for i, note in enumerate(items):
        if note.get("model_type") != "note":
            continue
        note_card = note.get("note_card", {})
        title = note_card.get("display_title", "")
        desc = ""
        note_id = note.get("id", "")
        xsec_token = note.get("xsec_token", "")
        if note_id:
            try:
                detail_res = client.get_note_detail(note_id, xsec_token)
                detail_items = detail_res.get("data", {}).get("items", [])
                if detail_items:
                    desc = detail_items[0].get("note_card", {}).get("desc", "")
            except Exception:
                desc = _get_note_detail_ssr(note_id).get("desc", "")
        combined_text += f"\n笔记{i + 1}:\n标题: {title}\n正文: {desc}\n"

    if not combined_text:
        return []

    # LLM 提纯
    extracted = _llm_extract_attractions(combined_text, city)
    if not extracted:
        return []

    # 地理编码 + 格式转换
    results: list[dict] = []
    for item in extracted:
        name = item.get("name", "")
        if not name:
            continue
        location = _geocode_with_amap(name, city)
        results.append({
            "name": name,
            "address": city,
            "location": location,
            "visit_duration": int(item.get("visit_duration", 120) or 120),
            "description": item.get("description", ""),
            "category": item.get("category", "景点"),
            "ticket_price": 0,
            "rating": None,
            "photo_url": "",
            "id": f"xhs_{len(results)}",
            "source": "xhs",
            "reservation_required": item.get("reservation_required", False),
            "reservation_tips": item.get("reservation_tips", ""),
            "route_city": city,
        })

    logger.info("XHS 提纯完成: city=%s, %d 个景点", city, len(results))
    return results


# ── LLM 增强（XHS 不可用时的 fallback）─────────────────────────────

def llm_enhance_attractions(
    amap_items: list[dict],
    city: str,
    preference: str | None = None,
) -> list[dict]:
    """使用 LLM 为高德 POI 数据生成真实的游览描述和时长。

    作为小红书数据源不可用时的 fallback，为每个景点补充:
    - description: 真实的游览评价/避坑提示
    - visit_duration: 基于景点特征的推荐游览时长（分钟）
    - reservation_required: 是否需要提前预约
    - reservation_tips: 预约提示

    批量处理所有景点，单次 LLM 调用，原地修改 amap_items 并返回。

    Args:
        amap_items: 高德 POI 景点列表（会被原地修改）
        city: 城市名称
        preference: 用户偏好类型（可选）

    Returns:
        增强后的 amap_items（同列表引用，原地修改）
    """
    if not amap_items:
        return amap_items

    try:
        from modules.ai.model_factory import get_model_for_agent
        client = get_model_for_agent("recommend")
        if not client.is_available:
            logger.info("LLM 增强跳过: 模型不可用")
            return amap_items
    except Exception:
        return amap_items

    # 构建精简的景点摘要（只发送 LLM 需要的关键字段，节省 token）
    summaries = []
    for i, item in enumerate(amap_items):
        summaries.append({
            "index": i,
            "name": item.get("name", ""),
            "category": item.get("category", ""),
            "type": item.get("type", ""),
            "address": item.get("address", ""),
        })

    pref_hint = f"用户偏好: {preference}" if preference else "无特别偏好"

    enhance_prompt = f"""请为以下{city}的景点生成真实的游览建议。

{pref_hint}

景点列表:
{json.dumps(summaries, ensure_ascii=False, indent=2)}

请为每个景点返回以下信息，格式为 JSON 数组:
[
  {{
    "index": 0,
    "description": "一句话真实游览评价或避坑提示",
    "visit_duration": 120,
    "reservation_required": false,
    "reservation_tips": ""
  }}
]

要求:
1. description 必须是基于该景点真实特色的实用建议（如最佳游览时间、注意事项、特色看点），不要泛泛而谈
2. visit_duration 是推荐游览时长（分钟），根据景点类型和规模合理估算
3. reservation_required 标注是否需要提前预约购票
4. 只返回 JSON 数组，不要输出任何其他文字

JSON 返回示例:
[
  {{"index": 0, "description": "建议清晨前往人少景美，西湖十景集中在此区域。", "visit_duration": 180, "reservation_required": false, "reservation_tips": ""}},
  {{"index": 1, "description": "需提前在公众号预约，每周一闭馆。", "visit_duration": 150, "reservation_required": true, "reservation_tips": "提前3天在官方公众号预约"}}
]"""

    try:
        response = client.client.chat.completions.create(
            model=client.chat_model,
            messages=[{"role": "user", "content": enhance_prompt}],
            temperature=0.3,
            max_tokens=4000,
        )
        content = response.choices[0].message.content or ""
        # 快速路径：先尝试直接解析，失败再走 6 层容错解析
        result = None
        try:
            result = json.loads(content)
        except (json.JSONDecodeError, Exception):
            result = _robust_json_parse(content)

        if not isinstance(result, list):
            logger.warning("LLM 增强结果非数组格式: %s", type(result).__name__ if result else "None")
            return amap_items

        # 将增强结果按 index 合并回原始数据（原地修改）
        enhanced_map: dict[int, dict] = {}
        for item in result:
            if isinstance(item, dict) and "index" in item:
                try:
                    enhanced_map[int(item["index"])] = item
                except (ValueError, TypeError):
                    continue

        enhanced_count = 0
        for i, amap_item in enumerate(amap_items):
            enhance = enhanced_map.get(i)
            if not enhance:
                continue
            if enhance.get("description"):
                amap_item["description"] = enhance["description"]
            if enhance.get("visit_duration"):
                try:
                    amap_item["visit_duration"] = int(enhance["visit_duration"])
                except (ValueError, TypeError):
                    pass
            amap_item["reservation_required"] = enhance.get("reservation_required", False)
            amap_item["reservation_tips"] = enhance.get("reservation_tips", "")
            amap_item["source"] = "amap+llm"
            enhanced_count += 1

        logger.info("LLM 增强完成: city=%s, %d/%d 个景点已增强", city, enhanced_count, len(amap_items))
        return amap_items

    except Exception as e:
        logger.warning("LLM 增强景点数据失败: %s", e)
        return amap_items


def is_xhs_available() -> bool:
    """检查小红书数据源是否可用（Cookie 已配置 + 签名引擎可用）。"""
    return _get_xhs_cookie() != "" and _get_sign_engine() is not None
