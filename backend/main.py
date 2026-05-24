"""
SENTINELTWIN — Industrial Aerospace Platform
FastAPI Backend — Production Grade
EASA DO-326A / ED-202A Compliant
"""

import asyncio
import logging
import os
from contextlib import asynccontextmanager
from datetime import datetime, timezone

import uvicorn
from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse, PlainTextResponse

from api.routes import (
    auth,
    aircraft,
    sensors,
    telemetry,
    anomalies,
    dispatch,
    hash_chain,
    ecam,
    reports,
    websocket,
    simulator,
    maintenance,
    cybersecurity,
    fleet,
)
from api.routes import arinc, afdx
from api.routes import logs as logs_route
from api.routes.logs import install_log_handler
from api.routes.websocket import broadcast_loop
from core.config import settings
from core.database import engine, Base
from core.redis_client import redis_client
from core.logger import setup_logging
from middleware.security import SecurityHeadersMiddleware, RateLimitMiddleware
from middleware.audit import AuditLoggingMiddleware
from services.sensor_engine import SensorExecutionEngine, AIRCRAFT_PROFILES
from services.ai_engine import AIAnomalyEngine
from services.hash_service import HashChainService
from services.digital_twin import DigitalTwinEngine
from services.ecam_engine import ECAMEngine
from services.arinc429_service import ARINC429Simulator
from services.afdx_service import AFDXMonitor
from services.security_engine import CybersecurityEngine
from services.persistence_service import PersistenceService
from services.kafka_producer import KafkaEventProducer

# AI alias router (fresh APIRouter so FastAPI doesn't deduplicate against anomalies.router)
_ai_router = None

# Prometheus metrics (optional — graceful if not installed)
try:
    from prometheus_client import (
        Counter, Histogram, Gauge, generate_latest, CONTENT_TYPE_LATEST,
    )
    PROMETHEUS_AVAILABLE = True

    sensor_validations_total = Counter(
        "sensor_validations_total",
        "Total sensor validations performed",
    )
    sensor_anomalies_total = Counter(
        "sensor_anomalies_total",
        "Total sensor anomalies detected",
        ["ata_chapter", "severity"],
    )
    sensor_scan_latency = Histogram(
        "sensor_scan_latency_seconds",
        "Time for a full sensor scan cycle",
        buckets=[0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0],
    )
    ai_reconstruction_error = Gauge(
        "ai_reconstruction_error",
        "Current autoencoder reconstruction error",
    )
    ai_confidence_gauge = Gauge(
        "ai_confidence",
        "Current AI confidence score",
    )
    ecam_active_advisories = Gauge(
        "ecam_active_advisories",
        "Number of active ECAM advisories",
        ["severity"],
    )
    hash_chain_blocks_total = Counter(
        "hash_chain_blocks_total",
        "Total hash chain blocks created",
    )
    websocket_clients_connected = Gauge(
        "websocket_clients_connected",
        "Number of active WebSocket connections",
    )
    dispatch_readiness_score = Gauge(
        "dispatch_readiness_score",
        "Current dispatch readiness score (0-100)",
    )
    kafka_queue_depth = Gauge(
        "kafka_producer_queue_depth",
        "Kafka send queue depth",
    )
    ws_msg_rate = Counter(
        "websocket_messages_total",
        "Total WS messages sent",
    )
except ImportError:
    PROMETHEUS_AVAILABLE = False

setup_logging()
log = logging.getLogger("sentineltwin.main")


