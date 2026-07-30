"""Dedicated trip planner inspired by helloagents-trip-planner's multi-agent flow."""

from __future__ import annotations

import logging
import json
import re
from datetime import datetime, timedelta
from typing import Any, Optional

from .schemas import (
    Attraction,
    Budget,
    DayPlan,
    Hotel,
    Location,
    Meal,
    TripPlan,
    TripRequest,
    WeatherInfo,
)
from .critic import CriticReport, _ROUTE_MAX_ATTRACTIONS, run_critic

logger = logging.getLogger(__name__)


FIELD_ALIASES = {
    "ticketPrice": "ticket_price",
    "ticket_price_yuan": "ticket_price",
    "price": "ticket_price",
    "门票": "ticket_price",
    "门票价格": "ticket_price",
    "visitDuration": "visit_duration",
    "duration": "visit_duration",
    "游览时长": "visit_duration",
    "dayTemp": "day_temp",
    "dayTemperature": "day_temp",
    "白天温度": "day_temp",
    "nightTemp": "night_temp",
    "nightTemperature": "night_temp",
    "夜间温度": "night_temp",
    "dayWeather": "day_weather",
    "白天天气": "day_weather",
    "nightWeather": "night_weather",
    "夜间天气": "night_weather",
    "windDirection": "wind_direction",
    "风向": "wind_direction",
    "windPower": "wind_power",
    "风力": "wind_power",
    "startDate": "start_date",
    "开始日期": "start_date",
    "endDate": "end_date",
    "结束日期": "end_date",
    "weatherInfo": "weather_info",
    "天气信息": "weather_info",
    "forbiddenCities": "forbidden_cities",
    "avoidCities": "forbidden_cities",
    "禁止城市": "forbidden_cities",
    "避开城市": "forbidden_cities",
    "overallSuggestions": "overall_suggestions",
    "summary": "overall_suggestions",
    "总体建议": "overall_suggestions",
    "dayIndex": "day_index",
    "第几天": "day_index",
    "priceRange": "price_range",
    "价格区间": "price_range",
    "estimatedCost": "estimated_cost",
    "estimated_cost_yuan": "estimated_cost",
    "预估费用": "estimated_cost",
    "totalAttractions": "total_attractions",
    "景点费用": "total_attractions",
    "totalHotels": "total_hotels",
    "酒店费用": "total_hotels",
    "totalMeals": "total_meals",
    "餐饮费用": "total_meals",
    "totalTransportation": "total_transportation",
    "交通费用": "total_transportation",
    "imageUrl": "image_url",
    "photoUrl": "image_url",
    "poiId": "poi_id",
    "经度": "longitude",
    "纬度": "latitude",
}


