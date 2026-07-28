# EdgeGuard Project Scope

Primary runtime path:

- `backend/main.py`
- `backend/app/`
- `modules/ai/`
- `modules/vision/`
- `frontend/`
- `data/knowledge/`

Reference or migration artifacts, not part of the primary runtime:

- `TripStar-main/`
- `helloagents-trip-planner/`
- `tripstar-edgeguard-comparison/`
- `design/`
- `mobile/`

Working data and runtime state:

- `data/edgeguard.db`
- `data/user_memory.db`
- `data/trip_tasks/`
- `runtime_settings.json`

Do not mix reference projects into the main app import path. If code is needed
from a reference project, migrate the smallest required module into `modules/`
or `frontend/src/` with tests and a clear owner.
