"""Strong trip-planning schemas adapted from helloagents-trip-planner."""

from __future__ import annotations

import re
from datetime import datetime, timedelta
from typing import List, Optional, Union

from pydantic import BaseModel, Field


def _extract_accommodation(query: str) -> str:
    """从用户自然语言中提取住宿偏好，映射为搜索关键词。"""
    q = query or ""

    # 1. 先提取价格范围（有具体数字，优先级最高）
    price = re.search(r'(\d{3,4})\s*[-~到至]\s*(\d{3,4})', q)
    price_tag = ""
    if price:
        lo, hi = int(price.group(1)), int(price.group(2))
        if hi >= 800:
            price_tag = f" {lo}-{hi}元"
        elif hi >= 400:
            price_tag = f" {lo}-{hi}元"
        else:
            price_tag = f" {lo}-{hi}元"

    # 2. 星级/质量关键词（与价格标签合并）
    if re.search(r"五星|5星|豪华|高端|高档|奢华|度假", q):
        return "五星级酒店" + price_tag
    if re.search(r"四星|4星|商务", q):
        return "四星级酒店" + price_tag
    if re.search(r"三星|3星|舒适", q):
        return "舒适型酒店" + price_tag
    if re.search(r"经济|便宜|实惠|快捷|青旅|民宿", q):
        return "经济型酒店" + price_tag

    # 3. 仅有价格范围
    if price_tag:
        if price and int(price.group(2)) >= 800:
            return "高档酒店" + price_tag
        return "舒适型酒店" + price_tag

    return "舒适型酒店"


