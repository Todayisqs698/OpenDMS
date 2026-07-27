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
                        "enum": ["search", "play", "pause", "stop", "next", "prev", "volume"],
                        "description": "控制命令。stop=停止播放(别名pause)"
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
            "name": "get_weather_forecast",
            "description": "查询城市逐日天气预报，用于多日行程规划。优先使用高德天气 forecast。",
            "parameters": {
                "type": "object",
                "properties": {
                    "city": {"type": "string", "description": "城市名称，如天津、北京"},
                    "days": {"type": "integer", "description": "需要的预报天数，默认3天", "default": 3}
                },
                "required": ["city"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "search_hotels",
            "description": "搜索城市真实酒店 POI，只返回酒店名称、地址、坐标、评分、价格区间和类型等住宿核心字段。",
            "parameters": {
                "type": "object",
                "properties": {
                    "city": {"type": "string", "description": "城市名称，如天津、北京"},
                    "count": {"type": "integer", "description": "返回酒店数量，默认5", "default": 5},
                    "preference": {"type": "string", "description": "住宿偏好，如舒适型酒店、经济型酒店、亲子酒店"}
                },
                "required": ["city"]
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
                    "origin": {"type": "string", "description": "自驾线路起点城市，如天津，可选"},
                    "waypoints": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "自驾线路必须途经的城市列表，如[\"西安\", \"兰州\"]，可选"
                    },
                    "forbidden_cities": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "自驾线路需要避开的城市列表，如[\"郑州\"]，可选"
                    },
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
    {
        "type": "function",
        "function": {
            "name": "save_location",
            "description": "保存一个常用地点（如家、公司）。保存后可直接说「导航回家」自动导航。当用户说「我家在XX路」或「记住公司地址是XX」时调用此工具。",
            "parameters": {
                "type": "object",
                "properties": {
                    "label": {
                        "type": "string",
                        "enum": ["home", "company"],
                        "description": "地点标签：home=家，company=公司"
                    },
                    "address": {"type": "string", "description": "详细地址，如「北京市朝阳区建国路88号」"}
                },
                "required": ["label", "address"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_saved_location",
            "description": "查询已保存的地点信息。当用户问「我家的地址是什么」或「你定义的家是哪里」时调用此工具查看。",
            "parameters": {
                "type": "object",
                "properties": {
                    "label": {
                        "type": "string",
                        "enum": ["home", "company"],
                        "description": "地点标签：home=家，company=公司"
                    }
                },
                "required": ["label"]
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
    控制车载音乐播放。支持搜索歌曲、播放、暂停/停止、切歌、音量调节。

    Args:
        command: 控制命令 (search / play / pause / stop / next / prev / volume)
        **kwargs: keyword, song_id, volume 等

    Returns:
        {"success": bool, ...}  success 严格基于后端返回的 status 字段
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
            songs = data.get("data", data.get("songs", []))
            return {"success": data.get("status") == "ok", "songs": songs,
                    "error": data.get("message", "") if data.get("status") != "ok" else ""}

        elif command == "play":
            song_id = kwargs.get("song_id")
            if song_id:
                # 有 song_id：直接播放指定歌曲
                resp = httpx.post(
                    f"{_BACKEND_BASE}/api/music/play",
                    json={"song_id": song_id},
                    timeout=_TIMEOUT,
                )
                data = resp.json()
                status = data.get("status", "")
                if status == "ok":
                    return {"success": True, "state": data.get("data")}
                else:
                    msg = data.get("message", "")
                    if status == "needs_audio":
                        msg = "当前歌曲无可用音频源，请先搜索并选择歌曲"
                    elif not msg:
                        msg = f"播放失败 (status={status})"
                    return {"success": False, "error": msg, "status": status}
            else:
                # 无 song_id：调用 pause 端点恢复当前播放（pause 是 toggle）
                resp = httpx.post(
                    f"{_BACKEND_BASE}/api/music/pause",
                    timeout=_TIMEOUT,
                )
                data = resp.json()
                status = data.get("status", "")
                state = data.get("data", {})
                playing = state.get("playing") if isinstance(state, dict) else None
                if status == "ok" and playing:
                    return {"success": True, "state": state,
                            "message": "已恢复播放"}
                elif status == "needs_audio":
                    return {"success": False, "error": "当前没有可播放的歌曲，请先搜索并选择歌曲",
                            "status": status}
                elif status == "ok" and not playing:
                    # toggle 后变为暂停，再 toggle 一次恢复
                    httpx.post(f"{_BACKEND_BASE}/api/music/pause", timeout=_TIMEOUT)
                    return {"success": True, "state": state,
                            "message": "已恢复播放"}
                else:
                    return {"success": False, "error": data.get("message", "播放失败"),
                            "status": status}

        elif command in ("pause", "stop"):
            # stop 作为 pause 的别名（后端 pause 实为 toggle）
            resp = httpx.post(
                f"{_BACKEND_BASE}/api/music/pause",
                timeout=_TIMEOUT,
            )
            data = resp.json()
            return {"success": data.get("status") == "ok",
                    "state": data.get("data"),
                    "error": data.get("message", "") if data.get("status") != "ok" else ""}

        elif command == "next":
            resp = httpx.post(
                f"{_BACKEND_BASE}/api/music/next",
                timeout=_TIMEOUT,
            )
            data = resp.json()
            return {"success": data.get("status") == "ok",
                    "state": data.get("data"),
                    "error": data.get("message", "") if data.get("status") != "ok" else ""}

        elif command == "prev":
            resp = httpx.post(
                f"{_BACKEND_BASE}/api/music/prev",
                timeout=_TIMEOUT,
            )
            data = resp.json()
            return {"success": data.get("status") == "ok",
                    "state": data.get("data"),
                    "error": data.get("message", "") if data.get("status") != "ok" else ""}

        elif command == "volume":
            volume = kwargs.get("volume", 50)
            resp = httpx.post(
                f"{_BACKEND_BASE}/api/music/volume",
                json={"volume": volume},
                timeout=_TIMEOUT,
            )
            data = resp.json()
            return {"success": data.get("status") == "ok",
                    "state": data.get("data"),
                    "error": data.get("message", "") if data.get("status") != "ok" else ""}

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


def get_weather_forecast(city: str, days: int = 3) -> dict:
    """
    查询城市逐日天气预报。

    当前实现使用高德天气 extensions=all；失败时返回 success=False，由调用方决定 fallback。
    """
    amap_key = _get_amap_key()
    if not amap_key:
        logger.warning("get_weather_forecast: AMAP_API_KEY 未配置")
        return {"success": False, "error": "高德地图 API Key 未配置", "city": city, "forecasts": []}

    try:
        geo_resp = httpx.get(
            "https://restapi.amap.com/v3/geocode/geo",
            params={"address": city, "key": amap_key},
            timeout=5.0,
        )
        geo_data = geo_resp.json()
        if geo_data.get("status") != "1" or not geo_data.get("geocodes"):
            return {"success": False, "error": "城市编码查询失败", "city": city, "forecasts": []}

        adcode = geo_data["geocodes"][0].get("adcode", "")
        if not adcode:
            return {"success": False, "error": "城市 adcode 不可用", "city": city, "forecasts": []}

        weather_resp = httpx.get(
            "https://restapi.amap.com/v3/weather/weatherInfo",
            params={"city": adcode, "key": amap_key, "extensions": "all"},
            timeout=5.0,
        )
        weather_data = weather_resp.json()
        if weather_data.get("status") != "1" or not weather_data.get("forecasts"):
            return {"success": False, "error": "天气预报查询失败", "city": city, "forecasts": []}

        casts = weather_data["forecasts"][0].get("casts", [])
        forecasts = []
        for cast in casts[:max(1, int(days or 1))]:
            forecasts.append({
                "date": cast.get("date", ""),
                "day_weather": cast.get("dayweather", ""),
                "night_weather": cast.get("nightweather", ""),
                "day_temp": cast.get("daytemp", ""),
                "night_temp": cast.get("nighttemp", ""),
                "wind_direction": cast.get("daywind", "") or cast.get("nightwind", ""),
                "wind_power": cast.get("daypower", "") or cast.get("nightpower", ""),
                "source": "amap_forecast",
                "note": "高德逐日天气预报",
            })

        return {
            "success": True,
            "city": city,
            "adcode": adcode,
            "report_time": weather_data["forecasts"][0].get("reporttime", ""),
            "forecasts": forecasts,
        }

    except httpx.TimeoutException:
        logger.error("get_weather_forecast: 高德 API 请求超时")
        return {"success": False, "error": "天气预报查询超时", "city": city, "forecasts": []}
    except Exception as e:
        logger.error(f"get_weather_forecast 执行异常: {e}")
        return {"success": False, "error": str(e), "city": city, "forecasts": []}


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


def search_hotels(city: str, count: int = 5, preference: Optional[str] = None) -> dict:
    """
    搜索城市酒店 POI。

    酒店解析独立于景点解析：不做室内检测、天气提示、游览时长估算或景点分类。
    """
    amap_key = _get_amap_key()
    if not amap_key:
        logger.warning("search_hotels: AMAP_API_KEY 未配置")
        return {"success": False, "error": "高德地图 API Key 未配置", "city": city, "hotels": []}

    keyword = preference or "酒店"
    if "酒店" not in keyword and "宾馆" not in keyword and "住宿" not in keyword:
        keyword = f"{keyword} 酒店"

    try:
        resp = httpx.get(_AMAP_POI_URL, params={
            "keywords": keyword,
            "city": city,
            "citylimit": "true",
            "types": "100000",
            "offset": min(count * 3, 25),
            "page": 1,
            "key": amap_key,
            "extensions": "all",
        }, timeout=10)
        data = resp.json()

        if data.get("status") != "1":
            logger.error(f"高德酒店 POI 搜索失败: {data.get('info', '')}")
            return {"success": False, "error": f"高德 API 错误: {data.get('info', '')}", "city": city, "hotels": []}

        hotels = []
        for poi in data.get("pois", []):
            biz_ext = poi.get("biz_ext", {}) or {}
            photos = poi.get("photos", []) or []

            rating = ""
            rating_str = biz_ext.get("rating", "") or ""
            if rating_str:
                try:
                    rating = str(round(float(rating_str), 1))
                except (ValueError, TypeError):
                    rating = str(rating_str)

            cost = 0
            cost_str = biz_ext.get("cost", "") or ""
            if cost_str:
                try:
                    cost = int(float(cost_str))
                except (ValueError, TypeError):
                    cost = 0

            photo_url = ""
            if photos and isinstance(photos, list):
                photo_url = photos[0].get("url", "") if isinstance(photos[0], dict) else ""

            hotels.append({
                "name": poi.get("name", ""),
                "address": poi.get("address", "") or city,
                "location": poi.get("location", ""),
                "rating": rating,
                "price_range": f"{cost}元起" if cost else "",
                "type": poi.get("type", "") or preference or "酒店",
                "estimated_cost": cost or 400,
                "photo_url": photo_url,
                "source": "amap",
            })

        return {"success": True, "city": city, "count": len(hotels[:count]), "hotels": hotels[:count]}

    except httpx.TimeoutException:
        logger.error("search_hotels: 高德 API 请求超时")
        return {"success": False, "error": "酒店搜索超时", "city": city, "hotels": []}
    except Exception as e:
        logger.error(f"search_hotels 执行异常: {e}")
        return {"success": False, "error": str(e), "city": city, "hotels": []}


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

    语义地点支持：destination 为"家"/"回家"/"home"/"公司"/"单位"时，
    先查已保存地点；未定义则返回 needs_clarification 要求用户设置。
    """
    # Step 0: 语义地点解析（家/公司等）
    _SEMANTIC_MAP = {
        "家": "home", "回家": "home", "home": "home", "我家": "home",
        "公司": "company", "单位": "company", "company": "company",
        "上班": "company", "去公司": "company",
    }
    dest_clean = destination.strip()
    if dest_clean in _SEMANTIC_MAP:
        label = _SEMANTIC_MAP[dest_clean]
        try:
            from modules.ai.memory import LongTermMemory
            ltm = LongTermMemory()
            saved = ltm.get_location(label)
            ltm._conn.close()
            if saved and saved.get("address"):
                destination = saved["address"]
                logger.info("语义地点解析: %s → %s", dest_clean, destination)
            else:
                friendly = "家" if label == "home" else "公司"
                return {
                    "success": False,
                    "needs_clarification": True,
                    "clarification_question": f"您还没有设置过「{friendly}」的地址。请告诉我您{friendly}的地址，比如「我家在北京市朝阳区XX路」，我会记住以后就能直接导航了。",
                }
        except Exception as e:
            logger.warning("语义地点查询失败: %s", e)

    # Step 1: 获取起点坐标（无 GPS 时默认上海市中心）
    gps = _get_current_gps()
    from_lat = float(gps["lat"]) if gps and gps.get("lat") else 31.2304
    from_lon = float(gps["lon"]) if gps and gps.get("lon") else 121.4737
    gps_source = gps.get("source", "fallback_shanghai") if gps else "fallback_shanghai"

    # Step 2: 用免费 NavigationService 规划路线（OSRM + Nominatim + 离线降级）
    from modules.ai.navigation_service import get_navigation_service
    nav = get_navigation_service()
    result = nav.plan(from_lat, from_lon, destination)
    result["origin_source"] = gps_source
    if gps_source == "fallback_shanghai":
        result.setdefault("origin", "上海市中心（未获取到真实定位）")

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
def plan_trip(
    city: str,
    days: int = 1,
    preference: Optional[str] = None,
    origin: str = "",
    waypoints: Optional[list] = None,
    forbidden_cities: Optional[list] = None,
) -> dict:
    """Generate a structured trip plan via the dedicated trip planner."""
    logger.info(
        "plan_trip: origin=%s, city=%s, waypoints=%s, forbidden_cities=%s, days=%s, preference=%s",
        origin,
        city,
        waypoints,
        forbidden_cities,
        days,
        preference,
    )
    try:
        from modules.ai.trip_planner import get_trip_planner_agent
        result = get_trip_planner_agent().plan_from_text(
            query=f"{origin + '到' if origin else ''}{city}{days}日游",
            city=city,
            days=days,
            preference=preference,
            origin=origin,
            waypoints=waypoints or [],
            forbidden_cities=forbidden_cities or [],
        )
        trip = result.get("trip_plan") or {}
        return {
            "success": result.get("success", True),
            "city": trip.get("city", city),
            "days": trip.get("days", days),
            "itinerary": trip.get("itinerary", []),
            "budget": trip.get("budget", {}),
            "weather": result.get("weather", {}),
            "weather_info": trip.get("weather_info", []),
            "attractions": [
                attr
                for day in trip.get("trip_schema", {}).get("days", [])
                for attr in day.get("attractions", [])
            ],
            "summary": trip.get("summary", ""),
            "trip_schema": result.get("trip_schema") or trip.get("trip_schema", {}),
        }
    except Exception as e:
        logger.error("plan_trip failed: %s", e)
        return {
            "success": False,
            "city": city,
            "days": days,
            "itinerary": [],
            "budget": {},
            "weather": {},
            "attractions": [],
            "summary": f"抱歉，无法为{city}生成行程规划",
            "error": str(e),
        }


def save_location(label: str, address: str) -> dict:
    """
    保存一个常用地点（如家、公司）到长期记忆。
    保存后用户说"导航回家"即可自动导航到该地址。

    Args:
        label: 地点标签 (home / company)
        address: 详细地址

    Returns:
        {"success": bool, ...}
    """
    try:
        from modules.ai.memory import LongTermMemory
        ltm = LongTermMemory()
        ltm.set_location(label, address)
        ltm._conn.close()
        friendly = "家" if label == "home" else "公司"
        return {"success": True, "message": f"已记住您的{friendly}地址：{address}"}
    except Exception as e:
        logger.error(f"save_location 失败: {e}")
        return {"success": False, "error": str(e)}


def get_saved_location(label: str) -> dict:
    """
    查询已保存的地点信息。

    Args:
        label: 地点标签 (home / company)

    Returns:
        {"success": bool, "location": {...} or None}
    """
    try:
        from modules.ai.memory import LongTermMemory
        ltm = LongTermMemory()
        saved = ltm.get_location(label)
        ltm._conn.close()
        if saved:
            friendly = "家" if label == "home" else "公司"
            return {"success": True, "location": saved,
                    "message": f"您的{friendly}地址是：{saved['address']}"}
        else:
            friendly = "家" if label == "home" else "公司"
            return {"success": True, "location": None,
                    "message": f"您还没有设置过{friendly}的地址。请告诉我您{friendly}的地址，我会记住。"}
    except Exception as e:
        logger.error(f"get_saved_location 失败: {e}")
        return {"success": False, "error": str(e)}


# ═══════════════════════════════════════════════════════════
#  工具执行器 — 名称 → 函数映射 + 统一调用入口
# ═══════════════════════════════════════════════════════════

TOOL_EXECUTOR = {
    "speak": speak,
    "control_ac": control_ac,
    "control_music": control_music,
    "search_knowledge": search_knowledge,
    "get_weather": get_weather,
    "get_weather_forecast": get_weather_forecast,
    "alert_driver": alert_driver,
    "ask_clarification": ask_clarification,
    "search_attractions": search_attractions,
    "search_hotels": search_hotels,
    "start_navigation": start_navigation,
    "plan_trip": plan_trip,
    "save_location": save_location,
    "get_saved_location": get_saved_location,
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
