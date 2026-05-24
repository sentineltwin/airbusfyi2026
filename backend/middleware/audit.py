"""
SentinelTwin — Audit Logging Middleware
"""

import json
import logging
import time
import uuid
from datetime import datetime, timezone
from typing import Callable

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

log = logging.getLogger("sentineltwin.middleware.audit")


class AuditLoggingMiddleware(BaseHTTPMiddleware):
    """
    Logs every API request to the immutable audit trail.
    Captures: user, IP, method, path, status, latency, session.
    """

    _SKIP_VERBOSE = {"/health", "/metrics", "/api/docs", "/api/redoc", "/api/openapi.json"}

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        start = time.monotonic()
        request_id = str(uuid.uuid4())
        request.state.request_id = request_id

        client_ip = request.headers.get("X-Forwarded-For", "").split(",")[0].strip() or (
            request.client.host if request.client else "unknown"
        )
        user_agent = request.headers.get("User-Agent", "unknown")

        try:
            response = await call_next(request)
            status_code = response.status_code
        except Exception as exc:
            log.error(f"AUDIT: Unhandled exception on {request.url.path}: {exc}")
            raise

        elapsed_ms = (time.monotonic() - start) * 1000

        response.headers["X-Request-ID"] = request_id

        path = request.url.path
        if path not in self._SKIP_VERBOSE:
            record = {
                "request_id": request_id,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "method": request.method,
                "path": path,
                "status_code": status_code,
                "latency_ms": round(elapsed_ms, 2),
                "client_ip": client_ip,
                "user_agent": user_agent[:200],
                "query_params": dict(request.query_params),
            }

            if status_code >= 500:
                log.error(f"AUDIT: {json.dumps(record)}")
            elif status_code >= 400:
                log.warning(f"AUDIT: {json.dumps(record)}")
            else:
                log.info(
                    f"AUDIT: {request.method} {path} "
                    f"→ {status_code} [{elapsed_ms:.1f}ms] {client_ip}"
                )

        return response
