"""SentinelTwin — Anomalies Routes"""
from datetime import datetime, timezone
from typing import Dict
from fastapi import APIRouter, Depends, HTTPException, Request
from api.routes._auth_utils import get_current_user, require_role

router = APIRouter()

@router.get("/status")
async def ai_status(request: Request, user: Dict = Depends(get_current_user)):
    engine = getattr(request.app.state, "ai_engine", None)
    if not engine:
        raise HTTPException(status_code=503, detail="AI_ENGINE_NOT_READY")
    return engine.get_status()

@router.get("/events")
async def get_ai_events(request: Request, limit: int = 50, user: Dict = Depends(get_current_user)):
    engine = getattr(request.app.state, "ai_engine", None)
    if not engine:
        raise HTTPException(status_code=503, detail="AI_ENGINE_NOT_READY")
    events = list(engine.event_history)[-limit:][::-1]
    return {
        "count": len(events), "active_events": len(engine.active_events),
        "events": [
            {"event_id": e.event_id, "sensor_id": e.sensor_id, "ata_chapter": e.ata_chapter,
             "detected_at": datetime.fromtimestamp(e.detected_at, tz=timezone.utc).isoformat(),
             "anomaly_type": e.anomaly_type, "severity": e.severity,
             "reconstruction_error": round(e.reconstruction_error, 6),
             "confidence": round(e.confidence, 4), "description": e.description,
             "is_resolved": e.is_resolved}
            for e in events
        ],
    }

@router.post("/threshold")
async def update_threshold(request: Request, threshold: float,
                           user: Dict = Depends(get_current_user)):
    engine = getattr(request.app.state, "ai_engine", None)
    if not engine:
        raise HTTPException(status_code=503, detail="AI_ENGINE_NOT_READY")
    if not 0.01 <= threshold <= 1.0:
        raise HTTPException(status_code=422, detail="Threshold must be between 0.01 and 1.0")
    old = engine.autoencoder.anomaly_threshold
    engine.autoencoder.anomaly_threshold = threshold
    return {"status": "UPDATED", "old_threshold": old, "new_threshold": threshold,
            "updated_by": user["username"], "timestamp": datetime.now(timezone.utc).isoformat()}


# ─────────────────────────────────────────────────────────────
# NEW — AI Model Info, Threshold Tuning, Top Anomalies
# ─────────────────────────────────────────────────────────────

@router.get("/model/info")
async def model_info(
    request: Request,
    user: Dict = Depends(get_current_user),
):
    """Get AI model metadata, version, and performance metrics."""
    ai = getattr(request.app.state, "ai_engine", None)
    if not ai:
        raise HTTPException(503, "AI engine not available")
    return ai.get_model_info()


@router.post("/model/threshold")
async def set_threshold(
    request: Request,
    threshold: float,
    user: Dict = Depends(require_role("administrator", "qa_inspector")),
):
    """
    Adjust anomaly detection threshold at runtime.
    threshold: float in range [0.01, 1.0]
    Lower = more sensitive (more alerts), Higher = less sensitive (fewer alerts)
    """
    ai = getattr(request.app.state, "ai_engine", None)
    if not ai:
        raise HTTPException(503, "AI engine not available")
    if not 0.01 <= threshold <= 1.0:
        raise HTTPException(422, "threshold must be between 0.01 and 1.0")
    return ai.set_anomaly_threshold(threshold)


@router.get("/top")
async def top_anomalies(
    request: Request,
    limit: int = 20,
    user: Dict = Depends(get_current_user),
):
    """Get the current top anomalous sensors ranked by AI score."""
    ai     = getattr(request.app.state, "ai_engine",     None)
    sensor = getattr(request.app.state, "sensor_engine", None)
    if not ai or not sensor:
        raise HTTPException(503, "Engines not available")
    sensors = getattr(sensor, "sensors", [])
    return {
        "top_anomalies": ai.get_top_anomalous_sensors(sensors, top_n=limit),
        "timestamp":     datetime.now(timezone.utc).isoformat(),
    }


@router.get("/history")
async def anomaly_history(
    request: Request,
    hours: int = 24,
    user: Dict = Depends(get_current_user),
):
    """
    Return anomaly events from the last `hours` hours from DB.
    Falls back to in-memory event log if DB not available.
    """
    persistence = getattr(request.app.state, "persistence_service", None)
    if persistence and persistence.has_db:
        events = await persistence.get_anomaly_history(hours)
        return {"hours": hours, "events": events, "count": len(events), "source": "TIMESCALEDB"}
    # Fallback: in-memory from AI engine
    ai = getattr(request.app.state, "ai_engine", None)
    events = ai.get_event_history() if ai and hasattr(ai, "get_event_history") else []
    return {"hours": hours, "events": events[:200], "count": len(events), "source": "MEMORY"}

