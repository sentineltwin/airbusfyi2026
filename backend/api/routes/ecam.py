"""SentinelTwin — ECAM Routes"""
from datetime import datetime, timezone
from typing import Dict
from fastapi import APIRouter, Depends, HTTPException, Request
from api.routes._auth_utils import get_current_user
from dataclasses import asdict

router = APIRouter()

@router.get("/active")
async def get_active_ecam(request: Request, user: Dict = Depends(get_current_user)):
    engine = getattr(request.app.state, "ecam_engine", None)
    if not engine:
        raise HTTPException(status_code=503, detail="ECAM_ENGINE_NOT_READY")
    return {"active": engine.get_active(), "stats": engine.get_stats(),
            "timestamp": datetime.now(timezone.utc).isoformat()}

@router.get("/history")
async def get_ecam_history(request: Request, limit: int = 100,
                           user: Dict = Depends(get_current_user)):
    engine = getattr(request.app.state, "ecam_engine", None)
    if not engine:
        raise HTTPException(status_code=503, detail="ECAM_ENGINE_NOT_READY")
    history = list(engine._history)[-limit:][::-1]
    return {
        "count": len(history),
        "advisories": [
            {"message_id": m.message_id, "severity": m.severity, "system": m.system,
             "ata_chapter": m.ata_chapter, "message": m.message,
             "dispatch_impact": m.dispatch_impact, "mel_reference": m.mel_reference,
             "generated_at": m.generated_at, "is_active": m.is_active, "cleared_at": m.cleared_at}
            for m in history
        ],
    }
