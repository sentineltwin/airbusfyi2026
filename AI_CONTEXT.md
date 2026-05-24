# SENTINELTWIN — AI Assistant Context File

> **Purpose:** This file gives any AI assistant (Claude, Gemini, ChatGPT, Copilot, etc.)
> full context about the SentinelTwin project — what it is, how it's built, what's done,
> and what needs future work. Paste this file as context when starting a new conversation.

> **Last Updated:** 2026-05-19 | **Version:** 4.4.0 | **Status:** Operationally Complete

---

## 1. PROJECT IDENTITY

| Field | Value |
|-------|-------|
| **Name** | SentinelTwin |
| **Full Title** | Airbus Airworthiness Assurance & Sensor Integrity Platform |
| **Version** | 4.4.0 |
| **Competition** | Airbus Fly Your Ideas 2026 — Team Lift & Logic (HITS Chennai) |
| **Aircraft** | 7 profiles: A220 (6,400), A319 (7,200), A320 (7,800), A320neo (8,192), A321 (8,500), A330 (10,240), A350 (12,000) |
| **Compliance** | EASA DO-326A, ED-202A, AMC 20-42, ARINC 429/664 |
| **Sensors** | 6,400–12,000 across 14 ATA chapters (dynamic per aircraft profile) |
| **Core Idea** | Framing sensor anomaly detection as a **dynamic configuration integrity** problem (DO-326A) |

---

## 2. WHAT IT DOES (ONE PARAGRAPH)

SentinelTwin is a real-time aerospace platform that validates 6,400–12,000 aircraft sensors (across 7 Airbus aircraft profiles) through a 14-stage pipeline at 20 Hz, detects anomalies using a physics-informed sparse autoencoder + statistical layer (CUSUM), performs 2oo3 redundancy voting with ATA-specific tolerance bands, monitors ARINC 429 bus data and AFDX virtual link timing, enforces cybersecurity via rate limiting and spoof detection, maintains an immutable SHA-256 cryptographic audit chain per DO-326A, generates Airbus-style ECAM advisories, streams events to Kafka topics, provides a full maintenance action CRUD lifecycle, and produces a GO/NO-GO dispatch determination — all streamed live via 10 WebSocket channels to a React dashboard with 18 panels.

---

## 3. TECH STACK

### Backend
| Technology | Version | Purpose |
|------------|---------|---------|
| Python | 3.14 | Core language |
| FastAPI | 0.136+ | REST API + WebSocket |
| Uvicorn | 0.46+ | ASGI server |
| Pydantic v2 | 2.x | Settings + validation |
| SQLAlchemy | 2.x | ORM (async) |
| asyncpg | — | PostgreSQL async driver |
| NumPy | — | AI engine + signal processing |
| bcrypt | — | Password hashing |
| PyJWT | — | JWT tokens |
| aiokafka | — | Kafka event streaming |
| ReportLab | — | PDF airworthiness reports |

### Frontend
| Technology | Version | Purpose |
|------------|---------|---------|
| React | 18.3 | UI framework |
| Vite | 5.3 | Dev server + build |
| Zustand | 4.5 | State management |
| Recharts | 2.12 | Data visualisation charts |
| Three.js + R3F | 0.164 | 3D aircraft model |
| Lucide React | 0.383 | Icons |
| TypeScript | 5.4 | Type checking (devDep) |

### Infrastructure (Docker — all optional)
| Service | Image | Port |
|---------|-------|------|
| PostgreSQL + TimescaleDB | timescale/timescaledb:latest-pg16 | 5432 |
| Redis | redis:7.2-alpine | 6379 |
| Kafka | confluentinc/cp-kafka:7.6.0 | 9092 |
| Zookeeper | confluentinc/cp-zookeeper:7.6.0 | 2181 |
| Prometheus | prom/prometheus:v2.51.0 | 9090 |
| Grafana | grafana/grafana:10.4.0 | 3001 |
| Nginx | nginx:1.25-alpine | 80, 443 |

### Key: The system runs WITHOUT Docker/DB/Redis/Kafka in standalone mode (graceful fallbacks).

---

## 4. ARCHITECTURE

### 4.1 Five Core Engines (all async, run as background tasks)

