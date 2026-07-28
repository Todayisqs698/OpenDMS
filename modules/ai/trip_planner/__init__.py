"""Trip planner package inspired by helloagents-trip-planner."""

from .agent import EdgeGuardTripPlanner, get_trip_planner_agent
from .critic import CriticReport, Issue, run_critic
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

__all__ = [
    "Attraction",
    "Budget",
    "CriticReport",
    "DayPlan",
    "EdgeGuardTripPlanner",
    "Hotel",
    "Issue",
    "Location",
    "Meal",
    "TripPlan",
    "TripRequest",
    "WeatherInfo",
    "get_trip_planner_agent",
    "run_critic",
]
