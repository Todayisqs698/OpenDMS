"""
出行建议 Agent — 天气/导航/路线规划建议
========================================

整合天气、时间、位置等上下文信息，给出出行建议。

接口规范：
  输入: {"query": "去公司怎么走", "city": "Beijing", "destination": "company"}
  输出: {
    "success": true,
    "type": "navigation" | "weather" | "general",
    "reply": "根据当前路况，建议走...",
    "weather": {"temp": 28, "desc": "晴", ...},
    "suggestions": ["建议...", "注意..."],
    "needs_clarification": false,
    "clarification_question": ""
  }
"""

import logging
from typing import List, Dict, Any

from modules.ai.base_agent import BaseScaffoldAgent
from modules.ai.schemas import RecommendAgentInput, TripPlanOutput, AgentStatus

logger = logging.getLogger(__name__)


class RecommendAgent(BaseScaffoldAgent[RecommendAgentInput, TripPlanOutput]):
    """出行建议智能体

    改造后继承 BaseScaffoldAgent，对外统一入口 run(context)。
    原有 analyze() 保持不变，供旧调用方兼容。
    """

    input_model = RecommendAgentInput
    output_model = TripPlanOutput

    def __init__(self):
        self._env_agent = None
        self._llm_client = None
        self._last_poi_results = []
        self._last_poi_city = ""
        super().__init__()

    @property
    def env_agent(self):
        if self._env_agent is None:
            from modules.ai.agents.environment_agent import EnvironmentAgent
            self._env_agent = EnvironmentAgent()
        return self._env_agent

    @property
    def llm(self):
        if self._llm_client is None:
            from modules.ai.model_factory import get_model_for_agent
            self._llm_client = get_model_for_agent("recommend")
        return self._llm_client

    def analyze(self, data: dict) -> dict:
        """
        分析出行建议请求。

        Args:
            data: 请求数据，包含 query, city, destination 等

        Returns:
            出行建议 dict
        """
        query = data.get("query", "")
        category = data.get("category", "general")

        try:
            if category == "weather":
                return self._weather_advice(query, data.get("city", ""))
            elif category == "navigation":
                return self._navigation_advice(query, data.get("destination", ""))
            elif category == "trip_plan":
                return self._trip_plan(
                    query,
                    city=data.get("city", ""),
                    days=data.get("days"),
                    preference=data.get("preference"),
                )
            elif category == "attractions":
                return self._attractions(query, data.get("city", ""))
            else:
                # 通用建议：结合天气和时间
                return self._general_advice(query)
        except Exception as e:
            logger.error(f"出行建议生成失败: {e}")
            return {
                "success": False,
                "type": "general",
                "reply": f"抱歉，暂时无法提供建议：{str(e)[:30]}",
                "weather": {},
                "suggestions": [],
                "error": str(e),
            }

    def _weather_advice(self, query: str = "", city: str = "") -> dict:
        """天气建议。"""
        env_result = self.env_agent.analyze({"city": city} if city else {})

        weather_desc = env_result.get("weather_desc", "未知")
        temp = env_result.get("temperature", "N/A")
        humidity = env_result.get("humidity", "N/A")
        context = env_result.get("driving_context", "")
        alerts = env_result.get("alerts", [])

        reply = f"当前天气：{weather_desc}，温度 {temp}°C，湿度 {humidity}%。"
        if context:
            reply += f"\n{context}"

        suggestions = []
        if alerts:
            for alert in alerts[:2]:
                suggestions.append(alert.get("text", ""))
        else:
            suggestions.append("天气良好，适合出行")
            suggestions.append("注意检查车辆状况")

        return {
            "success": True,
            "type": "weather",
            "reply": reply,
            "weather": {
                "desc": weather_desc,
                "temperature": temp,
                "humidity": humidity,
                "icon": env_result.get("weather_icon", ""),
            },
            "suggestions": suggestions[:3],
            "needs_clarification": False,
        }

    def _navigation_advice(self, query: str = "", destination: str = "") -> dict:
        """导航建议 — 调用 tools.start_navigation 获取真实路线规划。"""
        # 如果 LLM 提取了 destination，优先使用
        if not destination:
            # 否则从 query 中去掉导航前缀词提取
            import re
            destination = re.sub(r"帮我|导航|到|去|一下|吧|怎么走|路线|规划", "", query).strip()

        if not destination or "去哪" in query or "哪里" in query:
            return {
                "success": True,
                "type": "navigation",
                "reply": "请告诉我您想去哪里？我可以为您规划最佳路线。",
                "weather": {},
                "suggestions": [],
                "needs_clarification": True,
                "clarification_question": "请问您的目的地是哪里？",
            }

        # 调用 tools.py 的 start_navigation 获取真实路线
        try:
            from modules.ai.tools import start_navigation
            nav_result = start_navigation(destination=destination)

            # 语义地点（家/公司）未设置时，工具返回 needs_clarification
            if nav_result.get("needs_clarification"):
                clarification = nav_result.get("clarification_question",
                                               f"请问您要导航到哪里？")
                return {
                    "success": True,
                    "type": "navigation",
                    "reply": clarification,
                    "weather": {},
                    "suggestions": [],
                    "needs_clarification": True,
                    "clarification_question": clarification,
                }

            if nav_result.get("success"):
                distance = nav_result.get("distance_km", 0)
                duration = nav_result.get("duration_min", 0)
                origin = nav_result.get("origin", "当前位置")
                route_summary = nav_result.get("route_summary", "")

                reply = f"已为您规划从{origin}到{destination}的路线，全程{distance}公里，预计{duration}分钟。"
                if route_summary:
                    reply += f"途经：{route_summary}。"

                return {
                    "success": True,
                    "type": "navigation",
                    "reply": reply,
                    "weather": {},
                    "destination": destination,
                    "distance_km": distance,
                    "duration_min": duration,
                    "origin": origin,
                    "suggestions": [
                        f"目的地: {destination}",
                        f"距离: {distance}公里",
                        f"预计时间: {duration}分钟",
                    ],
                    "needs_clarification": False,
                    "nav_data": nav_result,  # 附带完整导航数据供前端使用
                }
            else:
                error = nav_result.get("error", "路线规划失败")
                return {
                    "success": False,
                    "type": "navigation",
                    "reply": f"抱歉，无法规划前往{destination}的路线：{error}",
                    "weather": {},
                    "suggestions": [],
                    "needs_clarification": False,
                    "error": error,
                }
        except Exception as e:
            logger.error(f"导航调用失败: {e}")
            return {
                "success": False,
                "type": "navigation",
                "reply": f"导航服务暂时不可用：{str(e)[:30]}",
                "weather": {},
                "suggestions": [],
                "needs_clarification": False,
                "error": str(e),
            }

    def _general_advice(self, query: str = "") -> dict:
        """通用出行建议。"""
        env_result = self.env_agent.analyze({})

        temp = env_result.get("temperature", 25)
        weather = env_result.get("weather_desc", "晴")

        try:
            prompt = f"""用户说："{query}"
当前天气：{weather}，{temp}°C
请给出一句简短的出行建议（30字内）。"""

            response = self.llm.client.chat.completions.create(
                model=self.llm.chat_model,
                messages=[
                    {"role": "system", "content": "你是贴心的出行助手，回答简洁实用。"},
                    {"role": "user", "content": prompt},
                ],
                max_tokens=512,
                temperature=0.7,
            )
            reply = response.choices[0].message.content.strip()
        except Exception:
            reply = f"今日天气{weather}，{temp}°C，祝您出行顺利。"

        return {
            "success": True,
            "type": "general",
            "reply": reply,
            "weather": {
                "desc": weather,
                "temperature": temp,
            },
            "suggestions": ["出行注意安全", "检查车辆状况"],
            "needs_clarification": False,
        }

    def _trip_plan(self, query: str, city: str = "", days: int = None, preference: str = None) -> dict:
        """Plan a trip via the dedicated helloagents-style planner."""
        city = (city or "").strip()
        extracted = self._extract_route_trip_params(query)
        if not city:
            city = extracted.get("city", "")
        if days is None:
            days = extracted.get("days")

        if not city:
            return {
                "success": True,
                "type": "trip_plan",
                "reply": "请告诉我想规划哪个城市的一日游？",
                "weather": {},
                "trip_plan": None,
                "suggestions": [],
                "needs_clarification": True,
                "clarification_question": "请问目的地城市是哪里？",
            }

        days = max(1, min(int(days or 1), 30))
        origin = extracted.get("origin", "")
        waypoints = extracted.get("waypoints", [])
        forbidden_cities = extracted.get("forbidden_cities", [])

        try:
            from modules.ai.trip_planner import get_trip_planner_agent
            return get_trip_planner_agent().plan_from_text(
                query=query,
                city=city,
                days=days,
                preference=preference,
                origin=origin,
                waypoints=waypoints,
                forbidden_cities=forbidden_cities,
            )
        except Exception as e:
            logger.error("Trip planner failed: %s", e)
            return {
                "success": False,
                "type": "trip_plan",
                "reply": f"抱歉，行程规划暂时不可用：{str(e)[:30]}",
                "weather": {},
                "trip_plan": None,
                "suggestions": [],
                "error": str(e),
            }

    def _extract_route_trip_params(self, query: str) -> dict:
        """Extract origin, destination, required waypoint cities and days for route trips."""
        import re

        extracted = self._llm_extract_trip_params(query)
        params = dict(extracted or {})

        compact = re.sub(r"\s+", "", query or "")
        cn_num = {'一': 1, '二': 2, '两': 2, '三': 3, '四': 4, '五': 5, '六': 6, '七': 7, '八': 8, '九': 9, '十': 10}
        day_match = re.search(r'(\d+|[一二两三四五六七八九十]+)\s*(?:日|天)', compact)
        if day_match:
            raw_days = day_match.group(1)
            params["days"] = int(raw_days) if raw_days.isdigit() else cn_num.get(raw_days, params.get("days", 1))

        route_match = re.search(r"从(?P<origin>.+?)(?:自驾)?(?:到|去|前往)(?P<dest>.+?)(?:的|，|,|。|$)", compact)
        if route_match:
            origin = self._clean_city_name(route_match.group("origin"))
            dest = self._clean_city_name(route_match.group("dest"))
            if origin:
                params["origin"] = origin
            if dest:
                params["city"] = dest
            params["is_multi_city"] = True

        waypoint_match = re.search(r"(?:途径|途经|经过|路过|必须途径|必须途经)(?P<waypoints>.+?)(?:的|，|,|。|$)", compact)
        if waypoint_match:
            waypoints = self._split_waypoints(waypoint_match.group("waypoints"))
            if waypoints:
                params["waypoints"] = waypoints
                params["is_multi_city"] = True

        forbidden_match = re.search(r"(?:不要去|不去|别去|避开|绕开|不要经过|不经过|别经过|不要途经|不要途径)(?P<cities>.+?)(?:的|，|,|。|$)", compact)
        if forbidden_match:
            forbidden = self._split_forbidden_cities(forbidden_match.group("cities"))
            if forbidden:
                params["forbidden_cities"] = forbidden

        params.setdefault("waypoints", [])
        params.setdefault("forbidden_cities", [])
        forbidden_set = set(params.get("forbidden_cities", []))
        params["waypoints"] = [
            city for city in params.get("waypoints", [])
            if city and city not in {params.get("origin", ""), params.get("city", "")} and city not in forbidden_set
        ]
        params["forbidden_cities"] = [
            city for city in params.get("forbidden_cities", [])
            if city and city not in {params.get("origin", ""), params.get("city", "")}
        ]
        return params

    def _split_waypoints(self, text: str) -> List[str]:
        import re
        cleaned = re.sub(r"(中间|必须|途径|途经|经过|路过|和|与|及)", " ", text or "")
        parts = [self._clean_city_name(part) for part in re.split(r"[、,，\s]+", cleaned)]
        return [part for part in parts if part]

    def _split_forbidden_cities(self, text: str) -> List[str]:
        import re
        cleaned = re.sub(r"(不要去|不去|别去|避开|绕开|不要经过|不经过|别经过|不要途经|不要途径|和|与|及)", " ", text or "")
        parts = [self._clean_city_name(part) for part in re.split(r"[、,，\s]+", cleaned)]
        seen = set()
        result = []
        for part in parts:
            if part and part not in seen:
                seen.add(part)
                result.append(part)
        return result

    def _clean_city_name(self, value: str) -> str:
        import re
        value = re.sub(r"(自驾|出发|行程|行程规划|路线|旅游|旅行|游玩|七日|7日|七天|7天|三日|3日|三天|3天)", "", value or "")
        value = re.sub(r"(不要去|不去|别去|避开|绕开|不要经过|不经过|别经过|不要途经|不要途径)", "", value)
        value = re.sub(r"(中间)?(必须)?(途径|途经|经过|路过).*$", "", value)
        value = re.sub(r"(的)?(七|7|六|6|五|5|四|4|三|3|两|2|二|一|1)(日|天).*$", "", value)
        return value.strip(" ，,。")

    def _llm_extract_trip_params(self, query: str) -> dict:
        """Use LLM to extract destination city and days from any phrasing."""
        import json as _json
        try:
            if not self.llm.is_available:
                return {}
            resp = self.llm.client.chat.completions.create(
                model=self.llm.chat_model,
                messages=[{
                    "role": "system",
                    "content": (
                        "Extract trip destination city, number of days, and whether this is a "
                        "multi-city road-trip (途经/经过/中途停/路过 multiple cities) from user input. "
                        "For '从X到Y'/ 'X出发去Y', destination is Y, NOT X. "
                        "CRITICAL: 新疆→乌鲁木齐, 西藏→拉萨, 内蒙古→呼和浩特. Always resolve province to capital. "
                        "Output ONLY valid JSON: "
                        '{"city": "目的地城市名(必须是城市不是省份)", "origin": "起点城市名或空", "waypoints": ["必经城市"], '
                        '"forbidden_cities": ["禁止经过或不要去的城市"], "days": 数字, "is_multi_city": true/false, '
                        '"reason": "简短说明如果是多城路线为什么"}'
                    ),
                }, {
                    "role": "user",
                    "content": query,
                }],
                max_tokens=200,
                temperature=0,
            )
            raw = resp.choices[0].message.content.strip()
            if "{" in raw and "}" in raw:
                raw = raw[raw.find("{"):raw.rfind("}") + 1]
            return _json.loads(raw)
        except Exception:
            return {}

    def _attractions(self, query: str, city: str = "") -> dict:
        """景点/美食推荐。"""
        import json
        detail = self._answer_poi_detail_from_context(query)
        if detail:
            return detail

        env_result = self.env_agent.analyze({"city": city} if city else {})
        weather = env_result.get("weather_desc", "晴")
        temp = env_result.get("temperature", 25)

        target_city = city or "本地"
        is_food = any(w in query for w in ['吃', '美食', '餐厅', '推荐哪家', '哪家好', '有什么推荐', '锅贴', '面', '肉', '菜'])
        focus = "美食餐厅" if is_food else "景点和美食"

        prompt = f"""推荐{target_city}的{focus}。用户说："{query}"。天气：{weather}，{temp}°C。
请返回JSON：{{"city":"{target_city}","attractions":[{{"name":"{'餐厅名' if is_food else '景点/餐厅名'}","category":"{'美食' if is_food else '景点/美食'}","rating":4.5,"ticket_price":{'0' if is_food else '60'},"indoor":true,"address":"地址","weather_hint":"适合当前天气"}}]}}
推荐{'，专注推荐知名餐厅和特色小吃' if is_food else ''}。只返回JSON。"""

        try:
            resp = self.llm.client.chat.completions.create(
                model=self.llm.chat_model,
                messages=[{"role": "system", "content": "只输出JSON。"}, {"role": "user", "content": prompt}],
                max_tokens=4096, temperature=0.7,
            )
            text = resp.choices[0].message.content.strip()
            if text.startswith("```"):
                text = text.split("```")[1]
                if text.startswith("json"): text = text[4:]
            result = json.loads(text.strip())
            attrs = result.get("attractions", [])
            self._last_poi_results = attrs
            self._last_poi_city = result.get("city", target_city)
            names = [a["name"] for a in attrs[:3]]
            return {
                "success": True,
                "type": "attractions",
                "reply": f"为您推荐{target_city}的{len(attrs)}个目的地：{'、'.join(names)}等。",
                "city": result.get("city", target_city),
                "attractions": attrs,
                "suggestions": names,
                "needs_clarification": False,
            }
        except Exception as e:
            logger.error(f"景点推荐失败: {e}")
            return {"success": False, "type": "attractions", "reply": f"抱歉，推荐暂时不可用：{str(e)[:30]}", "error": str(e)}

    def _answer_poi_detail_from_context(self, query: str) -> dict:
        """Answer follow-up questions about the last recommended POI list."""
        if not query or not self._last_poi_results:
            return {}

        detail_words = ("在哪里", "地址", "人均", "多少钱", "价格", "评分", "怎么样", "电话", "营业")
        if not any(word in query for word in detail_words):
            return {}

        matched = None
        for item in self._last_poi_results:
            name = str(item.get("name", ""))
            if name and (name in query or query in name):
                matched = item
                break
        if not matched:
            for item in self._last_poi_results:
                name = str(item.get("name", ""))
                if name and any(part and part in query for part in name.replace("·", " ").split()):
                    matched = item
                    break

        if not matched:
            return {}

        name = matched.get("name", "")
        address = matched.get("address") or matched.get("location") or "暂无地址信息"
        rating = matched.get("rating")
        avg_cost = (
            matched.get("avg_cost")
            or matched.get("cost")
            or matched.get("ticket_price")
            or matched.get("price")
        )
        category = matched.get("category") or matched.get("type") or "目的地"

        rating_text = f"{rating}分" if rating not in (None, "", 0, 0.0) else "暂无评分"
        cost_text = f"约{avg_cost}元" if avg_cost not in (None, "", 0, 0.0) else "暂无人均价格"
        reply = f"{name}：地址 {address}；人均 {cost_text}；评分 {rating_text}。"

        return {
            "success": True,
            "type": "poi_detail",
            "reply": reply,
            "city": self._last_poi_city,
            "poi": {
                "name": name,
                "category": category,
                "address": address,
                "rating": rating,
                "avg_cost": avg_cost,
                "location": matched.get("location", ""),
                "photo_url": matched.get("photo_url", ""),
            },
            "suggestions": [name],
            "needs_clarification": False,
        }

    # ── BaseScaffoldAgent 实现 ──

    def _run_impl(self, context: RecommendAgentInput) -> TripPlanOutput:
        """统一入口：RecommendAgentInput → 现有 analyze() → TripPlanOutput"""
        data = {
            "query": context.query,
            "category": context.category,
            "city": context.city,
            "destination": context.destination,
            "days": context.days,
            "preference": context.preference,
        }
        result = self.analyze(data)

        # 行程模板匹配：从 trip_templates.json 查找匹配的模板
        template_id = None
        evidence_ids: list[str] = []
        if context.category == "trip_plan" and context.city:
            tmpl = self._match_trip_template(context.city, context.days)
            if tmpl:
                template_id = tmpl["id"]
                evidence_ids.append(f"[TMPL:{tmpl['id']}]")

        # 导航类结果添加 API 证据引用
        if result.get("type") == "navigation" and result.get("nav_data"):
            evidence_ids.append("[API:amap_nav]")
        elif result.get("type") == "weather" and result.get("weather"):
            evidence_ids.append("[API:amap_weather]")
        elif result.get("type") == "attractions" and result.get("attractions"):
            evidence_ids.append("[API:amap_poi]")

        return TripPlanOutput(
            status=AgentStatus.SUCCEEDED if result.get("success") else AgentStatus.FAILED,
            city=result.get("city", context.city),
            days=context.days,
            reply=result.get("reply", ""),
            type=result.get("type", "general"),
            trip_plan=result.get("trip_plan"),
            weather=result.get("weather", {}),
            nav_data=result.get("nav_data"),
            attractions=result.get("attractions", []),
            suggestions=result.get("suggestions", []),
            needs_clarification=result.get("needs_clarification", False),
            clarification_question=result.get("clarification_question", ""),
            template_id=template_id,
            evidence_ids=evidence_ids,
        )

    @staticmethod
    def _match_trip_template(city: str, days: int) -> dict | None:
        """从 trip_templates.json 查找匹配的行程模板"""
        import json
        import os
        template_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(
                os.path.dirname(os.path.abspath(__file__))))),
            "data", "knowledge", "trip_templates.json"
        )
        try:
            with open(template_path, "r", encoding="utf-8") as f:
                templates = json.load(f)
        except Exception:
            return None

        for tmpl in templates:
            if tmpl.get("city") == city and tmpl.get("days") == days:
                return tmpl
        # 退化：城市匹配但天数不同
        for tmpl in templates:
            if tmpl.get("city") == city:
                return tmpl
        return None