def _extract_trip_constraints(query: str) -> dict:
    """从用户自然语言中提取所有出行约束。"""
    q = query or ""

    result = {
        "accommodation": _extract_accommodation(q),
        "hotel_name": "",
        "hotel_address": "",
        "transportation": "自驾",
        "pax": 0,
        "age_groups": [],
        "pace": "normal",
        "food_budget": "",
        "queue_tolerance": "",
        "walk_tolerance": "",
        "must_go": [],
        "can_go": [],
        "avoid_places": [],
        "avoid_types": [],
        "likes": [],
        "dislikes": [],
    }

    # ── 人数 ──
    cn_num = {"一": 1, "两": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8}
    pax = re.search(r'(\d|[一两三四五六七八])\s*(?:个)?人', q)
    if pax:
        raw = pax.group(1)
        if raw in cn_num:
            result["pax"] = cn_num[raw]
        elif raw.isdigit():
            result["pax"] = int(raw)

    # ── 年龄段 ──
    if re.search(r'老人|长辈|爸妈|父母|爷爷|奶奶|年纪大', q):
        result["age_groups"].append("senior")
    if re.search(r'小孩|孩子|宝宝|儿童|亲子|带娃', q):
        result["age_groups"].append("child")

    # ── 节奏（先检查否定模式）──
    if re.search(r'轻松|休闲|慢一点|慢慢|不急|放松|不想太赶|不要太赶|别太累', q):
        result["pace"] = "relaxed"
    elif "senior" in result["age_groups"] or "child" in result["age_groups"]:
        result["pace"] = "relaxed"
    elif re.search(r'紧凑|赶一点|特种兵|暴走|多走走|多玩|尽量多', q):
        result["pace"] = "fast"

    # ── 餐饮预算 ──
    fb = re.search(r'(?:吃饭|餐|人均|预算).*?(\d{2,4})\s*(?:块|元|¥)?', q)
    if fb:
        result["food_budget"] = f"人均{fb.group(1)}元"

    # ── 排队容忍度（先否定）──
    if re.search(r'不.*排队|讨厌排队|拒绝排队|不想排|别排队|不要排队', q):
        result["queue_tolerance"] = "low"
    elif re.search(r'愿意排队|可以排队|能排队|排队.*行|不怕排', q):
        result["queue_tolerance"] = "high"

    # ── 走路容忍度（先否定）──
    if re.search(r'走不动|不能走|不想走|少走路|别走|不走|打车|坐车|不.*走路', q) or "senior" in result["age_groups"]:
        result["walk_tolerance"] = "low"
    elif re.search(r'能走|可以走|走路.*行|多走|暴走|步行', q):
        result["walk_tolerance"] = "high"

    # ── 酒店 ──
    hotel = re.search(r'(?:住|订了|酒店|宾馆|民宿|旅馆)\s*[:：]?\s*([^，。,\.\n]{3,40})', q)
    if hotel:
        name = hotel.group(1).strip()
        if not re.search(r'^[在了到是要去]', name):
            result["hotel_name"] = name
    addr = re.search(r'(?:酒店地址|地址|在)\s*[:：]?\s*([^，。,\.\n]{5,50})', q)
    if addr:
        result["hotel_address"] = addr.group(1).strip()

    # ── 交通偏好 ──
    if re.search(r'地铁|公交|公共交通', q):
        result["transportation"] = "公共交通"
    elif re.search(r'打车|出租车|网约车', q):
        result["transportation"] = "打车"
    elif re.search(r'自驾|开车|租车', q):
        result["transportation"] = "自驾"

    # ── 一定要去 ──
    for m in re.finditer(r'(?:一定要去|必须去|必去|一定要看|必须看|硬要去)\s*([^，。,\n]{2,30})', q):
        raw = m.group(1).strip()
        # 拆分"和""跟""与""以及"连接的并列
        items = re.split(r'[和跟与及、，,]', raw)
        for item in items:
            item = item.strip()
            if item and len(item) >= 2 and item not in result["must_go"]:
                result["must_go"].append(item)

    # "想去"列表 — 提取"想去A、B、C"模式
    want = re.search(r'(?:想去|要去|想看看?|要看|希望去)\s*([^，。,\n]{2,60})', q)
    if want:
        # 按中文分隔符和空格拆分，防止"西湖 亲子"被误提为单个景点
        items = re.split(r'[、，,和跟与及\s]+', want.group(1))
        for item in items:
            item = item.strip()
            if item and len(item) >= 2 and item not in result["must_go"] and item not in result["can_go"]:
                result["can_go"].append(item)

    # ── 不要去 / 不喜欢 ──
    for m in re.finditer(r'(?:不去|不想去|讨厌|不要|别去|避开|拒绝)\s*([^，。,\n]{2,20})', q):
        a = m.group(1).strip()
        # 跳过动词前缀（如"去宋城"中的"去"）
        a = re.sub(r'^[去了到在]', '', a).strip()
        if a and len(a) >= 2 and a not in result["avoid_places"]:
            result["avoid_places"].append(a)

    # 类型避讳
    if re.search(r'(?:不喜欢|讨厌|不要|别|不想|避开|拒绝)\s*网红', q):
        result["avoid_types"].append("网红店")
    if re.search(r'(?:不喜欢|讨厌|不要|别|不想|避开|拒绝)\s*寺庙', q):
        result["avoid_types"].append("寺庙")
    if re.search(r'(?:不喜欢|讨厌|不要|别|不想|避开|拒绝)\s*爬山', q):
        result["avoid_types"].append("爬山")

    # ── 不喜欢的标签（用短距否定，避免远程误匹配）──
    for pattern, tag in [
        (r'(?:不喜欢|讨厌|不要|别|不想|拒绝)\s*(?:喝|吃|去|逛|拍)?\s*咖啡', '咖啡'),
        (r'(?:不喜欢|讨厌|不要|别|不想|拒绝)\s*(?:喝|去|泡)?\s*(?:酒吧|酒)', '酒吧'),
        (r'(?:不喜欢|讨厌|不要|别|不想|拒绝)\s*(?:吃|买)?\s*(?:甜点|甜品|甜的)', '甜点'),
        (r'(?:不喜欢|讨厌|不要|别|不想|拒绝)\s*拍', '拍照'),
        (r'(?:不喜欢|讨厌|不要|别|不想|拒绝)\s*(?:逛|买|购物)', '购物'),
    ]:
        if re.search(pattern, q) and tag not in result["dislikes"]:
            result["dislikes"].append(tag)

    # ── 喜好（排除否定前缀）──
    like_map = [
        (r'咖啡', '咖啡'),
        (r'酒吧|喝酒|清酒|精酿', '酒吧'),
        (r'甜点|甜品|蛋糕|冰淇淋', '甜点'),
        (r'夜景|夜生活|晚上.*逛|夜游', '夜景'),
        (r'温泉|泡汤', '温泉'),
        (r'拍照|打卡|出片', '拍照'),
        (r'购物|逛街|买', '购物'),
        (r'二次元|动漫|宅', '二次元'),
        (r'博物馆|展览|展', '博物馆'),
        (r'户外|徒步|爬山|登山|骑行', '户外'),
    ]
    for pattern, tag in like_map:
        if tag in result["dislikes"]:
            continue  # 已标记为不喜欢
        # 排除否定模式 "不喜欢咖啡"（用短距，避免远程"不"误匹配）
        if re.search(rf'(?:不喜欢|讨厌|不要|别|不想|拒绝)\s*(?:喝|吃|去|逛|拍|泡)?\s*{pattern}', q):
            continue
        if re.search(pattern, q) and tag not in result["likes"]:
            result["likes"].append(tag)

    return result


