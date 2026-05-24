"""SentinelTwin — Sensor API Routes"""
from collections import defaultdict
from datetime import datetime, timezone
from typing import Dict, Optional
from fastapi import APIRouter, Depends, HTTPException, Request
from api.routes._auth_utils import get_current_user

router = APIRouter()


@router.get("/")
async def list_sensors(
    request: Request,
    limit: int = 100,
    offset: int = 0,
    ata_chapter: Optional[int] = None,
    user: Dict = Depends(get_current_user),
):
    """Paginated sensor list with optional ATA chapter filter."""
    engine = getattr(request.app.state, "sensor_engine", None)
    if not engine:
        raise HTTPException(status_code=503, detail="SENSOR_ENGINE_NOT_READY")
    sensors = engine.sensors or []
    if ata_chapter is not None:
        sensors = [s for s in sensors if s.ata_chapter == ata_chapter]
    total = len(sensors)
    page = sensors[offset: offset + limit]
    return {
        "total": total,
        "limit": limit,
        "offset": offset,
        "sensors": [
            {
                "sensor_id": s.sensor_id,
                "ata_chapter": s.ata_chapter,
                "subsystem": s.subsystem,
                "zone": s.aircraft_zone,
                "unit": s.engineering_unit,
                "state": s.state.value if hasattr(s.state, "value") else str(s.state),
                "last_value": round(s.last_calibrated_value, 4),
                "ai_score": round(s.ai_anomaly_score, 4),
                "confidence": round(s.confidence_score, 4),
            }
            for s in page
        ],
    }