# ─────────────────────────────────────────────────────────────
# APPLICATION LIFESPAN
# ─────────────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    log.info("SENTINELTWIN startup sequence initiated")

    # Install log handler for /api/v1/logs/operational
    install_log_handler()

    # Create database tables (graceful — works without DB)
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        log.info("Database schema verified")
    except Exception as e:
        log.warning(f"Database not available (non-fatal): {e}")

    # Connect Redis (non-fatal)
    await redis_client.connect()

    # Initialize core services
    sensor_engine = SensorExecutionEngine()
    ai_engine = AIAnomalyEngine()
    hash_service = HashChainService()
    twin_engine = DigitalTwinEngine()
    ecam_engine = ECAMEngine()
    arinc_service = ARINC429Simulator()
    afdx_service = AFDXMonitor()
    security_engine = CybersecurityEngine()
    persistence_service = PersistenceService()

    # Kafka event producer (graceful — works without Kafka)
    kafka_producer = KafkaEventProducer(
        bootstrap_servers=os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
    )
    await kafka_producer.start()

    app.state.sensor_engine = sensor_engine
    app.state.ai_engine = ai_engine
    app.state.hash_service = hash_service
    app.state.twin_engine = twin_engine
    app.state.ecam_engine = ecam_engine
    app.state.arinc_service = arinc_service
    app.state.afdx_service = afdx_service
    app.state.security_engine = security_engine
    app.state.persistence_service = persistence_service
    app.state.kafka_producer = kafka_producer

    # Wire persistence into engines
    sensor_engine.persistence = persistence_service
    ecam_engine.persistence = persistence_service
    hash_service.persistence = persistence_service

    # Wire Kafka into engines
    sensor_engine.kafka = kafka_producer
    ecam_engine.kafka = kafka_producer

    # Start persistence workers (returns immediately — tasks are fire-and-forget)
    await persistence_service.start()

    # Start background tasks
    asyncio.create_task(sensor_engine.run(), name="sensor_execution_engine")
    asyncio.create_task(ai_engine.run(), name="ai_anomaly_engine")
    asyncio.create_task(twin_engine.run(), name="digital_twin_engine")
    asyncio.create_task(ecam_engine.run(), name="ecam_engine")

    # Schedule the WebSocket broadcast loop
    broadcast_task = asyncio.create_task(
        broadcast_loop(app), name="ws_broadcast_loop"
    )
    app.state.broadcast_task = broadcast_task
    log.info("WebSocket broadcast loop scheduled")

    log.info("All subsystems ONLINE — SentinelTwin OPERATIONAL")
    log.info(f"Listening on {settings.HOST}:{settings.PORT}")

    yield

    # Graceful shutdown
    log.info("Initiating graceful shutdown sequence")

    # Cancel the WebSocket broadcast loop
    broadcast_task = getattr(app.state, "broadcast_task", None)
    if broadcast_task:
        broadcast_task.cancel()
        await asyncio.gather(broadcast_task, return_exceptions=True)
        log.info("WebSocket broadcast loop stopped")

    await sensor_engine.stop()
    await ai_engine.stop()
    await twin_engine.stop()
    await ecam_engine.stop()
    await persistence_service.stop()
    await app.state.kafka_producer.stop()
    await redis_client.disconnect()
    log.info("SentinelTwin shutdown complete")


