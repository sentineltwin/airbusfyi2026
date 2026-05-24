"""SentinelTwin — Aircraft Routes"""
from datetime import datetime, timezone
from typing import Dict
from fastapi import APIRouter, Depends, HTTPException, Request
from api.routes._auth_utils import get_current_user

router = APIRouter()

AIRCRAFT_PROFILES = {
    "A220": {"family": "A220", "engines": 2, "engine_type": "PW1500G", "max_pax": 160, "range_nm": 3350, "ceiling_ft": 41000},
    "A319": {"family": "A320", "engines": 2, "engine_type": "CFM56-5B/IAE V2500", "max_pax": 156, "range_nm": 3700, "ceiling_ft": 39800},
    "A320": {"family": "A320", "engines": 2, "engine_type": "CFM56-5B", "max_pax": 180, "range_nm": 3300, "ceiling_ft": 39800},
    "A320neo": {"family": "A320neo", "engines": 2, "engine_type": "PW1100G/LEAP-1A", "max_pax": 194, "range_nm": 3500, "ceiling_ft": 39800},
    "A321": {"family": "A320", "engines": 2, "engine_type": "CFM56-5B/IAE V2500", "max_pax": 236, "range_nm": 3200, "ceiling_ft": 39800},
    "A330": {"family": "A330", "engines": 2, "engine_type": "Trent 700/PW4000/CF6", "max_pax": 440, "range_nm": 7400, "ceiling_ft": 41450},
    "A350": {"family": "A350", "engines": 2, "engine_type": "Trent XWB", "max_pax": 440, "range_nm": 8100, "ceiling_ft": 43100},
}

@router.get("/types")
async def get_aircraft_types(user: Dict = Depends(get_current_user)):
    return {"aircraft_types": list(AIRCRAFT_PROFILES.keys()), "profiles": AIRCRAFT_PROFILES,
            "timestamp": datetime.now(timezone.utc).isoformat()}

@router.get("/types/{aircraft_type}")
async def get_aircraft_profile(aircraft_type: str, user: Dict = Depends(get_current_user)):
    profile = AIRCRAFT_PROFILES.get(aircraft_type)
    if not profile:
        raise HTTPException(status_code=404, detail=f"Aircraft type {aircraft_type} not found")
    return {"aircraft_type": aircraft_type, **profile}

@router.get("/current")
async def get_current_aircraft(request: Request, user: Dict = Depends(get_current_user)):
    twin_engine = getattr(request.app.state, "twin_engine", None)
    if twin_engine:
        return twin_engine.get_state()
    return {"aircraft_type": "A320neo", "msn": "8234", "registration": "F-WXWB"}