@router.get("/stats")
async def sensor_stats(request: Request, user: Dict = Depends(get_current_user)):
    """Alias for /sensors/summary — returns aggregate stats."""
    engine = getattr(request.app.state, "sensor_engine", None)
    if not engine:
        raise HTTPException(status_code=503, detail="SENSOR_ENGINE_NOT_READY")
    stats = engine.get_stats()
    return {
        "total_sensors": stats.get("total_sensors", 8192),
        "healthy_count": stats.get("healthy_count", 0),
        "anomaly_count": stats.get("anomaly_count", 0),
        "total_validations": stats.get("total_validations", 0),
        "cycle_duration_ms": stats.get("cycle_duration_ms", 0),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@router.get("/summary")
async def sensor_summary(request: Request, user: Dict = Depends(get_current_user)):
    engine = getattr(request.app.state, "sensor_engine", None)
    if not engine:
        raise HTTPException(status_code=503, detail="SENSOR_ENGINE_NOT_READY")
    stats = engine.get_stats()
    ata_breakdown = {}
    for sensor in (engine.sensors or []):
        ata = sensor.ata_chapter
        if ata not in ata_breakdown:
            ata_breakdown[ata] = {"total": 0, "healthy": 0, "degraded": 0, "failed": 0, "other": 0}
        ata_breakdown[ata]["total"] += 1
        state = sensor.state.value if hasattr(sensor.state, "value") else str(sensor.state)
        if state == "HEALTHY": ata_breakdown[ata]["healthy"] += 1
        elif state == "DEGRADED": ata_breakdown[ata]["degraded"] += 1
        elif state == "FAILED": ata_breakdown[ata]["failed"] += 1
        else: ata_breakdown[ata]["other"] += 1
    return {
        "total_sensors": stats.get("total_sensors", 8192),
        "healthy_count": stats.get("healthy_count", 0),
        "anomaly_count": stats.get("anomaly_count", 0),
        "total_validations": stats.get("total_validations", 0),
        "cycle_duration_ms": stats.get("cycle_duration_ms", 0),
        "ata_breakdown": ata_breakdown,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@router.get("/ata/{ata_chapter}")
async def sensors_by_ata(ata_chapter: int, request: Request, limit: int = 100,
                         offset: int = 0, user: Dict = Depends(get_current_user)):
    engine = getattr(request.app.state, "sensor_engine", None)
    if not engine:
        raise HTTPException(status_code=503, detail="SENSOR_ENGINE_NOT_READY")
    sensors = [s for s in engine.sensors if s.ata_chapter == ata_chapter]
    page = sensors[offset:offset + limit]
    return {
        "ata_chapter": ata_chapter, "total": len(sensors), "limit": limit, "offset": offset,
        "sensors": [
            {"sensor_id": s.sensor_id, "subsystem": s.subsystem, "zone": s.aircraft_zone,
             "unit": s.engineering_unit,
             "state": s.state.value if hasattr(s.state, "value") else str(s.state),
             "last_value": round(s.last_calibrated_value, 4),
             "physics_residual": round(s.last_physics_residual, 6),
             "confidence": round(s.confidence_score, 4),
             "ai_score": round(s.ai_anomaly_score, 4),
             "redundancy_group": s.redundancy_group, "arinc_label": s.arinc_label,
             "validation_count": s.validation_count}
            for s in page
        ],
    }


@router.get("/anomalous")
async def get_anomalous_sensors(request: Request, threshold: float = 0.5,
                                 user: Dict = Depends(get_current_user)):
    engine = getattr(request.app.state, "sensor_engine", None)
    if not engine:
        raise HTTPException(status_code=503, detail="SENSOR_ENGINE_NOT_READY")
    anomalous = [s for s in engine.sensors if s.ai_anomaly_score > threshold or
                 (hasattr(s.state, "value") and s.state.value != "HEALTHY")]
    return {
        "count": len(anomalous), "threshold": threshold,
        "sensors": [
            {"sensor_id": s.sensor_id, "ata_chapter": s.ata_chapter, "subsystem": s.subsystem,
             "state": s.state.value if hasattr(s.state, "value") else str(s.state),
             "ai_score": round(s.ai_anomaly_score, 4),
             "confidence": round(s.confidence_score, 4),
             "physics_residual": round(s.last_physics_residual, 6)}
            for s in anomalous[:200]
        ],
    }


@router.get("/redundancy")
async def redundancy_status(
    request: Request,
    ata_chapter: Optional[int] = None,
    user: Dict = Depends(get_current_user),
):
    """
    Return current 2oo3 redundancy vote results per redundancy group.
    Groups sensors by redundancy_group field and returns VoteResult for each.
    """
    sensor_engine = getattr(request.app.state, "sensor_engine", None)
    if not sensor_engine:
        raise HTTPException(503, "Sensor engine not available")

    sensors = getattr(sensor_engine, "sensors", []) or []
    if ata_chapter:
        sensors = [s for s in sensors if s.ata_chapter == ata_chapter]

    # Group sensors by redundancy_group
    groups = defaultdict(list)
    for s in sensors:
        rg = getattr(s, "redundancy_group", None)
        if rg:
            groups[rg].append(s)

    # Run voter for each group with >= 2 sensors
    voter = getattr(sensor_engine, "voter", None)
    results = []
    for group_id, group_sensors in list(groups.items())[:50]:
        if len(group_sensors) < 2:
            continue
        readings = [float(s.last_calibrated_value) for s in group_sensors]
        ata = group_sensors[0].ata_chapter
        eng_range = float(
            group_sensors[0].max_limit - group_sensors[0].min_limit
        ) if hasattr(group_sensors[0], "max_limit") else 100.0

        vote_result = None
        if voter:
            try:
                vote_result = voter.vote(
                    readings, ata_chapter=ata
                )
            except Exception:
                pass

        results.append({
            "group_id":      group_id,
            "ata_chapter":   ata,
            "channel_count": len(group_sensors),
            "channels": [
                {
                    "index":     i,
                    "sensor_id": s.sensor_id,
                    "value":     round(float(s.last_calibrated_value), 3),
                    "state":     s.state.value if hasattr(s.state, "value") else str(s.state),
                    "unit":      s.engineering_unit,
                }
                for i, s in enumerate(group_sensors)
            ],
            "vote": {
                "voted_value":     round(vote_result.voted_value, 3)     if vote_result else None,
                "confidence":      round(vote_result.confidence, 3)      if vote_result else None,
                "byzantine_fault": vote_result.byzantine_fault            if vote_result else False,
                "failed_channels": vote_result.failed_channels            if vote_result else [],
                "method":          vote_result.method                     if vote_result else "UNKNOWN",
            } if vote_result else None,
        })

    return {
        "groups":     results,
        "count":      len(results),
        "ata_filter": ata_chapter,
        "timestamp":  datetime.now(timezone.utc).isoformat(),
    }
