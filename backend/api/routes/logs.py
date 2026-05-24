"""SentinelTwin — Operational Logs Route"""
import logging
from collections import deque
from datetime import datetime, timezone
from typing import Dict, List, Optional
from fastapi import APIRouter, Depends, Request
from api.routes._auth_utils import get_current_user

router = APIRouter()

# Shared in-memory log buffer — populated by the logging handler below
_log_buffer: deque = deque(maxlen=2000)


class SentinelLogHandler(logging.Handler):
    """Captures structured log records into the in-memory buffer."""
    def emit(self, record: logging.LogRecord) -> None:
        try:
            _log_buffer.append({
                "id":        f"log-{record.created:.6f}",
                "timestamp": datetime.fromtimestamp(
                    record.created, tz=timezone.utc
                ).isoformat(),
                "level":     record.levelname,
                "source":    record.name,
                "message":   self.format(record),
            })
        except Exception:
            pass


def install_log_handler() -> None:
    """Call once from main.py startup to wire the buffer handler."""
    handler = SentinelLogHandler()
    handler.setFormatter(logging.Formatter("%(message)s"))
    handler.setLevel(logging.DEBUG)
    root = logging.getLogger("sentineltwin")
    if not any(isinstance(h, SentinelLogHandler) for h in root.handlers):
        root.addHandler(handler)


@router.get("/operational")
async def get_operational_logs(
    limit: int = 500,
    offset: int = 0,
    level: Optional[str] = None,
    source: Optional[str] = None,
    user: Dict = Depends(get_current_user),
):
    """
    Return the last `limit` operational log entries.
    Optionally filter by level (INFO/WARNING/ERROR/CRITICAL) or source prefix.
    """
    logs = list(_log_buffer)
    logs.reverse()  # Newest first
    
    if level and level != "ALL":
        logs = [l for l in logs if l["level"] == level]
    if source:
        logs = [l for l in logs if source.lower() in l["source"].lower()]
        
    logs = logs[offset : offset + limit]
    
    return {
        "logs":      logs,
        "count":     len(logs),
        "total_buffered": len(_log_buffer),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
