# SentinelTwin — Operational Runbook

**Version:** 4.2.1  |  **Compliance:** EASA DO-326A · ED-202A · EASA AMC 20-42

---

## 1. Quick Reference

| Action | Command |
|--------|---------|
| Start (Linux/macOS) | `./start_sentineltwin.sh` |
| Start (Windows) | `start_sentineltwin.bat` |
| Start (Docker only) | `make up` |
| Dev mode | `make dev` |
| First-time setup | `make init` |
| Run tests | `make test` |
| Seed database | `make seed` |
| Check health | `make health` |
| Prod readiness | `python3 scripts/production_check.py` |
| Generate report | `make generate-report` |
| Download PDF report | `make download-report` |
| View logs | `make logs` |
| Stop | `make down` or Ctrl+C |

---

## 2. First-Time Setup

```bash
# Clone and initialize
git clone <repo> && cd sentineltwin
cp .env.example backend/.env
# Edit backend/.env — change SECRET_KEY!

make init        # installs deps, starts infra, runs migrations, seeds DB
make dev         # starts backend + frontend dev servers
```

### Windows First-Time

```cmd
REM Double-click or run from terminal:
start_sentineltwin.bat
REM The script handles everything: Docker, Python deps, migrations, frontend
```

---

## 3. System Architecture

```
User Browser
│
▼ HTTPS:443
┌─────────────┐
│    Nginx    │  ← TLS termination, rate limiting, security headers
└──────┬──────┘
       │
┌──────┴──────────────────────────────────┐
│          FastAPI Backend :8000           │
│  ┌────────────┐  ┌──────────────────┐   │
│  │ Sensor     │  │ AI Anomaly       │   │
│  │ Engine     │  │ Engine           │   │
│  │ (8192 sns) │  │ (Autoencoder)    │   │
│  └────────────┘  └──────────────────┘   │
│  ┌────────────┐  ┌──────────────────┐   │
│  │ ECAM       │  │ Digital Twin     │   │
│  │ Engine     │  │ Engine           │   │
│  └────────────┘  └──────────────────┘   │
│  ┌────────────┐  ┌──────────────────┐   │
│  │ Hash Chain │  │ Persistence      │   │
│  │ Service    │  │ Service (5 wkrs) │   │
│  └────────────┘  └──────────────────┘   │
│  ┌────────────┐  ┌──────────────────┐   │
│  │ ARINC 429  │  │ AFDX Monitor    │   │
│  │ Simulator  │  │ (664 Part 7)    │   │
│  └────────────┘  └──────────────────┘   │
│  ┌────────────┐  ┌──────────────────┐   │
│  │ Cyber      │  │ Simulator       │   │
│  │ Security   │  │ (X-Plane/CSV)   │   │
│  └────────────┘  └──────────────────┘   │
└─────────┬───────────┬───────────┬───────┘
          │           │           │
          ▼           ▼           ▼
   PostgreSQL/     Redis       Kafka
   TimescaleDB   (cache,    (event stream)
                sessions)
```

### WebSocket Channels (9 real-time feeds)

| Channel | Data | Rate |
|---------|------|------|
| `telemetry` | Sensor stats, ATA breakdown | 1 Hz |
| `anomalies` | AI-detected anomalies | 1 Hz |
| `ecam` | ECAM advisories | On event |
| `twin` | Digital twin state (fuel, thermal, structural) | 1 Hz |
| `ai_status` | AI confidence, reconstruction error | 1 Hz |
| `hashchain` | Audit chain blocks | On block |
| `arinc429` | ARINC 429 bus words | 2 Hz |
| `afdx` | AFDX virtual link status | 1 Hz |
| `events` | System event log | On event |

---

## 4. Default Credentials

| Role | Username | Password | Access |
|------|----------|----------|--------|
| Administrator | admin | sentinel2026 | Full access |
| Pilot | pilot | pilot2026 | Read + dispatch |
| Maintenance Engineer | engineer | engineer2026 | Read + maintenance |
| Dispatcher | dispatcher | dispatcher2026 | Read + dispatch |
| Ground Crew | ground | ground2026 | Read only |
| QA Inspector | inspector | inspector2026 | Read + reports |

> [!CAUTION]
> **Change all passwords before production deployment.** Update via the admin API or seed script.

