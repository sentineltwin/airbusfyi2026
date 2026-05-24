"""SentinelTwin — Fleet Routes"""
from datetime import datetime, timezone
from typing import Dict
from fastapi import APIRouter, Depends, HTTPException
from api.routes._auth_utils import get_current_user

router = APIRouter()

FLEET_DATA = [
    {"msn": "8234", "reg": "F-WXWB", "type": "A320neo", "airline": "Air France",
     "cycles": 4821, "hours": 12450.3, "status": "ACTIVE", "location": "CDG"},
    {"msn": "9012", "reg": "D-AVVB", "type": "A321", "airline": "Lufthansa",
     "cycles": 3201, "hours": 8920.1, "status": "ACTIVE", "location": "FRA"},
    {"msn": "7891", "reg": "G-EZWX", "type": "A320", "airline": "easyJet",
     "cycles": 6432, "hours": 15230.7, "status": "MAINTENANCE", "location": "LTN"},
    {"msn": "6543", "reg": "EC-MXY", "type": "A350", "airline": "Iberia",
     "cycles": 1823, "hours": 5840.2, "status": "ACTIVE", "location": "MAD"},
    {"msn": "5210", "reg": "OE-IVM", "type": "A320neo", "airline": "Austrian",
     "cycles": 2904, "hours": 7612.9, "status": "ACTIVE", "location": "VIE"},
    {"msn": "4480", "reg": "HB-JCA", "type": "A330", "airline": "Swiss",
     "cycles": 5102, "hours": 28430.1, "status": "ACTIVE", "location": "ZRH"},
]

@router.get("/")
async def get_fleet(user: Dict = Depends(get_current_user)):
    return {"total_aircraft": len(FLEET_DATA),
            "active": sum(1 for a in FLEET_DATA if a["status"] == "ACTIVE"),
            "maintenance": sum(1 for a in FLEET_DATA if a["status"] == "MAINTENANCE"),
            "fleet": FLEET_DATA, "timestamp": datetime.now(timezone.utc).isoformat()}

@router.get("/{msn}")
async def get_aircraft(msn: str, user: Dict = Depends(get_current_user)):
    aircraft = next((a for a in FLEET_DATA if a["msn"] == msn), None)
    if not aircraft:
        raise HTTPException(status_code=404, detail=f"Aircraft MSN {msn} not found")
    return aircraft
