# SentinelTwin — System Architecture

**Version:** 4.2.1 | **Updated:** `2026-05-21T06:22:00Z` | **Compliance:** EASA DO-326A · ED-202A · ARINC 664

---

## Overview

SentinelTwin is a **real-time aerospace digital twin** built on a microservice-style FastAPI backend
with an asyncio event loop driving all real-time engines simultaneously.

---

## Layer Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    Browser / Operator Console                     │
│  React + Zustand state management · 21 operational panels        │
│  WebSocket live feeds · Vite dev server (prod: Nginx)            │
└─────────────────────────┬───────────────────────────────────────┘
                          │ HTTPS / WSS
┌─────────────────────────▼───────────────────────────────────────┐
│                     Nginx Reverse Proxy                          │
│  TLS termination · Rate limiting · Security headers              │
└─────────────────────────┬───────────────────────────────────────┘
                          │ HTTP
┌─────────────────────────▼───────────────────────────────────────┐
│                   FastAPI Backend :8000                          │
│                                                                   │
│  ┌──────────────────┐  ┌──────────────────┐  ┌──────────────┐  │
│  │ SensorExecution  │  │  AIAnomalyEngine  │  │ DigitalTwin  │  │
│  │ Engine           │  │  Sparse AE        │  │ Engine       │  │
│  │ 8,192 sensors    │  │  256-128-64-32    │  │ ISA physics  │  │
│  │ 20 Hz / 16 thrd  │  │  SHAP attribution │  │ 10 Hz update │  │
│  └────────┬─────────┘  └────────┬──────────┘  └──────┬───────┘  │
│           │                     │                     │           │
│  ┌────────▼─────────┐  ┌────────▼──────────┐  ┌──────▼───────┐  │
│  │ PersistenceService│  │  ECAMEngine       │  │ HashChain    │  │
│  │ Async batch queue │  │  21 ECAM rules    │  │ Service      │  │
│  │ 500ms flush cycle │  │  EMERGENCY→STATUS │  │ SHA-256      │  │
│  └────────┬─────────┘  └──────────────────┘  └──────────────┘  │
│           │                                                        │
│  ┌────────▼─────────┐  ┌──────────────────┐  ┌──────────────┐  │
│  │ KafkaProducer    │  │ ARINC429Simulator │  │ AFDXMonitor  │  │
│  │ aiokafka async   │  │ 32-bit words      │  │ VL timing    │  │
│  │ graceful fallback│  │ 100 kbps bus      │  │ BAG enforce  │  │
│  └──────────────────┘  └──────────────────┘  └──────────────┘  │
│                                                                   │
│  ┌──────────────────┐  ┌──────────────────┐                     │
│  │ CyberSecurity    │  │ SimulatorManager  │                     │
│  │ Engine DO-326A   │  │ X-Plane · CSV     │                     │
│  └──────────────────┘  └──────────────────┘                     │
└─────────────────────────┬───────────────────────────────────────┘
                          │
       ┌──────────────────┼─────────────────────┐
       ▼                  ▼                      ▼
  PostgreSQL/        Redis :6379          Kafka :9092
  TimescaleDB        Session cache        Event streaming
  :5432              Rate limiting        Telemetry topics
  Telemetry data     WS pub/sub           Anomaly topics
