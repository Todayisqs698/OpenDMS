"""
导航路线服务 — 车辆导航整合

功能：
  1. 地理编码：目的地名称 → 坐标（Nominatim 免费 API，无需 key）
  2. 路线规划：起点(GPS) → 终点 → 路线摘要（OSRM 免费路由，无需 key）
  3. 离线降级：网络不可用时返回直线距离估算 + 提示

设计要点：
  - 全部走免费公开 API（OpenStreetMap 系），无需任何 key
  - 任何异常都降级，不阻塞主流程
  - 结果可直接推送前端地图组件 / 移动端

接口：
  NavigationService().plan(from_lat, from_lon, destination) -> dict
    {
      "success": bool,
      "destination": str,
      "destination_coords": [lat, lon],
      "distance_km": float,
      "duration_min": float,
      "steps": [str],            # 关键转弯提示（最多8条）
      "geometry": [[lat,lon],...],  # 路线折线（用于地图绘制）
      "route_summary": str,
      "source": "osrm" | "fallback"
    }
"""
import logging
import time
from typing import Optional

logger = logging.getLogger(__name__)

# 免费公开 API（无需 key）
NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
OSRM_URL = "https://router.project-osrm.org/route/v1/driving/{lon1},{lat1};{lon2},{lat2}?overview=full&geometries=geojson"

# 地球半径（km），用于直线距离估算
_EARTH_R = 6371.0

# 离线地标表（覆盖国内主要城市/景点，在 Nominatim 不可达时兜底）
_OFFLINE_LANDMARKS = {
    # 北京
    "天安门": (39.9087, 116.3974), "天安门广场": (39.9054, 116.3976),
    "故宫": (39.9163, 116.3972), "北京故宫": (39.9163, 116.3972),
    "颐和园": (39.9999, 116.2755), "圆明园": (40.0080, 116.2980),
    "鸟巢": (39.9929, 116.3960), "国家体育场": (39.9929, 116.3960),
    "水立方": (39.9924, 116.3917), "国家游泳中心": (39.9924, 116.3917),
    "长城": (40.4319, 116.5704), "八达岭长城": (40.4319, 116.5704),
    "北京站": (39.9027, 116.4273), "北京西站": (39.8946, 116.3219),
    "北京南站": (39.8654, 116.3780), "北京首都机场": (40.0801, 116.5846),
    "大兴机场": (39.5098, 116.4108), "首都国际机场": (40.0801, 116.5846),
    "中关村": (39.9836, 116.3164), "王府井": (39.9135, 116.4180),
    "西单": (39.9075, 116.3735), "东单": (39.9144, 116.4247),
    "国贸": (39.9089, 116.4604), "CBD": (39.9089, 116.4604),
    "三里屯": (39.9376, 116.4560), "后海": (39.9420, 116.3820),
    "南锣鼓巷": (39.9376, 116.4036), "798": (39.9847, 116.4969),
    "北京": (39.9042, 116.4074), "北京市": (39.9042, 116.4074),
    # 上海
    "上海": (31.2304, 121.4737), "上海市": (31.2304, 121.4737),
    "外滩": (31.2400, 121.4900), "东方明珠": (31.2397, 121.4997),
    "陆家嘴": (31.2397, 121.4997), "南京路": (31.2358, 121.4800),
    "豫园": (31.2270, 121.4920), "迪士尼": (31.1434, 121.6570),
    "上海迪士尼": (31.1434, 121.6570), "虹桥": (31.1979, 121.3363),
    "浦东机场": (31.1434, 121.8052), "上海站": (31.2497, 121.4555),
    # 广州
    "广州": (23.1291, 113.2644), "广州市": (23.1291, 113.2644),
    "广州塔": (23.1066, 113.3215), "小蛮腰": (23.1066, 113.3215),
    "白云机场": (23.3924, 113.2988), "天河": (23.1357, 113.3610),
    "北京路": (23.1291, 113.2700), "珠江": (23.1066, 113.2644),
    # 深圳
    "深圳": (22.5431, 114.0579), "深圳市": (22.5431, 114.0579),
    "深圳湾": (22.5160, 113.9430), "世界之窗": (22.5380, 113.9870),
    "华强北": (22.5470, 114.0860), "福田": (22.5210, 114.0550),
    "宝安机场": (22.6394, 113.8108),
    # 杭州
    "杭州": (30.2741, 120.1551), "杭州市": (30.2741, 120.1551),
    "西湖": (30.2425, 120.1430), "灵隐寺": (30.2408, 120.0990),
    "千岛湖": (29.6050, 118.9870), "萧山机场": (30.2295, 120.4347),
    # 成都
    "成都": (30.5728, 104.0668), "成都市": (30.5728, 104.0668),
    "春熙路": (30.6558, 104.0811), "宽窄巷子": (30.6741, 104.0612),
    "锦里": (30.6423, 104.0455), "双流机场": (30.5785, 103.9471),
    # 西安
    "西安": (34.3416, 108.9398), "西安市": (34.3416, 108.9398),
    "兵马俑": (34.3853, 109.2794), "钟楼": (34.3416, 108.9398),
    "大雁塔": (34.2196, 108.9636), "咸阳机场": (34.4471, 108.7516),
    # 其他主要城市
    "南京": (32.0603, 118.7969), "苏州": (31.2989, 120.5853),
    "天津": (39.3434, 117.3616), "重庆": (29.5630, 106.5516),
    "武汉": (30.5928, 114.3055), "长沙": (28.2282, 112.9388),
    "青岛": (36.0671, 120.3826), "大连": (38.9140, 121.6147),
    "厦门": (24.4798, 118.0894), "哈尔滨": (45.8038, 126.5350),
}