class TripRequest(BaseModel):
    """Travel planning request with structured traveler constraints."""

    # ── 目的地 ──
    city: str = Field(..., description="Destination city")
    origin: str = Field(default="", description="Origin city for road trips")
    waypoints: List[str] = Field(default_factory=list, description="Required waypoint cities")
    forbidden_cities: List[str] = Field(default_factory=list, description="Cities that must be avoided")
    trip_type: str = Field(default="city", description="city or route")

    # ── 时间 ──
    start_date: str = Field(..., description="Start date YYYY-MM-DD")
    end_date: str = Field(..., description="End date YYYY-MM-DD")
    travel_days: int = Field(..., ge=1, le=30, description="Number of travel days")
    arrival_time: str = Field(default="", description="Arrival time, e.g. 14:00")
    departure_time: str = Field(default="", description="Return departure time, e.g. 17:00")

    # ── 住宿 ──
    transportation: str = Field(default="自驾", description="Transportation preference")
    accommodation: str = Field(default="舒适型酒店", description="Accommodation preference")
    hotel_name: str = Field(default="", description="Hotel name if already booked")
    hotel_address: str = Field(default="", description="Hotel address if already booked")

    # ── 人员 ──
    pax: int = Field(default=0, description="Number of travelers")
    age_groups: List[str] = Field(default_factory=list, description="e.g. adult, senior, child")
    preferences: List[str] = Field(default_factory=list, description="Travel preference tags")

    # ── 节奏与预算 ──
    pace: str = Field(default="normal", description="Pace: relaxed / normal / fast")
    food_budget: str = Field(default="", description="Per-meal budget, e.g. 人均100")
    queue_tolerance: str = Field(default="", description="Queue tolerance: low / medium / high")
    walk_tolerance: str = Field(default="", description="Walking tolerance: low / medium / high")

    # ── 喜好与避讳 ──
    must_go: List[str] = Field(default_factory=list, description="Must-visit places")
    can_go: List[str] = Field(default_factory=list, description="Optional places")
    avoid_places: List[str] = Field(default_factory=list, description="Places to avoid")
    avoid_types: List[str] = Field(default_factory=list, description="Types to avoid, e.g. 网红店, 寺庙")
    likes: List[str] = Field(default_factory=list, description="Likes: 咖啡, 酒吧, 甜点, 夜景, 拍照...")
    dislikes: List[str] = Field(default_factory=list, description="Dislikes")

    # ── 自由文本 ──
    free_text_input: str = Field(default="", description="Extra user request")

    @classmethod
    def from_text(
        cls,
        city: str,
        days: int = 1,
        preference: Optional[str] = None,
        query: str = "",
        origin: str = "",
        waypoints: Optional[List[str]] = None,
        forbidden_cities: Optional[List[str]] = None,
    ) -> "TripRequest":
        start = datetime.now() + timedelta(days=1)
        safe_days = max(1, min(int(days or 1), 30))
        end = start + timedelta(days=safe_days - 1)
        preferences = [preference] if preference else []

        # ── 从用户原话中提取所有约束 ──
        # 只用 query 提取约束，不拼接 preference，避免偏好标签（如"亲子"）
        # 污染 can_go/must_go 提取（如"西湖 亲子"被误提为单个景点）
        constraints = _extract_trip_constraints(query or "")

        accommodation = constraints.get("accommodation", "舒适型酒店")
        if accommodation != "舒适型酒店":
            preferences.append(accommodation)
        if constraints.get("food_budget"):
            preferences.append(f"餐标{constraints['food_budget']}")
        if constraints.get("likes"):
            preferences.extend(constraints["likes"])

        return cls(
            city=city,
            origin=origin or "",
            waypoints=waypoints or [],
            forbidden_cities=forbidden_cities or [],
            trip_type="route" if origin or waypoints else "city",
            start_date=start.strftime("%Y-%m-%d"),
            end_date=end.strftime("%Y-%m-%d"),
            travel_days=safe_days,
            transportation=constraints.get("transportation", "自驾"),
            accommodation=accommodation,
            hotel_name=constraints.get("hotel_name", ""),
            hotel_address=constraints.get("hotel_address", ""),
            pax=constraints.get("pax", 0),
            age_groups=constraints.get("age_groups", []),
            preferences=preferences,
            pace=constraints.get("pace", "normal"),
            food_budget=constraints.get("food_budget", ""),
            queue_tolerance=constraints.get("queue_tolerance", ""),
            walk_tolerance=constraints.get("walk_tolerance", ""),
            must_go=constraints.get("must_go", []),
            can_go=constraints.get("can_go", []),
            avoid_places=constraints.get("avoid_places", []),
            avoid_types=constraints.get("avoid_types", []),
            likes=constraints.get("likes", []),
            dislikes=constraints.get("dislikes", []),
            free_text_input=query or "",
        )


