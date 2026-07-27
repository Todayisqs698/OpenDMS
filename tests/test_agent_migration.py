from types import SimpleNamespace
import importlib.util
from pathlib import Path

from modules.ai.intention_agent import IntentionAgent, rule_based_intent_detection
from modules.ai.intent_guard import BLOCK, CLARIFY, guard_intent, normalize_intent
from modules.ai.local_decision_engine import decide_locally
from modules.ai.orchestrator import AgentOrchestrator, ExecutionResult
from modules.ai.structured_results import push_structured_results
from modules.ai.memory import LongTermMemory
from modules.ai.trip_planner import get_trip_planner_agent
from modules.ai.trip_planner.agent import EdgeGuardTripPlanner, _normalize_keys
from modules.ai.trip_planner.schemas import Attraction, Hotel, TripPlan, TripRequest, WeatherInfo
from modules.ai.tools import get_weather_forecast, plan_trip, search_hotels


def _load_recommend_agent_class():
    path = Path(__file__).resolve().parents[1] / "modules" / "ai" / "agents" / "recommend_agent.py"
    spec = importlib.util.spec_from_file_location("recommend_agent_for_test", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.RecommendAgent


def test_trip_plan_rule_needs_llm_for_slot_filling():
    intents = rule_based_intent_detection("杭州几日游")

    assert intents
    assert intents[0].category == "trip_plan"
    assert intents[0].confidence <= 0.70
    assert IntentionAgent()._needs_llm("杭州几日游", intents)[0] is True


def test_high_confidence_control_skips_llm():
    intents = rule_based_intent_detection("打开空调")

    assert intents
    assert intents[0].category == "ac_control"
    assert intents[0].confidence > 0.72
    assert IntentionAgent()._needs_llm("打开空调", intents) == (
        False,
        "high_confidence_rule",
    )


def test_local_speech_does_not_execute_weak_keywords():
    samples = ["好的", "不去了", "暂停这个话题", "这个路线是什么意思"]

    for text in samples:
        result = decide_locally({"trigger": "speech", "data": {"text": text}})
        assert result.get("decision_mode") != "EXECUTE"
        assert result.get("action_code") not in {
            "Navigate",
            "StopMusic",
            "NoticeRoad",
        }


def test_local_speech_executes_only_explicit_commands():
    result = decide_locally({"trigger": "speech", "data": {"text": "打开空调"}})

    assert result["decision_mode"] == "EXECUTE"
    assert result["action_code"] == "TurnOnAC"


def test_navigation_rule_requires_explicit_destination():
    weak = rule_based_intent_detection("这个路线是什么意思")
    strong = rule_based_intent_detection("导航到北京天安门")

    assert all(intent.category != "navigation" or not intent.params.get("destination") for intent in weak)
    assert any(
        intent.category == "navigation" and intent.params.get("destination") == "北京天安门"
        for intent in strong
    )


def test_intent_guard_clarifies_missing_navigation_destination():
    intent = SimpleNamespace(
        id="n1",
        category="navigation",
        agent="recommend_agent",
        priority=4,
        description="导航查询",
        params={},
        confidence=0.9,
        metadata={},
    )

    normalized = normalize_intent(intent)
    decision = guard_intent(normalized, {"severity": "normal"})

    assert decision.allowed is False
    assert decision.mode == CLARIFY
    assert decision.missing_slots == ["destination"]


def test_intent_guard_blocks_distracting_task_when_dangerous():
    intent = SimpleNamespace(
        id="m1",
        category="music_control",
        agent="control_executor",
        priority=6,
        description="播放音乐",
        params={"action": "play"},
        confidence=0.9,
        metadata={},
    )

    decision = guard_intent(normalize_intent(intent), {"severity": "dangerous"})

    assert decision.allowed is False
    assert decision.mode == BLOCK


def test_orchestrator_clarifies_before_running_missing_slot_tool():
    orch = AgentOrchestrator()
    intent = SimpleNamespace(
        id="n1",
        category="navigation",
        agent="recommend_agent",
        priority=4,
        description="导航查询",
        params={},
        confidence=0.9,
        metadata={},
    )

    result = orch._execute_one_intent(intent, "导航", {"severity": "normal"})

    assert result.success is True
    assert result.data["type"] == "guard_decision"
    assert result.data["mode"] == CLARIFY
    assert "哪里" in result.reply_text


def test_orchestrator_parallel_gate_blocks_react_agent():
    orch = AgentOrchestrator()
    intents = [
        SimpleNamespace(category="trip_plan", agent="recommend_agent", params={}, metadata={}),
        SimpleNamespace(category="chitchat", agent="react_agent", params={}, metadata={}),
    ]

    assert orch._can_parallelize(intents) is False


def test_orchestrator_parallel_gate_allows_independent_recommendations():
    orch = AgentOrchestrator()
    intents = [
        SimpleNamespace(category="trip_plan", agent="recommend_agent", params={}, metadata={}),
        SimpleNamespace(category="weather", agent="recommend_agent", params={}, metadata={}),
    ]

    assert orch._can_parallelize(intents) is True


def test_weather_structured_push_uses_city_and_weather_desc():
    pushed = []
    response = SimpleNamespace(results=[
        ExecutionResult(
            intent_id="w1",
            intent_category="weather",
            agent_name="recommend_agent",
            success=True,
            data={
                "reply": "适合出行",
                "weather": {
                    "city": "杭州",
                    "weather_desc": "小雨",
                    "temperature": 26,
                },
            },
        )
    ])

    push_structured_results(response, lambda event, data: pushed.append((event, data)))

    assert pushed == [(
        "weather_query",
        {
            "city": "杭州",
            "weather_desc": "小雨",
            "temperature": 26,
            "driving_context": "适合出行",
        },
    )]


def test_memory_supports_dislike_and_decay(tmp_path):
    db_path = tmp_path / "memory.db"
    mem = LongTermMemory(str(db_path))
    mem.set_like("ac_temp", 22)
    mem.set_dislike("music_artist", "周杰伦")

    value, weight = mem.get_pref_with_decay("ac_temp")
    prefs = mem.get_all_preferences()

    assert value == 22
    assert 0 < weight <= 1
    assert prefs["music_artist"]["pref_type"] == "dislike"
    assert prefs["music_artist"]["value"] == "周杰伦"


def test_trip_plan_llm_extracts_params_from_complex_phrasing(monkeypatch):
    """LLM-based param extraction handles '从X到Y', 'X日游', etc."""
    class FakeCompletions:
        def create(self, **kwargs):
            content = kwargs["messages"][-1]["content"]
            if "天津" in content and "新疆" in content:
                city, days = "新疆", 7
            elif "腾冲" in content:
                city, days = "腾冲", 1
            elif "杭州" in content:
                city, days = "杭州", 3
            else:
                city, days = "北京", 1
            msg = SimpleNamespace(content='{"city": "' + city + '", "days": ' + str(days) + '}')
            return SimpleNamespace(choices=[SimpleNamespace(message=msg)])

    fake_client = SimpleNamespace(is_available=True, client=SimpleNamespace(chat=SimpleNamespace(completions=FakeCompletions())))
    monkeypatch.setattr("modules.ai.deepseek_client.deepseek_client", fake_client)
    agent = _load_recommend_agent_class()()

    r1 = agent._llm_extract_trip_params("帮我规划从天津到新疆的7日自驾游")
    assert r1["city"] == "新疆"
    assert r1["days"] == 7

    r2 = agent._llm_extract_trip_params("帮我规划腾冲一日游")
    assert r2["city"] == "腾冲"
    assert r2["days"] == 1


def test_route_trip_extracts_origin_destination_waypoints_and_days(monkeypatch):
    fake_client = SimpleNamespace(is_available=False)
    monkeypatch.setattr("modules.ai.deepseek_client.deepseek_client", fake_client)
    agent = _load_recommend_agent_class()()

    params = agent._extract_route_trip_params("帮我规划从天津自驾到乌鲁木齐的七日行程，中间必须途径西安和兰州")

    assert params["origin"] == "天津"
    assert params["city"] == "乌鲁木齐"
    assert params["waypoints"] == ["西安", "兰州"]
    assert params["days"] == 7
    assert params["is_multi_city"] is True


def test_route_trip_extracts_forbidden_city(monkeypatch):
    fake_client = SimpleNamespace(is_available=False)
    monkeypatch.setattr("modules.ai.deepseek_client.deepseek_client", fake_client)
    agent = _load_recommend_agent_class()()

    params = agent._extract_route_trip_params("帮我规划从天津到兰州三日的自驾游路线，中间一定要经过西安，不要去郑州")

    assert params["origin"] == "天津"
    assert params["city"] == "兰州"
    assert params["waypoints"] == ["西安"]
    assert params["forbidden_cities"] == ["郑州"]
    assert params["days"] == 3


def test_recommend_agent_answers_poi_detail_from_previous_results():
    agent = _load_recommend_agent_class()()
    agent._last_poi_city = "腾冲"
    agent._last_poi_results = [{
        "name": "雪域牦牛火锅店",
        "address": "腾冲市火山路88号",
        "rating": 4.6,
        "ticket_price": 98,
        "category": "美食",
    }]

    result = agent._answer_poi_detail_from_context("雪域牦牛火锅店在哪里，人均多少，评分怎么样")

    assert result["success"] is True
    assert result["type"] == "poi_detail"
    assert "腾冲市火山路88号" in result["reply"]
    assert "98" in result["reply"]
    assert "4.6" in result["reply"]


def test_dedicated_trip_planner_returns_strong_schema():
    planner = EdgeGuardTripPlanner()
    planner._search_attractions = lambda request: []
    planner._query_weather = lambda request: []
    planner._search_hotels = lambda request, attractions: []
    planner._llm_plan_trip = lambda request, attractions, weather, hotels, interpreted_context: None

    result = planner.plan_from_text("帮我规划腾冲一日游", city="腾冲", days=1)

    assert result["success"] is True
    assert result["type"] == "trip_plan"
    assert result["trip_schema"]["city"] == "腾冲"
    assert result["trip_schema"]["days"]
    assert result["trip_plan"]["itinerary"]
    assert result["trip_plan"]["budget"]["total"] >= 0


def test_route_trip_fallback_preserves_full_route_context():
    planner = EdgeGuardTripPlanner()
    planner._search_attractions = lambda request: []
    planner._query_weather = lambda request: []
    planner._search_hotels = lambda request, attractions: []
    planner._llm_plan_trip = lambda request, attractions, weather, hotels, interpreted_context: None

    result = planner.plan_from_text(
        "帮我规划从天津自驾到乌鲁木齐的七日行程，中间必须途径西安和兰州",
        city="乌鲁木齐",
        days=7,
        origin="天津",
        waypoints=["西安", "兰州"],
    )

    assert result["success"] is True
    assert result["trip_schema"]["origin"] == "天津"
    assert result["trip_schema"]["waypoints"] == ["西安", "兰州"]
    assert result["trip_schema"]["route_summary"] == "天津 → 西安 → 兰州 → 乌鲁木齐"
    assert result["trip_plan"]["origin"] == "天津"
    assert result["trip_plan"]["waypoints"] == ["西安", "兰州"]
    assert result["trip_plan"]["route_summary"] == "天津 → 西安 → 兰州 → 乌鲁木齐"
    assert "天津 → 西安 → 兰州 → 乌鲁木齐" in result["trip_plan"]["summary"]


def test_plan_trip_tool_forwards_route_fields(monkeypatch):
    calls = []

    class FakePlanner:
        def plan_from_text(self, **kwargs):
            calls.append(kwargs)
            return {
                "success": True,
                "weather": {},
                "trip_plan": {
                    "city": kwargs["city"],
                    "origin": kwargs["origin"],
                    "waypoints": kwargs["waypoints"],
                    "forbidden_cities": kwargs["forbidden_cities"],
                    "days": kwargs["days"],
                    "itinerary": [],
                    "budget": {},
                    "summary": "ok",
                    "trip_schema": {"days": []},
                },
                "trip_schema": {"days": []},
            }

    monkeypatch.setattr("modules.ai.trip_planner.get_trip_planner_agent", lambda: FakePlanner())

    result = plan_trip(city="乌鲁木齐", origin="天津", waypoints=["西安", "兰州"], forbidden_cities=["郑州"], days=7)

    assert result["success"] is True
    assert calls[0]["city"] == "乌鲁木齐"
    assert calls[0]["origin"] == "天津"
    assert calls[0]["waypoints"] == ["西安", "兰州"]
    assert calls[0]["forbidden_cities"] == ["郑州"]
    assert calls[0]["days"] == 7


def test_trip_planner_normalizes_llm_key_aliases_recursively():
    data = {
        "startDate": "2026-07-28",
        "endDate": "2026-07-28",
        "overallSuggestions": "雨天优先室内。",
        "days": [{
            "dayIndex": 0,
            "hotel": {"priceRange": "300元起", "estimatedCost": 320},
            "attractions": [{"ticketPrice": 50, "visitDuration": 90, "photoUrl": "https://example.com/a.jpg"}],
        }],
        "weatherInfo": [{"dayWeather": "小雨", "dayTemp": 24, "nightTemp": 20}],
        "budget": {"totalAttractions": 50, "totalHotels": 320, "totalMeals": 210, "totalTransportation": 50},
    }

    normalized = _normalize_keys(data)

    assert normalized["start_date"] == "2026-07-28"
    assert normalized["overall_suggestions"] == "雨天优先室内。"
    assert normalized["days"][0]["day_index"] == 0
    assert normalized["days"][0]["hotel"]["price_range"] == "300元起"
    assert normalized["days"][0]["hotel"]["estimated_cost"] == 320
    assert normalized["days"][0]["attractions"][0]["ticket_price"] == 50
    assert normalized["days"][0]["attractions"][0]["visit_duration"] == 90
    assert normalized["days"][0]["attractions"][0]["image_url"] == "https://example.com/a.jpg"
    assert normalized["weather_info"][0]["day_weather"] == "小雨"
    assert normalized["weather_info"][0]["day_temp"] == 24
    assert normalized["budget"]["total_transportation"] == 50


def test_trip_planner_llm_path_accepts_alias_json(monkeypatch):
    class FakeCompletions:
        def create(self, **kwargs):
            content = """{
              "city": "腾冲",
              "startDate": "2026-07-28",
              "endDate": "2026-07-28",
              "days": [{
                "date": "2026-07-28",
                "dayIndex": 0,
                "description": "上午火山地质公园，下午热海，动线清晰。",
                "transportation": "自驾",
                "accommodation": "舒适型酒店",
                "hotel": {
                  "name": "腾冲温泉酒店",
                  "address": "腾冲市热海路1号",
                  "priceRange": "480元起",
                  "rating": "4.7",
                  "type": "酒店",
                  "estimatedCost": 480,
                  "source": "amap"
                },
                "attractions": [{
                  "name": "火山地质公园",
                  "address": "腾冲市",
                  "visitDuration": 120,
                  "description": "上午光线好，适合看火山地貌。",
                  "category": "自然景观",
                  "rating": 4.6,
                  "ticketPrice": 35
                }],
                "meals": [{"type": "lunch", "name": "当地午餐", "estimatedCost": 80}]
              }],
              "weatherInfo": [{"date": "2026-07-28", "dayWeather": "多云", "dayTemp": 23, "nightTemp": 18}],
              "overallSuggestions": "先看火山地貌，再去热海放松，节奏适合自驾。",
              "budget": {"totalAttractions": 35, "totalHotels": 480, "totalMeals": 80, "totalTransportation": 50, "total": 645}
            }"""
            message = SimpleNamespace(content=content)
            choice = SimpleNamespace(message=message)
            return SimpleNamespace(choices=[choice])

    fake_client = SimpleNamespace(
        is_available=True,
        client=SimpleNamespace(chat=SimpleNamespace(completions=FakeCompletions())),
    )
    monkeypatch.setattr("modules.ai.deepseek_client.deepseek_client", fake_client)

    request = TripRequest(
        city="腾冲",
        start_date="2026-07-28",
        end_date="2026-07-28",
        travel_days=1,
        free_text_input="帮我规划腾冲一日游",
    )
    planner = EdgeGuardTripPlanner()
    plan = planner._llm_plan_trip(
        request,
        attractions=[],
        weather_info=[],
        hotels=[],
        interpreted_context={"attractions": "", "weather": "", "hotels": ""},
    )

    assert plan is not None
    assert plan.days[0].day_index == 0
    assert plan.days[0].hotel.price_range == "480元起"
    assert plan.days[0].hotel.estimated_cost == 480
    assert plan.days[0].attractions[0].ticket_price == 35
    assert plan.weather_info[0].day_weather == "多云"


def test_trip_planner_prompt_includes_interpreted_context():
    request = TripRequest(
        city="腾冲",
        start_date="2026-07-28",
        end_date="2026-07-28",
        travel_days=1,
        free_text_input="帮我规划腾冲一日游",
    )
    planner = EdgeGuardTripPlanner()
    prompt = planner._build_planner_prompt(
        request,
        attractions=[],
        weather_info=[],
        hotels=[],
        interpreted_context={
            "attractions": "火山地质公园适合上午。",
            "weather": "当前天气仅作参考。",
            "hotels": "优先选择真实高德酒店。",
        },
    )

    assert "景点解读:" in prompt
    assert "火山地质公园适合上午。" in prompt
    assert "天气解读:" in prompt
    assert "当前天气仅作参考。" in prompt
    assert "酒店解读:" in prompt
    assert "优先选择真实高德酒店。" in prompt


def test_trip_planner_prompt_includes_forbidden_and_dedupe_constraints():
    request = TripRequest(
        city="兰州",
        origin="天津",
        waypoints=["西安"],
        forbidden_cities=["郑州"],
        trip_type="route",
        start_date="2026-07-28",
        end_date="2026-07-30",
        travel_days=3,
        free_text_input="从天津到兰州三日，经西安，不去郑州",
    )
    planner = EdgeGuardTripPlanner()
    prompt = planner._build_planner_prompt(
        request,
        attractions=[],
        weather_info=[],
        hotels=[],
        interpreted_context={"attractions": "", "weather": "", "hotels": ""},
    )

    assert "禁止经过/停靠城市: 郑州" in prompt
    assert "全程景点名称不能跨日重复" in prompt
    assert "严格避开禁止城市" in prompt


def test_fallback_route_days_do_not_repeat_same_city_attractions():
    request = TripRequest(
        city="兰州",
        origin="天津",
        waypoints=["西安"],
        forbidden_cities=["郑州"],
        trip_type="route",
        start_date="2026-07-28",
        end_date="2026-07-30",
        travel_days=3,
    )
    attractions = [
        Attraction(name="大雁塔", route_city="西安"),
        Attraction(name="陕西历史博物馆", route_city="西安"),
        Attraction(name="西安城墙", route_city="西安"),
        Attraction(name="大唐不夜城", route_city="西安"),
        Attraction(name="甘肃省博物馆", route_city="兰州"),
        Attraction(name="黄河铁桥", route_city="兰州"),
    ]
    hotels = [
        Hotel(name="西安酒店", route_city="西安", source="amap"),
        Hotel(name="兰州酒店", route_city="兰州", source="amap"),
    ]

    days = EdgeGuardTripPlanner()._assemble_days(request, attractions, hotels)
    names = [attr.name for day in days for attr in day.attractions]

    assert len(names) == len(set(names))
    assert any(day.hotel and day.hotel.route_city == "西安" for day in days[:2])
    assert days[-1].hotel and days[-1].hotel.route_city == "兰州"


def test_llm_payload_repair_removes_duplicate_and_forbidden_attractions():
    request = TripRequest(
        city="兰州",
        origin="天津",
        waypoints=["西安"],
        forbidden_cities=["郑州"],
        trip_type="route",
        start_date="2026-07-28",
        end_date="2026-07-30",
        travel_days=3,
    )
    candidates = [
        Attraction(name="大雁塔", route_city="西安"),
        Attraction(name="陕西历史博物馆", route_city="西安"),
        Attraction(name="西安城墙", route_city="西安"),
        Attraction(name="甘肃省博物馆", route_city="兰州"),
    ]
    data = {
        "city": "兰州",
        "start_date": "2026-07-28",
        "end_date": "2026-07-30",
        "days": [
            {"attractions": [{"name": "大雁塔", "route_city": "西安"}]},
            {"attractions": [{"name": "大雁塔", "route_city": "西安"}, {"name": "郑州二七广场", "route_city": "郑州"}]},
            {"attractions": [{"name": "甘肃省博物馆", "route_city": "兰州"}]},
        ],
    }

    repaired = EdgeGuardTripPlanner()._repair_llm_payload(data, request, candidates, [], [])
    names = [attr["name"] for day in repaired["days"] for attr in day["attractions"]]

    assert len(names) == len(set(names))
    assert "郑州二七广场" not in names
    assert "陕西历史博物馆" in names


def test_search_hotels_uses_hotel_specific_fields(monkeypatch):
    class FakeResponse:
        def json(self):
            return {
                "status": "1",
                "pois": [{
                    "name": "腾冲温泉酒店",
                    "address": "腾冲市热海路1号",
                    "location": "98.5,25.0",
                    "type": "住宿服务;宾馆酒店",
                    "biz_ext": {"rating": "4.7", "cost": "480"},
                    "photos": [{"url": "https://example.com/hotel.jpg"}],
                }],
            }

    monkeypatch.setattr("modules.ai.tools._get_amap_key", lambda: "fake-key")
    monkeypatch.setattr("modules.ai.tools.httpx.get", lambda *args, **kwargs: FakeResponse())

    result = search_hotels("腾冲", count=1, preference="舒适型酒店")
    hotel = result["hotels"][0]

    assert result["success"] is True
    assert hotel["name"] == "腾冲温泉酒店"
    assert hotel["rating"] == "4.7"
    assert hotel["price_range"] == "480元起"
    assert hotel["estimated_cost"] == 480
    assert hotel["source"] == "amap"
    assert "indoor" not in hotel
    assert "weather_hint" not in hotel
    assert "visit_duration" not in hotel


def test_get_weather_forecast_parses_amap_daily_casts(monkeypatch):
    class FakeResponse:
        def __init__(self, payload):
            self._payload = payload

        def json(self):
            return self._payload

    responses = [
        FakeResponse({"status": "1", "geocodes": [{"adcode": "530581"}]}),
        FakeResponse({
            "status": "1",
            "forecasts": [{
                "reporttime": "2026-07-27 10:00:00",
                "casts": [
                    {
                        "date": "2026-07-28",
                        "dayweather": "小雨",
                        "nightweather": "多云",
                        "daytemp": "24",
                        "nighttemp": "18",
                        "daywind": "西南",
                        "daypower": "≤3",
                    },
                    {
                        "date": "2026-07-29",
                        "dayweather": "晴",
                        "nightweather": "晴",
                        "daytemp": "26",
                        "nighttemp": "17",
                        "daywind": "无风向",
                        "daypower": "≤3",
                    },
                ],
            }],
        }),
    ]

    monkeypatch.setattr("modules.ai.tools._get_amap_key", lambda: "fake-key")
    monkeypatch.setattr("modules.ai.tools.httpx.get", lambda *args, **kwargs: responses.pop(0))

    result = get_weather_forecast("腾冲", days=2)

    assert result["success"] is True
    assert result["adcode"] == "530581"
    assert len(result["forecasts"]) == 2
    assert result["forecasts"][0]["day_weather"] == "小雨"
    assert result["forecasts"][0]["night_weather"] == "多云"
    assert result["forecasts"][0]["source"] == "amap_forecast"


def test_trip_planner_query_weather_prefers_forecast(monkeypatch):
    monkeypatch.setattr("modules.ai.tools.get_weather_forecast", lambda city, days: {
        "success": True,
        "forecasts": [{
            "date": "2026-07-28",
            "day_weather": "小雨",
            "night_weather": "多云",
            "day_temp": "24",
            "night_temp": "18",
            "wind_direction": "西南",
            "wind_power": "≤3",
            "source": "amap_forecast",
            "note": "高德逐日天气预报",
        }],
    })
    monkeypatch.setattr("modules.ai.tools.get_weather", lambda city: (_ for _ in ()).throw(AssertionError("should not call current weather")))

    request = TripRequest(city="腾冲", start_date="2026-07-28", end_date="2026-07-28", travel_days=1)
    weather = EdgeGuardTripPlanner()._query_weather(request)

    assert weather[0].day_weather == "小雨"
    assert weather[0].night_weather == "多云"
    assert weather[0].source == "amap_forecast"


def test_trip_planner_query_weather_marks_current_copy_fallback(monkeypatch):
    monkeypatch.setattr("modules.ai.tools.get_weather_forecast", lambda city, days: {
        "success": False,
        "forecasts": [],
    })
    monkeypatch.setattr("modules.ai.tools.get_weather", lambda city: {
        "status": "ok",
        "data": {
            "weather_desc": "多云",
            "temperature": 23,
            "wind_direction": "西南",
            "wind_power": "≤3",
        },
    })

    request = TripRequest(city="腾冲", start_date="2026-07-28", end_date="2026-07-29", travel_days=2)
    weather = EdgeGuardTripPlanner()._query_weather(request)

    assert len(weather) == 2
    assert all(item.day_weather == "多云" for item in weather)
    assert all(item.source == "current_copy" for item in weather)
    assert "非真实逐日预报" in weather[0].note


def test_trip_plan_legacy_payload_keeps_weather_source():
    plan = TripPlan(
        city="腾冲",
        start_date="2026-07-28",
        end_date="2026-07-28",
        days=[],
        weather_info=[
            WeatherInfo(
                date="2026-07-28",
                day_weather="小雨",
                source="amap_forecast",
                note="高德逐日天气预报",
            )
        ],
    )

    legacy = plan.to_legacy_payload()

    assert legacy["weather_info"][0]["source"] == "amap_forecast"
    assert legacy["weather_info"][0]["note"] == "高德逐日天气预报"
