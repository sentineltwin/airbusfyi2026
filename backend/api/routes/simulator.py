"""SentinelTwin — Simulator Routes"""
from datetime import datetime, timezone
from typing import Dict, List, Optional
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from api.routes._auth_utils import get_current_user, require_role

router = APIRouter()

class PhaseRequest(BaseModel):
    phase: str
    altitude_ft: Optional[float] = None
    speed_kt: Optional[float] = None

@router.get("/status")
async def simulator_status(request: Request, user: Dict = Depends(get_current_user)):
    """Get current simulator state and data source."""
    twin = getattr(request.app.state, "twin_engine", None)
    from services.simulator import simulator_manager
    sim = simulator_manager

    # Base status from twin engine
    base = {
        "connected": twin is not None,
        "supported_sources": ["X-PLANE", "MSFS", "INTERNAL", "REPLAY", "CSV_REPLAY"],
        "current_phase": twin.twin.flight_phase if twin else "GROUND",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    # Merge simulator manager status
    base["source"]        = getattr(sim, "_source", "SYNTHETIC")
    base["active_source"] = getattr(sim, "_active_source", "SYNTHETIC")
    base["replay_index"]  = getattr(sim, "_replay_index", 0)
    base["replay_total"]  = len(getattr(sim, "_replay_frames", []))
    base["replay_speed"]  = getattr(sim, "_replay_speed", 1.0)
    last_frame = getattr(sim, "_last_frame", None)
    base["last_frame_ts"] = getattr(last_frame, "timestamp_utc", None) if last_frame else None
    return base

@router.post("/phase")
async def set_phase(body: PhaseRequest, request: Request,
                    user: Dict = Depends(require_role("pilot", "administrator", "maintenance_engineer"))):
    twin = getattr(request.app.state, "twin_engine", None)
    if not twin:
        raise HTTPException(status_code=503, detail="TWIN_ENGINE_NOT_READY")
    valid = ["GROUND", "TAXI", "TAKEOFF", "CLIMB", "CRUISE", "DESCENT", "APPROACH", "LANDING"]
    phase = body.phase.upper()
    if phase not in valid:
        raise HTTPException(status_code=422, detail=f"Phase must be one of: {valid}")
    twin.set_phase(phase)
    sensor_engine = getattr(request.app.state, "sensor_engine", None)
    if sensor_engine:
        sensor_engine.flight_phase = phase
    return {"status": "OK", "phase": phase, "set_by": user["username"],
            "timestamp": datetime.now(timezone.utc).isoformat()}


# ─────────────────────────────────────────────────────────────
# X-Plane UDP Integration
# ─────────────────────────────────────────────────────────────

@router.post("/xplane/connect")
async def connect_xplane(
    request: Request,
    port: int = 49001,
    user: Dict = Depends(require_role("administrator", "maintenance_engineer")),
):
    """Connect to X-Plane UDP stream."""
    from services.simulator import simulator_manager
    sim = simulator_manager
    ok = await sim.start_xplane(recv_port=port)
    return {"connected": ok, "source": sim._source, "port": port}


# ─────────────────────────────────────────────────────────────
# CSV Replay Engine
# ─────────────────────────────────────────────────────────────

@router.post("/replay/load")
async def load_replay(
    request: Request,
    csv_path: str,
    user: Dict = Depends(require_role("administrator", "maintenance_engineer", "qa_inspector")),
):
    """Load a CSV telemetry file for replay."""
    from services.simulator import simulator_manager
    sim = simulator_manager
    ok = await sim.load_csv_replay(csv_path)
    frame_count = len(getattr(sim, "_replay_frames", []))
    return {"loaded": ok, "frame_count": frame_count, "csv_path": csv_path}


@router.post("/replay/start")
async def start_replay(
    request: Request,
    speed: float = 1.0,
    user: Dict = Depends(require_role("administrator", "maintenance_engineer")),
):
    """Start CSV replay at given speed multiplier (0.5, 1.0, 2.0, 4.0)."""
    from services.simulator import simulator_manager
    sim = simulator_manager
    await sim.start_csv_replay(speed_multiplier=speed)
    return {
        "status": "PLAYING",
        "speed": speed,
        "frames": len(getattr(sim, "_replay_frames", [])),
    }