class Location(BaseModel):
    longitude: float = 0.0
    latitude: float = 0.0


class Attraction(BaseModel):
    name: str
    address: str = ""
    location: Location = Field(default_factory=Location)
    visit_duration: int = 120
    description: str = ""
    category: str = "景点"
    rating: Optional[float] = None
    photos: List[str] = Field(default_factory=list)
    poi_id: str = ""
    image_url: Optional[str] = None
    ticket_price: int = 0
    route_city: str = ""  # which route city this attraction belongs to
    source: str = "amap"  # 数据来源: amap / amap+llm / amap+xhs / xhs
    reservation_required: bool = False  # 是否需要提前预约
    reservation_tips: str = ""  # 预约提示


class Meal(BaseModel):
    type: str
    name: str
    address: Optional[str] = None
    location: Optional[Location] = None
    description: Optional[str] = None
    estimated_cost: int = 0


class Hotel(BaseModel):
    name: str
    address: str = ""
    location: Optional[Location] = None
    price_range: str = ""
    rating: str = ""
    distance: str = ""
    type: str = ""
    estimated_cost: int = 0
    source: str = "estimated"
    route_city: str = ""


class DayPlan(BaseModel):
    date: str
    day_index: int
    description: str
    transportation: str
    accommodation: str
    hotel: Optional[Hotel] = None
    attractions: List[Attraction] = Field(default_factory=list)
    meals: List[Meal] = Field(default_factory=list)


class WeatherInfo(BaseModel):
    date: str
    day_weather: str = ""
    night_weather: str = ""
    day_temp: Union[int, str] = 0
    night_temp: Union[int, str] = 0
    wind_direction: str = ""
    wind_power: str = ""
    source: str = "unknown"
    note: str = ""


class Budget(BaseModel):
    total_attractions: int = 0
    total_hotels: int = 0
    total_meals: int = 0
    total_transportation: int = 0
    total: int = 0


