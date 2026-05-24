"""SentinelTwin — Maintenance Actions — Full CRUD lifecycle"""
import uuid
from datetime import datetime, timezone
from typing import Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from api.routes._auth_utils import get_current_user, require_role

router = APIRouter()

# In-memory store (replace with DB query via persistence_service in production)
_actions: Dict[str, dict] = {}


class CreateActionRequest(BaseModel):
    title:           str
    ata_chapter:     int = 27
    system:          str = ""
    priority:        str = "ROUTINE"   # "IMMEDIATE" | "URGENT" | "ROUTINE" | "DEFERRED"
    description:     str = ""
    sensor_id:       Optional[str] = None
    ecam_message_id: Optional[str] = None
    mel_reference:   Optional[str] = None
    estimated_hours: Optional[float] = None


class UpdateActionRequest(BaseModel):
    status:         Optional[str] = None  # "OPEN"|"IN_PROGRESS"|"COMPLETED"|"DEFERRED"|"CANCELLED"
    assigned_to:    Optional[str] = None
    notes:          Optional[str] = None
    completed_at:   Optional[str] = None


@router.get("/actions")
async def get_actions(
    status: Optional[str] = None,
    ata_chapter: Optional[int] = None,
    user: Dict = Depends(get_current_user),
):
    actions = list(_actions.values())
    if status:
        actions = [a for a in actions if a["status"] == status]
    if ata_chapter:
        actions = [a for a in actions if a["ata_chapter"] == ata_chapter]
    return {
        "actions": sorted(actions, key=lambda a: a["created_at"], reverse=True),
        "count":   len(actions),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@router.post("/actions")
async def create_action(
    request: Request,
    body: CreateActionRequest,
    user: Dict = Depends(require_role(
        "administrator", "maintenance_engineer", "qa_inspector"
    )),
):
    action_id = f"MX-{str(uuid.uuid4())[:8].upper()}"
    now       = datetime.now(timezone.utc).isoformat()
    action    = {
        "action_id":       action_id,
        "id":              action_id,
        "title":           body.title,
        "ata_chapter":     body.ata_chapter,
        "ata":             body.ata_chapter,
        "system":          body.system,
        "priority":        body.priority,
        "description":     body.description,
        "sensor_id":       body.sensor_id,
        "ecam_message_id": body.ecam_message_id,
        "mel_reference":   body.mel_reference,
        "mel":             body.mel_reference or "",
        "estimated_hours": body.estimated_hours,
        "status":          "OPEN",
        "assigned_to":     None,
        "assigned":        user.get("full_name", user["username"]),
        "notes":           "",
        "created_by":      user["username"],
        "created_at":      now,
        "updated_at":      now,
        "completed_at":    None,
        "due":             "",
    }
    _actions[action_id] = action
    # Also persist to DB via persistence_service if available
    persistence = getattr(request.app.state, "persistence_service", None)
    if persistence:
        try:
            persistence.put_nowait_safe("maintenance", action)
        except Exception:
            pass  # Non-blocking
    return action


@router.patch("/actions/{action_id}")
async def update_action(
    action_id: str,
    body: UpdateActionRequest,
    user: Dict = Depends(require_role(
        "administrator", "maintenance_engineer", "qa_inspector", "dispatcher"
    )),
):
    if action_id not in _actions:
        raise HTTPException(404, f"Action {action_id} not found")
    action = _actions[action_id]
    if body.status:
        action["status"] = body.status
    if body.assigned_to:
        action["assigned_to"] = body.assigned_to
        action["assigned"] = body.assigned_to
    if body.notes is not None:
        action["notes"] = body.notes
    if body.status == "COMPLETED":
        action["completed_at"] = body.completed_at or datetime.now(timezone.utc).isoformat()
    action["updated_at"] = datetime.now(timezone.utc).isoformat()
    return action


@router.delete("/actions/{action_id}")
async def delete_action(
    action_id: str,
    user: Dict = Depends(require_role("administrator")),
):
    if action_id not in _actions:
        raise HTTPException(404, f"Action {action_id} not found")
    deleted = _actions.pop(action_id)
    return {"deleted": True, "action_id": action_id, "title": deleted["title"]}


@router.get("/summary")
async def maintenance_summary(user: Dict = Depends(get_current_user)):
    actions = list(_actions.values())
    return {
        "total":       len(actions),
        "open":        sum(1 for a in actions if a["status"] == "OPEN"),
        "in_progress": sum(1 for a in actions if a["status"] == "IN_PROGRESS"),
        "completed":   sum(1 for a in actions if a["status"] == "COMPLETED"),
        "immediate":   sum(1 for a in actions if a["priority"] == "IMMEDIATE"),
        "timestamp":   datetime.now(timezone.utc).isoformat(),
    }


@router.get("/schedule")
async def maintenance_schedule(user: Dict = Depends(get_current_user)):
    return {"schedule": [
        {"task": "A-CHECK", "due": "2026-06-15", "interval": "600 FH", "status": "SCHEDULED"},
        {"task": "C-CHECK", "due": "2027-03-20", "interval": "7500 FH", "status": "PLANNED"},
        {"task": "ENGINE BORESCOPE", "due": "2026-07-01", "interval": "1000 CYC", "status": "SCHEDULED"},
    ], "timestamp": datetime.now(timezone.utc).isoformat()}
