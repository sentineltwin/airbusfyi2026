"""SentinelTwin — AFDX API Routes"""
from datetime import datetime, timezone
from typing import Dict
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from api.routes._auth_utils import get_current_user, require_role

router = APIRouter()


class TimingFaultRequest(BaseModel):
    vl_id: str
    fault_type: str  # "LATE" | "EARLY" | "DUPLICATE" | "MISSING"


@router.get("/vls")
async def get_virtual_links(
    request: Request,
    user: Dict = Depends(get_current_user),
):
    """Get all virtual links with current jitter/status."""
    afdx = getattr(request.app.state, "afdx_service", None)
    if not afdx:
        raise HTTPException(503, "AFDX service not available")
    vls = afdx.get_all_vl_status()
    return {
        "virtual_links": vls,
        "count": len(vls),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@router.get("/stats")
async def get_network_stats(
    request: Request,
    user: Dict = Depends(get_current_user),
):
    """Get AFDX network utilization summary."""
    afdx = getattr(request.app.state, "afdx_service", None)
    if not afdx:
        raise HTTPException(503, "AFDX service not available")
    return afdx.get_network_stats()


@router.post("/inject")
async def inject_timing_fault(
    request: Request,
    body: TimingFaultRequest,
    user: Dict = Depends(require_role("administrator", "maintenance_engineer")),
):
    """Inject a timing fault on a virtual link."""
    afdx = getattr(request.app.state, "afdx_service", None)
    if not afdx:
        raise HTTPException(503, "AFDX service not available")
    result = afdx.inject_timing_fault(body.vl_id, body.fault_type)
    if "error" in result:
        raise HTTPException(400, result["error"])
    return result


@router.post("/clear")
async def clear_fault(
    request: Request,
    vl_id: str,
    user: Dict = Depends(require_role("administrator", "maintenance_engineer")),
):
    """Clear a previously injected timing fault."""
    afdx = getattr(request.app.state, "afdx_service", None)
    if not afdx:
        raise HTTPException(503, "AFDX service not available")
    return afdx.clear_fault(vl_id)