```

---

## Core Services

### SensorExecutionEngine
- **8,192 sensors** across 14 ATA chapters
- **20 Hz** validation cycle (50ms per cycle)
- **16 ThreadPoolExecutor workers** for CPU-bound sensor math
- **14-stage validation pipeline:**
  1. Raw signal acquisition
  2. ARINC 429 SSM decode
  3. Sanity range check (hard limits)
  4. Engineering unit conversion
  5. Calibration correction
  6. Physics residual computation
  7. ISA atmosphere compensation
  8. Statistical outlier detection (Z-score)
  9. AI anomaly score injection
  10. 2oo3 redundancy vote
  11. Confidence score assignment
  12. State determination (HEALTHY/DEGRADED/FAILED)
  13. Persistence queue hand-off (non-blocking put_nowait)
  14. Kafka event production (on anomaly)

### AIAnomalyEngine
- **Architecture:** Sparse autoencoder (256→128→64→32→64→128→256)
- **Input:** Feature vector of 14 normalised sensor dimensions
- **Threshold:** 0.15 (configurable via API)
- **SHAP attribution:** Identifies which ATA chapters drive anomalies
- **Output:** Reconstruction error, severity level, SHAP feature scores

### DigitalTwinEngine
- **Physics model:** ISA 1976 standard atmosphere
- **Update rate:** 10 Hz
- **Modelled systems:**
  - ISA atmosphere (temperature, pressure, density per altitude)
  - Engine thermodynamics (EGT, N1, N2, fuel flow)
  - Hydraulic pressure (green/blue/yellow circuits)
  - Fuel system (burn model, imbalance detection)
  - Structural loads (g-load, turbulence, fatigue index)
  - Thermal model (avionics bay, brake temperature)

### PersistenceService
- **Async queue:** `asyncio.Queue` with `put_nowait` (non-blocking)
- **Batch flush:** Every 500ms — bulk `executemany` SQL insert
- **5 concurrent workers:** Telemetry, anomalies, ECAM, hash blocks, dispatch
- **TimescaleDB:** Hypertable with 10-second time buckets

### HashChainService
- **Algorithm:** SHA-256 (DO-326A compliant)
- **Block format:** `SHA256(prev_hash + payload_digest + timestamp)`
- **Genesis:** 64× zero hash
- **Verification:** O(n) chain integrity check

---

## WebSocket Channels

| Channel | Frequency | Content |
|---------|-----------|---------|
| `telemetry` | 1 Hz | Sensor stats, ATA breakdown, scan rate |
| `ai` | 1 Hz | Reconstruction error, confidence, severity |
| `twin` | 1 Hz | Digital twin full state |
| `ecam` | 1 Hz + events | Active advisories, stats |
| `hashchain` | Every 5s | New block, chain stats |
| `dispatch` | 3s | GO/NO-GO readiness |
| `arinc` | 2 Hz | ARINC 429 bus frames |
| `afdx` | Every 3s | AFDX virtual link status |
| `cyber` | Every 5s | Threat dashboard |

---

## Data Flow: Telemetry Pipeline

```
ARINC 429 Bus → Sensor → Calibration → Physics Residual → AI Score
     ↓                                                       ↓
SSM decode                                           SHAP attribution
     ↓                                                       ↓
Engineering value ────────────────────────────────→ Anomaly event
     ↓                                                       ↓
2oo3 Voting ──→ Vote result ──→ Sensor state         Kafka topic
     ↓                              ↓                        ↓
Persistence queue ──────────→ TimescaleDB ──→ Grafana dashboard
     ↓
WebSocket broadcast ──→ React dashboard (1 Hz)
```

---

## ATA Chapter Distribution (A320neo)

| ATA | System | Sensors |
|-----|--------|---------|
| 21 | Air Conditioning / Pressurization | 512 |
| 22 | Auto Flight | 448 |
| 24 | Electrical Power | 576 |
| 27 | Flight Controls | 1,024 |
| 28 | Fuel | 640 |
| 29 | Hydraulics | 768 |
| 30 | Ice & Rain Protection | 256 |
| 31 | Instruments / EFIS | 512 |
| 32 | Landing Gear | 512 |
| 34 | Navigation | 1,120 |
| 36 | Pneumatics | 384 |
| 49 | APU | 192 |
| 52 | Doors | 320 |
| 71 | Powerplant | 928 |
| **TOTAL** | **A320neo** | **8,192** |

---

*Auto-generated by `generate_docs.py` — 2026-05-21T06:22:00Z*