---

## 5. Common Operations

### Generate a PDF Airworthiness Report

```bash
make generate-report
# Or download via curl:
make download-report
# Saves to reports/sentineltwin-report-<timestamp>.pdf
```

### Adjust AI Detection Sensitivity

```bash
# More sensitive (lower threshold = more alerts):
curl -X POST http://localhost:8000/api/v1/anomalies/model/threshold?threshold=0.10 \
  -H "Authorization: Bearer <token>"

# Less sensitive (fewer false positives):
curl -X POST http://localhost:8000/api/v1/anomalies/model/threshold?threshold=0.25 \
  -H "Authorization: Bearer <token>"

# Check current model info:
curl http://localhost:8000/api/v1/anomalies/model/info \
  -H "Authorization: Bearer <token>"
```

### Inject a Fault for Testing

```bash
# Inject FREEZE fault on IRS_LATITUDE (ARINC label 0o101 = 65)
curl -X POST http://localhost:8000/api/v1/arinc/inject \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{"label_octal": 65, "fault_type": "FREEZE"}'

# Inject AFDX timing fault on a virtual link
curl -X POST http://localhost:8000/api/v1/afdx/inject \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{"vl_id": "VL-0100", "fault_type": "LATE"}'
```

### Connect X-Plane Simulator

```bash
# Prerequisites: In X-Plane → Settings → Data Output
#   Check "Send via UDP", IP=127.0.0.1, Port=49001

curl -X POST http://localhost:8000/api/v1/simulator/xplane/connect?port=49001 \
  -H "Authorization: Bearer <token>"
```

### Load CSV Replay

```bash
# Load a recording file
curl -X POST "http://localhost:8000/api/v1/simulator/replay/load?csv_path=/data/recording.csv" \
  -H "Authorization: Bearer <token>"

# Start playback at 2× speed
curl -X POST "http://localhost:8000/api/v1/simulator/replay/start?speed=2.0" \
  -H "Authorization: Bearer <token>"

# Check replay status
curl http://localhost:8000/api/v1/simulator/status \
  -H "Authorization: Bearer <token>"
```

### Database Operations

```bash
make db-migrate       # Apply pending migrations
make seed             # Seed with default data (7 aircraft, 6 users)
make db-reset         # Drop + recreate + migrate + seed (DESTRUCTIVE)
make exec-postgres    # Open psql shell
```

---

## 6. Monitoring

### Dashboards

| Dashboard | URL | Purpose |
|-----------|-----|---------|
| SentinelTwin UI | http://localhost:5173 | Main operations (21 panels) |
| API Docs (Swagger) | http://localhost:8000/api/docs | Interactive API |
| Grafana | http://localhost:3001 | Metrics & dashboards (20 panels) |
| Prometheus | http://localhost:9090 | Raw metrics |
| Health | http://localhost:8000/health | Quick status check |

### Key Metrics to Watch

| Metric | Normal | Warning | Action |
|--------|--------|---------|--------|
| `sensor_validations_total` | Increasing | Flat | Check sensor engine |
| `sensor_anomalies_total` | < 5% of sensors | > 5% | Check AI threshold |
| `ai_confidence` | > 0.90 | < 0.85 | Retrain model |
| `dispatch_readiness_score` | > 85 | < 70 | Investigate blockers |
| `ecam_active{severity="EMERGENCY"}` | 0 | > 0 | Immediate investigation |
| `persistence_queue_depth` | < 100 | > 500 | Check DB connection |
| `ws_connected_clients` | > 0 | 0 | Check WebSocket |

### Grafana Dashboard Panels (20 total)

1. Sensor Health Gauge
2. AI Confidence Gauge
3. Anomaly Rate (time series)
4. Validation Throughput
5. Sensor State Distribution (pie)
6. ECAM Advisory Count
7. Dispatch Score
8. Hash Chain Length
9. Persistence Queue Depth
10. WebSocket Client Count
11. Scan Cycle Duration
12. ATA Chapter Heatmap
13. Digital Twin Fuel Rate
14. Threat Event Rate
15. ARINC 429 Label Throughput
16. AFDX VL Utilization
17. API Latency (P95)
18. Backend Memory Usage
19. Database Connection Pool
20. System Uptime

---

## 7. UI Panel Reference (21 panels)

