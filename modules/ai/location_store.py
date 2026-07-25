"""
车辆 GPS 位置存储 — 单例模块

提供全系统共享的当前车辆位置，供天气、导航等模块读取。
由前端 /api/location（Web 端）或移动端 uni.getLocation 上报后经后端写入。

设计要点：
  - 线程安全（asyncio / 多线程场景）用一把锁保护
  - 支持 GPS 坐标 (lat/lon) 与反查城市名
  - 记录更新时间，供"定位是否新鲜"判断
"""
import time
import threading
import logging
from typing import Optional

logger = logging.getLogger(__name__)


class LocationStore:
    """车辆位置存储单例"""

    def __init__(self):
        # RLock：update() 内部会调用 snapshot()，需要可重入锁
        self._lock = threading.RLock()
        self._lat: Optional[float] = None
        self._lon: Optional[float] = None
        self._city: Optional[str] = None
        self._source: str = "default"   # gps / manual / default
        self._updated_at: float = 0.0

    # ── 写入 ──

    def update(self, lat: Optional[float] = None, lon: Optional[float] = None,
                city: Optional[str] = None, source: str = "gps") -> dict:
        """更新位置，返回更新后的快照"""
        with self._lock:
            changed = False
            if lat is not None:
                self._lat = float(lat)
                changed = True
            if lon is not None:
                self._lon = float(lon)
                changed = True
            if city is not None:
                self._city = city
            if changed or city:
                self._source = source
                self._updated_at = time.time()
            return self.snapshot()

    # ── 读取 ──

    def snapshot(self) -> dict:
        with self._lock:
            return {
                "lat": self._lat,
                "lon": self._lon,
                "city": self._city,
                "source": self._source,
                "updated_at": self._updated_at,
                "fresh": (time.time() - self._updated_at) < 600 if self._updated_at else False,
            }

    def get_coords(self) -> tuple:
        """返回 (lat, lon)，未定位则 (None, None)"""
        with self._lock:
            return self._lat, self._lon

    def get_city(self) -> Optional[str]:
        with self._lock:
            return self._city


# 全局单例
_location_store: Optional[LocationStore] = None


def get_location_store() -> LocationStore:
    global _location_store
    if _location_store is None:
        _location_store = LocationStore()
    return _location_store
