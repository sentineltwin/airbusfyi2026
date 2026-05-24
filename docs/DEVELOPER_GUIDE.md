# Developer Guide

## SentinelTwin — Development Setup & Contribution Guide

> **Version:** 4.4.0 | **Last Updated:** 2026-05-19

---

## Prerequisites

| Tool | Version | Purpose |
|------|---------|---------|
| Python | 3.12+ (tested 3.14) | Backend runtime |
| Node.js | 20+ | Frontend build tool |
| pip | 26+ | Python package manager |
| npm | 10+ | Node package manager |
| PostgreSQL | 16+ | **Optional** — persistent storage |
| Redis | 7+ | **Optional** — caching/sessions |
| Kafka | 7.6+ | **Optional** — event streaming |
| Docker | 24+ | **Optional** — full stack deployment |

---

## First-Time Setup

### Backend

```bash
cd backend

# Create a virtual environment (recommended)
python -m venv venv
venv\Scripts\activate       # Windows
source venv/bin/activate    # Linux/macOS

# Install dependencies
pip install -r requirements.txt

# Or minimal deps for local development (no DB/Redis/Kafka):
pip install fastapi uvicorn pyjwt bcrypt numpy pydantic pydantic-settings \
            python-dotenv sqlalchemy asyncpg

# Copy environment config
copy .env.example .env      # Windows
cp .env.example .env        # Linux/macOS

# Start the server
py -3 main.py               # Windows
python3 main.py             # Linux/macOS
```

### Frontend

```bash
cd frontend
npm install
npm run dev
```

### Verify

```bash
# Health check
curl http://localhost:8000/health

# Detailed health (10 subsystems)
curl http://localhost:8000/health/detailed

# Login
curl -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"sentinel2026"}'

# Open browser
# http://localhost:5173
```

---

## Common Development Tasks

### Adding a New API Endpoint

1. Create or edit a route module in `backend/api/routes/`:

```python
# backend/api/routes/my_feature.py
from fastapi import APIRouter, Request, Depends
from api.routes._auth_utils import get_current_user, require_role

router = APIRouter()

@router.get("/my-data")
async def get_my_data(request: Request, user=Depends(get_current_user)):
    # Access services via app.state
    engine = request.app.state.sensor_engine
    return {"data": engine.get_stats()}

@router.post("/admin-action")
async def admin_action(
    request: Request,
    user=Depends(require_role("administrator", "maintenance_engineer")),
):
    return {"status": "ok"}
```

2. Register in `backend/main.py`:

```python
from api.routes import my_feature

# In create_app():
app.include_router(my_feature.router, prefix=f"{PREFIX}/my-feature", tags=["My Feature"])
```

### Adding a New ECAM Rule

Edit `backend/services/ecam_engine.py`, add to `ECAM_LOGIC_TABLE`:

```python
("my_condition_key", "WARNING", "SYS", ata_chapter, "MESSAGE TEXT",
 "PROCEDURE TEXT", dispatch_impact_bool, "MEL XX-XXX"),
```

### Adding a New Kafka Topic

Edit `backend/services/kafka_producer.py`:

```python
TOPIC_MY_EVENTS = "sentineltwin.my_events"

def publish_my_event(self, data: dict) -> None:
    self._enqueue(TOPIC_MY_EVENTS, {
        "event_type": "MY_EVENT",
        **data,
    })
```

Then call `kafka_producer.publish_my_event(...)` from your engine.

### Adding a New WebSocket Channel

1. In `backend/api/routes/websocket.py`, add broadcast logic in `broadcast_loop()`:

```python
if cycle % N == 0:  # every N seconds
    tasks.append(ws_manager.broadcast_channel("my_channel", {
        "type": "my_data",
        "value": some_value,
    }))
```

### Adding a New Dashboard Panel

1. Add component in `frontend/src/SentinelTwinPanels.jsx`
2. Export the function
3. Import in `frontend/src/SentinelTwin.jsx`
4. Add sidebar entry to `NAV_ITEMS` array
5. Add component to the panel rendering map
6. Handle WebSocket channel data in `sentinel.store.ts`

---

## Architecture Patterns

### Service Access

All services are attached to `app.state` during lifespan:

```python
# In routes — use request.app.state
engine = request.app.state.sensor_engine
twin = request.app.state.twin_engine
kafka = request.app.state.kafka_producer
```

### Authentication

```python
from api.routes._auth_utils import get_current_user, require_role

# Any authenticated user
@router.get("/data")
async def get_data(user=Depends(get_current_user)):
    ...

# Role-restricted
@router.post("/action")
async def create_action(user=Depends(require_role("administrator", "maintenance_engineer"))):
    ...
```

### Service Injection (Kafka / Persistence)

Services are injected into engines in `main.py` lifespan:

```python
sensor_engine.persistence = persistence_service
sensor_engine.kafka = kafka_producer
ecam_engine.persistence = persistence_service
ecam_engine.kafka = kafka_producer
```

### Configuration

