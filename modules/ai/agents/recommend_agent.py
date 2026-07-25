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

logger = logging.getLogger(__name__)


class RecommendAgent:
    """出行建议智能体"""

    def __init__(self):
        self._env_agent = None
        self._llm_client = None

    @property
    def env_agent(self):
        if self._env_agent is None:
            from modules.ai.agents.environment_agent import EnvironmentAgent
            self._env_agent = EnvironmentAgent()
        return self._env_agent

    @property
    def llm(self):
        if self._llm_client is None:
            from modules.ai.deepseek_client import deepseek_client
            self._llm_client = deepseek_client
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
                return self._trip_plan(query)
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
                model="deepseek-v4-flash",
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

    def _trip_plan(self, query: str) -> dict:
        """行程规划 — 用 DeepSeek 生成结构化 JSON 行程。"""
        import json, re
        from datetime import datetime, timedelta

        env_result = self.env_agent.analyze({})
        weather = env_result.get("weather_desc", "晴")
        temp = env_result.get("temperature", 25)

        # 从 query 提取城市和天数
        city_match = re.search(r'(北京|上海|广州|深圳|杭州|成都|重庆|武汉|西安|南京|天津|苏州|长沙|郑州|青岛|厦门)', query)
        city = city_match.group(1) if city_match else "上海"
        cn_num = {'一':1,'二':2,'三':3,'四':4,'五':5,'六':6,'七':7,'八':8,'九':9,'十':10}
        days_match = re.search(r'(\d+|[一二三四五六七八九十]+)\s*(日|天)', query)
        if days_match:
            d = days_match.group(1)
            days = cn_num.get(d) or int(d) if d.isdigit() else 1
        else:
            days = 1

        tomorrow = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
        weather_hint = "优先室内景点" if weather in ('雨','阴','雾','霾','雪') else "室内外皆可"

        # 精简 prompt，减少 tokens，加快响应
        prompt = f"""{city}{days}日游。天气{weather}{temp}°C。{weather_hint}。生成JSON行程：

{{"city":"{city}","days":{days},"date":"{tomorrow}","summary":"概述（20字）","budget":{{"total":总费用,"tickets":门票,"meals":餐饮,"transport":交通}},"itinerary":[{{"day":1,"date":"{tomorrow}","slots":[{{"time":"09:00","type":"visit","title":"景点","desc":"描述","cost":0,"rating":4.5,"ticket_price":60}},{{"time":"12:00","type":"meal","title":"午餐","desc":"美食","cost":50,"rating":0,"ticket_price":0}},{{"time":"14:00","type":"visit","title":"景点","desc":"描述","cost":0,"rating":4.3,"ticket_price":0}},{{"time":"17:00","type":"visit","title":"景点","desc":"描述","cost":60,"rating":4.0,"ticket_price":0}},{{"time":"19:00","type":"meal","title":"晚餐","desc":"结束","cost":0,"rating":0,"ticket_price":0}}]}}]}}

要求：知名景点，真实名称，预算合理(200-500元)，只返回JSON。"""

        try:
            resp = self.llm.client.chat.completions.create(
                model="deepseek-v4-flash",
                messages=[
                    {"role": "system", "content": "只输出JSON，不含markdown代码块。用真实景点名称。"},
                    {"role": "user", "content": prompt},
                ],
                max_tokens=4096,
                temperature=0.6,
                timeout=60,
            )
            text = resp.choices[0].message.content
            if not text:
                raise ValueError("LLM returned empty response")
            text = text.strip()
            # 清理 markdown 代码块
            if text.startswith("```"):
                text = re.sub(r'^```\w*\s*', '', text)
                text = re.sub(r'\s*```$', '', text)
            # 提取 JSON
            m = re.search(r'\{[\s\S]*\}', text)
            if m:
                text = m.group(0)
            trip = json.loads(text)

            budget = trip.get("budget", {})
            summary = trip.get("summary", "")
            reply = f"行程规划已显示在中控屏上咯！{summary}预算约¥{budget.get('total','--')}元～"

            return {
                "success": True,
                "type": "trip_plan",
                "reply": reply,
                "weather": {"desc": weather, "temperature": temp},
                "trip_plan": trip,
                "suggestions": [f"{city}{days}日游", f"预算¥{budget.get('total','--')}"],
                "needs_clarification": False,
            }
        except Exception as e:
            logger.error(f"行程规划失败: {e}")
            return {
                "success": False,
                "type": "trip_plan",
                "reply": f"抱歉，行程规划暂时不可用：{str(e)[:30]}",
                "weather": {"desc": weather, "temperature": temp},
                "trip_plan": None,
                "suggestions": [],
                "error": str(e),
            }

    def _attractions(self, query: str, city: str = "") -> dict:
        """景点/美食推荐。"""
        import json
        env_result = self.env_agent.analyze({"city": city} if city else {})
        weather = env_result.get("weather_desc", "晴")
        temp = env_result.get("temperature", 25)

        target_city = city or "本地"
        is_food = any(w in query for w in ['吃', '美食', '餐厅', '推荐哪家', '哪家好', '有什么推荐', '锅贴', '面', '肉', '菜'])
        focus = "美食餐厅" if is_food else "景点和美食"

        prompt = f"""推荐{target_city}的{focus}。用户说："{query}"。天气：{weather}，{temp}°C。
请返回JSON：{{"city":"{target_city}","attractions":[{{"name":"{'餐厅名' if is_food else '景点/餐厅名'}","category":"{'美食' if is_food else '景点/美食'}","rating":4.5,"ticket_price":{'0' if is_food else '60'},"indoor":true,"address":"地址","weather_hint":"适合当前天气"}}]}}
推荐5个{'，专注推荐知名餐厅和特色小吃' if is_food else ''}。只返回JSON。"""

        try:
            resp = self.llm.client.chat.completions.create(
                model="deepseek-v4-flash",
                messages=[{"role": "system", "content": "只输出JSON。"}, {"role": "user", "content": prompt}],
                max_tokens=4096, temperature=0.7,
            )
            text = resp.choices[0].message.content.strip()
            if text.startswith("```"):
                text = text.split("```")[1]
                if text.startswith("json"): text = text[4:]
            result = json.loads(text.strip())
            attrs = result.get("attractions", [])
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
