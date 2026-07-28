"""Critic: deterministic validators that catch hard errors before a trip plan is
returned to the user. These are cheap, model-free checks that run after the LLM
produces a draft plan.

The goal is *not* to be clever — it is to guarantee that obvious mistakes
(forbidden cities leaking in, duplicate attractions across days, outdoor
attractions scheduled in storms, impossible driving loads) never reach the HMI.

Each validator returns a list of :class:`Issue`. An empty list means the plan is
clean for that dimension. Issues are structured so the planner can feed them
back to the LLM for a repair round.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Iterable

from .schemas import Attraction, DayPlan, TripPlan, TripRequest, WeatherInfo

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────────────────────
# Issue model
# ──────────────────────────────────────────────────────────────────────────────

# Severity buckets. A single ERROR blocks the plan from being returned as-is and
# triggers a repair round; WARN is surfaced for transparency but does not block.
SEVERITY_ERROR = "error"
SEVERITY_WARN = "warn"

# Stable issue codes — the planner prompt references these so the LLM can map
# the feedback to a concrete fix. Keep the set small and documented.
CODE_FORBIDDEN_CITY = "forbidden_city"
CODE_DUPLICATE_ATTRACTION = "duplicate_attraction"
CODE_OUTDOOR_IN_STORM = "outdoor_in_storm"
CODE_DRIVE_OVERLOAD = "drive_overload"
CODE_SUB_ATTRACTION_SPLIT = "sub_attraction_split"
CODE_HOTEL_IN_FIELD = "hotel_in_wrong_field"


@dataclass
class Issue:
    """A single validation finding produced by a Critic check."""

    code: str
    severity: str
    day_index: int  # 0-based; -1 means plan-global
    message: str
    fix_hint: str = ""
    # Optional references that the repair step can use for targeted edits.
    attraction_name: str = ""
    city: str = ""

    def to_prompt_line(self) -> str:
        """Render as a concise, LLM-actionable line for the repair prompt."""
        day_label = f"Day{self.day_index + 1}" if self.day_index >= 0 else "全局"
        line = f"- [{self.severity.upper()}] {day_label} · {self.message}"
        if self.fix_hint:
            line += f"（修正建议：{self.fix_hint}）"
        return line


@dataclass
class CriticReport:
    """Aggregate result of running all validators."""

    issues: list[Issue] = field(default_factory=list)

    @property
    def errors(self) -> list[Issue]:
        return [i for i in self.issues if i.severity == SEVERITY_ERROR]

    @property
    def has_blocking(self) -> bool:
        return any(i.severity == SEVERITY_ERROR for i in self.issues)

    def prompt_block(self) -> str:
        """Render the whole report as a block the LLM must address line by line."""
        if not self.issues:
            return ""
        lines = [i.to_prompt_line() for i in self.issues]
        return "Critic 发现以下问题，请在重规划时逐一修正：\n" + "\n".join(lines)


# ──────────────────────────────────────────────────────────────────────────────
# Heuristics
# ──────────────────────────────────────────────────────────────────────────────

# Keywords that mark an attraction as essentially outdoor. Used for the
# storm check — we only flag when the weather is genuinely severe so that a
# light "多云" day does not trigger false positives.
_OUTDOOR_KEYWORDS = (
    "山", "峰", "岭", "峡谷", "瀑布", "湖", "公园", "广场", "长城",
    "草原", "沙漠", "滩", "岛", "寺", "塔", "宫", "陵", "遗址", "园",
)

# Weather descriptions that make outdoor visits unsafe or unpleasant. We match
# on substrings so both "大雨" and "暴雨" are caught.
_STORM_KEYWORDS = ("暴雨", "大雨", "雷阵雨", "冰雹", "暴雪", "大风", "沙尘暴")

# Above this many attractions on a single day we consider the day overloaded
# for a road-trip leg (where part of the day is spent driving). City-only days
# use a slightly higher ceiling.
_CITY_MAX_ATTRACTIONS = 4
_ROUTE_MAX_ATTRACTIONS = 3

# Heuristic daily driving-hour estimate per road-trip leg. The overload check
# compares "attractions × avg visit + gaps" against a sane awake budget when the
# day is expected to include a long drive.
_AVG_VISIT_MINUTES = 120
_TRAVEL_GAP_MINUTES = 30
_AWAKE_BUDGET_MINUTES = 14 * 60  # 06:00 → 22:00


def _is_outdoor(attraction: Attraction) -> bool:
    text = f"{attraction.name}{attraction.category}{attraction.description}"
    return any(k in text for k in _OUTDOOR_KEYWORDS)


def _weather_is_storm(weather: WeatherInfo | None) -> bool:
    if weather is None:
        return False
    text = f"{weather.day_weather}{weather.night_weather}"
    return any(k in text for k in _STORM_KEYWORDS)


def _weather_for_day(plan: TripPlan, day: DayPlan) -> WeatherInfo | None:
    for w in plan.weather_info:
        if w.date == day.date:
            return w
    # Fallback: weather_info is often aligned by index rather than date.
    idx = day.day_index
    if 0 <= idx < len(plan.weather_info):
        return plan.weather_info[idx]
    return None


def _text_mentions_city(text: str, cities: Iterable[str]) -> str | None:
    """Return the first forbidden city that appears in *text*, else None."""
    for city in cities:
        if city and city in text:
            return city
    return None


# ──────────────────────────────────────────────────────────────────────────────
# Validators — each is a pure function over (plan, request)
# ──────────────────────────────────────────────────────────────────────────────

def check_forbidden_cities(plan: TripPlan, request: TripRequest) -> list[Issue]:
    """Forbidden cities must not appear anywhere in the itinerary.

    Catches the classic LLM slip where the user said "不去郑州" but the planner
    still drops a 郑州 hotel or attraction into Day 3.
    """
    if not request.forbidden_cities:
        return []
    forbidden = [c.strip() for c in request.forbidden_cities if c and c.strip()]
    if not forbidden:
        return []

    issues: list[Issue] = []
    seen_keys: set[tuple[int, str, str]] = set()

    for day in plan.days:
        fields: list[tuple[str, str]] = []
        for a in day.attractions:
            fields.append(("景点", f"{a.name} {a.address} {a.description} {a.route_city}"))
        if day.hotel:
            h = day.hotel
            fields.append(("酒店", f"{h.name} {h.address} {h.distance} {h.route_city}"))
        fields.append(("描述", day.description))
        for meal in day.meals:
            fields.append(("餐饮", f"{meal.name} {meal.description or ''} {meal.address or ''}"))

        for label, text in fields:
            hit = _text_mentions_city(text, forbidden)
            if not hit:
                continue
            key = (day.day_index, label, hit)
            if key in seen_keys:
                continue
            seen_keys.add(key)
            issues.append(
                Issue(
                    code=CODE_FORBIDDEN_CITY,
                    severity=SEVERITY_ERROR,
                    day_index=day.day_index,
                    message=f"禁城市「{hit}」出现在{label}中",
                    fix_hint=f"移除或替换涉及{hit}的内容，改为允许的城市",
                    city=hit,
                )
            )

    if plan.overall_suggestions:
        hit = _text_mentions_city(plan.overall_suggestions, forbidden)
        if hit:
            issues.append(
                Issue(
                    code=CODE_FORBIDDEN_CITY,
                    severity=SEVERITY_ERROR,
                    day_index=-1,
                    message=f"禁城市「{hit}」出现在总体建议中",
                    fix_hint=f"从 overall_suggestions 中删除{hit}相关表述",
                    city=hit,
                )
            )
    return issues


def check_duplicate_attractions(plan: TripPlan, request: TripRequest) -> list[Issue]:
    """No attraction should appear on more than one day.

    The planner prompt already forbids this, but LLMs routinely violate it.
    The check is by name (normalized) — same name on two days is a defect
    regardless of which city slot it landed in.
    """
    seen: dict[str, int] = {}  # name -> first day_index
    issues: list[Issue] = []

    for day in plan.days:
        for a in day.attractions:
            name = a.name.strip()
            if not name:
                continue
            if name in seen:
                issues.append(
                    Issue(
                        code=CODE_DUPLICATE_ATTRACTION,
                        severity=SEVERITY_ERROR,
                        day_index=day.day_index,
                        message=f"景点「{name}」在 Day{seen[name] + 1} 已出现，Day{day.day_index + 1} 重复",
                        fix_hint=f"Day{day.day_index + 1} 用同城市其他景点替换「{name}」",
                        attraction_name=name,
                    )
                )
            else:
                seen[name] = day.day_index
    return issues


def check_outdoor_in_storm(plan: TripPlan, request: TripRequest) -> list[Issue]:
    """Outdoor attractions should not be scheduled on storm-weather days.

    Only fires when the weather source is a real forecast (we deliberately
    ignore the current_copy fallback — there the "daily" weather is just today's
    weather replicated, so flagging it would produce false positives on every
    outdoor attraction for multi-day trips).
    """
    # Skip if we only have the current-copy fallback: the "per-day" weather is
    # not actually per-day, so a storm flag would be noise.
    sources = {w.source for w in plan.weather_info if w.source}
    if not sources or sources <= {"current_copy", "unknown"}:
        return []

    issues: list[Issue] = []
    for day in plan.days:
        weather = _weather_for_day(plan, day)
        if not _weather_is_storm(weather):
            continue
        for a in day.attractions:
            if not _is_outdoor(a):
                continue
            issues.append(
                Issue(
                    code=CODE_OUTDOOR_IN_STORM,
                    severity=SEVERITY_ERROR,
                    day_index=day.day_index,
                    message=(
                        f"户外景点「{a.name}」安排在{weather.day_weather or weather.night_weather}天气"
                        f"（{day.date}），不宜室外活动"
                    ),
                    fix_hint=(
                        f"将「{a.name}」替换为室内景点（博物馆/科技馆/商场），"
                        "或调整到天气好转的日期"
                    ),
                    attraction_name=a.name,
                )
            )
    return issues


def check_drive_overload(plan: TripPlan, request: TripRequest) -> list[Issue]:
    """Road-trip days must not be overloaded with attractions.

    For route trips each day carries a driving leg, so the attraction ceiling
    is tighter. We also sanity-check the total awake budget: if the summed
    visit durations + gaps would overflow ~14h, the day is impossible.
    """
    if request.trip_type != "route":
        return []

    max_attractions = _ROUTE_MAX_ATTRACTIONS
    issues: list[Issue] = []

    for day in plan.days:
        n = len(day.attractions)
        if n <= max_attractions:
            # Even under the count ceiling, verify the time budget.
            total_minutes = sum(a.visit_duration for a in day.attractions) + max(0, n - 1) * _TRAVEL_GAP_MINUTES
            if total_minutes <= _AWAKE_BUDGET_MINUTES - 4 * 60:
                continue  # at least 4h left for driving + meals
        # Either too many attractions, or the time budget overflows.
        total_minutes = sum(a.visit_duration for a in day.attractions) + max(0, n - 1) * _TRAVEL_GAP_MINUTES
        drive_left = _AWAKE_BUDGET_MINUTES - total_minutes
        issues.append(
            Issue(
                code=CODE_DRIVE_OVERLOAD,
                severity=SEVERITY_ERROR,
                day_index=day.day_index,
                message=(
                    f"Day{day.day_index + 1} 安排了 {n} 个景点"
                    f"（总游览+间隙约 {total_minutes // 60}h，剩余驾驶时间约 {drive_left // 60}h），"
                    "自驾日负载过重"
                ),
                fix_hint=(
                    f"减少到 {max_attractions} 个景点以内，或把部分景点移到纯游览日；"
                    "优先保留起点/终点的标志性景点"
                ),
            )
        )
    return issues


# ──────────────────────────────────────────────────────────────────────────────
# Orchestrator
# ──────────────────────────────────────────────────────────────────────────────

def check_sub_attraction_split(plan: TripPlan, request: TripRequest) -> list[Issue]:
    """同一景区的子区域不应被拆成多个独立景点。

    例如候选列表可能包含「灵隐寺」「灵隐寺-天王殿」「灵隐寺-华严殿」「济公殿」，
    它们应该合并为一个景点而不是分别占满行程。
    """
    issues: list[Issue] = []
    for day in plan.days:
        names = [a.name for a in day.attractions]
        # 找共享前缀的名称对：取前 2-4 个汉字作为基名，看是否有多个景点共享
        from collections import Counter
        for base_len in (4, 3, 2):
            bases = Counter()
            for name in names:
                if len(name) >= base_len:
                    bases[name[:base_len]] += 1
            for base, count in bases.most_common():
                if count >= 2:
                    dup_names = [n for n in names if n.startswith(base)]
                    issues.append(Issue(
                        code=CODE_SUB_ATTRACTION_SPLIT,
                        severity=SEVERITY_ERROR,
                        day_index=day.day_index,
                        message=f"Day{day.day_index + 1} 的景点 {dup_names} 疑似为同一景区的子区域（共享前缀「{base}」），请合并为一个景点",
                        fix_hint=f"将这些子景点合并为一个主景点（如「{base}」），在 description 中提及可游览的区域即可",
                    ))
                    break  # 一天只报一次
            else:
                continue
            break
    return issues


def check_hotel_in_wrong_field(plan: TripPlan, request: TripRequest) -> list[Issue]:
    """酒店名称/地址不应出现在 attractions、meals、description 等字段中。"""
    issues: list[Issue] = []
    for day in plan.days:
        hotel_name = day.hotel.name if day.hotel else ""
        hotel_addr = day.hotel.address if day.hotel else ""
        if not hotel_name and not hotel_addr:
            continue
        # 检查 attractions
        for a in day.attractions:
            if hotel_name and hotel_name in (a.name or ""):
                issues.append(Issue(
                    code=CODE_HOTEL_IN_FIELD,
                    severity=SEVERITY_ERROR,
                    day_index=day.day_index,
                    message=f"酒店名称「{hotel_name}」出现在景点名中",
                    fix_hint="将酒店从 attractions 中移除，酒店信息只放在 hotel 字段",
                ))
            if hotel_name and hotel_name in (a.description or ""):
                issues.append(Issue(
                    code=CODE_HOTEL_IN_FIELD,
                    severity=SEVERITY_WARN,
                    day_index=day.day_index,
                    message=f"酒店信息出现在景点「{a.name}」的 description 中",
                    fix_hint="移除 description 中的酒店名称/地址",
                ))
        # 检查 meals
        for meal in day.meals:
            if hotel_name and hotel_name in (meal.name or ""):
                issues.append(Issue(
                    code=CODE_HOTEL_IN_FIELD,
                    severity=SEVERITY_ERROR,
                    day_index=day.day_index,
                    message=f"酒店名称「{hotel_name}」出现在餐饮名称中",
                    fix_hint="将 meals 中的酒店信息移除，替换为具体餐厅名或通用描述",
                ))
    return issues


_VALIDATORS = (
    check_forbidden_cities,
    check_duplicate_attractions,
    check_sub_attraction_split,
    check_outdoor_in_storm,
    check_drive_overload,
    check_hotel_in_wrong_field,
)


def run_critic(plan: TripPlan, request: TripRequest) -> CriticReport:
    """Run every validator and return the aggregated report.

    A validator that raises is logged and treated as "no issues found" for
    that dimension — we never let a critic bug block the whole plan, because
    the critic's whole point is to be a safety net, not a new failure surface.
    """
    report = CriticReport()
    for validator in _VALIDATORS:
        try:
            report.issues.extend(validator(plan, request))
        except Exception as e:  # noqa: BLE001 — critic must never raise to caller
            logger.warning("Critic validator %s failed: %s", validator.__name__, e)
    return report