| Engine | File | Rate | What It Does |
|--------|------|------|-------------|
| **Sensor Execution Engine** | `services/sensor_engine.py` | 20 Hz | 8,192 sensors through 14-stage validation pipeline. ThreadPoolExecutor with 16 workers |
| **AI Anomaly Engine** | `services/ai_engine.py` | 5 Hz | Sparse autoencoder (256→128→64→32→64→128→256) on physics-normalised residuals + CUSUM/EGT spike/freeze statistical layer |
| **Digital Twin Engine** | `services/digital_twin.py` | 10 Hz | Full A320neo physics model: ISA atmosphere, LEAP-1A engines, Green/Blue/Yellow hydraulics, electrical, fuel |
| **ECAM Engine** | `services/ecam_engine.py` | 0.5 Hz | 21 Airbus-style advisory rules, 4 severity levels (EMERGENCY/WARNING/CAUTION/STATUS). Publishes to Kafka |
| **Hash Chain Service** | `services/hash_service.py` | On-demand | SHA-256 immutable audit chain, genesis block → append per scan cycle, full chain verification |

### 4.2 Additional Service Modules

| Module | File | What It Does |
|--------|------|-------------|
| **Kafka Event Producer** | `services/kafka_producer.py` | Async Kafka streaming to 4 topics (anomalies, ecam, dispatch, hashchain). Graceful no-op fallback |
| **ARINC 429 Simulator** | `services/arinc429_service.py` | Full 32-bit word encode/decode, 11 Airbus labels, SSM/SDI/parity, fault injection |
| **AFDX Monitor** | `services/afdx_service.py` | 5 virtual links, BAG enforcement, jitter tracking, frame sequencing, timing fault injection |
| **Cybersecurity Engine** | `services/security_engine.py` | Rate limiting, nonce-cache replay detection, 4-method spoof detection, composite threat level |
| **Persistence Service** | `services/persistence_service.py` | Async write-batching via `asyncio.Queue` workers (telemetry/anomaly/ECAM/hash/dispatch) |
| **Report Generator** | `services/report_service.py` | ReportLab PDF: 6-page Airbus-style reports. SHA-256 document hashing |
| **Redundancy Voter** | `services/sensor_engine.py` | 2oo3 voting with ATA-specific tolerance bands, Byzantine fault detection, cross-channel drift |

### 4.3 API Layer (17 route modules + WebSocket)

| Route Module | Prefix | Key Endpoints |
|-------------|--------|---------------|
| `auth.py` | `/api/v1/auth` | login, refresh, logout, me |
| `aircraft.py` | `/api/v1/aircraft` | current twin state, aircraft types, profiles |
| `sensors.py` | `/api/v1/sensors` | summary, by ATA chapter, anomalous list |
| `telemetry.py` | `/api/v1/telemetry` | stream metadata |
| `anomalies.py` | `/api/v1/anomalies` | AI status, events, threshold control |
| `dispatch.py` | `/api/v1/dispatch` | GO/NO-GO status (12-point checklist), authorize |
| `hash_chain.py` | `/api/v1/hashchain` | latest blocks, chain verify |
| `ecam.py` | `/api/v1/ecam` | active advisories, history |
| `reports.py` | `/api/v1/reports` | airworthiness report generation (PDF) |
| `simulator.py` | `/api/v1/simulator` | flight phase control, sim status |
| `maintenance.py` | `/api/v1/maintenance` | **Full CRUD:** GET/POST/PATCH/DELETE actions, summary, schedule |
| `cybersecurity.py` | `/api/v1/cybersecurity` | threat dashboard (real engine), threat events |
| `fleet.py` | `/api/v1/fleet` | fleet overview, aircraft by MSN |
| `arinc.py` | `/api/v1/arinc` | bus frame, stats, labels, fault inject/clear |
| `afdx.py` | `/api/v1/afdx` | VL status, network stats, timing fault inject/clear |
| `websocket.py` | `/ws` | real-time telemetry (10 channels) |
| `main.py` (inline) | various | `/health`, `/health/detailed`, `/metrics`, `/api/v1/aircraft/profiles` |

### 4.4 Kafka Event Streaming (4 topics)

| Topic | Event Type | Trigger |
|-------|-----------|---------|
| `sentineltwin.anomalies` | Sensor anomaly | ai_anomaly_score > 0.6 |
| `sentineltwin.ecam` | ECAM advisory | New advisory generated |
| `sentineltwin.dispatch` | Dispatch status | Status change |
| `sentineltwin.hashchain` | Hash block | Block appended |

### 4.5 Middleware Stack (applied in order)
1. `CORSMiddleware` — origins whitelist
2. `GZipMiddleware` — compress responses > 1KB
3. `SecurityHeadersMiddleware` — CSP, X-Frame-Options, HSTS, etc.
4. `RateLimitMiddleware` — 1000 req/min general, 10/5min auth
5. `AuditLoggingMiddleware` — log all API requests

