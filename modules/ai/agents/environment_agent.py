"""
环境 Agent — 天气 + 时间 + 位置上下文分析（增强版）

参考 In-Vehicle-Multimodal-Interaction-System 优化：
- 双天气数据源：OpenWeatherMap（优先）+ wttr.in（免费兜底）
- 天气图标映射（sun/rain/cloud/snow/fog/mist）
- 更丰富的时间段判断（黎明/早高峰/上午/中午/下午/晚高峰/夜间）
- 集成 TTS 语音预警 + 交互日志记录
- 驾驶环境综合风险评分

接口规范：
  输入: {"city": "Beijing"} 或 {}
  输出: {
    "time_of_day": "evening_rush",
    "weather": "rainy",
    "weather_icon": "rain",
    "weather_desc": "中雨",
    "temperature": 28, "humidity": 65,
    "wind_speed": 15, "visibility": 10,
    "driving_context": "雨天+晚高峰，建议减速慢行",
    "risk_score": 0.65,
    "alerts": [{"level": "warning", "text": "...", "icon": "⚠️"}],
    "reasoning": "..."
  }
"""
import logging
import os
import time
from datetime import datetime
from typing import Optional, Dict, Any

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))), '.env'))

logger = logging.getLogger(__name__)

# ── 天气 API 配置 ──
def _get_openweather_key() -> str:
    """从环境变量读取 OpenWeatherMap API Key"""
    return os.getenv("OPENWEATHER_API_KEY", "")

def _build_openweather_url(city: str = None, lat: float = None, lon: float = None) -> str:
    """构建 OpenWeatherMap 请求 URL（API Key 从环境变量读取）"""
    key = _get_openweather_key()
    if not key:
        logger.warning("OPENWEATHER_API_KEY 未配置，OpenWeatherMap 数据源不可用")
        return ""
    if lat is not None and lon is not None:
        return (
            f"https://api.openweathermap.org/data/2.5/weather"
            f"?lat={lat}&lon={lon}&appid={key}&units=metric&lang=zh_cn"
        )
    return (
        f"https://api.openweathermap.org/data/2.5/weather"
        f"?q={city}&appid={key}&units=metric&lang=zh_cn"
    )
WTTR_URL = "https://wttr.in/{city}?format=j1"
DEFAULT_CITY = "Beijing"

# ── GPS 反查城市配置 ──
# 高德 Web 服务 API（免费额度足够实训用）
# 如未配置 key，将降级为 OpenWeatherMap 返回的城市名
AMAP_REVERSE_URL = (
    "https://restapi.amap.com/v3/geocode/regeo"
    "?location={lon},{lat}&key={key}&extensions=base"
)


def _get_amap_key():
    """动态读取高德 API Key"""
    return os.getenv("AMAP_API_KEY", "")

# ── 天气→中文+图标映射 ──
WEATHER_META = {
    # (类型, 图标, Emoji)
    "rain":     {"icon": "rain",     "emoji": "🌧️", "cn": "雨"},
    "drizzle":  {"icon": "rain",     "emoji": "🌦️", "cn": "毛毛雨"},
    "shower":   {"icon": "rain",     "emoji": "🌧️", "cn": "阵雨"},
    "thunder":  {"icon": "rain",     "emoji": "⛈️", "cn": "雷雨"},
    "snow":     {"icon": "snow",     "emoji": "❄️", "cn": "雪"},
    "sleet":    {"icon": "snow",     "emoji": "🌨️", "cn": "雨夹雪"},
    "ice":      {"icon": "snow",     "emoji": "🧊", "cn": "冰雹"},
    "hail":     {"icon": "snow",     "emoji": "🧊", "cn": "冰雹"},
    "fog":      {"icon": "fog",      "emoji": "🌫️", "cn": "雾"},
    "mist":     {"icon": "fog",      "emoji": "🌫️", "cn": "薄雾"},
    "haze":     {"icon": "fog",      "emoji": "🌫️", "cn": "霾"},
    "cloud":    {"icon": "cloud",    "emoji": "☁️", "cn": "多云"},
    "overcast": {"icon": "cloud",    "emoji": "☁️", "cn": "阴天"},
    "sunny":    {"icon": "sun",      "emoji": "☀️", "cn": "晴"},
    "clear":    {"icon": "sun",      "emoji": "☀️", "cn": "晴"},
    "unknown":  {"icon": "unknown",  "emoji": "❓", "cn": "未知"},
}

