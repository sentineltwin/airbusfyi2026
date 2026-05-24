"""SentinelTwin — Hash Chain Routes"""
from datetime import datetime, timezone
from typing import Dict
from fastapi import APIRouter, Depends, HTTPException, Request
from api.routes._auth_utils import get_current_user, require_role

router = APIRouter()

@router.get("/latest")
async def get_latest_blocks(request: Request, n: int = 50, user: Dict = Depends(get_current_user)):
    service = getattr(request.app.state, "hash_service", None)
    if not service:
        raise HTTPException(status_code=503, detail="HASH_SERVICE_NOT_READY")
    return {"blocks": service.get_latest_blocks(n), "stats": service.get_stats(),
            "timestamp": datetime.now(timezone.utc).isoformat()}

@router.get("/verify")
async def verify_chain(request: Request,
                       user: Dict = Depends(require_role("qa_inspector", "administrator", "maintenance_engineer"))):
    service = getattr(request.app.state, "hash_service", None)
    if not service:
        raise HTTPException(status_code=503, detail="HASH_SERVICE_NOT_READY")
    ok, tampered_at = service.verify_chain()
    return {"chain_valid": ok, "tampered_at_sequence": tampered_at,
            "total_blocks": len(service._chain), "algorithm": "SHA-256",
            "compliance": "DO-326A",
            "verification_timestamp": datetime.now(timezone.utc).isoformat(),
            "verified_by": user["username"]}