```python
from core.config import settings

threshold = settings.AI_ANOMALY_THRESHOLD
port = settings.PORT
```

### Logging

```python
import logging
log = logging.getLogger("sentineltwin.my_module")

log.info("Normal operation")
log.warning("Non-fatal issue: %s", detail)
log.error("Error occurred", exc_info=True)
```

---

## Environment Variables

### Critical Settings

| Variable | Default | Notes |
|----------|---------|-------|
| `SECRET_KEY` | random | **MUST change in production** |
| `DEBUG` | `false` | Set `true` to enable `/api/docs` |
| `DATABASE_URL` | postgresql... | System works without it |
| `REDIS_URL` | redis://... | System works without it |
| `KAFKA_BOOTSTRAP_SERVERS` | localhost:9092 | System works without it |
| `CORS_ORIGINS` | `["http://localhost:5173"]` | **Must be JSON array** |

### .env Format

```bash
# List[str] fields MUST use JSON array syntax:
CORS_ORIGINS=["http://localhost:5173"]

# Boolean fields are case-insensitive:
DEBUG=true

# Strings need NO quotes:
SECRET_KEY=my-secret-key
```

---

## Testing

```bash
cd backend

# Smoke test (10 checks: 8 offline + 5 network)
py -3 _smoke_test.py          # Windows
python3 _smoke_test.py        # Linux/macOS

# Run pytest suite
pytest tests/

# With coverage
pytest --cov=services --cov-report=html tests/

# Performance benchmark
python scripts/benchmark.py
```

### Smoke Test Checks

| # | Category | What It Validates |
|---|----------|-------------------|
| 1 | ARINC 429 | Encode/decode, parity, fault injection |
| 2 | AFDX | Virtual links, network stats, faults |
| 3 | Cybersecurity | Rate limit, replay, spoof, threat level |
| 4 | Persistence | Queue system initialization |
| 5 | Redundancy Voter | 6 edge cases (triplex/duplex/simplex) |
| 6 | WebSocket | Live connection + frame validation |
| 7 | PDF Report | Endpoint + valid PDF header |
| 8 | ARINC 429 API | `/arinc/frame` label decoding |
| 9 | AFDX API | `/afdx/vls` virtual link enumeration |
| 10 | Prometheus | `/metrics` endpoint liveness |

---

## Troubleshooting

### "Python was not found" on Windows
Use `py -3 main.py` instead of `python main.py`. Windows Store aliases can shadow real Python.

### "error parsing value for field CORS_ORIGINS"
Use JSON array syntax: `CORS_ORIGINS=["http://localhost:5173"]`

### Server keeps restarting every 400ms
The file watcher detects log file changes. `reload=False` is already set in main.py.

### ARINC 429 fault injection not working
Use the correct octal label format. POST to `/api/v1/arinc/inject` with `{"label": 134, "fault_type": "FREEZE"}`.

### WebSocket not connecting from frontend
Ensure `vite.config.ts` has the WebSocket proxy:
```typescript
proxy: {
  '/ws': { target: 'ws://localhost:8000', ws: true }
}
```

### Kafka unavailable warning on startup
This is non-fatal. The system logs a warning and continues without event streaming. Install `aiokafka` and start a Kafka broker to enable streaming.

---

## File Quick Reference

| Need to... | Look in... |
|------------|-----------|
| Add an API endpoint | `backend/api/routes/` |
| Change auth/JWT logic | `backend/api/routes/_auth_utils.py` |
| Modify sensor pipeline | `backend/services/sensor_engine.py` |
| Add/change aircraft profiles | `backend/services/sensor_engine.py` (`AIRCRAFT_PROFILES`) |
| Tune AI thresholds | `backend/services/ai_engine.py` or `.env` |
| Add ECAM rules | `backend/services/ecam_engine.py` |
| Change physics model | `backend/services/digital_twin.py` |
| Modify ARINC 429 labels | `backend/services/arinc429_service.py` |
| Modify AFDX virtual links | `backend/services/afdx_service.py` |
| Tune cybersecurity rules | `backend/services/security_engine.py` |
| Add Kafka topics | `backend/services/kafka_producer.py` |
| Configure persistence queues | `backend/services/persistence_service.py` |
| Generate PDF reports | `backend/services/report_service.py` |
| Modify security headers | `backend/middleware/security.py` |
| Update DB schema | `backend/models/db_models.py` + alembic |
| Configure settings | `backend/core/config.py` + `.env` |
| Frontend UI (core panels) | `frontend/src/SentinelTwin.jsx` |
| Frontend UI (extended panels) | `frontend/src/SentinelTwinPanels.jsx` |
| Frontend state management | `frontend/src/stores/sentinel.store.ts` |
| WebSocket channels | `backend/api/routes/websocket.py` |
| Run smoke tests | `backend/_smoke_test.py` |
| Maintenance CRUD | `backend/api/routes/maintenance.py` |

---

*Last updated: 2026-05-19 | v4.4.0*
