"""
EdgeGuard Agent Tools — OpenAI Function Calling 格式
=====================================================

为 LLM 提供 8 个可调用的工具，每个工具包含：
  - Python 函数实现（实际执行逻辑）
  - JSON Schema（供 LLM tools 参数使用）

工具列表：
  1. speak           → TTS 语音播报
  2. control_ac      → 空调控制
  3. control_music   → 音乐控制
  4. search_knowledge → 车辆知识库检索
  5. get_weather     → 天气查询
  6. alert_driver   → 安全告警
  7. ask_clarification → 追问澄清
  8. (预留扩展)
"""

import logging
import os
from typing import Optional

import httpx
from dotenv import load_dotenv

# 加载 .env 文件（项目根目录，tools.py 在 modules/ai/ 下需上溯 3 级）
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), '.env'))

logger = logging.getLogger(__name__)

_BACKEND_BASE = "http://localhost:8000"
_TIMEOUT = 10

# 高德地图 API Key（用于 search_attractions 工具）
_AMAP_POI_URL = "https://restapi.amap.com/v3/place/text"


def _get_amap_key() -> str:
    """动态读取高德 API Key（确保 .env 已加载）"""
    return os.getenv("AMAP_API_KEY", "")


# ═══════════════════════════════════════════════════════════
#  JSON Schema — 供 LLM 的 tools 参数使用
# ═══════════════════════════════════════════════════════════

TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "speak",
            "description": "通过TTS语音播报消息给驾驶员",
            "parameters": {
                "type": "object",
                "properties": {
                    "text": {"type": "string", "description": "要播报的文本"}
                },
                "required": ["text"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "control_ac",
            "description": "控制车载空调。支持开关、温度调节、模式切换、风速调节",
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {
                        "type": "string",
                        "enum": ["TurnOnAC", "TurnOffAC", "temp_up", "temp_down", "set"],
                        "description": "控制命令"
                    },
                    "temperature": {"type": "integer", "description": "设定温度(16-30)，仅set命令时使用"},
                    "mode": {
                        "type": "string",
                        "enum": ["cool", "heat", "auto", "fan"],
                        "description": "空调模式，仅set命令时使用"
                    },
                    "fanSpeed": {"type": "integer", "description": "风速(1-5)，仅set命令时使用"}
                },
                "required": ["command"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "control_music",
            "description": "控制车载音乐播放。支持搜索歌曲、播放、暂停、切歌、音量调节",
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {
                        "type": "string",
                        "enum": ["search", "play", "pause", "next", "prev", "volume"],
                        "description": "控制命令"
                    },
                    "keyword": {"type": "string", "description": "搜索关键词，仅search命令时使用"},
                    "song_id": {"type": "integer", "description": "歌曲ID，仅play命令时使用"},
                    "volume": {"type": "integer", "description": "音量(0-100)，仅volume命令时使用"}
                },
                "required": ["command"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "search_knowledge",
            "description": "检索车辆故障知识库，回答关于车辆故障、保养、驾驶安全等问题",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "搜索问题"}
                },
                "required": ["query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_weather",
            "description": "查询当前天气信息，包括温度、湿度、风力等",
            "parameters": {
                "type": "object",
                "properties": {
                    "city": {"type": "string", "description": "城市名称，可选"}
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "alert_driver",
            "description": "向驾驶员发出安全告警（疲劳、分心、视线偏离等）",
            "parameters": {
                "type": "object",
                "properties": {
                    "alert_type": {
                        "type": "string",
                        "enum": ["fatigue", "distraction", "gaze", "crowd", "absence"],
                        "description": "告警类型"
                    },
                    "severity": {
                        "type": "string",
                        "enum": ["mild", "moderate", "severe"],
                        "description": "告警级别"
                    },
                    "message": {"type": "string", "description": "告警消息文本"}
                },
                "required": ["alert_type", "severity", "message"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "ask_clarification",
            "description": "当意图不明确时向驾驶员追问，获取更多信息",
            "parameters": {
                "type": "object",
                "properties": {
                    "question": {"type": "string", "description": "追问的问题文本"}
                },
                "required": ["question"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "search_attractions",
            "description": "搜索城市热门景点，根据天气和偏好智能推荐。雨天优先推荐室内景点，高温天标注避暑提示",
            "parameters": {
                "type": "object",
                "properties": {
                    "city": {"type": "string", "description": "城市名称，如天津、北京"},
                    "weather": {"type": "string", "description": "当前天气描述，如晴、小雨、多云，用于智能过滤"},
                    "count": {"type": "integer", "description": "返回景点数量，默认5", "default": 5},
                    "preference": {
                        "type": "string",
                        "enum": ["历史文化", "亲子", "户外", "美食", "拍照打卡"],
                        "description": "偏好类型，可选"
                    }
                },
                "required": ["city"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "start_navigation",
            "description": "启动导航到指定目的地。返回路线距离、预计时间和途经道路信息。",
            "parameters": {
                "type": "object",
                "properties": {
                    "destination": {"type": "string", "description": "目的地名称，如天安门广场、故宫博物院"},
                    "city": {"type": "string", "description": "目的地所在城市，如北京", "default": "当前位置"}
                },
                "required": ["destination"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "plan_trip",
            "description": "为用户生成结构化行程规划。自动搜索景点、查询天气，生成包含游览、用餐、交通的时间线。结果会展示在专门的行程面板中。",
            "parameters": {
                "type": "object",
                "properties": {
                    "city": {"type": "string", "description": "目的地城市，如天津、北京"},
                    "days": {"type": "integer", "description": "旅行天数，默认1天", "default": 1},
                    "preference": {
                        "type": "string",
                        "enum": ["历史文化", "亲子", "户外", "美食", "拍照打卡"],
                        "description": "偏好类型，可选"
                    }
                },
                "required": ["city"]
            }
        }
    },
]


# ═══════════════════════════════════════════════════════════
#  工具函数实现 — 每个 Schema 对应一个 Python 函数
# ═══════════════════════════════════════════════════════════

def speak(text: str) -> dict:
    """
    通过 TTS 语音播报消息给驾驶员。

    Args:
        text: 要播报的文本

    Returns:
        {"success": bool, "audio_bytes": int}
    """
    try:
        resp = httpx.post(
            f"{_BACKEND_BASE}/api/tts",
            params={"text": text},
            timeout=_TIMEOUT,
        )
        return {"success": True, "audio_bytes": len(resp.content)}
    except Exception as e:
        logger.error(f"speak 工具调用失败: {e}")
        return {"success": False, "error": str(e)}


def control_ac(command: str, **kwargs) -> dict:
    """
    控制车载空调。支持开关、温度调节、模式切换、风速调节。

    Args:
        command: 控制命令 (TurnOnAC / TurnOffAC / temp_up / temp_down / set)
        **kwargs: temperature, mode, fanSpeed 等，仅 set 命令时使用

    Returns:
        {"success": bool, "state": dict}
    """
    try:
        body = {"command": command, **kwargs}
        resp = httpx.post(
            f"{_BACKEND_BASE}/api/ac/command",
            json=body,
            timeout=_TIMEOUT,
        )
        data = resp.json()
        return {"success": data.get("status") == "ok", "state": data.get("data")}
    except Exception as e:
        logger.error(f"control_ac 工具调用失败: {e}")
        return {"success": False, "error": str(e)}


def control_music(command: str, **kwargs) -> dict:
    """
    控制车载音乐播放。支持搜索歌曲、播放、暂停、切歌、音量调节。

    Args:
        command: 控制命令 (search / play / pause / next / prev / volume)
        **kwargs: keyword, song_id, volume 等

    Returns:
        {"success": bool, ...}
    """
    try:
        if command == "search":
            keyword = kwargs.get("keyword", "")
            resp = httpx.post(
                f"{_BACKEND_BASE}/api/music/search",
                json={"keyword": keyword},
                timeout=_TIMEOUT,
            )
            data = resp.json()
            return {"success": True, "songs": data.get("data", data.get("songs", []))}

        elif command == "play":
            song_id = kwargs.get("song_id")
            resp = httpx.post(
                f"{_BACKEND_BASE}/api/music/play",
                json={"song_id": song_id},
                timeout=_TIMEOUT,
            )
            data = resp.json()
            return {"success": True, "state": data.get("data")}

        elif command == "pause":
            resp = httpx.post(
                f"{_BACKEND_BASE}/api/music/pause",
                timeout=_TIMEOUT,
            )
            return {"success": resp.status_code == 200}

        elif command == "next":
            resp = httpx.post(
                f"{_BACKEND_BASE}/api/music/next",
                timeout=_TIMEOUT,
            )
            return {"success": resp.status_code == 200}

        elif command == "prev":
            resp = httpx.post(
                f"{_BACKEND_BASE}/api/music/prev",
                timeout=_TIMEOUT,
            )
            return {"success": resp.status_code == 200}

        elif command == "volume":
            volume = kwargs.get("volume", 50)
            resp = httpx.post(
                f"{_BACKEND_BASE}/api/music/volume",
                json={"volume": volume},
                timeout=_TIMEOUT,
            )
            return {"success": resp.status_code == 200}

        else:
            return {"success": False, "error": f"未知的音乐控制命令: {command}"}

    except Exception as e:
        logger.error(f"control_music 工具调用失败: {e}")
        return {"success": False, "error": str(e)}


def search_knowledge(query: str) -> dict:
    """
    检索车辆故障知识库，回答关于车辆故障、保养、驾驶安全等问题。

    Args:
        query: 搜索问题

    Returns:
        {"success": bool, "docs": list}
    """
    try:
        from modules.ai.vehicle_knowledge_base import get_knowledge_base

        kb = get_knowledge_base()
        result = kb.retrieve_knowledge(query)
        return {"success": result.get("success", False), "docs": result.get("docs", [])}
    except Exception as e:
        logger.error(f"search_knowledge 工具调用失败: {e}")
        return {"success": False, "error": str(e)}


def get_weather(city: Optional[str] = None) -> dict:
    """
    查询当前天气信息，包括温度、湿度、风力等。

    Args:
        city: 城市名称，可选

    Returns:
        天气数据 dict
    """
    try:
        resp = httpx.get(
            f"{_BACKEND_BASE}/api/environment",
            params={"city": city or ""},
            timeout=20,  # EnvironmentAgent 可能先试 OpenWeatherMap 再降级 wttr.in
        )
        data = resp.json()
        return data
    except Exception as e:
        logger.error(f"get_weather 工具调用失败: {e}")
        return {"success": False, "error": str(e)}


def alert_driver(alert_type: str, severity: str, message: str) -> dict:
    """
    向驾驶员发出安全告警（疲劳、分心、视线偏离等）。

    Args:
        alert_type: 告警类型 (fatigue / distraction / gaze / crowd / absence)
        severity: 告警级别 (mild / moderate / severe)
        message: 告警消息文本

    Returns:
        {"success": bool, "alert": dict}
    """
    try:
        alert = {
            "alert_type": alert_type,
            "severity": severity,
            "message": message,
        }
        return {"success": True, "alert": alert}
    except Exception as e:
        logger.error(f"alert_driver 工具调用失败: {e}")
        return {"success": False, "error": str(e)}


def ask_clarification(question: str) -> dict:
    """
    当意图不明确时向驾驶员追问，获取更多信息。

    Args:
        question: 追问的问题文本

    Returns:
        {"success": bool, "question": str}
    """
    try:
        return {"success": True, "question": question}
    except Exception as e:
        logger.error(f"ask_clarification 工具调用失败: {e}")
        return {"success": False, "error": str(e)}


# ── 景点搜索辅助 ──

_INDOOR_KEYWORDS = [
    "博物馆", "美术馆", "科技馆", "展览馆", "纪念馆",
    "图书馆", "文化宫", "剧院", "音乐厅", "购物中心",
    "商场", "海洋馆", "水族馆", "天文馆", "蜡像馆",
    "室内", "体验馆", "艺术中心", "大悦城", "万象城",
    "地下", "拱廊", "室内乐园", "儿童乐园", "DIY",
    "手工", "陶艺", "烘焙", "密室", "VR", "剧本杀",
]
# 雨天补充搜索的室内 POI 类型码（高德 POI type code）
_INDOOR_POI_TYPES = "140200|140300|140500|150200|060100|060200"
# 文化场馆|博物馆|展览馆|影剧院|购物相关|商场
_RAIN_KEYWORDS = ["雨", "rain", "shower", "drizzle", "雷", "雪", "snow", "sleet", "冰"]
_HOT_KEYWORDS = ["高温", "炎热", "暴晒"]


def _classify_weather(weather_desc: str) -> str:
    if not weather_desc:
        return "normal"
    for kw in _RAIN_KEYWORDS:
        if kw in weather_desc.lower() or kw in weather_desc:
            return "rain"
    for kw in _HOT_KEYWORDS:
        if kw in weather_desc or kw in weather_desc.lower():
            return "hot"
    return "normal"


def _is_indoor(name: str, type_names: str) -> bool:
    text = f"{name} {type_names}"
    return any(kw in text for kw in _INDOOR_KEYWORDS)


def _classify_category(type_names: str) -> str:
    """根据 POI type 字段分类景点。"""
    if "博物馆" in type_names or "纪念馆" in type_names:
        return "博物馆"
    elif "公园" in type_names:
        return "公园"
    elif "乐园" in type_names:
        return "主题乐园"
    elif "古迹" in type_names or "遗址" in type_names:
        return "历史古迹"
    elif "购物" in type_names or "商场" in type_names:
        return "购物"
    elif "电影" in type_names or "剧院" in type_names:
        return "文化娱乐"
    return "景点"


def _estimate_duration(type_names: str) -> int:
    """根据 POI 类型估算游览时长（分钟）。"""
    if "博物馆" in type_names or "纪念馆" in type_names:
        return 180
    elif "公园" in type_names or "广场" in type_names:
        return 90
    elif "乐园" in type_names:
        return 240
    elif "购物" in type_names or "商场" in type_names:
        return 120
    elif "电影" in type_names:
        return 150
    return 120


def search_attractions(
    city: str,
    weather: Optional[str] = None,
    count: int = 5,
    preference: Optional[str] = None,
) -> dict:
    """
    搜索城市热门景点，根据天气和偏好智能推荐。
    雨天优先推荐室内景点，高温天标注避暑提示。

    Args:
        city: 城市名称（如"天津"、"北京"）
        weather: 当前天气描述（如"晴"、"小雨"），用于智能过滤
        count: 返回景点数量（默认 5）
        preference: 偏好类型（历史文化/亲子/户外/美食/拍照打卡）

    Returns:
        {"success": bool, "city": str, "weather_type": str, "attractions": list}
    """
    amap_key = _get_amap_key()
    if not amap_key:
        logger.warning("search_attractions: AMAP_API_KEY 未配置")
        return {"success": False, "error": "高德地图 API Key 未配置", "city": city, "attractions": []}

    search_keyword = "景点"
    if preference:
        pref_map = {
            "历史文化": "历史 古迹 遗址", "亲子": "乐园 公园 亲子",
            "户外": "公园 山 湖 户外", "美食": "美食 小吃街", "拍照打卡": "网红 打卡 景点",
        }
        search_keyword = pref_map.get(preference, "景点")

    weather_type = _classify_weather(weather or "")

    try:
        resp = httpx.get(_AMAP_POI_URL, params={
            "keywords": search_keyword, "city": city, "citylimit": "true",
            "types": "110000", "offset": min(count * 3, 25),
            "page": 1, "key": amap_key, "extensions": "all",
        }, timeout=10)
        data = resp.json()

        if data.get("status") != "1":
            logger.error(f"高德 POI 搜索失败: {data.get('info', '')}")
            return {"success": False, "error": f"高德 API 错误: {data.get('info', '')}", "city": city, "attractions": []}

        pois = data.get("pois", [])
        if not pois:
            resp2 = httpx.get(_AMAP_POI_URL, params={
                "keywords": "旅游景点", "city": city, "citylimit": "true",
                "offset": min(count * 3, 25), "page": 1, "key": amap_key, "extensions": "all",
            }, timeout=10)
            pois = resp2.json().get("pois", [])

        attractions = []
        for poi in pois:
            name = poi.get("name", "")
            address = poi.get("address", "") or city
            type_names = poi.get("type", "")
            indoor = _is_indoor(name, type_names)

            # 借鉴 hello-agents: 提取更丰富的 POI 数据
            biz_ext = poi.get("biz_ext", {}) or {}
            photos = poi.get("photos", []) or {}
            # 门票价格
            ticket_price = 0
            cost_str = biz_ext.get("cost", "") or ""
            if cost_str:
                try:
                    ticket_price = int(float(cost_str))
                except (ValueError, TypeError):
                    pass
            # 评分
            rating = 0.0
            rating_str = biz_ext.get("rating", "") or ""
            if rating_str:
                try:
                    rating = round(float(rating_str), 1)
                except (ValueError, TypeError):
                    pass
            # 照片 URL
            photo_url = ""
            if photos and isinstance(photos, list):
                url = photos[0].get("url", "") if isinstance(photos[0], dict) else ""
                photo_url = url

            # 游览时长估算（根据类型）
            visit_duration = 120  # 默认 2 小时
            if "博物馆" in type_names or "纪念馆" in type_names:
                visit_duration = 180
            elif "公园" in type_names or "广场" in type_names:
                visit_duration = 90
            elif "乐园" in type_names:
                visit_duration = 240

            # 分类
            category = "景点"
            if "博物馆" in type_names:
                category = "博物馆"
            elif "公园" in type_names:
                category = "公园"
            elif "乐园" in type_names:
                category = "主题乐园"
            elif "古迹" in type_names or "遗址" in type_names:
                category = "历史古迹"

            attr = {
                "name": name,
                "address": address,
                "type": type_names,
                "indoor": indoor,
                "weather_hint": "",
                "category": category,
                "rating": rating,
                "ticket_price": ticket_price,
                "visit_duration": visit_duration,
                "photo_url": photo_url,
                "location": poi.get("location", ""),
            }

            if weather_type == "rain":
                attr["weather_hint"] = "室内景点，雨天推荐" if indoor else "户外景点，雨天需带伞"
            elif weather_type == "hot":
                attr["weather_hint"] = "室内有空调，避暑推荐" if indoor else "户外较热，建议早晚前往"

            attractions.append(attr)

        # ── 雨天/高温：主动补充室内景点搜索 ──
        if weather_type in ("rain", "hot"):
            indoor_count = sum(1 for a in attractions if a["indoor"])
            if indoor_count < count:
                try:
                    indoor_resp = httpx.get(_AMAP_POI_URL, params={
                        "keywords": f"{city}室内",
                        "city": city, "citylimit": "true",
                        "types": _INDOOR_POI_TYPES,
                        "offset": min((count - indoor_count) * 3, 20),
                        "page": 1, "key": amap_key, "extensions": "all",
                    }, timeout=8)
                    indoor_pois = indoor_resp.json().get("pois", [])
                    existing_names = {a["name"] for a in attractions}
                    for poi in indoor_pois:
                        pname = poi.get("name", "")
                        if pname in existing_names:
                            continue
                        biz_ext = poi.get("biz_ext", {}) or {}
                        photos = poi.get("photos", []) or []
                        ticket_price = 0
                        cost_str = biz_ext.get("cost", "") or ""
                        if cost_str:
                            try:
                                ticket_price = int(float(cost_str))
                            except (ValueError, TypeError):
                                pass
                        rating = 0.0
                        rating_str = biz_ext.get("rating", "") or ""
                        if rating_str:
                            try:
                                rating = round(float(rating_str), 1)
                            except (ValueError, TypeError):
                                pass
                        photo_url = ""
                        if photos and isinstance(photos, list):
                            url = photos[0].get("url", "") if isinstance(photos[0], dict) else ""
                            photo_url = url
                        type_names = poi.get("type", "")
                        attractions.append({
                            "name": pname,
                            "address": poi.get("address", "") or city,
                            "type": type_names,
                            "indoor": True,
                            "weather_hint": "室内景点，雨天推荐" if weather_type == "rain" else "室内有空调，避暑推荐",
                            "category": "室内活动" if not _is_indoor(pname, type_names) else _classify_category(type_names),
                            "rating": rating,
                            "ticket_price": ticket_price,
                            "visit_duration": _estimate_duration(type_names),
                            "photo_url": photo_url,
                            "location": poi.get("location", ""),
                        })
                        existing_names.add(pname)
                except Exception as e:
                    logger.warning(f"室内景点补充搜索失败: {e}")

            attractions.sort(key=lambda x: (0 if x["indoor"] else 1, -x.get("rating", 0)))

        attractions = attractions[:count]
        return {"success": True, "city": city, "weather_type": weather_type, "count": len(attractions), "attractions": attractions}

    except httpx.TimeoutException:
        logger.error("search_attractions: 高德 API 请求超时")
        return {"success": False, "error": "景点搜索超时", "city": city, "attractions": []}
    except Exception as e:
        logger.error(f"search_attractions 执行异常: {e}")
        return {"success": False, "error": str(e), "city": city, "attractions": []}


def _get_current_gps() -> dict:
    """读取当前 GPS 坐标：优先 LocationStore，降级 main._current_gps"""
    # 优先从 LocationStore 读取（线程安全，NavPanel 浏览器 GPS 写入）
    try:
        from modules.ai.location_store import get_location_store
        store = get_location_store()
        lat, lon = store.get_coords()
        if lat is not None and lon is not None:
            return {"lat": lat, "lon": lon, "source": "location_store"}
    except Exception:
        pass
    # 降级：从 main._current_gps 读取（旧路径）
    try:
        import importlib
        main_mod = importlib.import_module("main")
        gps = getattr(main_mod, "_current_gps", {})
        if gps and "lat" in gps and "lon" in gps:
            return gps
    except Exception:
        pass
    return {}


def _reverse_geocode(lng: float, lat: float) -> str:
    """逆地理编码：坐标 → 地址名称"""
    amap_key = _get_amap_key()
    if not amap_key:
        return "当前位置"
    try:
        resp = httpx.get(
            "https://restapi.amap.com/v3/geocode/regeo",
            params={"location": f"{lng},{lat}", "key": amap_key, "extensions": "base"},
            timeout=5.0,
        )
        data = resp.json()
        if data.get("status") == "1":
            addr = data.get("regeocode", {}).get("formatted_address", "")
            if addr:
                # 简化显示：取最后两级地址
                parts = addr.split("省")[-1].split("市")[-1]
                return parts[:20] if parts else addr[:20]
            return "当前位置"
    except Exception:
        pass
    return "当前位置"


def start_navigation(destination: str, city: str = "") -> dict:
    """
    启动导航到指定目的地。
    主力：免费 OSRM 路线 + Nominatim 地理编码（无需任何 API Key），含离线地标表降级。
    增强：高德深链（有 Key 时附上 amap_nav_url，可一键跳转高德 App）。
    """
    # Step 1: 获取起点坐标
    gps = _get_current_gps()
    from_lat = float(gps["lat"]) if gps and gps.get("lat") else None
    from_lon = float(gps["lon"]) if gps and gps.get("lon") else None

    # Step 2: 用免费 NavigationService 规划路线（OSRM + Nominatim + 离线降级）
    from modules.ai.navigation_service import get_navigation_service
    nav = get_navigation_service()
    result = nav.plan(from_lat, from_lon, destination)

    # Step 3: 高德深链增强（有 Key 时附上，可一键跳转 App）
    try:
        amap_key = _get_amap_key()
        if amap_key and result.get("success") and result.get("destination_coords"):
            dest = result["destination_coords"]
            result["amap_nav_url"] = (
                f"https://uri.amap.com/navigation"
                f"?from={from_lon or 116.397428},{from_lat or 39.90923},起点"
                f"&to={dest[1]},{dest[0]},{result['destination']}"
                f"&mode=car&src=EdgeGuard&coordinate=gcj02&callnative=0"
            )
    except Exception:
        pass

    return result
def plan_trip(city: str, days: int = 1, preference: Optional[str] = None) -> dict:
    """
    生成结构化行程规划，借鉴 hello-agents trip-planner 数据模型。

    包含：多日行程结构、预算估算（门票+餐饮+交通）、景点照片/评分/门票/游览时长、天气信息。

    Args:
        city: 目的地城市（如"天津"、"北京"）
        days: 旅行天数（默认 1，限制 1-5）
        preference: 偏好类型（历史文化/亲子/户外/美食/拍照打卡）

    Returns:
        {
            "success": bool, "city": str, "days": int,
            "itinerary": [{"day": 1, "date": "第1天", "slots": [...]}],
            "budget": {"total": int, "tickets": int, "meals": int, "transport": int, "per_day": int},
            "weather": {...}, "attractions": [...], "summary": str
        }
    """
    logger.info(f"plan_trip: city={city}, days={days}, preference={preference}")
    days = max(1, min(days, 5))

    # Step 1: 先查天气（决定景点搜索策略）
    weather_result = get_weather(city=city)
    weather_info = {}
    weather_desc = ""
    if weather_result.get("status") == "ok":
        wdata = weather_result.get("data", {})
        weather_desc = wdata.get("weather_desc", "")
        weather_info = {
            "city": wdata.get("city", city),
            "temperature": wdata.get("temperature"),
            "weather_desc": weather_desc,
            "weather_emoji": wdata.get("weather_emoji", ""),
            "humidity": wdata.get("humidity"),
            "wind_speed": wdata.get("wind_speed"),
            "driving_context": wdata.get("driving_context", ""),
        }

    # Step 2: 搜索景点（传入天气描述，雨天自动优先室内）
    attr_result = search_attractions(city=city, weather=weather_desc, count=days * 3 + 2, preference=preference)
    all_attractions = attr_result.get("attractions", [])
    if not all_attractions:
        return {
            "success": False, "city": city, "days": days,
            "error": attr_result.get("error", "未找到景点"),
            "itinerary": [], "budget": {}, "summary": f"抱歉，无法为{city}生成行程规划",
        }
    weather_str = weather_info.get("weather_desc", "")
    if weather_info.get("temperature") is not None:
        weather_str += f" {weather_info['temperature']}°C"

    # Step 3: 按天数分配景点（每天 3 个）
    attractions_per_day = 3
    total_needed = days * attractions_per_day
    if len(all_attractions) < total_needed:
        while len(all_attractions) < total_needed:
            all_attractions.extend(all_attractions[:total_needed - len(all_attractions)])
    selected = all_attractions[:total_needed]

    # Step 4: 构建每日行程 + 预算累计
    itinerary = []
    total_tickets = 0
    total_meals = 0
    total_transport = 0

    for day_idx in range(days):
        day_attractions = selected[day_idx * attractions_per_day:(day_idx + 1) * attractions_per_day]
        slots = []

        # 早餐
        slots.append({"time": "08:00", "type": "meal", "title": "早餐",
                      "desc": f"品尝{city}地道早餐", "cost": 30})
        total_meals += 30

        # 上午景点
        if len(day_attractions) > 0:
            attr = day_attractions[0]
            ticket = attr.get("ticket_price", 0)
            total_tickets += ticket
            slots.append({
                "time": "09:00", "type": "visit", "title": attr["name"],
                "desc": f"{attr.get('category', '景点')} · 预计游览{attr.get('visit_duration', 120)}分钟 · 📍 {attr.get('address', '')}",
                "address": attr.get("address", ""), "ticket_price": ticket,
                "rating": attr.get("rating", 0), "photo_url": attr.get("photo_url", ""),
                "visit_duration": attr.get("visit_duration", 120), "cost": ticket,
            })

        # 午餐
        slots.append({"time": "12:00", "type": "meal", "title": "午餐",
                      "desc": "游览途中就近用餐", "cost": 80})
        total_meals += 80

        # 下午景点 1
        if len(day_attractions) > 1:
            attr = day_attractions[1]
            ticket = attr.get("ticket_price", 0)
            total_tickets += ticket
            slots.append({
                "time": "14:00", "type": "visit", "title": attr["name"],
                "desc": f"{attr.get('category', '景点')} · 预计游览{attr.get('visit_duration', 120)}分钟 · 📍 {attr.get('address', '')}",
                "address": attr.get("address", ""), "ticket_price": ticket,
                "rating": attr.get("rating", 0), "photo_url": attr.get("photo_url", ""),
                "visit_duration": attr.get("visit_duration", 120), "cost": ticket,
            })

        # 下午景点 2
        if len(day_attractions) > 2:
            attr = day_attractions[2]
            ticket = attr.get("ticket_price", 0)
            total_tickets += ticket
            slots.append({
                "time": "16:30", "type": "visit", "title": attr["name"],
                "desc": f"{attr.get('category', '景点')} · 预计游览{attr.get('visit_duration', 120)}分钟 · 📍 {attr.get('address', '')}",
                "address": attr.get("address", ""), "ticket_price": ticket,
                "rating": attr.get("rating", 0), "photo_url": attr.get("photo_url", ""),
                "visit_duration": attr.get("visit_duration", 120), "cost": ticket,
            })

        # 交通
        day_transport = 50
        total_transport += day_transport
        slots.append({"time": "18:30", "type": "transport", "title": "前往晚餐",
                      "desc": f"驾车或公共交通，预计{day_transport}元", "cost": day_transport})

        # 晚餐
        slots.append({"time": "19:00", "type": "meal", "title": "晚餐",
                      "desc": f"享受{city}特色美食", "cost": 100})
        total_meals += 100

        # 休息
        slots.append({"time": "21:00", "type": "rest", "title": "休息",
                      "desc": "结束一天的行程", "cost": 0})

        itinerary.append({"day": day_idx + 1, "date": f"第{day_idx + 1}天", "slots": slots})

    # Step 5: 计算预算
    total_cost = total_tickets + total_meals + total_transport
    budget = {
        "total": total_cost,
        "tickets": total_tickets,
        "meals": total_meals,
        "transport": total_transport,
        "per_day": round(total_cost / days) if days > 0 else total_cost,
    }

    # Step 6: 生成摘要
    weather_text = f"（{weather_str}）" if weather_str else ""
    rain_warning = ""
    weather_type = _classify_weather(weather_desc)
    if weather_type == "rain":
        indoor_count = sum(1 for a in selected if a.get("indoor"))
        outdoor_count = len(selected) - indoor_count
        if outdoor_count > 0:
            rain_warning = f"今日有雨，已优先推荐{indoor_count}个室内景点，{outdoor_count}个户外景点建议携带雨具或调整至雨停时段。"

    summary = (
        f"{city}{days}日游{weather_text}："
        f"共{len(selected)}个景点，"
        f"预计总费用约{total_cost}元"
        f"（门票{total_tickets}+餐饮{total_meals}+交通{total_transport}）。"
    )
    if rain_warning:
        summary += rain_warning
    if weather_info.get("driving_context"):
        summary += weather_info["driving_context"]

    return {
        "success": True, "city": city, "days": days,
        "itinerary": itinerary, "budget": budget,
        "weather": weather_info, "attractions": selected,
        "summary": summary,
    }


# ═══════════════════════════════════════════════════════════
#  工具执行器 — 名称 → 函数映射 + 统一调用入口
# ═══════════════════════════════════════════════════════════

TOOL_EXECUTOR = {
    "speak": speak,
    "control_ac": control_ac,
    "control_music": control_music,
    "search_knowledge": search_knowledge,
    "get_weather": get_weather,
    "alert_driver": alert_driver,
    "ask_clarification": ask_clarification,
    "search_attractions": search_attractions,
    "start_navigation": start_navigation,
    "plan_trip": plan_trip,
}


def execute_tool(name: str, args: dict) -> dict:
    """
    统一工具执行入口。

    根据 LLM 返回的 function_call name 和 arguments，
    查找对应的执行函数并调用。

    Args:
        name: 工具名称（对应 TOOL_SCHEMAS 中的 function.name）
        args: 工具参数（LLM 返回的 function.arguments 解析后的 dict）

    Returns:
        工具执行结果 dict，至少包含 "success" 字段。
        未知工具时返回 {"success": False, "error": "Unknown tool: {name}"}
    """
    func = TOOL_EXECUTOR.get(name)
    if func is None:
        logger.warning(f"未知工具: {name}")
        return {"success": False, "error": f"Unknown tool: {name}"}

    try:
        return func(**args)
    except TypeError as e:
        logger.error(f"工具 {name} 参数错误: {e}, args={args}")
        return {"success": False, "error": f"Parameter error: {e}"}
    except Exception as e:
        logger.error(f"工具 {name} 执行异常: {e}")
        return {"success": False, "error": str(e)}