### 4.6 Frontend Structure
| File | Size | What It Does |
|------|------|-------------|
| `SentinelTwin.jsx` | ~93 KB | Main app: login screen, boot sequence, operations center with 18 sidebar panels, virtualized SensorMatrix, header bar, WebSocket connection |
| `SentinelTwinPanels.jsx` | ~53 KB | Extended panel components: Fleet Status, AFDX Monitor, Maintenance (with inline creation form), Phase Timeline, Neural Network, Environmental, Replay Console |
| `stores/sentinel.store.ts` | ~27 KB | Zustand state store: WebSocket management (10 channels), ARINC/AFDX/Cyber types, API calls, authentication |
| `main.jsx` | 237 B | React DOM entry point |

---

## 5. FILE TREE

```
sentineltwin/
├── README.md                              # Production README
├── AI_CONTEXT.md                          # THIS FILE — AI assistant context
├── docker-compose.yml                     # 9 services
├── Makefile                               # 40+ targets
├── start.bat / end.bat                    # Windows launcher
├── start_sentineltwin.sh                  # Unix launcher (TLS + frontend)
│
├── backend/
│   ├── main.py                            # FastAPI app + lifespan + Kafka + /health/detailed
│   ├── _smoke_test.py                     # 10 smoke tests (8 offline + 5 network)
│   ├── core/
│   │   ├── config.py                      # Pydantic Settings
│   │   ├── database.py                    # SQLAlchemy async engine
│   │   ├── redis_client.py                # Redis with non-fatal connect
│   │   └── logger.py                      # Structured JSON logging
│   ├── services/
│   │   ├── sensor_engine.py               # 8,192-sensor engine + 2oo3 voter + Kafka wiring
│   │   ├── ai_engine.py                   # Sparse autoencoder + CUSUM
│   │   ├── digital_twin.py                # A320neo physics model
│   │   ├── ecam_engine.py                 # ECAM advisory engine + Kafka wiring
│   │   ├── hash_service.py                # SHA-256 audit chain
│   │   ├── kafka_producer.py              # Async Kafka event producer (4 topics)
│   │   ├── arinc429_service.py            # ARINC 429 bus simulator
│   │   ├── afdx_service.py                # AFDX virtual link monitor
│   │   ├── security_engine.py             # Cybersecurity threat engine
│   │   ├── persistence_service.py         # Async DB write-batching
│   │   ├── report_service.py              # PDF airworthiness report gen
│   │   └── simulator.py                   # X-Plane / MSFS connector
│   ├── api/routes/
│   │   ├── _auth_utils.py                 # JWT/RBAC: get_current_user, require_role
│   │   ├── maintenance.py                 # Full CRUD: POST/GET/PATCH/DELETE + summary
│   │   └── websocket.py                   # WS broadcast loop + manager
│   ├── middleware/
│   │   ├── security.py                    # CSP headers + rate limiting
│   │   └── audit.py                       # Request audit logging
│   └── models/
│       └── db_models.py                   # SQLAlchemy ORM (13 tables)
│
├── frontend/
│   ├── index.html                         # HTML entry point (IBM Plex Mono)
│   ├── package.json                       # React 18 + Vite + Zustand + Three.js
│   ├── vite.config.ts                     # API/WS proxy to localhost:8000
│   └── src/
│       ├── main.jsx                       # React DOM mount
│       ├── SentinelTwin.jsx               # Operations center (18 panels, virtualized matrix)
│       ├── SentinelTwinPanels.jsx          # Extended panels + maintenance form
│       └── stores/sentinel.store.ts       # Zustand state + WebSocket
│
└── docs/
    ├── HOW_IT_WORKS.md                    # Full technical deep-dive
    └── CHANGELOG.md                       # Version history
```

---

## 6. HOW TO RUN

```bash
# Backend
cd backend && py -3 main.py          # Windows
cd backend && python3 main.py        # Linux/macOS

# Frontend (separate terminal)
cd frontend && npm install && npm run dev

# One-click (Linux/macOS)
./start_sentineltwin.sh
```

- Backend: `http://localhost:8000` (API docs: `/api/docs`)
- Frontend: `http://localhost:5173` (proxies to backend)

### Default Credentials
```
admin / sentinel2026       → Administrator
pilot / pilot2026          → Pilot
engineer / engineer2026    → Maintenance Engineer
dispatcher / dispatch2026  → Dispatcher
```

---

## 7. COMPONENT STATUS — ALL COMPLETE ✅