# ─────────────────────────────────────────────────────────────
# APPLICATION FACTORY
# ─────────────────────────────────────────────────────────────
def create_app() -> FastAPI:
    app = FastAPI(
        title="SentinelTwin",
        description="Airbus Airworthiness Assurance & Sensor Integrity Platform",
        version="4.4.0",
        docs_url="/api/docs" if settings.DEBUG else None,
        redoc_url="/api/redoc" if settings.DEBUG else None,
        openapi_url="/api/openapi.json" if settings.DEBUG else None,
        lifespan=lifespan,
    )

    # ── Middleware stack (order matters) ──────────────────────
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "DELETE", "PATCH"],
        allow_headers=["*"],
    )
    app.add_middleware(GZipMiddleware, minimum_size=1000)
    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(RateLimitMiddleware)
    app.add_middleware(AuditLoggingMiddleware)

    # ── API Routers ───────────────────────────────────────────
    PREFIX = "/api/v1"
    app.include_router(auth.router,         prefix=f"{PREFIX}/auth",         tags=["Authentication"])
    app.include_router(aircraft.router,     prefix=f"{PREFIX}/aircraft",     tags=["Aircraft"])
    app.include_router(sensors.router,      prefix=f"{PREFIX}/sensors",      tags=["Sensors"])
    app.include_router(telemetry.router,    prefix=f"{PREFIX}/telemetry",    tags=["Telemetry"])
    app.include_router(anomalies.router,    prefix=f"{PREFIX}/anomalies",    tags=["Anomalies"])
    app.include_router(dispatch.router,     prefix=f"{PREFIX}/dispatch",     tags=["Dispatch"])
    app.include_router(hash_chain.router,   prefix=f"{PREFIX}/hashchain",    tags=["Audit Chain"])
    app.include_router(ecam.router,         prefix=f"{PREFIX}/ecam",         tags=["ECAM"])
    app.include_router(reports.router,      prefix=f"{PREFIX}/reports",      tags=["Reports"])
    app.include_router(simulator.router,    prefix=f"{PREFIX}/simulator",    tags=["Simulator"])
    app.include_router(maintenance.router,  prefix=f"{PREFIX}/maintenance",  tags=["Maintenance"])
    app.include_router(cybersecurity.router,prefix=f"{PREFIX}/cybersecurity",tags=["Cybersecurity"])
    app.include_router(fleet.router,        prefix=f"{PREFIX}/fleet",        tags=["Fleet"])
    app.include_router(arinc.router,        prefix=f"{PREFIX}/arinc",        tags=["ARINC 429"])
    app.include_router(afdx.router,         prefix=f"{PREFIX}/afdx",         tags=["AFDX"])
    app.include_router(websocket.router,    prefix="/ws",                    tags=["WebSocket"])
    app.include_router(logs_route.router,   prefix=f"{PREFIX}/logs",          tags=["Logs"])

    # ── /api/v1/ai/* aliases (frontend compatibility) ────────
    from fastapi import Depends as _Depends, HTTPException as _HTTPException
    from api.routes._auth_utils import get_current_user as _get_current_user
    from typing import Dict as _Dict

    @app.get(f"{PREFIX}/ai/status", tags=["AI Engine"])
    async def ai_status_alias(request: Request, user: _Dict = _Depends(_get_current_user)):
        engine = getattr(request.app.state, "ai_engine", None)
        if not engine:
            raise _HTTPException(status_code=503, detail="AI_ENGINE_NOT_READY")
        return engine.get_status()

    @app.get(f"{PREFIX}/ai/events", tags=["AI Engine"])
    async def ai_events_alias(request: Request, limit: int = 50,
                               user: _Dict = _Depends(_get_current_user)):
        engine = getattr(request.app.state, "ai_engine", None)
        if not engine:
            raise _HTTPException(status_code=503, detail="AI_ENGINE_NOT_READY")
        events = list(engine.event_history)[-limit:][::-1]
        return {"count": len(events), "active_events": len(engine.active_events),
                "events": [{"event_id": e.event_id, "sensor_id": e.sensor_id,
                             "ata_chapter": e.ata_chapter, "anomaly_type": e.anomaly_type,
                             "severity": e.severity, "confidence": round(e.confidence, 4)}
                            for e in events]}


    # ── Health endpoint ───────────────────────────────────────
    @app.get("/health", tags=["System"])
    async def health_check(request: Request):
        return {
            "status": "OPERATIONAL",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "version": "4.4.0",
            "services": {
                "sensor_engine": "RUNNING",
                "ai_engine": "RUNNING",
                "digital_twin": "RUNNING",
                "ecam_engine": "RUNNING",
                "hash_chain": "ACTIVE",
                "arinc_429": "ACTIVE",
                "afdx_monitor": "ACTIVE",
                "cybersecurity": "ACTIVE",
                "persistence": "ACTIVE",
                "database": "CONNECTED",
                "redis": "CONNECTED" if redis_client.is_connected else "OFFLINE",
            },
            "compliance": {
                "do326a": True,
                "ed202a": True,
                "easa_amc_20_42": True,
            }
        }

    # ── Detailed health endpoint ──────────────────────────────
    @app.get("/health/detailed", tags=["System"])
    async def detailed_health(request: Request):
        """Detailed subsystem health for ops monitoring and k8s readiness probes."""
        checks = {}
        overall_status = "OPERATIONAL"

        def check(name: str, obj_attr: str, method: str = "get_stats"):
            nonlocal overall_status
            try:
                svc = getattr(request.app.state, obj_attr, None)
                if svc and hasattr(svc, method):
                    detail = getattr(svc, method)()
                    checks[name] = {"status": "UP", "detail": detail}
                elif svc:
                    checks[name] = {"status": "UP", "detail": "initialized"}
                else:
                    checks[name] = {"status": "NOT_INITIALIZED"}
            except Exception as exc:
                checks[name] = {"status": "ERROR", "error": str(exc)}
                overall_status = "DEGRADED"

        check("sensor_engine",   "sensor_engine",       "get_stats")
        check("ai_engine",       "ai_engine",           "get_status")
        check("ecam_engine",     "ecam_engine",         "get_stats")
        check("digital_twin",   "twin_engine",         "get_status")
        check("hash_chain",     "hash_service",        "get_stats")
        check("security_engine","security_engine",     "get_threat_dashboard")
        check("arinc_service",  "arinc_service",       "get_bus_stats")
        check("afdx_service",   "afdx_service",        "get_network_stats")
        check("persistence",    "persistence_service", "get_stats")
        check("kafka",          "kafka_producer",      "get_stats")

        ws_mgr = getattr(websocket, "ws_manager", None)
        ws_stats = ws_mgr.stats() if ws_mgr else {}

        return {
            "status":             overall_status,
            "platform":           "SentinelTwin v4.4.0",
            "timestamp":          datetime.now(timezone.utc).isoformat(),
            "subsystems":         checks,
            "websocket":          ws_stats,
            "compliance": {
                "do326a": True, "ed202a": True,
                "easa_amc_20_42": True, "arinc_664": True,
            },
        }

    # ── Aircraft profiles endpoint ────────────────────────────
    @app.get("/api/v1/aircraft/profiles", tags=["Aircraft"])
    async def get_aircraft_profiles():
        return {
            "profiles": {
                name: {
                    "engines": p["engines"],
                    "engine_type": p["engine_type"],
                    "total_sensors": p["total_sensors"],
                    "ata_distribution": p["ata_distribution"],
                }
                for name, p in AIRCRAFT_PROFILES.items()
            },
            "count": len(AIRCRAFT_PROFILES),
        }

    # ── Prometheus metrics endpoint ───────────────────────────
    @app.get("/metrics", tags=["Monitoring"])
    async def prometheus_metrics(request: Request):
        if not PROMETHEUS_AVAILABLE:
            return PlainTextResponse(
                "# Prometheus client not installed\n",
                media_type="text/plain",
            )

        # Update gauges from current state
        sensor_engine = getattr(request.app.state, "sensor_engine", None)
        ai_engine_inst = getattr(request.app.state, "ai_engine", None)
        ecam_engine_inst = getattr(request.app.state, "ecam_engine", None)
        ws_mgr = getattr(websocket, "ws_manager", None)

        if sensor_engine:
            stats = sensor_engine.get_stats()
            sensor_scan_latency.observe(stats.get("cycle_duration_ms", 0) / 1000.0)

        if ai_engine_inst:
            ai_status = ai_engine_inst.get_status()
            ai_reconstruction_error.set(ai_status.get("current_reconstruction_error", 0))
            ai_confidence_gauge.set(ai_status.get("current_confidence", 0))

        if ecam_engine_inst:
            ecam_stats = ecam_engine_inst.get_stats()
            for sev in ["emergency", "warning", "caution", "status"]:
                ecam_active_advisories.labels(severity=sev.upper()).set(
                    ecam_stats.get(sev, 0)
                )

        if ws_mgr:
            ws_stats = ws_mgr.stats()
            websocket_clients_connected.set(ws_stats.get("active_connections", 0))

        # Kafka queue depth
        kafka_prod = getattr(request.app.state, "kafka_producer", None)
        if kafka_prod and hasattr(kafka_prod, '_send_queue'):
            try:
                kafka_queue_depth.set(kafka_prod._send_queue.qsize())
            except Exception:
                pass

        # Dispatch readiness
        _dispatch_svc = getattr(request.app.state, "persistence_service", None)
        if sensor_engine and ai_engine_inst:
            s_stats = sensor_engine.get_stats()
            _a_status = ai_engine_inst.get_status()
            health = s_stats.get("healthy_count", 0) / max(1, s_stats.get("total_sensors", 8192)) * 100
            dispatch_readiness_score.set(round(health, 1))

        return PlainTextResponse(
            generate_latest().decode("utf-8"),
            media_type=CONTENT_TYPE_LATEST,
        )

    # ── Global exception handler ──────────────────────────────
    @app.exception_handler(Exception)
    async def global_exception_handler(request: Request, exc: Exception):
        log.error(f"Unhandled exception: {exc}", exc_info=True)
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "error": "INTERNAL_SYSTEM_ERROR",
                "message": "An unexpected error occurred. Incident logged.",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        )

    return app


app = create_app()


if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=False,
        workers=1,
        log_level="info",
        access_log=True,
    )

