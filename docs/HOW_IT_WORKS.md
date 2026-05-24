# How SentinelTwin Works

## Complete Technical Architecture & Data Flow Guide

> **Version:** 4.4.0  
> **Last Updated:** 2026-05-19  
> **Audience:** Developers, reviewers, assessors, future contributors

---

## Table of Contents

1. [System Overview](#1-system-overview)
2. [Boot Sequence](#2-boot-sequence)
3. [Backend Architecture](#3-backend-architecture)
4. [Sensor Execution Engine](#4-sensor-execution-engine)
5. [AI Anomaly Detection Engine](#5-ai-anomaly-detection-engine)
6. [Digital Twin Engine](#6-digital-twin-engine)
7. [ECAM Advisory Engine](#7-ecam-advisory-engine)
8. [Hash Chain Audit Service](#8-hash-chain-audit-service)
9. [WebSocket Real-Time Streaming](#9-websocket-real-time-streaming)
10. [API Route Architecture](#10-api-route-architecture)
11. [Security & Middleware Stack](#11-security--middleware-stack)
12. [Frontend Architecture](#12-frontend-architecture)
13. [Data Flow Diagram](#13-data-flow-diagram)
14. [Configuration System](#14-configuration-system)
15. [Graceful Degradation](#15-graceful-degradation)

---

## 1. System Overview

SentinelTwin is a **real-time sensor integrity verification platform** for
Airbus aircraft. It continuously validates 6,400–12,000 sensors (7 aircraft profiles)
through a 14-stage pipeline, applies AI anomaly detection with 2oo3 redundancy voting,
monitors ARINC 429 bus data and AFDX virtual links, enforces cybersecurity via
rate limiting and spoof detection, generates Airbus-style ECAM advisories,
and maintains a cryptographic audit chain — all at 20 Hz.

### Key Principle: Physics-First Architecture

Every sensor reading is validated against a physics model **before** AI
analysis. This means the system doesn't just check "is the sensor value
reasonable?" — it checks "does this reading match what physics predicts
for the current flight conditions?"

```
Traditional approach:    Sensor → Range Check → Alert
SentinelTwin approach:   Sensor → Physics Model → Residual → AI → Hash Chain → Alert
```

---

## 2. Boot Sequence

When `py -3 main.py` is executed, the following happens:

```
1. main.py loads
2. core/config.py reads .env via Pydantic Settings
3. create_app() builds FastAPI instance
4. Middleware stack is assembled (CORS → GZip → Security → RateLimit → Audit)
5. 14 API routers are mounted under /api/v1/*
6. WebSocket router is mounted under /ws/*
7. Uvicorn starts the ASGI server

─── LIFESPAN START ───
8.  Database: attempt connection → fallback if unavailable
9.  Redis: attempt connection → fallback if unavailable
10. SensorExecutionEngine() initializes → builds sensor registry for aircraft profile
11. AIAnomalyEngine() initializes → builds 256→32→256 autoencoder
12. HashChainService() initializes → creates genesis block
13. DigitalTwinEngine() initializes → loads A320neo physics model
14. ECAMEngine() initializes → loads 21 advisory rules
15. ARINC429Simulator() initializes → 11 labels, 32-bit word encoder
16. AFDXMonitor() initializes → 5 virtual links, BAG enforcement
17. CybersecurityEngine() initializes → rate limiter, replay/spoof detection
18. PersistenceService() initializes → 5 async write-batch queues
19. KafkaEventProducer() initializes → connect to broker (graceful fallback)

Wire services:
20. sensor_engine.persistence = persistence_service
21. sensor_engine.kafka = kafka_producer
22. ecam_engine.persistence = persistence_service
23. ecam_engine.kafka = kafka_producer

Background tasks start:
24. sensor_engine.run()    → 20 Hz loop (validates all sensors)
25. ai_engine.run()        → 5 Hz loop (AI inference on batches)
26. twin_engine.run()      → 10 Hz loop (physics state update)
27. ecam_engine.run()      → 0.5 Hz loop (advisory evaluation)
28. broadcast_loop(app)    → 1 Hz loop (10-channel WebSocket broadcast)

"All subsystems ONLINE — SentinelTwin OPERATIONAL"
```

---

## 3. Backend Architecture

### Package Structure

```
backend/
├── main.py               ← Entry point + lifespan management
├── core/                 ← Infrastructure layer
│   ├── config.py         ← Pydantic settings (reads .env)
│   ├── database.py       ← SQLAlchemy async engine
│   ├── redis_client.py   ← Redis with non-fatal connection
│   └── logger.py         ← Structured JSON logging
├── services/             ← Business logic layer
│   ├── sensor_engine.py  ← Multi-aircraft sensor engine + 2oo3 voter
│   ├── ai_engine.py      ← Sparse autoencoder + CUSUM detection
│   ├── digital_twin.py   ← A320neo physics model (ISA, engines, hyd)
│   ├── ecam_engine.py    ← ECAM advisory generation (21 rules)
│   ├── hash_service.py   ← SHA-256 immutable audit chain
│   ├── arinc429_service.py ← ARINC 429 bus simulator (32-bit word)
│   ├── afdx_service.py   ← AFDX virtual link monitor
│   ├── security_engine.py ← Cybersecurity threat engine
│   ├── persistence_service.py ← Async DB write-batching
│   ├── report_service.py ← PDF airworthiness reports
│   ├── kafka_producer.py ← Async Kafka event streaming (4 topics)
│   └── simulator.py      ← X-Plane / MSFS connector
├── api/routes/           ← API layer (17 route modules)
│   ├── _auth_utils.py    ← Shared JWT/RBAC: get_current_user, require_role
│   ├── auth.py           ← Login, logout, refresh, profile
│   ├── sensors.py        ← Sensor data endpoints
│   ├── anomalies.py      ← AI anomaly events
│   ├── dispatch.py       ← GO/NO-GO determination
│   ├── hash_chain.py     ← Audit chain queries
│   ├── ecam.py           ← Active advisories
│   ├── aircraft.py       ← Digital twin state + profiles
│   ├── telemetry.py      ← Telemetry metadata
│   ├── reports.py        ← Airworthiness reports
│   ├── simulator.py      ← Flight phase control
│   ├── maintenance.py    ← Maintenance CRUD (POST/GET/PATCH/DELETE)
│   ├── cybersecurity.py  ← Cyber threat status (real engine)
│   ├── fleet.py          ← Fleet overview
│   ├── arinc.py          ← ARINC 429 bus frames + faults
│   ├── afdx.py           ← AFDX virtual links + faults
│   └── websocket.py      ← WS endpoint + 10-channel broadcast
└── middleware/           ← Cross-cutting concerns
    ├── security.py       ← CSP headers, rate limiting
    └── audit.py          ← Immutable request logging
```

### Design Decision: Module Decomposition

The original architecture had monolithic files:
- `security.py` (500+ lines) contained DB, Redis, Logger, Security headers, Rate limiting
- `core_services.py` (650+ lines) contained Hash chain, ECAM, Digital twin
- `routes.py` (1000+ lines) contained all 14 route groups

These were decomposed into proper Python packages for:
- Independent testing
- Clear dependency graphs
- Reduced merge conflicts
- Faster import times

---

## 4. Sensor Execution Engine

**File:** `services/sensor_engine.py` (~650 lines)

### Sensor Registry

8,192 sensors are distributed across 14 ATA chapters:

| ATA | System | Count | Units |
|-----|--------|------:|-------|
| 21 | Air Conditioning | 256 | °C, kPa, L/s |
| 22 | Auto Flight | 384 | G, Hz, V, A |
| 24 | Electrical | 512 | V, A, Hz |
| 27 | Flight Controls | 1,024 | G, °C, PSI, N |
| 28 | Fuel | 768 | kg, L/s, °C, PSI |
| 29 | Hydraulics | 640 | PSI, L/s, °C, kg |
| 30 | Ice & Rain | 192 | °C, A, V |
| 31 | Indicating | 384 | V, A, Hz |
| 32 | Landing Gear | 640 | PSI, °C, G, N |
| 34 | Navigation | 1,024 | Hz, G, °C, V |
| 36 | Pneumatic | 256 | kPa, °C, L/s |
| 49 | APU | 192 | RPM, °C, PSI, V |
| 52 | Doors | 128 | A, V, G |
| 71 | Powerplant | 1,792 | °C, RPM, PSI, N, A |

Each sensor is a `dataclass` with:
- Identity: `sensor_id`, `ata_chapter`, `subsystem`, `aircraft_zone`
- Physics: `physics_nominal`, `physics_sigma`, limits, ARINC label
- Redundancy: `redundancy_group`, `redundancy_channel` (for 2oo3 voting)
- State: `state`, `confidence_score`, `last_calibrated_value`

### 14-Stage Validation Pipeline

```python
class ValidationPipeline:
    def validate(self, sensor, raw_value, altitude, speed, phase, t):
        # Stage 1-3: Acquisition → Calibration → Filtering
        calibrated = self._calibrate(sensor, raw_value)
        filtered = self._filter(sensor, calibrated)
        
        # Stage 4-7: Security validations
        self._check_timestamp(sensor, t)      # jitter detection
        self._check_crc(sensor, filtered)     # packet integrity
        self._check_stale(sensor, t)          # >5 sec threshold
        self._check_replay(sensor, filtered)  # 30-sec hash window
        
        # Stage 8-9: Physics + AI
        physics_ok = self._physics_validate(sensor, filtered, altitude, speed, phase, t)
        ai_score = self._ai_drift_check(sensor, filtered)
        
        # Stage 10-14: Redundancy → Classification → Dispatch
        voted = self._redundancy_vote(sensor)
        confidence = self._compute_confidence(sensor, flags)
        state = self._classify_state(sensor, flags)
        dispatch = self._check_dispatch_impact(sensor, state)
        maintenance = self._generate_advisory(sensor, state)
```

### Execution Model

```
                    ┌─────────────────────┐
                    │  Main asyncio loop   │
                    └──────────┬──────────┘
                               │ every 50ms (20 Hz)
                    ┌──────────▼──────────┐
                    │  Split 8192 sensors  │
                    │  into 16 batches     │
                    │  of 512 each         │
                    └──────────┬──────────┘
                               │
            ┌──────────────────┼──────────────────┐
            │                  │                   │
     ┌──────▼──────┐   ┌──────▼──────┐   ┌───────▼──────┐
     │ Thread 1    │   │ Thread 2    │   │ Thread 16    │
     │ 512 sensors │   │ 512 sensors │   │ 512 sensors  │
     │ (CPU-bound  │   │             │   │              │
     │  validation)│   │             │   │              │
     └──────┬──────┘   └──────┬──────┘   └──────┬───────┘
            │                  │                  │
            └──────────────────┼──────────────────┘
                               │ asyncio.gather()
                    ┌──────────▼──────────┐
                    │  Aggregate results   │
                    │  Update sensor states│
                    │  Emit to broadcast   │
                    └─────────────────────┘
```

### Redundancy Voting (2oo3)

Sensors are grouped in triples (`redundancy_group`). The `RedundancyVoter`
performs confidence-weighted 2-out-of-3 voting:

```python
# If spread > 5% of nominal value → Byzantine fault detected
# Otherwise → confidence-weighted average of healthy sensors
voted_value = np.average(healthy_values, weights=confidence_scores)
```

---

## 5. AI Anomaly Detection Engine

**File:** `services/ai_engine.py` (~550 lines)

### Sparse Autoencoder Architecture

```
Input Layer (256 neurons)  ← physics-normalised residuals, grouped by ATA
    ↓ Dense + Sigmoid + KL sparsity penalty
Hidden Layer 1 (128 neurons)
    ↓
Hidden Layer 2 (64 neurons)
    ↓
Latent Layer (32 neurons)  ← compressed representation
    ↓
Hidden Layer 3 (64 neurons)
    ↓
Hidden Layer 4 (128 neurons)
    ↓
Output Layer (256 neurons) ← reconstruction
```

### How It Detects Anomalies

1. **Feature aggregation:** Sensor values are grouped by ATA chapter into a 256-dim vector
2. **Physics normalisation:** Each value is divided by the physics model prediction
3. **Forward pass:** The normalised vector is fed through the autoencoder
4. **Reconstruction error:** MSE between input and output is computed
5. **Threshold check:** If error > 0.15, an anomaly event is raised
6. **Severity mapping:** Error magnitude maps to NOMINAL/LOW/MEDIUM/HIGH/CRITICAL

### Statistical Layer (CUSUM)

Runs in parallel with the autoencoder to catch:
- **EGT spikes:** Sudden temperature jumps that the autoencoder might reconstruct well
- **Frozen values:** Zero variance over a window (stale telemetry)
- **Replay attacks:** Duplicate sensor hash patterns within a 30-second window

### Training

The autoencoder trains online using mini-batch SGD with:
- Learning rate: 0.001 with decay
- L2 regularization: λ = 0.0001
- KL sparsity: target ρ = 0.05, β = 3.0
- Batch size: 256 features
- Warm-up: 100 forward passes before inference starts

---

## 6. Digital Twin Engine

**File:** `services/digital_twin.py` (~200 lines)

### A320neo Physics Model

The twin simulates an Airbus A320neo at 10 Hz. It provides:

#### ISA Atmosphere (International Standard Atmosphere)
```python
T(h) = T₀ - L × h           # Temperature at altitude h
P(h) = P₀ × (T/T₀)^(gM/RL) # Pressure
ρ(h) = P / (R_spec × T)     # Density
a(h) = sqrt(γ × R_spec × T) # Speed of sound
```

#### Engine Model (CFM LEAP-1A)
- N1/N2 spool speeds based on thrust setting
- EGT as function of N2 and altitude
- Oil temperature/pressure correlated with engine load
- Fuel flow proportional to thrust setting

#### Hydraulic System
- Green/Blue/Yellow system pressures
- Pressure varies with pump speed (N2-driven for Green/Yellow, electric for Blue)
- Accumulator pressure dynamics

#### Electrical System
- Generator voltage/frequency based on N2
- Bus voltage under load
- Battery charge state

#### Flight Dynamics
Simplified model for sensor context:
- Lift/drag in cruise → altitude/speed estimation
- Flight phase detection (GROUND → TAKEOFF → CLIMB → CRUISE → DESCENT → APPROACH → LANDING)

### Why a Physics Model?

The physics model serves two purposes:
1. **Sensor validation (Stage 8):** "Does this hydraulic pressure reading make sense for the current engine speed?"
2. **AI normalisation:** Feeding raw values to the AI would confuse it — a hydraulic pressure of 2800 PSI is normal in cruise but abnormal on ground. The physics model prediction removes this ambiguity.

---

## 7. ECAM Advisory Engine

**File:** `services/ecam_engine.py` (~160 lines)

### 21 Advisory Rules

| Rule ID | Severity | System | Message |
|---------|----------|--------|---------|
| hyd_green_press_lo | WARNING | HYD | HYD SYS GREEN PRESS LO |
| hyd_blue_press_lo | CAUTION | HYD | HYD SYS BLUE PRESS LO |
| hyd_yellow_press_lo | CAUTION | HYD | HYD SYS YELLOW PRESS LO |
| eng1_oil_temp_hi | CAUTION | ENG | ENG 1 OIL TEMP HIGH |
| eng2_oil_temp_hi | CAUTION | ENG | ENG 2 OIL TEMP HIGH |
| eng1_oil_press_lo | WARNING | ENG | ENG 1 OIL PRESS LOW |
| eng2_oil_press_lo | WARNING | ENG | ENG 2 OIL PRESS LOW |
| nav_adr_disagree | WARNING | NAV | NAV ADR 1/2/3 DISAGREE |
| fuel_imbalance | CAUTION | FUEL | FUEL IMBALANCE L-R > 500KG |
| slat_fault | WARNING | FLT | SLAT FAULT - ASYMMETRY |
| elac_fault | CAUTION | FLT | ELAC 1+2 FAULT |
| gen1_fault | CAUTION | ELEC | GEN 1 FAULT |
| gen2_fault | CAUTION | ELEC | GEN 2 FAULT |
| apu_bleed_fault | STATUS | APU | APU BLEED FAULT |
| lgciu_fault | CAUTION | LGCIU | L/G CTRL UNIT 1+2 FAULT |
| pack1_fault | EMERGENCY | PACK | PACK 1 BLEED OFF AUTO |
| afdx_timing | CAUTION | AFDX | AFDX VIRTUAL LINK TIMING FAULT |
| fadec_disagree | WARNING | ENG | FADEC 1+2 CHANNEL DISAGREE |
| irs1_fault | CAUTION | IRS | IRS 1 FAULT |
| brake_temp_hi | CAUTION | BRAKES | BRAKE TEMP HIGH - MULTIPLE |
| adr_spoof_detected | EMERGENCY | SEC | ADR DATA INTEGRITY FAULT - SPOOF |

Each rule includes:
- **procedure:** Crew action text (e.g., "REDUCE THRUST ENG 1 - MONITOR")
- **dispatch_impact:** Whether it blocks dispatch
- **mel_reference:** MEL reference for deferred maintenance

### Evaluation Loop

Runs at 0.5 Hz. In simulation mode, rules trigger stochastically (0.3% per cycle per rule, 5% auto-clear rate). In production mode, rules evaluate against actual sensor states and digital twin outputs.

---

## 8. Hash Chain Audit Service

**File:** `services/hash_service.py` (~100 lines)

### Block Structure

```python
@dataclass
class HashBlock:
    sequence: int           # Block number
    scan_id: str           # UUID for this scan cycle
    timestamp: str         # ISO 8601 UTC
    previous_hash: str     # SHA-256 of previous block
    block_hash: str        # SHA-256 of this block
    healthy_count: int     # Sensors in HEALTHY state
    anomaly_count: int     # Sensors in non-HEALTHY state
    flight_phase: str      # Current flight phase
```

### Append Operation

```python
async def append(self, healthy, anomaly, phase):
    block = HashBlock(
        sequence=self._sequence,
        scan_id=str(uuid.uuid4()),
        timestamp=datetime.now(utc).isoformat(),
        previous_hash=self._chain[-1].block_hash,
        block_hash="",  # computed next
        healthy_count=healthy,
        anomaly_count=anomaly,
        flight_phase=phase,
    )
    # Compute hash over all fields
    payload = f"{block.sequence}|{block.scan_id}|{block.timestamp}|" \
              f"{block.previous_hash}|{block.healthy_count}|" \
              f"{block.anomaly_count}|{block.flight_phase}"
    block.block_hash = hashlib.sha256(payload.encode()).hexdigest()
    self._chain.append(block)
```

### Verification

Chain integrity is verified by re-computing hashes:
```python
for i in range(1, len(chain)):
    if chain[i].previous_hash != chain[i-1].block_hash:
        return False  # TAMPERED
```

Blocks are appended every 5 seconds (every 5th WebSocket broadcast cycle).
Retained for 7 years per EASA Part M.

---

## 9. WebSocket Real-Time Streaming

**File:** `api/routes/websocket.py` (~160 lines)

### Connection Manager

Manages client connections with channel-based subscriptions:

```python
class ConnectionManager:
    _connections: Dict[str, WebSocket]      # conn_id → websocket
    _subscriptions: Dict[str, Set[str]]     # conn_id → channels
    _channels: Dict[str, Set[str]]          # channel → conn_ids
```

### 10 Broadcast Channels

| Channel | Frequency | Data |
|---------|-----------|------|
| `telemetry` | 1 Hz | Sensor stats: healthy/anomaly counts, scan rate |
| `ai` | 1 Hz | Reconstruction error, severity, confidence, events |
| `twin` | 1 Hz | Full aircraft state (engines, hyd, elec, flight) |
| `ecam` | 1 Hz | Active advisories with severity sorting |
| `hashchain` | 0.2 Hz | New audit blocks with chain validity |
| `dispatch` | 0.33 Hz | GO/NO-GO status with reason |
| `arinc` | 1 Hz | ARINC 429 bus frame with all decoded labels |
| `afdx` | 1 Hz | AFDX virtual link status + network stats |
| `cyber` | 0.33 Hz | Cybersecurity threat level + events |
| `fleet` | 0.5 Hz | Fleet-wide aircraft status |

### Keepalive

If no message received from client for 30 seconds, server sends keepalive.
Dead connections are automatically cleaned up.

---

## 10. API Route Architecture

### Route Module Pattern

Each route module follows the same pattern:

```python
# api/routes/sensors.py
from fastapi import APIRouter, Request
from api.routes._auth_utils import require_auth, require_role

router = APIRouter()

@router.get("/summary")
async def get_sensor_summary(request: Request, user=Depends(require_auth)):
    engine = request.app.state.sensor_engine
    stats = engine.get_stats()
    return {"total_sensors": 8192, "healthy_count": stats["healthy_count"], ...}
```

### Auth Utilities (`_auth_utils.py`)

Shared across all route modules:

- `create_access_token(data, expires_delta)` — JWT creation (HS256)
- `create_refresh_token(username)` — Refresh token with JTI
- `get_current_user` — FastAPI dependency that validates Bearer token and returns user dict
- `require_role(*roles)` — Returns a FastAPI dependency that checks user role
- `_USERS` — In-memory user store (4 pre-configured users: admin, pilot, engineer, dispatcher)
- `check_brute_force(ip)` — Brute-force protection (10 attempts / 300s lockout)

---

## 11. Security & Middleware Stack

### Middleware Execution Order

```
Request → AuditLogging → RateLimit → SecurityHeaders → GZip → CORS → Router
Response ← AuditLogging ← RateLimit ← SecurityHeaders ← GZip ← CORS ← Router
```

### Security Headers (injected on every response)

| Header | Value |
|--------|-------|
| X-Frame-Options | DENY |
| X-XSS-Protection | 1; mode=block |
| X-Content-Type-Options | nosniff |
| Strict-Transport-Security | max-age=31536000; includeSubDomains; preload |
| Content-Security-Policy | default-src 'self'; connect-src 'self' ws: wss: ... |
| Permissions-Policy | camera=(), microphone=(), geolocation=() |
| Cache-Control | no-store, no-cache, must-revalidate, private |
| X-SentinelTwin-Compliance | DO-326A:ACTIVE,ED-202A:ACTIVE |

### Rate Limiting

| Bucket | Limit | Window |
|--------|------:|--------|
| General | 1,000 | 60 sec |
| Auth endpoints | 10 | 300 sec |
| WebSocket | 50 | 60 sec |

---

## 12. Frontend Architecture

### Technology

- **React 18** with JSX
- **Vite** for build/dev
- **IBM Plex Mono** font (aerospace aesthetic)
- **Zustand** for state management
- **Three.js / React Three Fiber** for 3D digital twin
- **Recharts** for data visualisation

### Dashboard Panels (18 total)

1. **Overview** — KPI cards, ATA health bars, ECAM summary, sensor distribution
2. **Sensor Matrix** — Paginated grid of all sensors, filter by state/ATA
3. **Digital Twin** — 3D A320neo wireframe with live engine/hyd/elec readouts
4. **AI Anomaly** — Reconstruction error chart, inference metrics
5. **ECAM Console** — Active advisories with severity badges and procedures
6. **ARINC 429** — Live bus frame decoder with label table and fault injection
7. **AFDX Monitor** — Virtual link jitter analysis, switch status, timing faults
8. **Dispatch** — GO/NO-GO checklist with 12 criteria
9. **Redundancy** — 2oo3 voting group status
10. **Audit Chain** — SHA-256 block viewer with chain integrity
11. **Cybersecurity** — Threat level, rate limiting, spoof detection
12. **Fleet Status** — 8-aircraft fleet overview with health scores
13. **Maintenance** — Action tracker with priority/MEL/status
14. **Phase Timeline** — Flight phase progression visualization
15. **Neural Net** — Autoencoder architecture visualization
16. **Environment** — ISA atmosphere and environmental conditions
17. **Event Log** — Timestamped event history
18. **Report** — Airworthiness assurance report generator (PDF)

### WebSocket Integration

```javascript
// Frontend connects to ws://localhost:5173/ws/telemetry
// Vite proxy forwards to ws://localhost:8000/ws/telemetry
const ws = new WebSocket(`ws://${location.host}/ws/telemetry`);
ws.onmessage = (event) => {
    const { channel, data } = JSON.parse(event.data);
    // Route to appropriate store update
    switch(channel) {
        case 'telemetry': updateSensors(data); break;
        case 'ecam': updateECAM(data); break;
        case 'ai': updateAI(data); break;
        // ...
    }
};
```

---

## 13. Data Flow Diagram

```
┌────────────────────┐
│   Sensor Bus       │  (simulated: stochastic + physics-derived values)
│   8,192 sensors    │
└────────┬───────────┘
         │ raw telemetry (20 Hz per sensor)
         ▼
┌────────────────────┐
│  Sensor Execution  │  ← 14-stage pipeline
│  Engine            │  ← 16 parallel worker threads
│  (20 Hz main loop) │  ← redundancy voting
└────────┬───────────┘
         │ validation results
         ├──────────────────────────────────────┐
         ▼                                      ▼
┌────────────────────┐              ┌────────────────────┐
│  AI Anomaly Engine │              │  Digital Twin       │
│  (5 Hz)            │◄─────────────│  (10 Hz)            │
│  autoencoder +     │  physics     │  ISA + engine +     │
│  statistical layer │  predictions │  hyd + elec + flight│
└────────┬───────────┘              └────────┬───────────┘
         │ anomaly events                    │ twin state
         ▼                                   ▼
┌────────────────────┐              ┌────────────────────┐
│  ECAM Engine       │              │  Hash Chain Service │
│  (0.5 Hz)          │              │  (0.2 Hz)           │
│  21 advisory rules │              │  SHA-256 blocks     │
│  severity sorting  │              │  immutable log      │
└────────┬───────────┘              └────────┬───────────┘
         │ advisories                        │ blocks
         └────────────┬─────────────────────┘
                      ▼
         ┌────────────────────┐
         │  WebSocket         │
         │  Broadcast Loop    │
         │  (1 Hz)            │
         │  10 channels       │
         └────────┬───────────┘
                  │
         ┌────────┴───────────┐
         │  Kafka Producer    │
         │  4 topics          │
         │  (anomalies, ecam  │
         │   dispatch, hash)  │
         └────────┬───────────┘
                  │ JSON messages
                  ▼
         ┌────────────────────┐
         │  Frontend          │
         │  (React)           │
         │  18 dashboard      │
         │  panels            │
         └────────────────────┘
```

---

## 14. Configuration System

### Environment Variables (`.env`)

The system is configured via Pydantic Settings which reads `.env`:

```bash
# Application
APP_NAME=SentinelTwin
DEBUG=true                          # Enables /api/docs Swagger UI
HOST=0.0.0.0
PORT=8000

# Security
SECRET_KEY=<change-in-production>   # JWT signing key
JWT_ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=30

# Infrastructure (optional — system works without these)
DATABASE_URL=postgresql+asyncpg://user:pass@localhost:5432/sentineltwin
REDIS_URL=redis://localhost:6379/0

# CORS (JSON array format for pydantic-settings v2)
CORS_ORIGINS=["http://localhost:5173","http://localhost:3000"]

# Sensor Engine
SENSOR_COUNT=8192
SENSOR_SAMPLE_RATE_HZ=20.0
SENSOR_BATCH_SIZE=512

# AI Engine
AI_ANOMALY_THRESHOLD=0.15
AI_LATENT_DIM=32
AI_ENCODER_LAYERS=[256,128,64,32]
```

### Important: CORS_ORIGINS format

Pydantic Settings v2 requires JSON array syntax for `List[str]` fields:
```bash
# CORRECT
CORS_ORIGINS=["http://localhost:5173","http://localhost:3000"]

# WRONG — will cause JSON parse error
CORS_ORIGINS=http://localhost:5173,http://localhost:3000
```

---

## 15. Graceful Degradation

SentinelTwin is designed to run without external infrastructure:

| Service | Available | Behaviour |
|---------|-----------|-----------|
| PostgreSQL | ✗ | Warning logged, tables not created, in-memory state only |
| Redis | ✗ | Warning logged, rate-limit uses in-memory, no session cache |
| Kafka | ✗ | Events not published to topics (all engines continue normally) |
| PostgreSQL | ✓ | Full persistence, audit log to DB, session management |
| Redis | ✓ | Distributed rate limiting, session cache, pub/sub |

This means **developers can run `py -3 main.py` with zero infrastructure setup**
and the entire platform works with simulated data.

---

*SentinelTwin v4.4.0 — System Architecture Reference*
*EASA DO-326A | ED-202A | EASA AMC 20-42*