| # | Panel | Data Source | Key Features |
|---|-------|-----------|--------------|
| 1 | Overview | All engines | KPI cards, sensor health, AI confidence |
| 2 | Sensor Matrix | SensorExecutionEngine | 8,192 sensors, ATA chapter drill-down |
| 3 | Digital Twin | DigitalTwinEngine | ISA atmosphere, engine thermo, hydraulics |
| 4 | AI Anomaly | AIAnomalyEngine | Autoencoder, SHAP attribution, thresholds |
| 5 | ECAM Console | ECAMEngine | Color-coded advisories, MEL references |
| 6 | ARINC 429 | ARINC429Simulator | 32-bit word decode, bus status, faults |
| 7 | AFDX Monitor | AFDXMonitor | Virtual links, BAG timing, bandwidth |
| 8 | Dispatch | DispatchService | GO/NO-GO readiness, blocker list |
| 9 | Redundancy | `/api/v1/sensors/redundancy` | 2oo3 voting, channel values, byzantine fault |
| 10 | Audit Chain | HashChainService | SHA-256 blocks, tamper evidence |
| 11 | Cybersecurity | CybersecurityEngine | Threat detection, DO-326A compliance |
| 12 | Fleet Status | `/api/v1/fleet/status` | Multi-aircraft overview |
| 13 | Maintenance | `/api/v1/maintenance/actions` | Action history, scheduling |
| 14 | Phase Timeline | Zustand `twinState` | Flight phase progression, altitude canvas |
| 15 | Neural Net | Zustand `aiStatus` | Reconstruction error, layer weights |
| 16 | Environment | Zustand `twinState` | Fuel burn, thermal, structural loads |
| 17 | Fault Timeline | Zustand `ecamMessages` | Canvas scatter: ATA × time (60 min) |
| 18 | Op Logs | `/api/v1/logs/operational` | Live log viewer, level filter, export |
| 19 | Event Log | Zustand `eventLog` | System events, severity filter |
| 20 | Replay Console | Simulator API | X-Plane, CSV replay, speed control |
| 21 | Report | `/api/v1/reports/generate` | PDF airworthiness report generation |

---

## 8. Troubleshooting

### Backend fails to start

```bash
cat logs/backend.log          # Check error messages
make db-migrate               # Ensure DB schema is current
docker compose ps             # Check infrastructure is running
make health                   # Verify service endpoints
```

### WebSocket not connecting

1. Check backend is running: `make health`
2. Check browser console for WebSocket errors
3. Verify `vite.config.ts` proxy target is `http://localhost:8000`
4. Check nginx is not blocking `/ws/` path
5. Verify CORS settings in backend `main.py`

### PDF report generation fails

```bash
# Test directly
cd backend && python3 -c "
from services.report_service import AirworthinessReportGenerator
g = AirworthinessReportGenerator()
pdf = g.generate_pdf({
    'aircraft': {'type':'A320neo','msn':'8234','registration':'F-WXWB','operator':'Test'},
    'flight': {'number':'AF1234','origin':'LFPG','destination':'EGLL',
               'departure_utc':'2026-01-01T12:00:00Z','authorized_by':'admin'},
    'sensor_health': {},
    'ai': {'confidence':0.97,'severity':'NOMINAL','reconstruction_error':0.04,
           'model_version':'v2.4.1','top_anomalies':[]},
    'ecam': {'active':[],'cleared_count':0},
    'dispatch': {'ready':True,'score':99.0,'blockers':[]},
    'hash_chain': {'chain_valid':True,'block_count':42,'last_10_blocks':[]},
    'generated_by':'admin','report_id':'TEST-001'
})
print(f'PDF generated: {len(pdf):,} bytes')
"
```

### Database not persisting data

```bash
# Check persistence service is running
curl -sf http://localhost:8000/health \
  -H "Authorization: Bearer <token>" | python3 -m json.tool

# Check if queue depth is growing (workers may be stalled)
# Normal: queue_depth near 0. Problem: queue_depth > 100 and rising.

# Restart persistence workers
make restart
```

### High anomaly rate (> 5% of sensors)

1. Check AI threshold: `GET /api/v1/anomalies/model/info`
2. Increase threshold if false-positive rate is high:
   ```bash
   curl -X POST http://localhost:8000/api/v1/anomalies/model/threshold?threshold=0.20 \
     -H "Authorization: Bearer <token>"
   ```