class EdgeGuardTripPlanner:
    """Trip planner with real POI collection, LLM planning, and deterministic fallback."""

    def plan_from_text(
        self,
        query: str,
        city: str,
        days: int = 1,
        preference: Optional[str] = None,
        origin: str = "",
        waypoints: Optional[list[str]] = None,
        forbidden_cities: Optional[list[str]] = None,
    ) -> dict:
        request = TripRequest.from_text(
            city=city,
            days=days,
            preference=preference,
            query=query,
            origin=origin,
            waypoints=waypoints,
            forbidden_cities=forbidden_cities,
        )
        trip_plan = self.plan_trip(request)
        legacy = trip_plan.to_legacy_payload()
        return {
            "success": True,
            "type": "trip_plan",
            "reply": self._build_reply(legacy),
            "weather": legacy.get("weather_info", [{}])[0] if legacy.get("weather_info") else {},
            "trip_plan": legacy,
            "trip_schema": trip_plan.model_dump(),
            "suggestions": [
                self._trip_title(trip_plan),
                f"预算¥{legacy.get('budget', {}).get('total', '--')}",
            ],
            "needs_clarification": False,
        }

    def plan_trip(self, request: TripRequest) -> TripPlan:
        logger.info(
            "TripPlanner: city=%s days=%s preferences=%s",
            request.city,
            request.travel_days,
            request.preferences,
        )
        attractions = self._search_attractions(request)
        weather_info = self._query_weather(request)
        hotels = self._search_hotels(request, attractions)
        interpreted_context = self._interpret_context(request, attractions, weather_info, hotels)
        llm_plan = self._llm_plan_trip(request, attractions, weather_info, hotels, interpreted_context)
        if llm_plan:
            return llm_plan

        days = self._assemble_days(request, attractions, hotels)
        budget = self._calculate_budget(days)
        suggestions = self._overall_suggestions(request, weather_info, budget)
        return TripPlan(
            city=request.city,
            origin=request.origin,
            waypoints=request.waypoints,
            forbidden_cities=request.forbidden_cities,
            route_summary=self._route_summary(request),
            start_date=request.start_date,
            end_date=request.end_date,
            days=days,
            weather_info=weather_info,
            overall_suggestions=suggestions,
            budget=budget,
        )

    def _search_attractions(self, request: TripRequest) -> list[Attraction]:
        from modules.ai.tools import search_attractions
        from .xhs_service import search_xhs_attractions, is_xhs_available, llm_enhance_attractions

        preference = request.preferences[0] if request.preferences else None
        raw_items = []
        existing_names: set[str] = set()
        route_cities = self._route_cities(request)
        per_city_count = max(4, min(8 if request.trip_type == "route" else 6, (request.travel_days * 8 + max(len(route_cities), 1) - 1) // max(len(route_cities), 1)))
        for city in route_cities:
            result = search_attractions(
                city=city,
                weather="",
                count=per_city_count,
                preference=preference,
            )
            city_items: list[dict] = []
            if result.get("success"):
                for item in result.get("attractions", []):
                    item.setdefault("route_city", city)
                    name = item.get("name", "")
                    if name and name not in existing_names:
                        raw_items.append(item)
                        city_items.append(item)
                        existing_names.add(name)

            # ── 数据源增强策略：XHS 优先，LLM 兜底 ──────────────────
            # 高德 POI 只有基础字段（名称/地址/评分/估算时长），
            # 缺少真实游览评价和预约提示。
            # 优先用小红书游记提纯（真实用户内容），Cookie 不可用或失效时
            # 用 LLM 基于景点名称/类型生成游览建议作为 fallback。
            xhs_succeeded = False
            if is_xhs_available():
                try:
                    xhs_items = search_xhs_attractions(
                        city=city,
                        keywords=preference or "",
                        preference=preference,
                    )
                    if xhs_items:
                        raw_items = self._merge_xhs_attractions(raw_items, xhs_items, city)
                        xhs_succeeded = True
                    # else: XHS 返回空（Cookie 可能已失效），走 LLM 兜底
                except Exception as e:
                    logger.warning("XHS 增强失败 city=%s: %s", city, e)
            # XHS 未配置 / 返回空 / 异常时，用 LLM 增强高德 POI
            if not xhs_succeeded and city_items:
                try:
                    llm_enhance_attractions(city_items, city, preference)
                except Exception as e:
                    logger.warning("LLM 增强失败 city=%s: %s", city, e)

        # ── 搜索用户指定的 must_go / can_go 景点 ──────────────────
        # 用户说"想去西湖"时，西湖可能不在通用搜索结果中（高德 POI 搜索
        # 可能返回同一景区的多个子景点而非西湖本身）。这里用景点名称
        # 作为关键词单独搜索，确保用户想去的景点出现在候选列表中。
        specified_places = list(request.must_go) + list(request.can_go)
        for place in specified_places:
            place = place.strip()
            if not place or place in existing_names:
                continue
            for city in route_cities:
                item = self._search_specific_poi(city, place)
                if item:
                    name = item.get("name", "")
                    if name and name not in existing_names:
                        raw_items.append(item)
                        existing_names.add(name)
                        logger.info("用户指定景点搜索成功: %s (城市=%s)", name, city)
                    break

        attractions = [self._to_attraction(item) for item in raw_items]

        # ── 合并同一景区的子景点 ──────────────────────────────────
        # 高德 POI 搜索常返回同一景区的多个子区域（如"灵隐寺""灵隐寺-天王殿"
        # "济公殿"等），LLM 常常无视合并指令把它们拆成独立景点。
        # 这里在发送给 LLM 之前程序化合并，确保一个景区只占一个景点条目。
        attractions = self._merge_sub_attractions(attractions)

        if attractions:
            return attractions

        return [
            Attraction(
                name=f"{city}核心停靠点",
                address=city,
                description=f"{city}代表性目的地，适合纳入自驾行程。",
                category="景点",
                ticket_price=0,
                route_city=city,
            )
            for city in route_cities
        ]

    # 常见景点/地点缩写 → 全称映射，提升高德 POI 搜索命中率
    _ABBREVIATION_MAP = {
        "浙大": "浙江大学",
        "复旦": "复旦大学",
        "清华": "清华大学",
        "北大": "北京大学",
        "南大": "南京大学",
        "武大": "武汉大学",
        "厦大": "厦门大学",
        "中大": "中山大学",
        "川大": "四川大学",
        "交大": "交通大学",
        "上交": "上海交通大学",
        "北外": "北京外国语大学",
        "上外": "上海外国语大学",
        "国博": "国家博物馆",
        "军博": "军事博物馆",
        "科技馆": "科学技术馆",
    }

    def _expand_search_keyword(self, place_name: str) -> list[str]:
        """扩展搜索关键词：缩写 → 全称，返回 [缩写, 全称] 列表用于多轮搜索。"""
        keywords = [place_name]
        full_name = self._ABBREVIATION_MAP.get(place_name)
        if full_name and full_name != place_name:
            keywords.append(full_name)
        # 如果 place_name 本身就是全称，也尝试缩写反向匹配
        for abbr, full in self._ABBREVIATION_MAP.items():
            if place_name == full and abbr not in keywords:
                keywords.append(abbr)
        return keywords

    def _poi_name_matches(self, poi_name: str, search_term: str) -> bool:
        """检查高德返回的 POI 名称是否与用户搜索词相关。

        避免"浙大"搜索返回"华家池"这类不相关结果。
        """
        if not poi_name or not search_term:
            return False
        poi_name = poi_name.strip()
        search_term = search_term.strip()

        # 精确匹配
        if poi_name == search_term:
            return True

        # 搜索词是 POI 名称的子串（如"西湖"匹配"西湖风景名胜区"）
        if search_term in poi_name:
            return True

        # POI 名称是搜索词的子串（如"浙江大学"匹配搜索词"浙大紫金港"中的"浙江大学"）
        if poi_name in search_term:
            return True

        # 缩写匹配：检查全称和缩写是否互含
        for abbr, full in self._ABBREVIATION_MAP.items():
            terms = {search_term, poi_name}
            if abbr in terms and full in terms:
                return True
            if abbr in search_term and full in poi_name:
                return True
            if full in search_term and abbr in poi_name:
                return True

        return False

    def _search_specific_poi(self, city: str, place_name: str) -> Optional[dict]:
        """用景点名称作为关键词搜索高德 POI，确保用户指定景点出现在候选列表中。

        改进点：
        1. 缩写扩展（浙大 → 浙江大学），多关键词轮询搜索
        2. 移除 types=110000 限制，兼容大学/博物馆等非风景名胜类 POI
        3. 名称相关性校验：丢弃与搜索词无关的高德返回结果
        """
        from modules.ai.tools import _get_amap_key, _AMAP_POI_URL
        import httpx

        amap_key = _get_amap_key()
        if not amap_key:
            return None

        # 扩展搜索关键词（缩写 → 全称）
        search_keywords = self._expand_search_keyword(place_name)

        for keyword in search_keywords:
            try:
                # 不限制 types，让大学/博物馆/公园等都能被搜到
                resp = httpx.get(_AMAP_POI_URL, params={
                    "keywords": keyword,
                    "city": city,
                    "citylimit": "true",
                    "offset": 5,
                    "page": 1,
                    "key": amap_key,
                    "extensions": "all",
                }, timeout=10)
                data = resp.json()
                if data.get("status") != "1":
                    continue

                pois = data.get("pois", [])
                if not pois:
                    continue

                # 遍历返回的 POI，找到名称与搜索词最相关的那个
                poi = None
                for candidate_poi in pois:
                    candidate_name = candidate_poi.get("name", "")
                    if self._poi_name_matches(candidate_name, place_name):
                        poi = candidate_poi
                        break

                # 如果没有名称匹配的 POI，但只有一个结果，仍然采纳
                # （可能是"西湖"匹配到"西湖区XXX"这类情况）
                if poi is None and len(pois) == 1:
                    poi = pois[0]

                if poi is None:
                    logger.debug(
                        "特定景点搜索 '%s'（关键词'%s'）：高德返回 %d 个 POI 但无名称匹配",
                        place_name, keyword, len(pois),
                    )
                    continue

                biz_ext = poi.get("biz_ext", {}) or {}
                photos = poi.get("photos", []) or {}

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
                visit_duration = 120
                if "博物馆" in type_names or "纪念馆" in type_names:
                    visit_duration = 180
                elif "公园" in type_names or "广场" in type_names:
                    visit_duration = 90
                elif "乐园" in type_names:
                    visit_duration = 240
                elif "大学" in type_names or "学院" in type_names:
                    visit_duration = 150

                category = "景点"
                if "博物馆" in type_names:
                    category = "博物馆"
                elif "公园" in type_names:
                    category = "公园"
                elif "乐园" in type_names:
                    category = "主题乐园"
                elif "古迹" in type_names or "遗址" in type_names:
                    category = "历史古迹"
                elif "大学" in type_names or "学院" in type_names:
                    category = "高校"

                return {
                    "name": poi.get("name", ""),
                    "address": poi.get("address", "") or city,
                    "type": type_names,
                    "indoor": False,
                    "weather_hint": "",
                    "category": category,
                    "rating": rating,
                    "ticket_price": ticket_price,
                    "visit_duration": visit_duration,
                    "photo_url": photo_url,
                    "location": poi.get("location", ""),
                    "route_city": city,
                }
            except Exception as e:
                logger.warning("搜索特定景点 '%s'（关键词'%s'）失败: %s", place_name, keyword, e)
                continue

        return None

    def _merge_sub_attractions(self, attractions: list[Attraction]) -> list[Attraction]:
        """合并同一景区的子景点，避免 LLM 把一个景区拆成多个独立景点。

        检测规则：
        1. 名称包含关系：如"灵隐寺-天王殿"包含"灵隐寺"
        2. 子景点地址包含父景点名称
        3. 共享核心地址（如"法云弄1号"）
        """
        if len(attractions) <= 1:
            return attractions

        n = len(attractions)
        used = [False] * n

        # 按名称长度排序（短的优先做父景点），保持原始索引
        order = sorted(range(n), key=lambda i: len(attractions[i].name))

        merged: list[tuple[int, Attraction]] = []
        for i in order:
            if used[i]:
                continue
            parent = attractions[i]
            used[i] = True
            sub_names: list[str] = []

            for j in order:
                if used[j] or j == i:
                    continue
                child = attractions[j]
                if self._is_sub_attraction(parent, child):
                    used[j] = True
                    sub_names.append(child.name)

            if sub_names:
                enhanced = parent.model_copy()
                sub_text = "、".join(sub_names)
                extra = f"景区内还可游览{sub_text}等区域。"
                if enhanced.description:
                    enhanced.description = f"{enhanced.description} {extra}"
                else:
                    enhanced.description = extra
                merged.append((i, enhanced))
            else:
                merged.append((i, parent))

        # 恢复原始顺序
        merged.sort(key=lambda x: x[0])
        return [attr for _, attr in merged]

    def _is_sub_attraction(self, parent: Attraction, child: Attraction) -> bool:
        """判断 child 是否是 parent 的子景点。"""
        parent_name = parent.name.strip()
        child_name = child.name.strip()

        if not parent_name or not child_name or parent_name == child_name:
            return False

        # 规则1：名称包含关系（如"灵隐寺-天王殿"包含"灵隐寺"）
        if parent_name in child_name:
            return True

        # 规则2：child 地址包含 parent 名称
        # 避免误匹配：如"西湖"匹配到"西湖街道"中的行政区划名
        child_addr = child.address or ""
        if parent_name in child_addr:
            idx = child_addr.find(parent_name)
            after = child_addr[idx + len(parent_name):idx + len(parent_name) + 1]
            # 如果后面紧跟行政单位字符，说明是行政区划名（如"西湖街道"），不是景点名
            if after not in ("街", "区", "镇", "路", "弄", "巷", "村", "社"):
                return True

        # 规则3：parent 地址是 child 地址的子串（同一门牌号区域）
        parent_addr = (parent.address or "").strip()
        child_addr_stripped = child_addr.strip()
        if parent_addr and len(parent_addr) >= 5 and parent_addr in child_addr_stripped:
            return True

        return False

    def _query_weather(self, request: TripRequest) -> list[WeatherInfo]:
        from modules.ai.tools import get_weather, get_weather_forecast

        weather_city = request.city
        forecast = get_weather_forecast(city=weather_city, days=request.travel_days)
        forecast_items = forecast.get("forecasts", []) if forecast.get("success") else []
        if forecast_items:
            return [self._to_weather_info(item) for item in forecast_items[:request.travel_days]]

        weather = get_weather(city=weather_city)
        data = weather.get("data", {}) if weather.get("status") == "ok" else {}
        desc = data.get("weather_desc") or data.get("weather") or "未知"
        temp = data.get("temperature") or 0
        start = datetime.strptime(request.start_date, "%Y-%m-%d")
        note = "当前天气复制为多日参考，非真实逐日预报"
        return [
            WeatherInfo(
                date=(start + timedelta(days=i)).strftime("%Y-%m-%d"),
                day_weather=desc,
                night_weather=desc,
                day_temp=temp,
                night_temp=temp,
                wind_direction=str(data.get("wind_direction", "")),
                wind_power=str(data.get("wind_power", "")),
                source="current_copy",
                note=note,
            )
            for i in range(request.travel_days)
        ]

    def _search_hotels(self, request: TripRequest, attractions: list[Attraction]) -> list[Hotel]:
        from modules.ai.tools import search_hotels

        route_cities = self._route_cities(request)
        seen = set()
        all_hotels = []
        for city in route_cities:
            # count=8: 确保有足够的候选供 LLM 按质量/价格筛选
            result = search_hotels(city=city, count=8, preference=request.accommodation)
            for item in result.get("hotels", []) if result.get("success") else []:
                if item.get("name") and item["name"] not in seen:
                    seen.add(item["name"])
                    hotel = self._to_hotel(item)
                    hotel.route_city = city
                    all_hotels.append(hotel)
        if all_hotels:
            return all_hotels
        return [self._fallback_hotel(request, attractions)]

    def _fallback_hotel(self, request: TripRequest, attractions: list[Attraction]) -> Hotel:
        first = attractions[0] if attractions else None
        base_address = first.address if first else request.city
        return Hotel(
            name=f"{request.city}{request.accommodation}",
            address=base_address,
            location=first.location if first else None,
            price_range="300-500元",
            rating="4.5",
            distance="靠近主要游览区域",
            type=request.accommodation,
            estimated_cost=400,
        )

    def _llm_plan_trip(
        self,
        request: TripRequest,
        attractions: list[Attraction],
        weather_info: list[WeatherInfo],
        hotels: list[Hotel],
        interpreted_context: dict[str, str],
    ) -> Optional[TripPlan]:
        try:
            prompt = self._build_planner_prompt(
                request,
                attractions,
                weather_info,
                hotels,
                interpreted_context,
            )
            content = self._llm_text(
                system_prompt=(
                    "你是严谨的旅行规划 Agent。第一职责是替用户做减法，其次才是排行程。"
                    "用户可能列了很多想去的地方，但天数不够的、不顺路的、天气冲突的、与用户讨厌类型冲突的，必须主动砍掉并说明原因。"
                    "行程不是越满越好，是越顺越好。只能返回 JSON，不要输出 Markdown。"
                    "优先使用给定的真实 POI 和酒店候选，不要编造不存在的名称。"
                ),
                user_prompt=prompt,
                max_tokens=4096,
                temperature=0.4,
            )
            if not content:
                return None
            data = _normalize_keys(self._parse_robust_json(content))
            data = self._repair_llm_payload(data, request, attractions, weather_info, hotels)
            trip_plan = TripPlan(**data)

            # ── Critic 反思循环：最多重规划 2 轮 ───────────────────────
            # Critic 只抓确定性硬错误（禁城市/重复/户外暴雨/驾驶过载）。
            # 这些错误不该让用户看到，所以值得一次额外 LLM 调用来修。
            # Critic 自身异常被吞，绝不阻塞主流程。
            max_repair_rounds = 2
            for round_idx in range(max_repair_rounds):
                try:
                    report = run_critic(trip_plan, request)
                except Exception as e:  # noqa: BLE001 — critic 是安全网，不能成为新故障点
                    logger.warning("Critic 运行异常，跳过反思：round=%d err=%s", round_idx, e)
                    break
                if not report.has_blocking:
                    logger.info("Critic 通过（第 %d 轮，无阻塞问题）", round_idx + 1)
                    break

                logger.info(
                    "Critic 发现 %d 个阻塞问题（第 %d 轮），触发重规划：%s",
                    len(report.errors), round_idx + 1,
                    "; ".join(i.message for i in report.errors),
                )
                repaired = self._repair_with_critic(
                    request, attractions, weather_info, hotels, interpreted_context,
                    trip_plan, report,
                )
                if repaired is not None:
                    trip_plan = repaired
                    # 下一轮再校验，确认 LLM 真的修好了
                    continue
                # LLM 重规划失败（超时/异常/空返回）—— 放弃修复，用当前草稿
                logger.warning("Critic 重规划 LLM 调用失败，保留第 %d 轮草稿", round_idx + 1)
                break

            # 最终再跑一次 Critic，把残留问题记日志（不阻塞返回）
            try:
                final_report = run_critic(trip_plan, request)
                if final_report.has_blocking:
                    logger.warning(
                        "Critic 最终仍有 %d 个未修复的阻塞问题：%s",
                        len(final_report.errors),
                        "; ".join(i.message for i in final_report.errors),
                    )
            except Exception as e:  # noqa: BLE001
                logger.debug("最终 Critic 校验跳过：%s", e)

            if trip_plan.budget is None or trip_plan.budget.total <= 0:
                trip_plan.budget = self._calculate_budget(trip_plan.days)
            return trip_plan
        except Exception as e:
            logger.warning("TripPlanner LLM planning failed, using fallback: %s", e)
            return None

    def _repair_with_critic(
        self,
        request: TripRequest,
        attractions: list[Attraction],
        weather_info: list[WeatherInfo],
        hotels: list[Hotel],
        interpreted_context: dict[str, str],
        draft: TripPlan,
        report: CriticReport,
    ) -> Optional[TripPlan]:
        """Call the LLM again with the draft + Critic issues to produce a repair.

        Returns None on any failure so the caller can fall back to the previous
        draft rather than losing the whole plan. Uses a lower temperature for
        more deterministic correction.
        """
        prompt_block = report.prompt_block()
        if not prompt_block:
            return None

        import json as _json
        draft_json = _json.dumps(draft.model_dump(), ensure_ascii=False)

        repair_prompt = f"""你之前生成的行程计划被 Critic 校验出以下确定性错误，必须逐一修正后重新输出完整 JSON。

原始行程（含错误）:
{draft_json}

{prompt_block}

修正要求:
1. 必须修正 Critic 指出的每一个 ERROR 问题，不要遗漏。
2. 禁止城市：移除所有涉及禁止城市「{'、'.join(request.forbidden_cities) or '无'}」的景点/酒店/餐饮/描述。
3. 重复景点：用同城市其他真实候选景点替换重复项。
4. 户外暴雨：把暴雨日的户外景点换成室内景点（博物馆/科技馆/商场等）。
5. 驾驶过载：自驾日减少景点数量到 {_ROUTE_MAX_ATTRACTIONS} 个以内，或把部分景点移到纯游览日。
6. 只能使用给定的真实景点候选，不要编造新景点。
7. 输出完整修正后的行程 JSON，结构与原始一致，不要输出 Markdown 或解释。

真实景点候选:
{_json.dumps([a.model_dump() for a in attractions], ensure_ascii=False)}

真实酒店候选:
{_json.dumps([h.model_dump() for h in hotels], ensure_ascii=False)}
"""
        try:
            content = self._llm_text(
                system_prompt=(
                    "你是严谨的旅行规划 Agent。根据 Critic 反馈修正行程。"
                    "优先删掉不顺路、天数冲突、天气不适配的点，而不是强行全塞进去。"
                    "只能返回修正后的完整 JSON，不要输出 Markdown。"
                ),
                user_prompt=repair_prompt,
                max_tokens=4096,
                temperature=0.2,
            )
            if not content:
                return None
            data = _normalize_keys(self._parse_robust_json(content))
            data = self._repair_llm_payload(data, request, attractions, weather_info, hotels)
            return TripPlan(**data)
        except Exception as e:
            logger.warning("Critic 重规划调用失败：%s", e)
            return None

    def _interpret_context(
        self,
        request: TripRequest,
        attractions: list[Attraction],
        weather_info: list[WeatherInfo],
        hotels: list[Hotel],
    ) -> dict[str, str]:
        return {
            "attractions": self._interpret_attractions(request, attractions, weather_info),
            "weather": self._interpret_weather(request, weather_info),
            "hotels": self._interpret_hotels(request, hotels, attractions),
        }

    def _interpret_attractions(
        self,
        request: TripRequest,
        attractions: list[Attraction],
        weather_info: list[WeatherInfo],
    ) -> str:
        if not attractions:
            return "没有可用的真实景点候选，后续规划需要使用保守 fallback 景点。"

        weather_hint = weather_info[0].day_weather if weather_info else "未知"
        raw = json.dumps([a.model_dump() for a in attractions[:8]], ensure_ascii=False)
        prompt = f"""请解读这些真实景点候选，输出给下游 Planner 使用的简短判断材料。

城市: {request.city}
线路: {self._route_summary(request)}
天数: {request.travel_days}
偏好: {"、".join(request.preferences) if request.preferences else "无特别偏好"}
天气参考: {weather_hint}
景点候选 JSON:
{raw}

请用 4-8 条中文短句说明:
- 哪些景点更适合上午/下午/雨天/高温
- 哪些景点适合组合在同一天
- 哪些景点评分、时长、门票上更值得优先
不要输出 JSON。"""
        return self._llm_text(
            system_prompt="你是景点搜索结果解读 Agent，负责把 POI 原始数据压缩成行程规划判断。",
            user_prompt=prompt,
            max_tokens=1024,
            temperature=0.3,
        ) or self._fallback_attraction_interpretation(attractions, weather_hint)

    def _interpret_weather(self, request: TripRequest, weather_info: list[WeatherInfo]) -> str:
        if not weather_info:
            return "没有获得天气信息，行程排序不要声称基于真实天气预报。"

        raw = json.dumps([w.model_dump() for w in weather_info], ensure_ascii=False)
        source_note = _weather_source_note(weather_info)
        prompt = f"""请把天气信息解读成行程规划约束。

城市: {request.city}
线路: {self._route_summary(request)}
天数: {request.travel_days}
天气 JSON:
{raw}

重要事实: {source_note}

请用 3-5 条中文短句说明:
- 对户外/室内景点顺序的影响
- 对自驾和用餐安排的影响
- overall_suggestions 应如何避免伪装成逐日预报
不要输出 JSON。"""
        return self._llm_text(
            system_prompt="你是天气解读 Agent，负责把天气数据转成旅行规划约束。",
            user_prompt=prompt,
            max_tokens=768,
            temperature=0.2,
        ) or self._fallback_weather_interpretation(weather_info)

    def _interpret_hotels(
        self,
        request: TripRequest,
        hotels: list[Hotel],
        attractions: list[Attraction],
    ) -> str:
        if not hotels:
            return "没有可用酒店候选，若使用估算酒店必须标记 source=estimated。"

        hotel_raw = json.dumps([h.model_dump() for h in hotels[:5]], ensure_ascii=False)
        attraction_names = "、".join(a.name for a in attractions[:6]) or "暂无景点候选"
        prompt = f"""请解读酒店候选，输出给下游 Planner 使用的住宿选择判断。

城市: {request.city}
线路: {self._route_summary(request)}
住宿偏好: {request.accommodation}
主要景点候选: {attraction_names}
酒店候选 JSON:
{hotel_raw}

请用 3-6 条中文短句说明:
- 哪家酒店优先，为什么
- 价格/评分/位置的取舍
- 如果候选来自真实 POI，应提醒下游保留 source=amap
不要输出 JSON。"""
        return self._llm_text(
            system_prompt="你是酒店推荐 Agent，负责把酒店 POI 候选压缩成住宿选择判断。",
            user_prompt=prompt,
            max_tokens=768,
            temperature=0.3,
        ) or self._fallback_hotel_interpretation(hotels, attractions)

    def _llm_text(
        self,
        system_prompt: str,
        user_prompt: str,
        max_tokens: int,
        temperature: float,
    ) -> str:
        try:
            from modules.ai.model_factory import get_model_for_agent
            client = get_model_for_agent("recommend")
            if not client.is_available:
                return ""
            response = client.client.chat.completions.create(
                model=client.chat_model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                max_tokens=max_tokens,
                temperature=temperature,
            )
            return (response.choices[0].message.content or "").strip()
        except Exception as e:
            logger.info("TripPlanner interpretation LLM skipped: %s", e)
            return ""

    def _llm_repair_json(self, broken_json: str) -> str:
        """使用 LLM 修复无法自动修复的 JSON（第 6 层，最终手段）。

        只发送首尾片段以节省 token，让 LLM 补全为合法 JSON。
        """
        import re as _re
        tail = broken_json[-2000:] if len(broken_json) > 2000 else broken_json
        head = broken_json[:500] if len(broken_json) > 500 else broken_json
        repair_prompt = (
            "以下是一段被截断的旅行计划 JSON，请你补全它使其成为合法的 JSON。"
            "只输出修复后的完整 JSON，不要输出任何解释文字。\n\n"
            f"开头部分:\n{head}\n\n...(中间省略)...\n\n尾部被截断部分:\n{tail}"
        )
        content = self._llm_text(
            system_prompt="你是 JSON 修复助手。只输出合法 JSON，不要解释。",
            user_prompt=repair_prompt,
            max_tokens=1500,
            temperature=0.0,
        )
        if not content:
            return broken_json
        try:
            if "```json" in content:
                start = content.find("```json") + 7
                end = content.find("```", start)
                if end > start:
                    return content[start:end].strip()
            if "```" in content:
                start = content.find("```") + 3
                end = content.find("```", start)
                if end > start:
                    return content[start:end].strip()
            match = _re.search(r'\{[\s\S]*\}', content)
            if match:
                return match.group()
            return content
        except Exception as e:
            logger.warning("LLM 修复 JSON 提取失败: %s", e)
            return broken_json

    def _parse_robust_json(self, response: str) -> dict:
        """6 层容错 JSON 解析（移植自 TripStar）。

        层级: 基础清理 → 引号修复 → 截断修复 → 暴力正则 → 组合修复 → LLM 自修复。
        全部失败时抛出 ValueError，由调用方走 fallback。
        """
        import re as _re
        try:
            json_str = _extract_raw_json_str(response)
        except ValueError:
            raise

        json_str = _sanitize_json_str(json_str)

        # 构建各轮修复候选
        parse_attempts: list[tuple[str, str]] = [("基础清理", json_str)]
        fixed_quotes = _fix_unescaped_quotes(json_str)
        if fixed_quotes != json_str:
            parse_attempts.append(("修复未转义引号", fixed_quotes))
        repaired = _repair_truncated_json(json_str)
        if repaired != json_str:
            parse_attempts.append(("截断修复", repaired))
            repaired_fixed = _fix_unescaped_quotes(repaired)
            if repaired_fixed != repaired:
                parse_attempts.append(("截断+引号修复", repaired_fixed))
        match = _re.search(r'\{[\s\S]*\}', json_str)
        if match:
            brutal = _sanitize_json_str(match.group())
            brutal = _fix_unescaped_quotes(brutal)
            parse_attempts.append(("正则提取", brutal))
            brutal_repaired = _repair_truncated_json(brutal)
            if brutal_repaired != brutal:
                parse_attempts.append(("正则+截断修复", brutal_repaired))

        last_error: Optional[Exception] = None
        for attempt_name, candidate in parse_attempts:
            try:
                data = json.loads(candidate)
                if attempt_name != "基础清理":
                    logger.info("JSON 通过「%s」成功解析", attempt_name)
                return data
            except (json.JSONDecodeError, Exception) as e:
                last_error = e
                logger.debug("「%s」解析失败: %s", attempt_name, e)

        # 最终手段: LLM 修复
        logger.info("所有本地修复均失败，尝试使用 LLM 修复 JSON...")
        llm_fixed = self._llm_repair_json(json_str)
        llm_fixed = _sanitize_json_str(llm_fixed)
        try:
            data = json.loads(llm_fixed)
            logger.info("JSON 通过 LLM 修复成功解析")
            return data
        except Exception as e_llm:
            logger.warning("LLM 修复后仍然解析失败: %s", e_llm)
            raise ValueError(f"行程 JSON 解析失败: {last_error}") from last_error

    def _fallback_attraction_interpretation(self, attractions: list[Attraction], weather_hint: str) -> str:
        ranked = sorted(attractions, key=lambda a: a.rating or 0, reverse=True)
        names = "、".join(a.name for a in ranked[:5])
        avg_duration = round(sum(a.visit_duration for a in ranked[:5]) / max(len(ranked[:5]), 1))
        return (
            f"天气参考为{weather_hint}；优先考虑评分较高的{names}。"
            f"候选景点平均游览约{avg_duration}分钟，单日建议控制在2-3个点。"
            "若遇到雨天或高温，应把户外景点放在上午或缩短停留。"
        )

    def _fallback_weather_interpretation(self, weather_info: list[WeatherInfo]) -> str:
        desc = weather_info[0].day_weather if weather_info else "未知"
        return (
            f"天气参考为{desc}，目前不是逐日预报。"
            "规划可以把它作为当天舒适度参考，但总结中不要声称掌握了每天真实天气。"
        )

    def _fallback_hotel_interpretation(self, hotels: list[Hotel], attractions: list[Attraction]) -> str:
        first = hotels[0]
        anchor = attractions[0].name if attractions else "主要景点"
        source_text = "真实高德 POI" if first.source == "amap" else "估算酒店"
        return (
            f"优先考虑{first.name}，来源为{source_text}，价格参考{first.price_range or first.estimated_cost}。"
            f"住宿应尽量靠近{anchor}或当天最后一个景点，减少自驾折返。"
        )

    def _build_planner_prompt(
        self,
        request: TripRequest,
        attractions: list[Attraction],
        weather_info: list[WeatherInfo],
        hotels: list[Hotel],
        interpreted_context: dict[str, str],
    ) -> str:
        attractions_json = json.dumps([a.model_dump() for a in attractions], ensure_ascii=False)
        weather_json = json.dumps([w.model_dump() for w in weather_info], ensure_ascii=False)
        hotels_json = json.dumps([h.model_dump() for h in hotels], ensure_ascii=False)
        preferences = "、".join(request.preferences) if request.preferences else "无特别偏好"
        weather_source_note = _weather_source_note(weather_info)
        # ── 旅客画像 ──
        traveler_parts = []
        if request.pax:
            traveler_parts.append(f"{request.pax}人")
        if request.age_groups:
            ag = {"senior": "有老人", "child": "有小孩", "adult": "成人"}
            traveler_parts.append("、".join(ag.get(g, g) for g in request.age_groups))
        if request.pace != "normal":
            pace_map = {"relaxed": "轻松慢游", "fast": "紧凑高效"}
            traveler_parts.append(pace_map.get(request.pace, request.pace))
        if request.food_budget:
            traveler_parts.append(request.food_budget)
        if request.queue_tolerance:
            qt = {"high": "愿意排队", "low": "不愿排队", "medium": "可排短队"}
            traveler_parts.append(qt.get(request.queue_tolerance, ""))
        if request.walk_tolerance:
            wt = {"high": "能走", "low": "少走路", "medium": ""}
            traveler_parts.append(wt.get(request.walk_tolerance, ""))
        traveler_profile = "、".join(traveler_parts) if traveler_parts else "未指定"

        # ── 地点清单 ──
        place_parts = []
        if request.must_go:
            place_parts.append(f"一定要去: {'、'.join(request.must_go)}")
        if request.can_go:
            place_parts.append(f"想去: {'、'.join(request.can_go)}")
        if request.avoid_places:
            place_parts.append(f"❌ 不要去: {'、'.join(request.avoid_places)}")
        if request.avoid_types:
            place_parts.append(f"❌ 避免类型: {'、'.join(request.avoid_types)}")
        place_constraints = "；".join(place_parts) if place_parts else "无特别要求"

        # ── 喜好 ──
        like_str = "、".join(request.likes) if request.likes else ""
        dislike_str = "、".join(request.dislikes) if request.dislikes else ""

        return f"""请基于真实候选数据，为用户生成结构化行程。

基本信息:
- 行程类型: {"跨城自驾线路" if request.trip_type == "route" else "单城市游"}
- 起点: {request.origin or "未指定"}
- 必经城市: {"、".join(request.waypoints) if request.waypoints else "无"}
- 禁止经过/停靠城市: {"、".join(request.forbidden_cities) if request.forbidden_cities else "无"}
- 终点/目的地: {request.city}
- 完整线路: {self._route_summary(request)}
- 日期: {request.start_date} 至 {request.end_date}
- 天数: {request.travel_days}
- 到达时间: {request.arrival_time or "未指定"}
- 回程时间: {request.departure_time or "未指定"}
- 交通: {request.transportation}
- 住宿偏好: {request.accommodation}
- 酒店: {request.hotel_name + ' ' + request.hotel_address if request.hotel_name else "未指定"}

旅客画像: {traveler_profile}
喜好: {like_str or "未指定"}
不喜欢: {dislike_str or "未指定"}
地点约束: {place_constraints}
游玩偏好: {preferences}
- 用户原话: {request.free_text_input}

真实景点候选:
{attractions_json}

景点解读:
{interpreted_context.get("attractions", "")}

天气信息:
{weather_json}
说明: {weather_source_note}

天气解读:
{interpreted_context.get("weather", "")}

真实酒店候选:
{hotels_json}

酒店解读:
{interpreted_context.get("hotels", "")}

返回 JSON 必须符合下面结构和字段名:
{{
  "city": "{request.city}",
  "start_date": "{request.start_date}",
  "end_date": "{request.end_date}",
  "days": [
    {{
      "date": "YYYY-MM-DD",
      "day_index": 0,
      "description": "说明为什么这样安排",
      "transportation": "{request.transportation}",
      "accommodation": "{request.accommodation}",
      "hotel": {{"name": "酒店名", "address": "地址", "location": {{"longitude": 0, "latitude": 0}}, "price_range": "价格区间", "rating": "评分", "distance": "与景点关系", "type": "酒店类型", "estimated_cost": 400, "source": "amap"}},
      "attractions": [
        {{"name": "景点名", "address": "地址", "location": {{"longitude": 0, "latitude": 0}}, "visit_duration": 120, "description": "结合特色/天气/偏好的具体理由", "category": "景点类别", "rating": 4.5, "ticket_price": 0, "route_city": "当天停靠城市"}}
      ],
      "meals": [
        {{"type": "breakfast", "name": "早餐", "description": "建议", "estimated_cost": 30}},
        {{"type": "lunch", "name": "午餐", "description": "建议", "estimated_cost": 80}},
        {{"type": "dinner", "name": "晚餐", "description": "建议", "estimated_cost": 100}}
      ]
    }}
  ],
  "weather_info": [],
  "overall_suggestions": "3-5句话总结：①每天的区域逻辑 ②天气建议 ③砍掉了什么、为什么砍 ④提前订什么",
  "budget": {{"total_attractions": 0, "total_hotels": 0, "total_meals": 0, "total_transportation": 0, "total": 0}}
}}

要求:
# 核心原则
1. 行程不是越满越好，是越顺越好。替用户做减法比塞满更重要。
2. 每天限定一个主区域，景点之间的交通换乘不超过合理范围。不允许为了某个景点或餐厅让全天路线来回折返。
3. 到达日（第一天）不安排远距离景点，优先靠近酒店或机场的轻活动。离开日（最后一天）上午只排酒店附近轻活动，中午前留出返程时间。
4. 一天最多只放一个重预约点（需要提前订票/限流的景点）。

# 区域与动线
5. 每天的午餐必须在当天主区域内解决。餐厅是旅途中的补给点，不是路线锚点。不允许为了名店反向扭曲全天路线。
6. 每天 description 字段必须说明为什么这样安排（区域逻辑/天气考量/节奏控制）。

# 删点原则
7. must_go（一定要去）是硬约束，必须全部入选。can_go（想去）是软约束，优先但可以取舍。
   avoid_places（不要去）和 avoid_types（避免类型）是硬约束，必须严格避开。
8. 以下情况主动删除并在 overall_suggestions 中说明原因：
   - 天数不够塞的远郊点
   - 与 avoid_places / avoid_types 冲突的点
   - 天气不适配的户外点（给室内备选）
   - 顺路性差、为了它要专门绕半天的点
9. 被删掉的不代表不好，可以建议用户下次专门去。

# 旅客节奏
10. pace=relaxed（轻松慢游）：每天最多 2 个景点，多留休息时间，少排需要大量步行的点。
    pace=fast（紧凑高效）：每天可以排满 3 个，优先步行可达的密集区域。
    age_groups 有 senior（老人）或 child（小孩）：步行距离短、多留厕所/休息点。
11. queue_tolerance=low：避开需要排长队的网红店和热门时段景点。
    walk_tolerance=low：景点之间优先考虑打车/地铁，不要安排需要步行超过 15 分钟的点。
12. likes 里的标签（咖啡/酒吧/甜点/夜景/拍照等）应该体现在 meals 或 attractions 的选择中。
    dislikes 里的内容必须避开，不在任何字段中出现。

# 数据约束
13. 如果行程类型是跨城自驾线路，必须规划完整的起点到终点路线，不能只规划终点城市游；每天要体现路段推进、停靠城市和驾驶节奏。
14. 跨城线路每天必须使用当天停靠城市对应的酒店，不要全程只住一个城市。每个酒店都有 route_city 字段标明它属于哪个城市。
15. 每天安排 1-3 个停靠/游览点，只用当天停靠城市的景点（route_city 匹配当天城市）。不要把西安的景点放在兰州的天里。
16. 全程景点名称不能跨日重复；如果同一城市停留多天，也必须每天选择不同景点。
17. 严格避开禁止城市，不要把禁止城市写入线路、酒店、景点、餐饮或建议中。
18. 根据天气、景点类型、游览时长和自驾动线安排先后顺序。户外景点标记天气敏感，优先配附近室内备选。
19. 只返回一个 JSON 对象。

# 景点去重与子景点合并（重要）
20. 候选列表中如果出现同一景区的多个子区域（如"灵隐寺""灵隐寺-天王殿""灵隐寺-华严殿""济公殿"），必须合并为一个景点条目。用景区主名称（如"灵隐寺"），在 description 中简要提及可游览的主要区域。严禁把一个寺庙/公园拆成 3-4 个独立景点。
21. 同理，同一山脉、同一街区、同一园林的不同入口或分馆也必须合并。判断标准：如果它们在同一个地址、同一个围栏内、步行距离 < 5 分钟，就是一个景点。

# 格式约束
22. 酒店信息（名称、地址、评分）只能出现在 hotel 字段里，严禁出现在 attractions、meals、description 或其他任何字段中。
23. must_go 中的景点必须全部入选且排在当天第一位。can_go 中的景点优先入选，与候选列表同名或高度匹配的直接采纳。用户没提到的候选景点可以自由取舍。
24. 只能使用"真实景点候选"列表中的景点。严禁编造候选列表中不存在的景点名称。如果候选列表中没有某个景点，不要凭空编造，可以少排景点或用候选列表中的其他景点替代。
25. avoid_places 中的地点是硬约束，任何包含该名称的景点都不能出现在行程中（如"避开宋城"→不能有"宋城""宋城千古情"等）。
26. 不要在 JSON 中包含 photos、image_url、poi_id 字段，这些字段会由系统自动填充。不要在 JSON 中写任何 URL。"""

    def _repair_llm_payload(
        self,
        data: dict,
        request: TripRequest,
        attractions: list[Attraction],
        weather_info: list[WeatherInfo],
        hotels: list[Hotel],
    ) -> dict:
        data.setdefault("city", request.city)
        data.setdefault("origin", request.origin)
        data.setdefault("waypoints", request.waypoints)
        data.setdefault("forbidden_cities", request.forbidden_cities)
        data.setdefault("route_summary", self._route_summary(request))
        data.setdefault("start_date", request.start_date)
        data.setdefault("end_date", request.end_date)
        data.setdefault("weather_info", [w.model_dump() for w in weather_info])
        data.setdefault("overall_suggestions", "")

        if not data.get("days"):
            data["days"] = [d.model_dump() for d in self._assemble_days(request, attractions, hotels)]

        for idx, day in enumerate(data.get("days", [])):
            day.setdefault("date", (datetime.strptime(request.start_date, "%Y-%m-%d") + timedelta(days=idx)).strftime("%Y-%m-%d"))
            day.setdefault("day_index", idx)
            day.setdefault("description", f"{request.city}第{idx + 1}天行程")
            day.setdefault("transportation", request.transportation)
            day.setdefault("accommodation", request.accommodation)
            if not day.get("hotel"):
                day["hotel"] = (hotels[0] if hotels else self._fallback_hotel(request, attractions)).model_dump()
            if not day.get("meals"):
                day["meals"] = [m.model_dump() for m in self._default_meals(request.city)]

        data["days"] = self._sanitize_day_payloads(data.get("days", []), request, attractions, hotels)

        if not data.get("budget"):
            temp_plan = TripPlan(
                city=data["city"],
                origin=data.get("origin", ""),
                waypoints=data.get("waypoints", []),
                forbidden_cities=data.get("forbidden_cities", []),
                route_summary=data.get("route_summary", ""),
                start_date=data["start_date"],
                end_date=data["end_date"],
                days=data["days"],
                weather_info=data["weather_info"],
                overall_suggestions=data["overall_suggestions"],
            )
            data["budget"] = self._calculate_budget(temp_plan.days).model_dump()

        return data

    def _assemble_days(
        self,
        request: TripRequest,
        attractions: list[Attraction],
        hotels: list[Hotel],
    ) -> list[DayPlan]:
        start = datetime.strptime(request.start_date, "%Y-%m-%d")
        days = []
        route_cities = self._route_cities(request)
        city_segments = self._split_route_days(route_cities, request.travel_days)
        attractions_by_city = self._group_attractions_by_route_city(attractions, route_cities)
        hotels_by_city = {h.route_city: h for h in hotels if h.route_city}
        used_attraction_names = set()
        city_offsets = {city: 0 for city in route_cities}

        # 用户指定的景点名称集合（must_go + can_go），用于优先排列
        specified_names: set[str] = set(request.must_go)
        specified_names.update(request.can_go)

        for day_index in range(request.travel_days):
            day_city = city_segments[day_index]
            day_pool = attractions_by_city.get(day_city, attractions)
            fb_pools = [v for k, v in attractions_by_city.items() if k != day_city]

            # 第一天优先排列用户指定景点（must_go/can_go）
            if day_index == 0 and specified_names:
                day_pool = sorted(
                    day_pool,
                    key=lambda a: 0 if any(self._poi_name_matches(sn, a.name) for sn in specified_names) else 1,
                )

            day_attractions = self._take_unique_attractions(
                day_pool if day_pool else attractions,
                used_attraction_names,
                city_offsets,
                day_city,
                limit=3 if day_pool else 2,
                fallback_pools=fb_pools,
            )

            # 兜底：如果当天没有景点（候选池耗尽），搜索更多 POI
            if not day_attractions:
                extra = self._search_extra_poi(day_city, used_attraction_names, count=2)
                for attr in extra:
                    if attr.name not in used_attraction_names:
                        day_attractions.append(attr)
                        used_attraction_names.add(attr.name)
                        if len(day_attractions) >= 2:
                            break

            # 最终兜底：复用高评分景点
            if not day_attractions and attractions:
                best = max(attractions, key=lambda a: a.rating or 0)
                day_attractions.append(best)

            date = (start + timedelta(days=day_index)).strftime("%Y-%m-%d")
            day_hotel = hotels_by_city.get(day_city) or (hotels[0] if hotels else self._fallback_hotel(request, attractions))
            days.append(DayPlan(
                date=date,
                day_index=day_index,
                description=self._fallback_day_description(request, day_index, day_city, route_cities),
                transportation=request.transportation,
                accommodation=request.accommodation,
                hotel=day_hotel,
                attractions=day_attractions,
                meals=self._default_meals(day_city),
            ))
        return days

    def _matches_any_candidate(self, name: str, attractions: list[Attraction]) -> bool:
        """检查 LLM 生成的景点名称是否匹配真实候选列表中的任何一个。

        防止 LLM 幻觉：如果 LLM 生成了候选列表中不存在的景点（如"千岛湖""大明山"），
        应该被识别并丢弃，替换为真实候选。
        """
        if not name:
            return False
        for attr in attractions:
            if self._poi_name_matches(name, attr.name):
                return True
        return False

    def _find_matching_candidate(self, name: str, attractions: list[Attraction]) -> Optional[Attraction]:
        """在候选列表中找到与给定名称最匹配的景点。"""
        if not name:
            return None
        # 优先精确匹配
        for attr in attractions:
            if attr.name == name:
                return attr
        # 模糊匹配
        for attr in attractions:
            if self._poi_name_matches(name, attr.name):
                return attr
        return None

    def _enforce_must_go(
        self,
        days: list[dict],
        request: TripRequest,
        attractions: list[Attraction],
        used_names: set[str],
    ) -> None:
        """确保 must_go 景点全部出现在行程中。

        LLM 可能遗漏 must_go 景点，这里程序化强制注入到第一天首位。
        只注入在候选列表中找到匹配的 must_go 景点。
        """
        if not request.must_go or not days:
            return

        for must_go_name in request.must_go:
            must_go_name = must_go_name.strip()
            if not must_go_name:
                continue

            # 检查是否已在行程中
            already_included = False
            for day in days:
                for attr in day.get("attractions", []):
                    if self._poi_name_matches(must_go_name, attr.get("name", "")):
                        already_included = True
                        break
                if already_included:
                    break

            if already_included:
                continue

            # 在候选列表中找匹配
            matching = self._find_matching_candidate(must_go_name, attractions)
            if matching:
                attr_dict = matching.model_dump()
                attr_dict["route_city"] = days[0].get("route_city", request.city)
                if "attractions" not in days[0]:
                    days[0]["attractions"] = []
                # 插入到第一天首位
                days[0]["attractions"].insert(0, attr_dict)
                used_names.add(matching.name)
                logger.info("must_go 景点 '%s' 未在行程中，已强制注入第一天首位", must_go_name)
            else:
                logger.warning("must_go 景点 '%s' 在候选列表中未找到匹配，无法注入", must_go_name)

    def _enforce_can_go(
        self,
        days: list[dict],
        request: TripRequest,
        attractions: list[Attraction],
        used_names: set[str],
    ) -> None:
        """尽量将 can_go 景点纳入行程。

        can_go 是软约束：如果候选列表中能找到匹配且当天有空间（<3 个景点），
        就追加到当天末尾。不会挤掉已有的 must_go 或 LLM 选择的景点。
        """
        if not request.can_go or not days:
            return

        max_per_day = 3
        for can_go_name in request.can_go:
            can_go_name = can_go_name.strip()
            if not can_go_name:
                continue

            # 检查是否已在行程中
            already_included = False
            for day in days:
                for attr in day.get("attractions", []):
                    if self._poi_name_matches(can_go_name, attr.get("name", "")):
                        already_included = True
                        break
                if already_included:
                    break

            if already_included:
                continue

            # 在候选列表中找匹配
            matching = self._find_matching_candidate(can_go_name, attractions)
            if not matching:
                logger.warning("can_go 景点 '%s' 在候选列表中未找到匹配，无法注入", can_go_name)
                continue

            # 找到第一个有空间的那天（景点数 < max_per_day）
            for day in days:
                day_attrs = day.get("attractions", [])
                if len(day_attrs) < max_per_day:
                    attr_dict = matching.model_dump()
                    attr_dict["route_city"] = day.get("route_city", request.city)
                    day_attrs.append(attr_dict)
                    used_names.add(matching.name)
                    logger.info("can_go 景点 '%s' 已注入第 %d 天末尾", can_go_name, day.get("day_index", 0) + 1)
                    break
            else:
                # 所有天都满了，替换最后一天评分最低的景点
                if matching.rating and matching.rating > 0:
                    last_day = days[-1]
                    day_attrs = last_day.get("attractions", [])
                    if day_attrs:
                        worst_idx = min(range(len(day_attrs)), key=lambda i: float(day_attrs[i].get("rating", 0) or 0))
                        worst_rating = float(day_attrs[worst_idx].get("rating", 0) or 0)
                        if matching.rating > worst_rating:
                            old_name = day_attrs[worst_idx].get("name", "")
                            attr_dict = matching.model_dump()
                            attr_dict["route_city"] = last_day.get("route_city", request.city)
                            day_attrs[worst_idx] = attr_dict
                            used_names.discard(old_name)
                            used_names.add(matching.name)
                            logger.info(
                                "can_go 景点 '%s' 替换第 %d 天低评分景点 '%s'（%.1f → %.1f）",
                                can_go_name, len(days), old_name, worst_rating, matching.rating,
                            )

    def _sanitize_day_payloads(
        self,
        days: list[dict],
        request: TripRequest,
        attractions: list[Attraction],
        hotels: list[Hotel],
    ) -> list[dict]:
        """Remove forbidden-city POIs, detect LLM hallucinations, and enforce must_go constraints.

        改进点：
        1. 幻觉检测：LLM 生成的景点名必须在真实候选列表中存在，否则丢弃
        2. avoid_places 强制过滤：用户说"避开宋城"，任何包含"宋城"的景点都被移除
        3. must_go 强制注入：用户说"想去浙大"，浙大必须出现在行程中
        """
        route_cities = self._route_cities(request)
        city_segments = self._split_route_days(route_cities, request.travel_days)
        attractions_by_city = self._group_attractions_by_route_city(attractions, route_cities)
        hotels_by_city = {h.route_city: h for h in hotels if h.route_city}
        used_names = set()
        city_offsets = {city: 0 for city in route_cities}
        sanitized = []

        # avoid_places 集合（如 "宋城"）
        avoid_places = set(p.strip() for p in (request.avoid_places or []) if p.strip())

        fb_pools = [v for k, v in attractions_by_city.items() if k != request.city]
        for idx, day in enumerate(days[:request.travel_days]):
            day_city = city_segments[idx] if idx < len(city_segments) else request.city
            raw_attrs = day.get("attractions") or []
            kept_attrs = []
            for raw_attr in raw_attrs:
                name = str(raw_attr.get("name", "")).strip()
                if not name or name in used_names or self._mentions_forbidden_city(raw_attr, request):
                    continue
                # avoid_places 过滤（如"宋城"）
                if avoid_places and any(avoid in name or name in avoid for avoid in avoid_places):
                    logger.info("景点 '%s' 匹配 avoid_places %s，已过滤", name, avoid_places)
                    continue
                # 幻觉检测：景点名必须在真实候选列表中存在
                if attractions and not self._matches_any_candidate(name, attractions):
                    logger.info("LLM 幻觉景点 '%s' 不在候选列表中，已丢弃", name)
                    continue
                raw_attr.setdefault("route_city", day_city)
                kept_attrs.append(raw_attr)
                used_names.add(name)
                if len(kept_attrs) >= 3:
                    break

            if len(kept_attrs) < min(2, len(attractions_by_city.get(day_city, []))):
                replacements = self._take_unique_attractions(
                    attractions_by_city.get(day_city, attractions),
                    used_names,
                    city_offsets,
                    day_city,
                    limit=3 - len(kept_attrs),
                    fallback_pools=fb_pools,
                )
                kept_attrs.extend([attr.model_dump() for attr in replacements])

            # ── 兜底：如果去重后当天没有任何景点，搜索更多 POI 补充 ──
            # 多日行程中，LLM 可能在两天放同一景点（如"西湖"），
            # 去重后第二天变空。此时用通用关键词搜索更多不同景点。
            if not kept_attrs:
                extra_attractions = self._search_extra_poi(day_city, used_names, count=3)
                for attr in extra_attractions:
                    if attr.name not in used_names:
                        kept_attrs.append(attr.model_dump())
                        used_names.add(attr.name)
                        if len(kept_attrs) >= 2:
                            break

            # ── 最终兜底：如果仍然没有景点，允许复用高评分景点 ──
            # 大型景区（如西湖）本身可以分多天游览，不应强制去重
            if not kept_attrs and attractions:
                best = max(attractions, key=lambda a: a.rating or 0)
                kept_attrs.append(best.model_dump())

            day["attractions"] = kept_attrs
            if self._mentions_forbidden_city(day.get("hotel") or {}, request):
                day["hotel"] = (hotels_by_city.get(day_city) or self._fallback_hotel(request, attractions)).model_dump()
            if self._mentions_forbidden_city(day.get("description", ""), request):
                day["description"] = self._fallback_day_description(request, idx, day_city, route_cities)
            if any(self._mentions_forbidden_city(meal, request) for meal in day.get("meals", [])):
                day["meals"] = [m.model_dump() for m in self._default_meals(day_city)]
            sanitized.append(day)

        # ── 强制注入 must_go / can_go 景点 ──────────────────────────
        # 用户说"想去浙大和西湖"时，can_go 列表包含 ["浙大", "西湖"]。
        # LLM 可能遗漏这些景点，这里程序化强制注入。
        # must_go: 插入第一天首位（硬约束）
        # can_go: 插入有空间的那天末尾（软约束，但尽量满足）
        self._enforce_must_go(sanitized, request, attractions, used_names)
        self._enforce_can_go(sanitized, request, attractions, used_names)

        return sanitized

    def _search_extra_poi(self, city: str, used_names: set[str], count: int = 3) -> list[Attraction]:
        """当去重后某天没有景点时，用不同关键词搜索更多 POI 补充。

        使用"公园""广场""博物馆"等不同关键词搜索，避免和已用景点重复。
        """
        from modules.ai.tools import search_attractions

        extra: list[Attraction] = []
        # 用多个关键词搜索，增加找到不同景点的概率
        for keyword in ["公园", "博物馆", "广场"]:
            if len(extra) >= count:
                break
            try:
                result = search_attractions(city=city, weather="", count=3, preference=keyword)
                if result.get("success"):
                    for item in result.get("attractions", []):
                        name = item.get("name", "")
                        if name and name not in used_names:
                            item.setdefault("route_city", city)
                            extra.append(self._to_attraction(item))
                            if len(extra) >= count:
                                break
            except Exception as e:
                logger.warning("搜索额外景点失败 city=%s keyword=%s: %s", city, keyword, e)

        return extra

    def _take_unique_attractions(
        self,
        pool: list[Attraction],
        used_names: set[str],
        city_offsets: dict[str, int],
        city: str,
        limit: int,
        fallback_pools: list[list[Attraction]] = None,
    ) -> list[Attraction]:
        if limit <= 0:
            return []

        def _pick(p: list[Attraction], start: int) -> list[Attraction]:
            s = []
            off = start
            while off < len(p) and len(s) < limit:
                attr = p[off]
                if attr.name and attr.name not in used_names:
                    s.append(attr)
                    used_names.add(attr.name)
                off += 1
            city_offsets[city] = off
            return s

        selected = _pick(pool, city_offsets.get(city, 0))
        if len(selected) >= limit:
            return selected

        # pool exhausted — try fallback pools from other route cities
        for fb in (fallback_pools or []):
            if len(selected) >= limit:
                break
            extra = _pick(fb, 0)
            selected.extend(extra[:limit - len(selected)])
            if len(selected) >= limit:
                break

        return selected

    def _mentions_forbidden_city(self, item: Any, request: TripRequest) -> bool:
        if not request.forbidden_cities:
            return False
        if isinstance(item, dict):
            text = " ".join(str(item.get(key, "")) for key in ("name", "address", "description", "distance", "route_city"))
        else:
            text = str(item or "")
        return any(city and city in text for city in request.forbidden_cities)

    def _default_meals(self, city: str) -> list[Meal]:
        return [
            Meal(type="breakfast", name="当地特色早餐", description=f"品尝{city}地道早餐", estimated_cost=30),
            Meal(type="lunch", name="午餐", description="游览途中就近用餐", estimated_cost=80),
            Meal(type="dinner", name=f"{city}特色晚餐", description=f"享受{city}特色美食", estimated_cost=100),
        ]

    def _calculate_budget(self, days: list[DayPlan]) -> Budget:
        total_attractions = sum(a.ticket_price for day in days for a in day.attractions)
        total_hotels = sum((day.hotel.estimated_cost if day.hotel else 0) for day in days)
        total_meals = sum(meal.estimated_cost for day in days for meal in day.meals)
        total_transportation = len(days) * 50
        return Budget(
            total_attractions=total_attractions,
            total_hotels=total_hotels,
            total_meals=total_meals,
            total_transportation=total_transportation,
            total=total_attractions + total_hotels + total_meals + total_transportation,
        )

    def _overall_suggestions(self, request: TripRequest, weather: list[WeatherInfo], budget: Budget) -> str:
        weather_text = weather[0].day_weather if weather else "天气未知"
        if request.trip_type == "route":
            return (
                f"{self._route_summary(request)}，共{request.travel_days}天，天气以{request.city}预报为参考，"
                f"每日控制长途驾驶和1-2个停靠游览点，预计总费用约{budget.total}元。"
            )
        return (
            f"{request.city}{request.travel_days}日游，天气{weather_text}，"
            f"每日安排2-3个目的地，预计总费用约{budget.total}元。"
        )

    def _merge_xhs_attractions(
        self,
        amap_items: list[dict],
        xhs_items: list[dict],
        city: str,
    ) -> list[dict]:
        """将小红书提纯的景点合并到高德 POI 列表中。

        策略:
        - 名称匹配（忽略大小写/空格）的景点: 用 XHS 的 description 和 visit_duration
          覆盖高德数据（小红书数据更真实），但保留高德的 location/ticket_price/rating
        - XHS 独有的景点: 直接追加到列表末尾
        """
        if not xhs_items:
            return amap_items

        def _normalize_name(name: str) -> str:
            return name.strip().lower().replace(" ", "")

        amap_name_map = {}
        for item in amap_items:
            key = _normalize_name(item.get("name", ""))
            if key:
                amap_name_map[key] = item

        merged = list(amap_items)
        for xhs_item in xhs_items:
            key = _normalize_name(xhs_item.get("name", ""))
            if not key:
                continue
            if key in amap_name_map:
                amap_item = amap_name_map[key]
                # 用 XHS 数据增强高德条目
                if xhs_item.get("description"):
                    amap_item["description"] = xhs_item["description"]
                if xhs_item.get("visit_duration"):
                    amap_item["visit_duration"] = xhs_item["visit_duration"]
                if xhs_item.get("category"):
                    amap_item["category"] = xhs_item["category"]
                amap_item["source"] = "amap+xhs"
                logger.debug("XHS 增强: %s (合并到高德数据)", xhs_item["name"])
            else:
                # XHS 独有的景点，直接追加
                if not xhs_item.get("route_city"):
                    xhs_item["route_city"] = city
                merged.append(xhs_item)
                logger.debug("XHS 新增: %s", xhs_item["name"])

        return merged

    def _to_attraction(self, item: dict) -> Attraction:
        lon, lat = _parse_location(item.get("location", ""))
        photos = [item.get("photo_url", "")] if item.get("photo_url") else []
        return Attraction(
            name=item.get("name", ""),
            address=item.get("address", ""),
            location=Location(longitude=lon, latitude=lat),
            visit_duration=int(item.get("visit_duration", 120) or 120),
            description=item.get("description") or item.get("weather_hint") or item.get("category", "景点"),
            category=item.get("category", "景点"),
            rating=item.get("rating") or None,
            photos=photos,
            poi_id=item.get("id", ""),
            image_url=item.get("photo_url") or None,
            ticket_price=int(item.get("ticket_price", 0) or 0),
            route_city=item.get("route_city", ""),
            source=item.get("source", "amap"),
            reservation_required=bool(item.get("reservation_required", False)),
            reservation_tips=item.get("reservation_tips", ""),
        )

    def _to_hotel(self, item: dict) -> Hotel:
        lon, lat = _parse_location(item.get("location", ""))
        return Hotel(
            name=item.get("name", ""),
            address=item.get("address", ""),
            location=Location(longitude=lon, latitude=lat),
            price_range=item.get("price_range", ""),
            rating=str(item.get("rating", "") or ""),
            distance=item.get("distance", ""),
            type=item.get("type", "") or "酒店",
            estimated_cost=int(item.get("estimated_cost", 0) or 0),
            source=item.get("source", "amap"),
        )

    def _to_weather_info(self, item: dict) -> WeatherInfo:
        return WeatherInfo(
            date=item.get("date", ""),
            day_weather=item.get("day_weather", "") or item.get("dayweather", ""),
            night_weather=item.get("night_weather", "") or item.get("nightweather", ""),
            day_temp=item.get("day_temp", "") or item.get("daytemp", 0),
            night_temp=item.get("night_temp", "") or item.get("nighttemp", 0),
            wind_direction=item.get("wind_direction", "") or item.get("daywind", ""),
            wind_power=item.get("wind_power", "") or item.get("daypower", ""),
            source=item.get("source", "amap_forecast"),
            note=item.get("note", "逐日天气预报"),
        )

    def _build_reply(self, legacy: dict) -> str:
        budget = legacy.get("budget", {})
        return f"行程规划已显示在中控屏上咯！{legacy.get('summary', '')}预算约¥{budget.get('total', '--')}元～"

    def _route_cities(self, request: TripRequest) -> list[str]:
        cities = []
        forbidden = set(request.forbidden_cities or [])
        for city in [request.origin, *request.waypoints, request.city]:
            city = (city or "").strip()
            if city and city not in forbidden and city not in cities:
                cities.append(city)
        return cities or [request.city]

    def _route_summary(self, request: TripRequest) -> str:
        cities = self._route_cities(request)
        if request.trip_type == "route" and len(cities) >= 2:
            return " → ".join(cities)
        return f"{request.city}{request.travel_days}日游"

    def _trip_title(self, plan: TripPlan) -> str:
        if plan.origin or plan.waypoints:
            cities = [c for c in [plan.origin, *plan.waypoints, plan.city] if c]
            return f"{'→'.join(cities)}{len(plan.days)}日自驾"
        return f"{plan.city}{len(plan.days)}日游"

    def _split_route_days(self, route_cities: list[str], travel_days: int) -> list[str]:
        if not route_cities:
            return []
        if len(route_cities) == 1:
            return [route_cities[0] for _ in range(travel_days)]

        segments = []
        legs = len(route_cities) - 1
        for day in range(travel_days):
            leg_index = min((day * legs) // max(travel_days, 1), legs - 1)
            if day == travel_days - 1:
                segments.append(route_cities[-1])
            else:
                segments.append(route_cities[leg_index + 1])
        return segments

    def _group_attractions_by_route_city(
        self,
        attractions: list[Attraction],
        route_cities: list[str],
    ) -> dict[str, list[Attraction]]:
        grouped = {city: [] for city in route_cities}
        for attraction in attractions:
            city = (attraction.route_city or "").strip()
            if city and city in grouped:
                grouped[city].append(attraction)
            else:
                # fallback: substring match
                text = f"{attraction.name} {attraction.address}"
                matched = None
                for c in route_cities:
                    if c and c in text:
                        matched = c
                        break
                grouped.setdefault(matched or route_cities[-1], []).append(attraction)
        return grouped

    def _fallback_day_description(
        self,
        request: TripRequest,
        day_index: int,
        day_city: str,
        route_cities: list[str],
    ) -> str:
        if request.trip_type != "route":
            return f"{request.city}第{day_index + 1}天行程"
        if day_index == 0 and request.origin:
            return f"第{day_index + 1}天从{request.origin}出发，向{day_city}方向行驶并停靠游览"
        if day_index == request.travel_days - 1:
            return f"第{day_index + 1}天抵达{request.city}，完成{self._route_summary(request)}自驾线路"
        return f"第{day_index + 1}天沿{self._route_summary(request)}推进，重点停靠{day_city}"


def _extract_raw_json_str(response: str) -> str:
    """从 LLM 响应文本中提取 JSON 子串（不解析）。

    兼容三种包裹：```json ... ```、``` ... ```、裸 JSON。
    输出被 max_tokens 截断时（找不到闭合标记）取到末尾。
    """
    if "```json" in response:
        start = response.find("```json") + 7
        end = response.find("```", start)
        if end == -1 or end <= start:
            return response[start:].strip()
        return response[start:end].strip()
    if "```" in response:
        start = response.find("```") + 3
        end = response.find("```", start)
        if end == -1 or end <= start:
            return response[start:].strip()
        return response[start:end].strip()
    if "{" in response:
        start = response.find("{")
        end = response.rfind("}")
        if end > start:
            return response[start:end + 1]
        # 没有闭合 } —— 截断场景，取到末尾
        return response[start:]
    raise ValueError("响应中未找到 JSON 数据")


def _sanitize_json_str(json_str: str) -> str:
    """清理大模型输出中常见的 JSON 格式污染（第 1 层）。"""
    import re as _re
    # 1. 移除 ```json ... ``` 标记
    json_str = _re.sub(r'^```(?:json)?\s*', '', json_str.strip())
    json_str = _re.sub(r'```\s*$', '', json_str.strip())
    # 2. 移除 JS 风格注释 // ... 和 /* ... */
    json_str = _re.sub(r'//[^\n]*', '', json_str)
    json_str = _re.sub(r'/\*.*?\*/', '', json_str, flags=_re.DOTALL)
    # 3. 移除控制字符（保留 \t \n \r，在步骤 3b 中处理）
    json_str = _re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f]', '', json_str)
    # 3b. 转义 JSON 字符串值内部的字面换行符/制表符
    # LLM 常在 description 等字段中写入多行文本，字面 \n \r \t 在 JSON 字符串中是非法的
    # 用状态机扫描：只在双引号字符串内部将字面控制字符替换为转义序列
    result = []
    in_string = False
    escaped = False
    for ch in json_str:
        if escaped:
            result.append(ch)
            escaped = False
            continue
        if ch == '\\':
            result.append(ch)
            escaped = True
            continue
        if ch == '"':
            in_string = not in_string
            result.append(ch)
            continue
        if in_string:
            if ch == '\n':
                result.append('\\n')
                continue
            if ch == '\r':
                result.append('\\r')
                continue
            if ch == '\t':
                result.append('\\t')
                continue
        result.append(ch)
    json_str = ''.join(result)
    # 4. 修复尾部逗号: },] 或 },}
    json_str = _re.sub(r',\s*([\]\}])', r'\1', json_str)
    # 5. 修复中文引号和全角标点（双引号替换为单引号避免破坏 JSON 结构）
    json_str = json_str.replace('\u201c', "'").replace('\u201d', "'")
    json_str = json_str.replace('\u2018', "'").replace('\u2019', "'")
    json_str = json_str.replace('\uff1a', ':')
    json_str = json_str.replace('\uff0c', ',')
    # 5b. 移除 photos/image_url/poi_id 字段（LLM 常在此类字段中生成截断 URL，破坏 JSON 结构）
    # 先尝试移除格式正确的字段
    json_str = _re.sub(r'"(?:photos|image_url|poi_id)"\s*:\s*(?:\[[^\]]*\]|"[^"]*"|null)\s*,?\s*', '', json_str)
    # 再处理格式错误的字段：从字段名到下一个已知字段名之间的所有内容都移除
    _KNOWN_FIELDS = r'"(?:name|address|location|visit_duration|description|category|rating|ticket_price|route_city|type|estimated_cost|distance|source|hotel|attractions|meals|date|day_index|transportation|accommodation|city|start_date|end_date|days|weather_info|overall_suggestions|budget|breakfast|lunch|dinner|snack)"'
    json_str = _re.sub(
        r'"(?:photos|image_url|poi_id)"\s*:\s*.*?(?=' + _KNOWN_FIELDS + r'|\}|\])',
        '',
        json_str,
        flags=_re.DOTALL,
    )
    # 5c. 修复移除字段后可能产生的连续逗号
    json_str = _re.sub(r',\s*,', ',', json_str)
    json_str = _re.sub(r'\[\s*,', '[', json_str)
    json_str = _re.sub(r',\s*\]', ']', json_str)
    json_str = _re.sub(r'{\s*,', '{', json_str)
    json_str = _re.sub(r',\s*}', '}', json_str)
    # 6. 修复算术表达式 "total": 30+54+120=324 → "total": 324
    def _fix_arithmetic_expr(m):
        expr = m.group(1).strip()
        if '=' in expr:
            return m.group(0).replace(m.group(1), expr.split('=')[-1].strip())
        try:
            result = eval(expr, {"__builtins__": {}}, {})
            return m.group(0).replace(m.group(1), str(result))
        except Exception:
            return m.group(0)
    json_str = _re.sub(
        r':\s*(\d+(?:\s*[+\-*/]\s*\d+)+(?:\s*=\s*\d+)?)',
        _fix_arithmetic_expr,
        json_str,
    )
    return json_str


def _fix_unescaped_quotes(json_str: str) -> str:
    """修复 JSON 字符串值内部未转义的双引号（第 2 层）。

    状态机扫描，将字符串值内部的 " 替换为 '，只保留真正的结构引号。
    """
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
    """修复被 max_tokens 截断的不完整 JSON（第 3 层）。

    1. 关闭未终止的字符串
    2. 移除尾部不完整的 key-value 碎片
    3. 根据未闭合的括号栈补齐 ] 和 }
    """
    import re as _re
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
        s = s.rstrip('\\')
        s += '"'
    # Step 2: 移除尾部不完整碎片
    for _ in range(10):
        stripped = s.rstrip()
        if not stripped:
            break
        last = stripped[-1]
        if last in ('}', ']', '"') or last.isdigit() or last in ('e', 'l', 's'):
            break
        s = stripped[:-1]
    s = _re.sub(r',\s*$', '', s)
    # Step 3: 用精确栈补齐闭合括号
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


def _extract_json_object(text: str) -> dict:
    """基础 JSON 提取（保留向后兼容，仅做提取 + sanitize）。"""
    raw = _extract_raw_json_str(text)
    return json.loads(_sanitize_json_str(raw))


def _normalize_keys(obj: Any) -> Any:
    """Recursively map common LLM key variants to schema field names."""
    if isinstance(obj, list):
        return [_normalize_keys(item) for item in obj]
    if not isinstance(obj, dict):
        return obj

    normalized = {}
    for key, value in obj.items():
        mapped_key = FIELD_ALIASES.get(key, key)
        normalized[mapped_key] = _normalize_keys(value)
    return normalized


def _weather_source_note(weather_info: list[WeatherInfo]) -> str:
    sources = {w.source for w in weather_info if w.source}
    if "amap_forecast" in sources:
        return "天气信息来自高德逐日天气预报，可以作为每天行程排序参考。"
    if "current_copy" in sources:
        return (
            "当前天气工具未提供逐日预报；多日行程中每天天气相同表示当前天气被复制为参考信息，"
            "不代表真实逐日预报，overall_suggestions 中不要伪装成已获得逐日天气预报。"
        )
    return "天气来源不明确，只能作为弱参考，行程建议应避免过度依赖天气。"


def _parse_location(value: str) -> tuple[float, float]:
    if not value or "," not in value:
        return 0.0, 0.0
    try:
        lon, lat = value.split(",", 1)
        return float(lon), float(lat)
    except Exception:
        return 0.0, 0.0


_trip_planner_agent: Optional[EdgeGuardTripPlanner] = None


def get_trip_planner_agent() -> EdgeGuardTripPlanner:
    global _trip_planner_agent
    if _trip_planner_agent is None:
        _trip_planner_agent = EdgeGuardTripPlanner()
    return _trip_planner_agent
