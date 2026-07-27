"""Structured result push helpers shared by Agent API endpoints."""


def iter_structured_result_events(response):
    """Yield structured payloads for result listeners."""
    for result in response.results:
        if not result.success:
            continue
        rec_data = result.data or {}
        if result.intent_category == "navigation" and rec_data.get("nav_data"):
            nav = rec_data["nav_data"]
            yield "navigation", {
                "destination": nav.get("destination", ""),
                "distance_km": nav.get("distance_km", 0),
                "duration_min": nav.get("duration_min", 0),
                "route_summary": nav.get("route_summary", ""),
                "origin": nav.get("origin", "当前位置"),
                "origin_coords": nav.get("origin_coords"),
                "destination_coords": nav.get("destination_coords"),
                "geometry": nav.get("geometry", []),
                "steps": nav.get("steps", []),
                "coordinate_system": nav.get("coordinate_system", ""),
                "source": nav.get("source", ""),
                "map_url": nav.get("map_url", ""),
                "amap_nav_url": nav.get("amap_nav_url", ""),
            }
        elif result.intent_category == "weather":
            weather = rec_data.get("weather", {})
            yield "weather_query", {
                "city": weather.get("city", ""),
                "weather_desc": weather.get("weather_desc", ""),
                "temperature": weather.get("temperature"),
                "driving_context": rec_data.get("reply", ""),
            }
        elif result.intent_category == "trip_plan":
            trip = rec_data.get("trip_plan", {})
            if trip:
                yield "trip_plan", {
                    "city": trip.get("city", ""),
                    "days": trip.get("days", 1),
                    "start_date": trip.get("start_date", ""),
                    "end_date": trip.get("end_date", ""),
                    "summary": trip.get("summary", ""),
                    "budget": trip.get("budget", {}),
                    "itinerary": trip.get("itinerary", []),
                    "weather_info": trip.get("weather_info", []),
                    "trip_schema": trip.get("trip_schema", {}),
                }
        elif result.intent_category == "attractions":
            attrs = rec_data.get("attractions", [])
            if attrs:
                yield "attractions", {
                    "city": rec_data.get("city", ""),
                    "attractions": attrs,
                }


def push_structured_results(response, sync_push):
    """Push structured agent result payloads to WebSocket listeners."""
    for event_type, data in iter_structured_result_events(response):
        sync_push(event_type, data)
