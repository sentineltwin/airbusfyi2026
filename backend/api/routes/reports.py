"""SentinelTwin — Reports Routes — PDF generation"""
import io
import uuid
from datetime import datetime, timezone
from typing import Dict

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse

from api.routes._auth_utils import require_role
from services.report_service import AirworthinessReportGenerator

router = APIRouter()
_generator = AirworthinessReportGenerator()


@router.get("/generate")
async def generate_report(
    request: Request,
    user: Dict = Depends(require_role(
        "administrator", "maintenance_engineer", "qa_inspector", "dispatcher"
    )),
):
    """Generate a 6-page PDF airworthiness report and return it as a download."""
    sensor_engine = getattr(request.app.state, "sensor_engine", None)
    ai_engine     = getattr(request.app.state, "ai_engine",     None)
    ecam_engine   = getattr(request.app.state, "ecam_engine",   None)
    hash_service  = getattr(request.app.state, "hash_service",  None)
    twin_engine   = getattr(request.app.state, "twin_engine",   None)

    # Collect live data from engines
    sensor_stats = sensor_engine.get_stats()  if sensor_engine else {}
    ai_status    = ai_engine.get_status()     if ai_engine     else {}
    ecam_stats   = ecam_engine.get_stats()    if ecam_engine   else {}
    hash_stats   = hash_service.get_stats()   if hash_service  else {}
    twin_state   = twin_engine.get_state()    if twin_engine   else {}

    ecam_active = ecam_engine.get_active() if ecam_engine else []

    msn          = twin_state.get("msn", "8234")
    aircraft_type= twin_state.get("aircraft_type", "A320neo")
    registration = twin_state.get("registration", "F-WXWB")
    utc_str      = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    report_id    = str(uuid.uuid4()).upper()

    # Build the report_data dict expected by AirworthinessReportGenerator
    report_data = {
        "aircraft": {
            "type":         aircraft_type,
            "msn":          msn,
            "registration": registration,
            "operator":     twin_state.get("operator", "Airline"),
        },
        "flight": {
            "number":        twin_state.get("flight_number", "AF1234"),
            "origin":        twin_state.get("origin", "LFPG"),
            "destination":   twin_state.get("destination", "EGLL"),
            "departure_utc": twin_state.get("departure_utc", utc_str),
            "authorized_by": user["username"],
        },
        "sensor_health": sensor_stats,
        "ai_analysis": {
            "confidence":           ai_status.get("current_confidence", 0.97),
            "severity":             ai_status.get("current_severity", "NOMINAL"),
            "reconstruction_error": ai_status.get("current_reconstruction_error", 0.0),
            "model_version":        ai_status.get("model_version", "v2.4.1"),
            "top_anomalies":        ai_status.get("top_anomalies", []),
        },
        "ecam_summary": {
            "active_messages": ecam_active,
            **ecam_stats,
        },
        "dispatch": {
            "dispatch_ready": sensor_stats.get("anomaly_count", 0) < 50,
            "score":          sensor_stats.get("health_pct", 99.0),
            "blockers":       [],
        },
        "hash_chain": hash_stats,
        "generated_by": user["username"],
        "report_id":    report_id,
    }

    try:
        pdf_bytes = _generator.generate_pdf(report_data)
    except Exception as exc:
        raise HTTPException(500, f"PDF generation failed: {exc}") from exc

    filename = f"SENTINELTWIN-RPT-{msn}-{utc_str}.pdf"
    return StreamingResponse(
        io.BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/status")
async def report_status(
    request: Request,
    user: Dict = Depends(require_role(
        "administrator", "maintenance_engineer", "qa_inspector", "dispatcher"
    )),
):
    """Check report service availability."""
    return {
        "service":    "AirworthinessReportGenerator",
        "status":     "READY",
        "format":     "application/pdf",
        "pages":      6,
        "timestamp":  datetime.now(timezone.utc).isoformat(),
    }
