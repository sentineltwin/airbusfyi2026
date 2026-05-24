"""SentinelTwin — ARINC 429 API Routes"""
from datetime import datetime, timezone
from typing import Dict
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from api.routes._auth_utils import get_current_user, require_role

router = APIRouter()


class FaultInjectRequest(BaseModel):
    label_octal: int
    fault_type: str  # "FREEZE" | "NOISE" | "SSM_FAIL" | "PARITY_ERR"


@router.get("/frame")
async def get_bus_frame(
    request: Request,
    user: Dict = Depends(get_current_user),
):
    """Get current bus frame — all labels decoded."""
    arinc = getattr(request.app.state, "arinc_service", None)
    if not arinc:
        raise HTTPException(503, "ARINC 429 service not available")
    frame = arinc.generate_bus_frame()
    return {
        "frame": frame,
        "label_count": len(frame),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@router.get("/stats")
async def get_bus_stats(
    request: Request,
    user: Dict = Depends(get_current_user),
):
    """Get ARINC 429 bus statistics."""
    arinc = getattr(request.app.state, "arinc_service", None)
    if not arinc:
        raise HTTPException(503, "ARINC 429 service not available")
    return arinc.get_bus_stats()


@router.post("/inject")
async def inject_fault(
    request: Request,
    body: FaultInjectRequest,
    user: Dict = Depends(require_role("administrator", "maintenance_engineer")),
):
    """Inject a fault on a specific ARINC 429 label."""
    arinc = getattr(request.app.state, "arinc_service", None)
    if not arinc:
        raise HTTPException(503, "ARINC 429 service not available")
    result = arinc.inject_fault(body.label_octal, body.fault_type)
    if "error" in result:
        raise HTTPException(400, result["error"])
    return result


@router.post("/clear")
async def clear_fault(
    request: Request,
    label_octal: int,
    user: Dict = Depends(require_role("administrator", "maintenance_engineer")),
):
    """Clear a previously injected fault."""
    arinc = getattr(request.app.state, "arinc_service", None)
    if not arinc:
        raise HTTPException(503, "ARINC 429 service not available")
    return arinc.clear_fault(label_octal)


@router.get("/labels")
async def get_label_table(
    request: Request,
    user: Dict = Depends(get_current_user),
):
    """Get the full ARINC 429 label table definition."""
    arinc = getattr(request.app.state, "arinc_service", None)
    if not arinc:
        raise HTTPException(503, "ARINC 429 service not available")
    return {
        "labels": [
            {
                "label_octal": f"{label:03o}",
                "label_decimal": label,
                "name": info[0],
                "unit": info[1],
                "min_value": info[2],
                "max_value": info[3],
            }
            for label, info in arinc.LABEL_TABLE.items()
        ],
        "count": len(arinc.LABEL_TABLE),
    }
