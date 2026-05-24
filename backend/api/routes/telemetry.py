"""SentinelTwin — Telemetry Routes"""
import random
from datetime import datetime, timedelta, timezone
from typing import Dict
from fastapi import APIRouter, Depends, Request
from api.routes._auth_utils import get_current_user

router = APIRouter()

@router.get("/status")
async def telemetry_status(request: Request, user: Dict = Depends(get_current_user)):
    engine = getattr(request.app.state, "sensor_engine", None)
    stats = engine.get_stats() if engine else {}
    return {"status": "STREAMING", "sensors": stats.get("total_sensors", 8192),
            "scan_rate_hz": 20, "total_validations": stats.get("total_validations", 0),
            "cycle_ms": stats.get("cycle_duration_ms", 0),
            "timestamp": datetime.now(timezone.utc).isoformat()}

@router.get("/stream-info")
async def stream_info(request: Request, user: Dict = Depends(get_current_user)):
    return {"endpoint": "/ws/telemetry", "protocol": "WebSocket",
            "channels": ["telemetry", "ecam", "ai", "hashchain", "twin", "dispatch", "cyber"],
            "timestamp": datetime.now(timezone.utc).isoformat()}


@router.get("/history")
async def telemetry_history(
    request: Request,
    ata_chapter: int,
    minutes: int = 60,
    user: Dict = Depends(get_current_user),
):
    """
    Query TimescaleDB for telemetry history using time_bucket aggregation.
    Returns 1-minute buckets for the last `minutes` minutes.
    """
    persistence = getattr(request.app.state, "persistence_service", None)
    if not persistence or not persistence.has_db:
        # Fallback: generate synthetic history
        now = datetime.now(timezone.utc)
        return {
            "ata_chapter": ata_chapter,
            "minutes":     minutes,
            "buckets":     [
                {
                    "bucket": (now - timedelta(minutes=minutes - i)).isoformat(),
                    "avg_value": round(random.gauss(50, 10), 2),
                    "sensor_count": 8,
                }
                for i in range(minutes)
            ],
            "source": "SYNTHETIC_FALLBACK",
        }
    buckets = await persistence.get_recent_telemetry(ata_chapter, minutes)
    return {
        "ata_chapter": ata_chapter,
        "minutes":     minutes,
        "buckets":     buckets,
        "source":      "TIMESCALEDB",
    }
