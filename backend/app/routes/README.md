# Backend Route Split Plan

This folder is the landing zone for gradually moving endpoints out of
`backend/main.py` without changing behavior in one risky edit.

Suggested one-day-safe migration order:

1. `music.py`: `/api/music/*`
2. `navigation.py`: `/api/navigation/*`, `/api/map/*`, `/api/location`, `/api/gps/*`
3. `settings.py`: `/api/settings`
4. `agent.py`: `/api/agent/*`, `/ws/agent_*`
5. `telemetry.py`: camera, DMS, environment, report endpoints

Each router should own only request/response contracts. Shared mutable state
must move behind small services before the endpoint is migrated.
