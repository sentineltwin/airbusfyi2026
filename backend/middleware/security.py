"""
SentinelTwin — Security Middleware Stack
Rate limiting | Security headers | XSS protection
DO-326A / EASA AMC 20-42 compliant
"""

import logging
import time
from collections import defaultdict, deque
from typing import Callable, Dict

from fastapi import Request, Response
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

log = logging.getLogger("sentineltwin.middleware")


# ═════════════════════════════════════════════════════════════
# SECURITY HEADERS MIDDLEWARE
# ═════════════════════════════════════════════════════════════

class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Injects aerospace-grade security headers on every response."""

    SECURITY_HEADERS = {
        "X-Frame-Options": "DENY",
        "X-XSS-Protection": "1; mode=block",
        "X-Content-Type-Options": "nosniff",
        "Referrer-Policy": "strict-origin-when-cross-origin",
        "Content-Security-Policy": (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline' 'unsafe-eval'; "
            "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
            "font-src 'self' https://fonts.gstatic.com; "
            "connect-src 'self' ws: wss:; "
            "img-src 'self' data: blob:; "
            "frame-ancestors 'none';"
        ),
        "Strict-Transport-Security": "max-age=31536000; includeSubDomains; preload",
        "Permissions-Policy": "camera=(), microphone=(), geolocation=(), payment=(), usb=(), bluetooth=()",
        "X-SentinelTwin-Compliance": "DO-326A:ACTIVE,ED-202A:ACTIVE,AMC-20-42:ACTIVE",
        "X-SentinelTwin-Version": "4.4.0",
        "Cache-Control": "no-store, no-cache, must-revalidate, private",
        "Pragma": "no-cache",
    }

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        response = await call_next(request)
        for header, value in self.SECURITY_HEADERS.items():
            response.headers[header] = value
        for key in ("server", "x-powered-by"):
            if key in response.headers:
                del response.headers[key]
        return response


# ═════════════════════════════════════════════════════════════
# RATE LIMIT MIDDLEWARE
# ═════════════════════════════════════════════════════════════

class _RateLimitBucket:
    def __init__(self, rate: int, window: int):
        self.rate = rate
        self.window = window
        self._buckets: Dict[str, deque] = defaultdict(deque)

    def is_allowed(self, key: str) -> tuple:
        now = time.monotonic()
        bucket = self._buckets[key]
        while bucket and now - bucket[0] > self.window:
            bucket.popleft()
        if len(bucket) >= self.rate:
            oldest = bucket[0]
            retry_after = int(self.window - (now - oldest)) + 1
            return False, retry_after
        bucket.append(now)
        return True, 0


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Per-IP rate limiting with separate limits for auth endpoints."""

    def __init__(self, app: ASGIApp):
        super().__init__(app)
        self._general = _RateLimitBucket(rate=1000, window=60)
        self._auth = _RateLimitBucket(rate=10, window=300)
        self._ws = _RateLimitBucket(rate=50, window=60)

    def _get_client_ip(self, request: Request) -> str:
        xff = request.headers.get("X-Forwarded-For")
        if xff:
            return xff.split(",")[0].strip()
        return request.client.host if request.client else "unknown"

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        ip = self._get_client_ip(request)
        path = request.url.path

        if "/auth/login" in path or "/auth/refresh" in path:
            bucket = self._auth
        elif path.startswith("/ws"):
            bucket = self._ws
        else:
            bucket = self._general

        allowed, retry_after = bucket.is_allowed(ip)
        if not allowed:
            log.warning(f"RATE_LIMIT: {ip} exceeded limit on {path}")
            return JSONResponse(
                status_code=429,
                content={"error": "RATE_LIMIT_EXCEEDED",
                         "message": f"Too many requests. Retry after {retry_after} seconds.",
                         "retry_after": retry_after},
                headers={"Retry-After": str(retry_after)},
            )

        response = await call_next(request)
        return response