# 中文+英文关键词→weather类型（必须与 WEATHER_META 的 key 一致）
WEATHER_KEYWORDS = {
    # ── 雨 → rain ──
    "雨": "rain", "rain": "rain", "drizzle": "rain",
    "shower": "rain", "雷": "rain", "thunder": "rain",
    "阵雨": "rain", "暴雨": "rain", "毛毛雨": "rain",
    # ── 雪 → snow ──
    "雪": "snow", "snow": "snow", "sleet": "snow",
    "ice": "snow", "冰": "snow", "hail": "snow", "雹": "snow",
    # ── 雾/霾 → fog ──
    "雾": "fog", "fog": "fog", "mist": "fog",
    "霾": "fog", "haze": "fog", "尘": "fog",
    # ── 云/阴 → cloud ──
    "云": "cloud", "阴": "cloud", "cloud": "cloud",
    "overcast": "cloud", "多云": "cloud",
    # ── 晴 → sun ──
    "晴": "sunny", "sunny": "sunny", "clear": "sunny",
    "sun": "sunny",
}


class EnvironmentAgent:
    """环境 Agent — 时间+天气上下文分析（增强版）"""

    # ── 模块级单例（共享缓存 + 懒加载 LLM）──
    _llm_client = None
    _llm_disabled = False  # Key 有效，重置禁用标志
    _log_client = None

    def __init__(self):
        self._weather_cache: Dict[str, tuple] = {}  # city → (weather_dict, fetch_time)
        self._cache_ttl = 600  # 天气缓存10分钟

    @property
    def llm(self):
        """懒加载 LLM 客户端（首次调用才初始化，避免启动卡顿）"""
        if EnvironmentAgent._llm_client is None:
            try:
                from modules.ai.deepseek_client import DeepSeekClient
                EnvironmentAgent._llm_client = DeepSeekClient()
            except Exception:
                EnvironmentAgent._llm_client = False
        return EnvironmentAgent._llm_client if EnvironmentAgent._llm_client is not False else None

    @property
    def log_client(self):
        """懒加载交互日志"""
        if EnvironmentAgent._log_client is None:
            try:
                from modules.system.interaction_logger import interaction_logger
                EnvironmentAgent._log_client = interaction_logger
            except Exception:
                EnvironmentAgent._log_client = False
        return EnvironmentAgent._log_client if EnvironmentAgent._log_client is not False else None

    def analyze(self, data: dict = None) -> dict:
        """
        获取时间+天气，输出驾驶上下文建议。

        Args:
            data: 可选，支持三种输入方式：
              1. {"city": "Beijing"}      — 指定城市名
              2. {"lat": 39.9, "lon": 116.4}  — GPS 坐标，自动反查城市
              3. {}                        — 使用默认城市

        Returns:
            完整的环境分析结果，含 city / lat / lon / location_source 字段
        """
        if data is None:
            data = {}

        # ── 定位逻辑（GPS 优先）──
        lat = data.get("lat")
        lon = data.get("lon")
        city = data.get("city")
        location_source = "default"

        if lat is not None and lon is not None:
            # GPS 坐标输入：反查城市名
            location_source = "gps"
            resolved_city = self._reverse_geocode(lat, lon)
            if resolved_city:
                city = resolved_city
                location_source = "gps_resolved"
            elif city is None:
                city = DEFAULT_CITY
                location_source = "gps_fallback"
        elif city is None:
            city = DEFAULT_CITY
            location_source = "default"

        t_start = time.time()

        # 1. 时间分析
        now = datetime.now()
        hour = now.hour
        time_of_day, time_tip = self._analyze_time(hour)

        # 2. 天气获取（带缓存，双源，支持 GPS 坐标）
        weather_data = self._fetch_weather(city, lat=lat, lon=lon)

        # 3. 风险评分
        risk_score = self._compute_risk_score(time_of_day, weather_data)

        # 4. 构建上下文
        context = self._build_context(time_of_day, time_tip, weather_data)

        # 5. LLM 推理 或 规则兜底
        if not EnvironmentAgent._llm_disabled and self.llm:
            llm_result = self._llm_analyze(context)
        else:
            llm_result = self._fallback_analyze(context)

        # 6. 记录交互日志
        processing_time = time.time() - t_start
        if self.log_client:
            try:
                self.log_client.log_interaction(
                    interaction_type="environment_analysis",
                    modality="system",
                    input_data={"city": city, "time_of_day": time_of_day},
                    ai_response={
                        "driving_context": llm_result.get("driving_context", ""),
                        "risk_score": risk_score,
                        "alerts": llm_result.get("alerts", []),
                    },
                    processing_time=processing_time,
                    success=True,
                )
            except Exception:
                pass

        return {
            "time_of_day": time_of_day,
            "weather": weather_data.get("weather", "unknown"),
            "weather_icon": weather_data.get("weather_icon", "unknown"),
            "weather_emoji": weather_data.get("weather_emoji", "❓"),
            "weather_desc": weather_data.get("weather_desc", "天气数据不可用"),
            "temperature": weather_data.get("temperature"),
            "humidity": weather_data.get("humidity"),
            "wind_speed": weather_data.get("wind_speed"),
            "visibility": weather_data.get("visibility"),
            "driving_context": llm_result["driving_context"],
            "risk_score": risk_score,
            "alerts": llm_result["alerts"],
            "reasoning": llm_result.get("reasoning", ""),
            "city": city,
            "lat": lat,
            "lon": lon,
            "location_source": location_source,
            "timestamp": now.isoformat(),
        }

    # ── 时间分析（增强：7 段）──

    @staticmethod
    def _analyze_time(hour: int) -> tuple:
        """返回 (time_of_day, tip) — 7 段划分"""
        if 5 <= hour < 7:
            return "dawn", "黎明时分，能见度较低，请开车灯"
        elif 7 <= hour < 9:
            return "morning_rush", "早高峰时段，车流量大，注意车距"
        elif 9 <= hour < 12:
            return "morning", "上午时段，路况良好"
        elif 12 <= hour < 14:
            return "noon", "午后易疲劳，注意休息"
        elif 14 <= hour < 17:
            return "afternoon", "下午时段，光线变化注意安全"
        elif 17 <= hour < 19:
            return "evening_rush", "晚高峰时段，注意行人和非机动车"
        elif 19 <= hour < 22:
            return "evening", "夜间行车，请开车灯，控制车速"
        else:
            return "night", "深夜时段，注意疲劳驾驶"

    # ── 天气获取（双源）──

    def _fetch_weather(self, city: str, lat: float = None, lon: float = None) -> dict:
        """获取天气数据：优先高德天气（国内快），降级 OpenWeatherMap，再降级 wttr.in"""
        now_ts = time.time()

        # 缓存键：有 GPS 坐标时用坐标做 key，否则用城市名
        cache_key = f"{lat:.4f},{lon:.4f}" if (lat is not None and lon is not None) else city

        # 缓存命中（10分钟有效期）
        if cache_key in self._weather_cache:
            cached_data, cached_time = self._weather_cache[cache_key]
            if (now_ts - cached_time) < self._cache_ttl:
                return cached_data

        # 优先：高德天气 API（国内快速）
        result = self._try_amap_weather(city)
        if result is None:
            # 降级 OpenWeatherMap
            result = self._try_openweather(city, lat=lat, lon=lon)
        if result is None:
            # 降级 wttr.in
            result = self._try_wttr(city)
        if result is None:
            result = self._unknown_weather()

        self._weather_cache[cache_key] = (result, now_ts)
        logger.info(
            f"天气更新: {city} {result.get('temperature')}°C "
            f"{result.get('weather_desc', '')} "
            f"(湿度{result.get('humidity')}% 风速{result.get('wind_speed')}km/h)"
        )
        return result

    def _try_amap_weather(self, city: str) -> Optional[dict]:
        """高德天气 API（国内快速，需要 adcode）"""
        amap_key = _get_amap_key()
        if not amap_key:
            return None
        try:
            import httpx

            # Step 1: 城市名 → adcode（高德地理编码 API）
            geo_url = f"https://restapi.amap.com/v3/geocode/geo?address={city}&key={amap_key}"
            geo_resp = httpx.get(geo_url, timeout=5.0)
            if geo_resp.status_code != 200:
                return None
            geo_data = geo_resp.json()
            if geo_data.get("status") != "1" or not geo_data.get("geocodes"):
                return None
            adcode = geo_data["geocodes"][0].get("adcode", "")
            if not adcode:
                return None

            # Step 2: adcode → 天气实况
            weather_url = f"https://restapi.amap.com/v3/weather/weatherInfo?city={adcode}&key={amap_key}&extensions=base"
            w_resp = httpx.get(weather_url, timeout=5.0)
            if w_resp.status_code != 200:
                return None
            w_data = w_resp.json()
            if w_data.get("status") != "1" or not w_data.get("lives"):
                return None

            live = w_data["lives"][0]
            weather_text = live.get("weather", "")  # 如"晴"、"小雨"
            temp = self._safe_float(live.get("temperature"))
            humidity = self._safe_int(live.get("humidity"))
            wind_dir = live.get("winddirection", "")
            wind_power = live.get("windpower", "")  # 如"≤3级"

            # 风力等级 → 风速 km/h（粗略换算）
            wind_kmph = 0
            if wind_power:
                try:
                    level = int(wind_power.replace("≤", "").replace("级", ""))
                    wind_kmph = level * 5  # 粗略：1级≈5km/h
                except ValueError:
                    pass

            # 天气描述 → 类型映射
            weather_type = "unknown"
            for kw, wtype in WEATHER_KEYWORDS.items():
                if kw in weather_text:
                    weather_type = wtype
                    break

            meta = WEATHER_META.get(weather_type, WEATHER_META["unknown"])

            return {
                "temperature": temp,
                "humidity": humidity,
                "weather": weather_type,
                "weather_icon": meta["icon"],
                "weather_emoji": meta["emoji"],
                "weather_desc": weather_text,
                "wind_speed": wind_kmph,
                "wind_direction": wind_dir,
                "visibility": None,
                "data_source": "amap",
                "report_time": live.get("reporttime", ""),
            }

        except Exception as e:
            logger.debug(f"高德天气查询失败: {e}")
            return None

    def _try_openweather(self, city: str, lat: float = None, lon: float = None) -> Optional[dict]:
        """OpenWeatherMap API（支持城市名或 GPS 坐标查询）"""
        try:
            import httpx
            url = _build_openweather_url(city=city, lat=lat, lon=lon)
            if not url:
                return None  # API Key 未配置
            resp = httpx.get(url, timeout=8.0)
            if resp.status_code != 200:
                return None
            data = resp.json()

            main = data.get("main", {})
            weather_list = data.get("weather", [{}])
            weather_item = weather_list[0] if weather_list else {}
            wind = data.get("wind", {})

            temp_c = self._safe_float(main.get("temp"))
            humidity = self._safe_int(main.get("humidity"))
            wind_kmph = self._safe_float(wind.get("speed", 0)) * 3.6  # m/s → km/h
            visibility_m = data.get("visibility", 10000)
            visibility_km = round(visibility_m / 1000, 1) if visibility_m else None

            weather_desc = weather_item.get("description", "")
            weather_type = self._classify_weather(weather_desc)
            weather_meta = WEATHER_META.get(weather_type, WEATHER_META["unknown"])

            return {
                "weather": weather_type,
                "weather_icon": weather_meta["icon"],
                "weather_emoji": weather_meta["emoji"],
                "weather_desc": weather_desc or weather_meta["cn"],
                "temperature": temp_c,
                "humidity": humidity,
                "wind_speed": round(wind_kmph, 1) if wind_kmph else None,
                "visibility": visibility_km,
            }
        except Exception:
            return None

    def _try_wttr(self, city: str) -> Optional[dict]:
        """wttr.in 免费 API（兜底）"""
        try:
            import httpx
            url = WTTR_URL.format(city=city)
            resp = httpx.get(url, timeout=8.0)
            if resp.status_code != 200:
                return None

            data = resp.json()
            current = data.get("current_condition", [{}])[0]
            if not current:
                return None

            temp_c = self._safe_float(current.get("temp_C"))
            humidity = self._safe_int(current.get("humidity"))
            wind_kmph = self._safe_int(current.get("windspeedKmph"))
            visibility_km = self._safe_float(current.get("visibility"))

            weather_desc = ""
            wd_list = current.get("weatherDesc", [])
            if wd_list:
                weather_desc = wd_list[0].get("value", "")

            weather_type = self._classify_weather(weather_desc)
            weather_meta = WEATHER_META.get(weather_type, WEATHER_META["unknown"])

            return {
                "weather": weather_type,
                "weather_icon": weather_meta["icon"],
                "weather_emoji": weather_meta["emoji"],
                "weather_desc": weather_desc or weather_meta["cn"],
                "temperature": temp_c,
                "humidity": humidity,
                "wind_speed": wind_kmph,
                "visibility": visibility_km,
            }
        except Exception:
            return None

    def _reverse_geocode(self, lat: float, lon: float) -> Optional[str]:
        """
        GPS 坐标反查城市名。
        优先用高德 API（精确到区/县），失败时尝试从 OpenWeatherMap 返回的城市名提取。
        """
        # 方案 1：高德 regeo API（如果配置了 key）
        amap_key = _get_amap_key()
        if amap_key:
            try:
                import httpx
                url = AMAP_REVERSE_URL.format(lat=lat, lon=lon, key=amap_key)
                resp = httpx.get(url, timeout=3.0)
                if resp.status_code == 200:
                    data = resp.json()
                    if data.get("status") == "1":
                        comp = data.get("regeocode", {}).get("addressComponent", {})
                        city = comp.get("city") or comp.get("province") or ""
                        if city and city != "[]":
                            return city
            except Exception:
                pass

        # 方案 2：从 OpenWeatherMap 返回的城市名提取
        try:
            import httpx
            url = _build_openweather_url(lat=lat, lon=lon)
            if not url:
                return None  # API Key 未配置
            resp = httpx.get(url, timeout=3.0)
            if resp.status_code == 200:
                data = resp.json()
                city_name = data.get("name", "")
                if city_name:
                    return city_name
        except Exception:
            pass

        return None

    @staticmethod
    def _unknown_weather() -> dict:
        return {
            "weather": "unknown",
            "weather_icon": "unknown",
            "weather_emoji": "❓",
            "weather_desc": "天气数据不可用",
            "temperature": None,
            "humidity": None,
            "wind_speed": None,
            "visibility": None,
        }

    @staticmethod
    def _classify_weather(desc: str) -> str:
        """天气描述→简化类型（中文+英文关键词，长词优先匹配）"""
        if not desc:
            return "unknown"
        desc_lower = desc.lower()
        # 按关键词长度降序排列，长词优先（如"多云">"云"）
        sorted_keywords = sorted(WEATHER_KEYWORDS.items(), key=lambda x: -len(x[0]))
        for keyword, weather_type in sorted_keywords:
            if keyword in desc_lower:
                return weather_type
        return "unknown"

    # ── 风险评分 ──

    @staticmethod
    def _compute_risk_score(time_of_day: str, weather: dict) -> float:
        """综合时间+天气计算驾驶风险分数 (0.0~1.0)"""
        score = 0.0

        # 时间风险
        time_risk = {
            "dawn": 0.2, "morning_rush": 0.25, "morning": 0.0,
            "noon": 0.1, "afternoon": 0.0, "evening_rush": 0.3,
            "evening": 0.2, "night": 0.35,
        }
        score += time_risk.get(time_of_day, 0.0)

        # 天气风险
        weather_type = weather.get("weather", "unknown")
        weather_risk = {
            "rain": 0.3, "snow": 0.4, "fog": 0.35, "cloud": 0.05, "sunny": 0.0,
            "rainy": 0.3, "snowy": 0.4, "foggy": 0.35, "cloudy": 0.05,
        }
        score += weather_risk.get(weather_type, 0.0)

        # 温度风险
        temp = weather.get("temperature")
        if temp is not None:
            if temp > 38 or temp < -10:
                score += 0.1
            elif temp > 35 or temp < -5:
                score += 0.05

        # 能见度风险
        vis = weather.get("visibility")
        if vis is not None:
            if vis < 1:
                score += 0.15
            elif vis < 5:
                score += 0.05

        return round(min(score, 1.0), 2)

    # ── LLM 分析 ──

    @staticmethod
    def _build_context(time_of_day: str, time_tip: str, weather: dict) -> dict:
        return {
            "time_of_day": time_of_day,
            "time_tip": time_tip,
            "weather_type": weather.get("weather", "unknown"),
            "weather_desc": weather.get("weather_desc", ""),
            "weather_emoji": weather.get("weather_emoji", "❓"),
            "temperature": weather.get("temperature", "未知"),
            "humidity": weather.get("humidity", "未知"),
            "wind_speed": weather.get("wind_speed", "未知"),
            "visibility": weather.get("visibility", "未知"),
        }

    def _llm_analyze(self, context: dict) -> dict:
        """DeepSeek 环境推理"""
        import json
        prompt = f"""
你是车载智能驾驶系统的环境分析专家。请根据环境数据分析驾驶风险并给出建议。

## 环境数据
- 时段: {context['time_of_day']} ({context['time_tip']})
- 天气: {context['weather_desc']} ({context['weather_type']})
- 温度: {context['temperature']}°C
- 湿度: {context['humidity']}%
- 风速: {context['wind_speed']}km/h
- 能见度: {context['visibility']}km

## 任务
1. 综合判断驾驶环境的风险等级（low/medium/high/critical）
2. 给出简洁的驾驶建议（一句话，适合语音播报，15字以内）
3. 识别需要预警的事项（最多3条）

严格按 JSON 格式输出：
{{"driving_context": "一句话建议", "alerts": [{{"level": "warning", "text": "...", "icon": "⚠️"}}], "reasoning": "推理过程"}}
"""
        try:
            response = self.llm.client.chat.completions.create(
                model="deepseek-chat",
                messages=[
                    {"role": "system", "content": "你是专业的驾驶环境分析专家，只输出JSON。"},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.3,
                max_tokens=500,
            )
            content = response.choices[0].message.content
            if "```json" in content:
                json_str = content.split("```json")[1].split("```")[0].strip()
            else:
                json_str = content.strip()
            result = json.loads(json_str)
            return {
                "driving_context": result.get("driving_context", "路况正常"),
                "alerts": result.get("alerts", []),
                "reasoning": result.get("reasoning", ""),
            }
        except Exception as e:
            err_msg = str(e)
            # 401 认证失败 → 永久禁用 LLM，不再重试
            if "401" in err_msg or "Authentication" in err_msg or "invalid" in err_msg:
                logger.warning(f"LLM API Key 无效，永久切换为规则模式")
                EnvironmentAgent._llm_disabled = True
            else:
                logger.warning(f"LLM 环境分析失败: {e}，降级为规则")
            return self._fallback_analyze(context)

    @staticmethod
    def _fallback_analyze(context: dict) -> dict:
        """规则兜底"""
        time_of_day = context.get("time_of_day", "daytime")
        time_tip = context.get("time_tip", "")
        weather = {
            "weather": context.get("weather_type", "unknown"),
            "weather_desc": context.get("weather_desc", ""),
            "temperature": context.get("temperature"),
            "humidity": context.get("humidity"),
            "wind_speed": context.get("wind_speed"),
            "visibility": context.get("visibility"),
        }
        driving_context = EnvironmentAgent._generate_driving_context(
            time_of_day, time_tip, weather
        )
        alerts = EnvironmentAgent._generate_alerts(weather)
        return {
            "driving_context": driving_context,
            "alerts": alerts,
            "reasoning": "基于规则引擎的本地推理",
        }

    # ── 驾驶建议 ──

    @staticmethod
    def _generate_driving_context(time_of_day: str, time_tip: str, weather: dict) -> str:
        weather_type = weather.get("weather", "unknown")
        is_bad = weather_type in ("rain", "rainy", "snow", "snowy", "fog", "foggy")

        if is_bad:
            desc = weather.get("weather_desc", weather_type)
            parts = [f"{desc}天气"]
            rush_times = ("morning_rush", "evening_rush")
            if time_of_day in rush_times:
                parts.append("高峰期")
            elif time_of_day in ("night", "dawn"):
                parts.append("能见度低")
            parts.append("请减速慢行，保持安全车距")
            return "，".join(parts)

        if time_of_day in ("morning_rush", "evening_rush", "night", "dawn"):
            return time_tip

        return "路况正常，祝您驾驶愉快"

    # ── 预警生成 ──

    @staticmethod
    def _generate_alerts(weather: dict) -> list:
        alerts = []
        temp = weather.get("temperature")
        visibility = weather.get("visibility")
        wind = weather.get("wind_speed")

        if temp is not None:
            if temp > 38:
                alerts.append({"level": "warning", "text": f"极端高温{temp}°C，注意防暑降温", "icon": "🌡️"})
            elif temp > 35:
                alerts.append({"level": "warning", "text": f"高温预警：当前{temp}°C", "icon": "🌡️"})
            elif temp < -10:
                alerts.append({"level": "warning", "text": f"极端低温{temp}°C，注意路面结冰", "icon": "🥶"})
            elif temp < 0:
                alerts.append({"level": "info", "text": f"低温{temp}°C，路面可能结冰", "icon": "❄️"})

        if visibility is not None:
            if visibility < 0.5:
                alerts.append({"level": "warning", "text": f"重度浓雾！能见度仅{visibility}km", "icon": "🌫️"})
            elif visibility < 1:
                alerts.append({"level": "warning", "text": f"浓雾天气，能见度{visibility}km，开雾灯", "icon": "🌫️"})
            elif visibility < 5:
                alerts.append({"level": "info", "text": f"能见度{visibility}km，注意观察", "icon": "🌫️"})

        if wind is not None:
            if wind > 60:
                alerts.append({"level": "warning", "text": f"暴风{wind}km/h，注意横风！", "icon": "💨"})
            elif wind > 40:
                alerts.append({"level": "warning", "text": f"大风预警：风速{wind}km/h", "icon": "💨"})
            elif wind > 25:
                alerts.append({"level": "info", "text": f"风力较大：{wind}km/h", "icon": "🍃"})

        return alerts[:3]

    # ── 工具 ──

    @staticmethod
    def _safe_float(value) -> Optional[float]:
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _safe_int(value) -> Optional[int]:
        try:
            return int(value)
        except (TypeError, ValueError):
            return None