3. Check if simulator is injecting faults: `GET /api/v1/simulator/status`
4. Review SHAP feature attributions on the AI Anomaly panel

### Kafka connection refused

```bash
# Check Kafka is running
docker compose ps kafka zookeeper

# Restart Kafka
docker compose restart zookeeper kafka

# Note: Backend starts gracefully without Kafka (events are buffered/dropped)
```

### Redis connection errors

```bash
# Check Redis
docker compose exec redis redis-cli ping
# Expected: PONG

# Restart Redis
docker compose restart redis

# Note: Backend starts gracefully without Redis (caching disabled)
```

---

## 9. Compliance Reference

| Standard | Requirement | Implementation |
|----------|-------------|----------------|
| DO-326A §6.3 | Threat condition identification | CybersecurityEngine threat detection |
| DO-326A §6.4 | Security controls | JWT + RBAC + TLS + rate limiting |
| DO-326A §6.5 | Security event logging | AuditLoggingMiddleware + immutable hash chain |
| ED-202A §4.2 | Airworthiness security process | HashChainService tamper evidence |
| ED-202A §4.3 | Security risk assessment | AI anomaly scoring + SHAP attribution |
| EASA AMC 20-42 | Digital system security | Full audit trail + immutable log |
| ARINC 664 Part 7 | AFDX deterministic timing | AFDXMonitor BAG enforcement |
| ARINC 429 | Label encoding/decoding | ARINC429Simulator full 32-bit word |
| ARINC 424 | ATA chapter taxonomy | 14 ATA chapters across all subsystems |

---

## 10. Kubernetes Deployment

```bash
# Apply manifests
make k8s-apply

# Check status
make k8s-status

# View backend logs
make k8s-logs

# Check rollout
make k8s-rollout

# Remove
make k8s-delete
```

### HPA Configuration

The backend deployment includes a HorizontalPodAutoscaler:
- **Min replicas:** 2
- **Max replicas:** 8
- **CPU target:** 70%
- **Memory target:** 80%

---

## 11. Backup & Recovery

### Database Backup

```bash
# Manual backup
docker compose exec postgres pg_dump -U sentineltwin sentineltwin > \
  backups/sentineltwin-$(date +%Y%m%d).sql

# Compressed backup
docker compose exec postgres pg_dump -U sentineltwin sentineltwin | \
  gzip > backups/sentineltwin-$(date +%Y%m%d).sql.gz

# Or use Makefile target
make db-backup
```

### Database Restore

```bash
# From SQL dump
cat backups/sentineltwin-20260520.sql | \
  docker compose exec -T postgres psql -U sentineltwin sentineltwin

# From compressed dump
gunzip -c backups/sentineltwin-20260520.sql.gz | \
  docker compose exec -T postgres psql -U sentineltwin sentineltwin
```

### Hash Chain Archive

```bash
# The hash chain is critical for compliance — always back up
cp -r data/hash_chain/ backups/hash_chain-$(date +%Y%m%d)/
```

### Full System Recovery

```bash
# 1. Start infrastructure
make up

# 2. Wait for services
sleep 10

# 3. Restore database
cat backups/sentineltwin-latest.sql | \
  docker compose exec -T postgres psql -U sentineltwin sentineltwin

# 4. Verify
make health
python3 scripts/production_check.py
```

---

## 12. Production Deployment Checklist

Before deploying to production, run:

```bash
python3 scripts/production_check.py
```

Manual checks:
- [ ] `SECRET_KEY` changed in `.env`
- [ ] All default passwords changed
- [ ] TLS certificates from a trusted CA (not self-signed)
- [ ] `DEBUG=false` in `.env`
- [ ] Firewall rules: only 443 (HTTPS) and 8000 (API) exposed
- [ ] Database backups scheduled (daily recommended)
- [ ] Grafana alerting configured for critical metrics
- [ ] Log rotation configured for `logs/` directory
- [ ] Kafka retention policy set (default: 7 days)
- [ ] Redis maxmemory-policy set (recommended: `allkeys-lru`)

---

*SentinelTwin v4.2.1 — EASA DO-326A Compliant — Airbus Fly Your Ideas 2026*