class NavigationService:
    """导航路线服务"""

    def __init__(self):
        self._cache: dict = {}
        self._cache_ttl = 300  # 5 分钟

    def plan(self, from_lat: Optional[float], from_lon: Optional[float],
             destination: str) -> dict:
        """规划从当前位置到目的地的路线"""
        destination = (destination or "").strip()
        if not destination:
            return self._fail("未提供目的地")

        # 缓存
        cache_key = f"{from_lat:.4f},{from_lon:.4f}|{destination}"
        now = time.time()
        if cache_key in self._cache:
            cached, ts = self._cache[cache_key]
            if now - ts < self._cache_ttl:
                return cached

        # 1. 地理编码目的地
        dst_coords = self._geocode(destination)
        if dst_coords is None:
            return self._fail(f"无法定位目的地「{destination}」")
        dst_lat, dst_lon = dst_coords

        # 2. 无起点（无 GPS）→ 直线估算降级
        if from_lat is None or from_lon is None:
            dist = self._haversine(39.9042, 116.4074, dst_lat, dst_lon)  # 默认北京
            result = {
                "success": True,
                "destination": destination,
                "destination_coords": [dst_lat, dst_lon],
                "distance_km": round(dist, 1),
                "duration_min": round(dist / 40 * 60, 1),  # 假设均速40km/h
                "steps": ["未获取到车辆GPS，已按直线距离估算，请在导航仪确认实际路线"],
                "geometry": [],
                "route_summary": f"距「{destination}」约 {dist:.0f} 公里（估算）",
                "source": "fallback",
            }
            self._cache[cache_key] = (result, now)
            return result

        # 3. 路线规划
        route = self._route_osrm(from_lat, from_lon, dst_lat, dst_lon)
        if route is None:
            dist = self._haversine(from_lat, from_lon, dst_lat, dst_lon)
            result = {
                "success": True,
                "destination": destination,
                "destination_coords": [dst_lat, dst_lon],
                "distance_km": round(dist, 1),
                "duration_min": round(dist / 40 * 60, 1),
                "steps": ["路线服务暂不可用，已按直线距离估算"],
                "geometry": [],
                "route_summary": f"距「{destination}」约 {dist:.0f} 公里（估算）",
                "source": "fallback",
            }
            self._cache[cache_key] = (result, now)
            return result

        result = {
            "success": True,
            "destination": destination,
            "destination_coords": [dst_lat, dst_lon],
            "distance_km": route["distance_km"],
            "duration_min": route["duration_min"],
            "steps": route["steps"],
            "geometry": route["geometry"],
            "route_summary": f"到「{destination}」约 {route['distance_km']:.0f} 公里，"
                             f"预计 {route['duration_min']:.0f} 分钟",
            "source": "osrm",
        }
        self._cache[cache_key] = (result, now)
        return result

    # ── 内部 ──

    def _geocode(self, name: str):
        """地理编码：Nominatim 在线查询 → 离线地标表兜底"""
        name_clean = (name or "").strip()
        if not name_clean:
            return None

        # 1. 在线查询（Nominatim）
        try:
            import httpx
            resp = httpx.get(
                NOMINATIM_URL,
                params={"q": name_clean, "format": "json", "limit": 1},
                headers={"User-Agent": "EdgeGuard/1.0"},
                timeout=4.0,
            )
            if resp.status_code == 200:
                data = resp.json()
                if data:
                    return float(data[0]["lat"]), float(data[0]["lon"])
        except Exception as e:
            logger.debug(f"Nominatim 在线查询失败: {e}")

        # 2. 离线地标表兜底（覆盖主要城市/景点，演示环境也能用）
        for key, coords in _OFFLINE_LANDMARKS.items():
            if key == name_clean or key in name_clean or name_clean in key:
                logger.info(f"使用离线地标表匹配: {name_clean} -> {key} {coords}")
                return coords

        return None

    def _route_osrm(self, lat1, lon1, lat2, lon2):
        """OSRM 驾车路线规划"""
        try:
            import httpx
            url = OSRM_URL.format(lon1=lon1, lat1=lat1, lon2=lon2, lat2=lat2)
            resp = httpx.get(url, timeout=5.0)
            if resp.status_code != 200:
                return None
            data = resp.json()
            routes = data.get("routes", [])
            if not routes:
                return None
            r = routes[0]
            dist_m = r.get("distance", 0)
            dur_s = r.get("duration", 0)
            geom = r.get("geometry", {})
            coords = geom.get("coordinates", [])  # GeoJSON: [lon, lat]
            # 转为 [lat, lon] 便于前端地图
            latlon = [[c[1], c[0]] for c in coords]

            # 提取关键转弯步骤
            steps = []
            for leg in r.get("legs", []):
                for step in leg.get("steps", []):
                    txt = step.get("name") or step.get("ref") or ""
                    if txt and txt not in steps:
                        steps.append(txt)
            steps = steps[:8]

            return {
                "distance_km": round(dist_m / 1000, 1),
                "duration_min": round(dur_s / 60, 1),
                "steps": steps,
                "geometry": latlon,
            }
        except Exception as e:
            logger.warning(f"OSRM 路线规划失败: {e}")
            return None

    @staticmethod
    def _haversine(lat1, lon1, lat2, lon2) -> float:
        """两点直线距离（km）"""
        import math
        phi1, phi2 = math.radians(lat1), math.radians(lat2)
        dphi = math.radians(lat2 - lat1)
        dlam = math.radians(lon2 - lon1)
        a = (math.sin(dphi / 2) ** 2 +
             math.cos(phi1) * math.cos(phi2) * math.sin(dlam / 2) ** 2)
        return 2 * _EARTH_R * math.asin(math.sqrt(a))

    @staticmethod
    def _fail(msg: str) -> dict:
        return {
            "success": False,
            "destination": "",
            "destination_coords": None,
            "distance_km": 0,
            "duration_min": 0,
            "steps": [],
            "geometry": [],
            "route_summary": msg,
            "source": "error",
        }


# 全局单例
_nav_service: Optional[NavigationService] = None


def get_navigation_service() -> NavigationService:
    global _nav_service
    if _nav_service is None:
        _nav_service = NavigationService()
    return _nav_service