### Backend — FULLY OPERATIONAL
- [x] FastAPI application with async lifespan management
- [x] Sensor Execution Engine — 8,192 sensors, 14-stage pipeline, 20 Hz
- [x] AI Anomaly Engine — sparse autoencoder + CUSUM
- [x] Digital Twin Engine — full A320neo physics model
- [x] ECAM Advisory Engine — 21 Airbus rules, 4 severity levels, Kafka publishing
- [x] SHA-256 Hash Chain — immutable audit log
- [x] Kafka Event Producer — 4 topics (anomalies, ecam, dispatch, hashchain)
- [x] ARINC 429 Bus Simulator — 32-bit word encode/decode
- [x] AFDX Virtual Link Monitor — 5 VLs, timing analysis
- [x] Cybersecurity Engine — rate limiting, replay, spoof detection
- [x] Persistence Service — async DB write-batching
- [x] Report Generator — 6-page PDF with SHA-256 hashing
- [x] Maintenance CRUD — POST/GET/PATCH/DELETE with RBAC
- [x] `/health/detailed` — 10-subsystem diagnostic endpoint
- [x] Prometheus `/metrics` — counters, histograms, gauges
- [x] 10 smoke tests — full stack verification

### Frontend — FULLY OPERATIONAL
- [x] 18 sidebar navigation panels with live data
- [x] Virtualized SensorMatrix (8,192 sensors, no DOM freeze)
- [x] FleetPanel wired to live API with fallback
- [x] MaintenancePanel with inline action creation form
- [x] NeuralNetworkPanel wired to Zustand store
- [x] WebSocket — 10 channels streaming
- [x] Zustand state management

---

## 8. CODING CONVENTIONS & PATTERNS

### Backend Patterns
- **Pydantic Settings** for all configuration (env-driven, with `.env` file)
- **async/await** throughout — all engines are async loops with `asyncio.sleep`
- **Service pattern**: each engine has `__init__()`, `run()`, `stop()`, `get_stats()`
- **Application state**: services stored on `app.state.*` and accessed via `request.app.state.*`
- **Auth dependency**: `get_current_user` for any authenticated user, `require_role(...)` for RBAC
- **Kafka injection**: `engine.kafka = kafka_producer` in main.py lifespan
- **Persistence injection**: `engine.persistence = persistence_service` in main.py lifespan
- **Thread pool** for CPU-bound sensor validation (`ThreadPoolExecutor`, 16 workers)

### Frontend Patterns
- **Single-file components** (monolithic JSX)
- **Zustand store** for all state management
- **WebSocket** reconnect loop with 3-second retry
- **IBM Plex Mono** font throughout (aerospace aesthetic)
- **CSS-in-JS** via inline styles
- **INPUT_STYLE** constant for form elements
- **Bearer token** from `localStorage.getItem("st_token")` on all API calls

### Important Config Values
- Backend: port **8000**
- Frontend dev: port **5173** (proxies `/api` and `/ws` to backend)
- WebSocket: `ws://localhost:8000/ws/telemetry`
- Health: `GET /health` (no auth), `GET /health/detailed` (no auth)
- API docs: `GET /api/docs` (only when DEBUG=true)

---

## 9. WHEN ASKING AN AI FOR HELP

### Always mention:
1. This is a **FastAPI + React** project (Python backend, JSX frontend)
2. Python version is **3.14** (use `py -3` on Windows)
3. The system runs in **standalone mode** without DB/Redis/Kafka (graceful fallbacks)
4. All 5 engines are **async background tasks** started in the FastAPI lifespan
5. The frontend is **monolithic JSX** (not component-per-file)
6. WebSocket uses **10 channels**: telemetry, ecam, ai, hashchain, twin, dispatch, arinc, afdx, cyber, fleet
7. Kafka has **4 topics** wired into sensor_engine and ecam_engine
8. Auth uses `get_current_user` and `require_role(...)` from `_auth_utils.py`
9. Maintenance has **full CRUD** (POST/GET/PATCH/DELETE) at `/api/v1/maintenance/actions`

### Common tasks:
- "Add a new API endpoint" → Create file in `backend/api/routes/`, add router to `main.py`
- "Add a new ECAM rule" → Add tuple to `ECAM_LOGIC_TABLE` in `ecam_engine.py`
- "Add a new sensor type" → Modify `ATA_CHAPTERS` dict in `sensor_engine.py`
- "Add a new dashboard panel" → Add to `SentinelTwinPanels.jsx`, register in `SentinelTwin.jsx` sidebar
- "Add a Kafka topic" → Add topic constant + publish method in `kafka_producer.py`
- "Change config" → Add to `Settings` class in `core/config.py`, set in `backend/.env`

---

*End of AI Context — SentinelTwin v4.4.0*
*Team Lift & Logic — Airbus Fly Your Ideas 2026*
