# SentinelTwin — Aerospace Airworthiness Assurance Platform

<div align="center">

[![Version](https://img.shields.io/badge/version-4.4.0-blue)]()
[![Compliance](https://img.shields.io/badge/DO--326A-compliant-green)]()
[![Sensors](https://img.shields.io/badge/sensors-8192-orange)]()
[![Python](https://img.shields.io/badge/python-3.11+-blue)]()
[![License](https://img.shields.io/badge/license-Proprietary-red)]()

**Real-time digital twin · AI anomaly detection · ECAM advisory generation**  
**SHA-256 audit chain · 2oo3 redundancy voting · ARINC 429/664 bus simulation**

</div>

---

## Quick Start — ONE COMMAND

```bash
# Windows (double-click OR run in terminal):
start_sentineltwin.bat

# Linux / macOS:
chmod +x start_sentineltwin.sh && ./start_sentineltwin.sh

# Python (cross-platform, recommended):
python launch.py
```

The system will automatically:
1. Validate your environment
2. Install missing dependencies
3. Start Docker infrastructure (PostgreSQL, Redis, Kafka)
4. Run database migrations
5. Start the backend API server
6. Start the frontend dashboard
7. Open the operational dashboard in your browser

---

## What is SentinelTwin?

SentinelTwin is a **real-time aerospace digital twin and airworthiness assurance platform** designed for the Airbus A320neo. It combines:

| Capability | Description |
|-----------|-------------|
| **8,192 Sensor Network** | Real-time validation at 20 Hz across 14 ATA chapters |
| **AI Anomaly Detection** | Sparse autoencoder (256→128→64→32→64→128→256) with SHAP attribution |
| **Digital Twin Physics** | ISA atmosphere, engine thermodynamics, hydraulics, structural loads |
| **ECAM Advisory Engine** | Airbus-style advisories: EMERGENCY / WARNING / CAUTION / STATUS |
| **2oo3 Redundancy Voting** | Byzantine-fault-tolerant sensor voting per DO-178C |
| **SHA-256 Hash Chain** | Immutable tamper-evident audit trail (DO-326A / ED-202A) |
| **ARINC 429 Bus Sim** | Full 32-bit word encoding, parity, SSM, SDI at 100 kbps |
| **AFDX Monitor** | ARINC 664 Part 7 virtual link timing and BAG enforcement |
| **Cybersecurity Engine** | DO-326A threat detection, anomalous packet analysis |
| **X-Plane Integration** | Real-time UDP telemetry from X-Plane 11/12 |

---

## Supported Aircraft

| Aircraft | Sensors | ATA Chapters |
|---------|---------|-------------|
| **Airbus A320neo** (default) | 8,192 | 21, 22, 24, 27, 28, 29, 30, 31, 32, 34, 36, 49, 52, 71 |
| Airbus A350-900 | 8,192 | Extended set |
| Boeing 737 MAX | 8,192 | Extended set |

---

## Architecture Overview

```
Browser Dashboard (React + Vite)
         │
         │  WebSocket (9 channels) + REST API
         ▼
  FastAPI Backend :8000
    ├─ SensorExecutionEngine  (8,192 sensors × 20 Hz)
    ├─ AIAnomalyEngine        (Sparse autoencoder inference)
    ├─ DigitalTwinEngine      (ISA physics model, 10 Hz)
    ├─ ECAMEngine             (Advisory generation, 2s cycle)
    ├─ HashChainService       (SHA-256 audit chain)
    ├─ PersistenceService     (Async batch write to TimescaleDB)
    ├─ KafkaEventProducer     (Real-time event streaming)
    ├─ ARINC429Simulator      (32-bit bus word generation)
    ├─ AFDXMonitor            (Virtual link timing)
    ├─ CybersecurityEngine    (DO-326A threat detection)
    └─ SimulatorManager       (X-Plane UDP / CSV replay)
         │
         ├─ PostgreSQL / TimescaleDB :5432
         ├─ Redis :6379
         └─ Kafka :9092
```

---

## One-Click Startup

### Requirements

| Requirement | Minimum | Recommended |
|-------------|---------|-------------|
| Python | 3.9+ | 3.11+ |
| Node.js | 18+ | 20 LTS |
| RAM | 4 GB | 8 GB |
| Docker | Optional | 24+ |
| GPU | Optional | NVIDIA (CUDA 12) |

### Environment Setup

```bash
# 1. Copy environment template
cp .env.example backend/.env

# 2. Edit SECRET_KEY (REQUIRED for production):
# Open backend/.env and replace REPLACE_WITH_CRYPTOGRAPHICALLY_SECURE_256BIT_KEY

# 3. Launch (one command):
python launch.py
```

### Deployment Modes

| Mode | Command | Description |
|------|---------|-------------|
| Auto-detect | `python launch.py` | Uses Docker if available, else local dev |
| Local dev | `python launch.py --mode local` | Backend + frontend only |
| Docker full-stack | `python launch.py --mode docker` | All services in containers |
| Health check | `python launch.py --check-only` | Check running system |
| Stop all | `python launch.py --stop` | Graceful shutdown |

---

## Service URLs

| Service | URL | Notes |
|---------|-----|-------|
| **Dashboard** | http://localhost:5173 | Main operational interface |
| **REST API** | http://localhost:8000 | FastAPI backend |
| **API Docs** | http://localhost:8000/api/docs | Swagger interactive docs |
| **WebSocket** | ws://localhost:8000/ws/telemetry | Real-time feeds |
| **Health** | http://localhost:8000/health | Quick status |
| **Grafana** | http://localhost:3001 | Metrics dashboards |
| **Prometheus** | http://localhost:9090 | Raw metrics |

---

## Default Credentials

| Role | Username | Password |
|------|----------|----------|
| Administrator | `admin` | `sentinel2026` |
| Pilot | `pilot` | `pilot2026` |
| Maintenance Engineer | `engineer` | `engineer2026` |
| Dispatcher | `dispatcher` | `dispatch2026` |

> ⚠️ **Change all passwords before production deployment.**

---

## Simulator Integration

```bash
# Connect X-Plane 11/12 (set X-Plane to send UDP to 127.0.0.1:49001):
curl -X POST http://localhost:8000/api/v1/simulator/xplane/connect?port=49001 \
  -H "Authorization: Bearer <token>"

# Load CSV telemetry recording:
curl -X POST "http://localhost:8000/api/v1/simulator/replay/load?csv_path=/data/recording.csv" \
  -H "Authorization: Bearer <token>"
```

---

## Compliance

| Standard | Status |
|----------|--------|
| EASA DO-326A (Airworthiness Security) | ✅ Implemented |
| ED-202A (Airworthiness Security Process) | ✅ Implemented |
| EASA AMC 20-42 | ✅ Implemented |
| ARINC 429-18 (Label Bus) | ✅ Implemented |
| ARINC 664 Part 7 (AFDX) | ✅ Implemented |
| DO-178C (Software considerations) | ✅ Patterns applied |

---

## Documentation

| Document | Description |
|----------|-------------|
| [DEPLOYMENT_GUIDE.md](docs/DEPLOYMENT_GUIDE.md) | Full deployment instructions |
| [SYSTEM_ARCHITECTURE.md](docs/SYSTEM_ARCHITECTURE.md) | Architecture deep-dive |
| [API_DOCUMENTATION.md](docs/API_DOCUMENTATION.md) | Complete API reference |
| [RUNBOOK.md](docs/RUNBOOK.md) | Operational runbook |
| [SENSOR_REGISTRY.md](docs/SENSOR_REGISTRY.md) | All 8,192 sensors documented |
| [AI_ENGINE.md](docs/AI_ENGINE.md) | AI anomaly engine documentation |
| [DIGITAL_TWIN.md](docs/DIGITAL_TWIN.md) | Digital twin physics documentation |
| [SECURITY_AUDIT.md](docs/SECURITY_AUDIT.md) | Security and compliance audit |
| [RUNTIME_STATUS.md](docs/RUNTIME_STATUS.md) | Live system status |
| [CHANGELOG.md](docs/CHANGELOG.md) | Version history |

---

*SentinelTwin v4.4.0 — Generated 2026-05-21 — EASA DO-326A Compliant*