class TripPlan(BaseModel):
    city: str
    origin: str = ""
    waypoints: List[str] = Field(default_factory=list)
    forbidden_cities: List[str] = Field(default_factory=list)
    route_summary: str = ""
    start_date: str
    end_date: str
    days: List[DayPlan]
    weather_info: List[WeatherInfo] = Field(default_factory=list)
    overall_suggestions: str = ""
    budget: Optional[Budget] = None

    def to_legacy_payload(self) -> dict:
        """Return the old EdgeGuard trip_plan shape used by the HMI panels."""
        TRAVEL_GAP = 30  # minutes between attractions

        def _build_slot(attr: Attraction, time_str: str) -> dict:
            return {
                "time": time_str,
                "type": "visit",
                "title": attr.name,
                "desc": attr.description or attr.category,
                "address": attr.address,
                "ticket_price": attr.ticket_price,
                "rating": attr.rating or 0,
                "photo_url": attr.image_url or (attr.photos[0] if attr.photos else ""),
                "visit_duration": attr.visit_duration,
                "cost": attr.ticket_price,
                "source": attr.source,
                "reservation_required": attr.reservation_required,
                "reservation_tips": attr.reservation_tips,
            }

        def _mins(h: int, m: int) -> int:
            return h * 60 + m

        def _fmt(mins: int) -> str:
            h, m = divmod(mins, 60)
            return f"{h:02d}:{m:02d}"

        itinerary = []
        for day in self.days:
            slots = []
            attrs = day.attractions

            # split: morning gets ceil(n/2), afternoon the rest
            n_morning = (len(attrs) + 1) // 2

            # -- breakfast --
            for meal in day.meals:
                if meal.type == "breakfast":
                    slots.append({"time": "08:00", "type": "meal",
                                  "title": meal.name, "desc": meal.description or "",
                                  "address": meal.address or "", "cost": meal.estimated_cost})

            # -- morning attractions --
            cur = _mins(9, 0)
            for attr in attrs[:n_morning]:
                slots.append(_build_slot(attr, _fmt(cur)))
                cur += attr.visit_duration + TRAVEL_GAP

            # -- lunch (after morning, around 12:00 at earliest) --
            lunch_at = max(cur, _mins(12, 0))
            for meal in day.meals:
                if meal.type == "lunch":
                    slots.append({"time": _fmt(lunch_at), "type": "meal",
                                  "title": meal.name, "desc": meal.description or "",
                                  "address": meal.address or "", "cost": meal.estimated_cost})
            cur = lunch_at + 60  # 1 hour for lunch

            # -- afternoon attractions --
            for attr in attrs[n_morning:]:
                slots.append(_build_slot(attr, _fmt(cur)))
                cur += attr.visit_duration + TRAVEL_GAP

            # -- dinner (after last attraction, around 18:30 at earliest) --
            dinner_at = max(cur, _mins(18, 30))
            for meal in day.meals:
                if meal.type == "dinner":
                    slots.append({"time": _fmt(dinner_at), "type": "meal",
                                  "title": meal.name, "desc": meal.description or "",
                                  "address": meal.address or "", "cost": meal.estimated_cost})

            # -- afternoon snack (optional) --
            for meal in day.meals:
                if meal.type == "snack":
                    snack_at = (lunch_at + dinner_at) // 2
                    slots.append({"time": _fmt(snack_at), "type": "meal",
                                  "title": meal.name, "desc": meal.description or "",
                                  "address": meal.address or "", "cost": meal.estimated_cost})

            slots.sort(key=lambda item: item.get("time", ""))
            hotel_payload = day.hotel.model_dump() if day.hotel else None
            itinerary.append({
                "day": day.day_index + 1,
                "date": day.date,
                "hotel": hotel_payload,
                "hotel_source": (day.hotel.source if day.hotel else ""),
                "slots": slots,
            })

        budget = self.budget or Budget()
        legacy_budget = {
            "total": budget.total,
            "tickets": budget.total_attractions,
            "meals": budget.total_meals,
            "transport": budget.total_transportation,
            "hotels": budget.total_hotels,
            "per_day": round(budget.total / len(self.days)) if self.days else budget.total,
        }

        return {
            "city": self.city,
            "origin": self.origin,
            "waypoints": self.waypoints,
            "forbidden_cities": self.forbidden_cities,
            "route_summary": self.route_summary,
            "days": len(self.days),
            "date": self.start_date,
            "start_date": self.start_date,
            "end_date": self.end_date,
            "summary": self.overall_suggestions,
            "budget": legacy_budget,
            "itinerary": itinerary,
            "weather_info": [w.model_dump() for w in self.weather_info],
            "trip_schema": self.model_dump(),
        }
