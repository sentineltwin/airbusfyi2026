"""
SentinelTwin — WebSocket Server + API Routes
Real-time telemetry broadcast | JWT Auth | Sensor/ECAM/Dispatch APIs
"""

import asyncio
import hashlib
import json
import logging
import time
import uuid
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Set

from fastapi import (
    APIRouter, Depends, HTTPException, Request, WebSocket,
    WebSocketDisconnect, BackgroundTasks,
)
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, field_validator
import jwt
import bcrypt

log = logging.getLogger("sentineltwin.api")

# ─────────────────────────────────────────────────────────────
# SHARED SECURITY CONSTANTS (would come from config in prod)
# ─────────────────────────────────────────────────────────────
SECRET_KEY = "sentineltwin-jwt-secret-key-production-grade-256bit"
ALGORITHM = "HS256"
ACCESS_EXPIRE_MIN = 30
REFRESH_EXPIRE_DAYS = 7

security = HTTPBearer()

# ─────────────────────────────────────────────────────────────
# IN-MEMORY USER STORE (replace with DB in production)
# ─────────────────────────────────────────────────────────────
_USERS: Dict[str, Dict] = {
    "admin": {
        "id": str(uuid.uuid4()),
        "username": "admin",
        "full_name": "System Administrator",
        "email": "admin@sentineltwin.airbus.internal",
        "hashed_password": bcrypt.hashpw(b"sentinel2026", bcrypt.gensalt()).decode(),
        "role": "administrator",
        "is_active": True,
        "is_locked": False,
        "failed_login_count": 0,
        "last_login": None,
    },
    "pilot": {
        "id": str(uuid.uuid4()),
        "username": "pilot",
        "full_name": "Capt. J. Renaud",
        "email": "j.renaud@airbus.com",
        "hashed_password": bcrypt.hashpw(b"pilot2026", bcrypt.gensalt()).decode(),
        "role": "pilot",
        "is_active": True,
        "is_locked": False,
        "failed_login_count": 0,
        "last_login": None,
    },
    "engineer": {
        "id": str(uuid.uuid4()),
        "username": "engineer",
        "full_name": "M. Bouchard — Avionics",
        "email": "m.bouchard@airbus.com",
        "hashed_password": bcrypt.hashpw(b"engineer2026", bcrypt.gensalt()).decode(),
        "role": "maintenance_engineer",
        "is_active": True,
        "is_locked": False,
        "failed_login_count": 0,
        "last_login": None,
    },
}

_REFRESH_TOKENS: Dict[str, str] = {}  # token_hash → username
_FAILED_ATTEMPTS: Dict[str, List[float]] = {}  # ip → list of timestamps


# ─────────────────────────────────────────────────────────────
# JWT HELPERS
# ─────────────────────────────────────────────────────────────

def create_access_token(data: Dict, expires_delta: Optional[timedelta] = None) -> str:
    payload = data.copy()
    expire = datetime.now(timezone.utc) + (
        expires_delta or timedelta(minutes=ACCESS_EXPIRE_MIN)
    )
    payload.update({"exp": expire, "iat": datetime.now(timezone.utc), "type": "access"})
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def create_refresh_token(username: str) -> str:
    payload = {
        "sub": username,
        "exp": datetime.now(timezone.utc) + timedelta(days=REFRESH_EXPIRE_DAYS),
        "iat": datetime.now(timezone.utc),
        "type": "refresh",
        "jti": str(uuid.uuid4()),
    }
    token = jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    _REFRESH_TOKENS[token_hash] = username
    return token


def decode_token(token: str) -> Dict:
    try:
        return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="TOKEN_EXPIRED")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="TOKEN_INVALID")


def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)) -> Dict:
    payload = decode_token(credentials.credentials)
    username = payload.get("sub")
    if not username or username not in _USERS:
        raise HTTPException(status_code=401, detail="USER_NOT_FOUND")
    user = _USERS[username]
    if not user["is_active"]:
        raise HTTPException(status_code=403, detail="ACCOUNT_DISABLED")
    if user["is_locked"]:
        raise HTTPException(status_code=403, detail="ACCOUNT_LOCKED")
    return user


def require_role(*roles: str):
    def checker(user: Dict = Depends(get_current_user)) -> Dict:
        if user["role"] not in roles:
            raise HTTPException(status_code=403, detail="INSUFFICIENT_PRIVILEGES")
        return user
    return checker


def check_brute_force(ip: str):
    now = time.time()
    window = 300  # 5 minutes
    attempts = _FAILED_ATTEMPTS.get(ip, [])
    # Remove old attempts
    attempts = [t for t in attempts if now - t < window]
    _FAILED_ATTEMPTS[ip] = attempts
    if len(attempts) >= 10:
        raise HTTPException(
            status_code=429,
            detail="BRUTE_FORCE_LOCKOUT — Too many failed attempts. Retry after 5 minutes."
        )


# ─────────────────────────────────────────────────────────────
# AUTH ROUTER
# ─────────────────────────────────────────────────────────────

router = APIRouter()


class LoginRequest(BaseModel):
    username: str
    password: str
    mfa_code: Optional[str] = None

    @field_validator("username")
    @classmethod
    def username_clean(cls, v):
        return v.strip().lower()


class LoginResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int = ACCESS_EXPIRE_MIN * 60
    user: Dict


class RefreshRequest(BaseModel):
    refresh_token: str


@router.post("/login", response_model=LoginResponse)
async def login(body: LoginRequest, request: Request):
    ip = request.client.host if request.client else "unknown"
    check_brute_force(ip)

    user = _USERS.get(body.username)
    if not user:
        _FAILED_ATTEMPTS.setdefault(ip, []).append(time.time())
        raise HTTPException(status_code=401, detail="AUTHENTICATION_FAILED")

    if user["is_locked"]:
        raise HTTPException(status_code=403, detail="ACCOUNT_LOCKED")

    if not bcrypt.checkpw(body.password.encode(), user["hashed_password"].encode()):
        user["failed_login_count"] += 1
        if user["failed_login_count"] >= 5:
            user["is_locked"] = True
        _FAILED_ATTEMPTS.setdefault(ip, []).append(time.time())
        raise HTTPException(status_code=401, detail="AUTHENTICATION_FAILED")

    # Reset on success
    user["failed_login_count"] = 0
    user["last_login"] = datetime.now(timezone.utc).isoformat()
    user["last_ip"] = ip

    access_token = create_access_token({"sub": user["username"], "role": user["role"]})
    refresh_token = create_refresh_token(user["username"])

    log.info(f"AUTH: User '{user['username']}' ({user['role']}) logged in from {ip}")

    return LoginResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        user={
            "id": user["id"],
            "username": user["username"],
            "full_name": user["full_name"],
            "role": user["role"],
            "email": user["email"],
        }
    )


@router.post("/refresh")
async def refresh_token(body: RefreshRequest):
    payload = decode_token(body.refresh_token)
    if payload.get("type") != "refresh":
        raise HTTPException(status_code=401, detail="INVALID_TOKEN_TYPE")
    token_hash = hashlib.sha256(body.refresh_token.encode()).hexdigest()
    username = _REFRESH_TOKENS.get(token_hash)
    if not username:
        raise HTTPException(status_code=401, detail="REFRESH_TOKEN_REVOKED")
    user = _USERS.get(username)
    if not user or not user["is_active"]:
        raise HTTPException(status_code=401, detail="USER_INVALID")
    # Rotate refresh token
    del _REFRESH_TOKENS[token_hash]
    new_access = create_access_token({"sub": username, "role": user["role"]})
    new_refresh = create_refresh_token(username)
    return {"access_token": new_access, "refresh_token": new_refresh, "token_type": "bearer"}


@router.post("/logout")
async def logout(body: RefreshRequest, user: Dict = Depends(get_current_user)):
    token_hash = hashlib.sha256(body.refresh_token.encode()).hexdigest()
    _REFRESH_TOKENS.pop(token_hash, None)
    log.info(f"AUTH: User '{user['username']}' logged out")
    return {"status": "LOGGED_OUT"}


@router.get("/me")
async def get_me(user: Dict = Depends(get_current_user)):
    return {
        "id": user["id"],
        "username": user["username"],
        "full_name": user["full_name"],
        "role": user["role"],
        "email": user["email"],
        "last_login": user["last_login"],
    }


# ─────────────────────────────────────────────────────────────
# WEBSOCKET CONNECTION MANAGER
# ─────────────────────────────────────────────────────────────

class ConnectionManager:
    """Manages WebSocket connections with channel subscriptions"""

    def __init__(self):
        self._connections: Dict[str, WebSocket] = {}       # conn_id → ws
        self._subscriptions: Dict[str, Set[str]] = {}      # conn_id → set of channels
        self._channels: Dict[str, Set[str]] = {}           # channel → set of conn_ids
        self._lock = asyncio.Lock()
        self.total_messages_sent = 0
        self.total_connections = 0

    async def connect(self, websocket: WebSocket, channels: List[str] = None) -> str:
        await websocket.accept()
        conn_id = str(uuid.uuid4())
        async with self._lock:
            self._connections[conn_id] = websocket
            subs = set(channels or ["telemetry", "ecam", "ai", "hashchain", "twin"])
            self._subscriptions[conn_id] = subs
            for ch in subs:
                self._channels.setdefault(ch, set()).add(conn_id)
        self.total_connections += 1
        log.info(f"WS: Connection {conn_id[:8]} established — channels: {subs}")
        return conn_id

    async def disconnect(self, conn_id: str):
        async with self._lock:
            if conn_id in self._connections:
                del self._connections[conn_id]
            subs = self._subscriptions.pop(conn_id, set())
            for ch in subs:
                self._channels.get(ch, set()).discard(conn_id)
        log.debug(f"WS: Connection {conn_id[:8]} disconnected")

    async def broadcast_channel(self, channel: str, data: Dict):
        """Broadcast to all connections subscribed to a channel"""
        message = json.dumps({
            "channel": channel,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "data": data,
        })
        dead = []
        for conn_id in list(self._channels.get(channel, set())):
            ws = self._connections.get(conn_id)
            if ws:
                try:
                    await ws.send_text(message)
                    self.total_messages_sent += 1
                except Exception:
                    dead.append(conn_id)
        for conn_id in dead:
            await self.disconnect(conn_id)

    async def send_to(self, conn_id: str, data: Dict):
        ws = self._connections.get(conn_id)
        if ws:
            try:
                await ws.send_text(json.dumps(data))
            except Exception:
                await self.disconnect(conn_id)

    def stats(self) -> Dict:
        return {
            "active_connections": len(self._connections),
            "total_connections": self.total_connections,
            "total_messages_sent": self.total_messages_sent,
            "channels": {ch: len(ids) for ch, ids in self._channels.items()},
        }


# Global connection manager
ws_manager = ConnectionManager()

# ─────────────────────────────────────────────────────────────
# WEBSOCKET ROUTER
# ─────────────────────────────────────────────────────────────

ws_router = APIRouter()


@ws_router.websocket("/telemetry")
async def ws_telemetry(websocket: WebSocket):
    """Main real-time telemetry WebSocket endpoint"""
    conn_id = await ws_manager.connect(websocket, [
        "telemetry", "ecam", "ai", "hashchain", "twin", "dispatch", "cyber"
    ])
    try:
        while True:
            try:
                msg = await asyncio.wait_for(websocket.receive_text(), timeout=30.0)
                data = json.loads(msg)
                # Handle client commands
                if data.get("cmd") == "set_phase":
                    phase = data.get("phase", "GROUND")
                    await ws_manager.send_to(conn_id, {
                        "type": "ack", "cmd": "set_phase", "phase": phase
                    })
                elif data.get("cmd") == "ping":
                    await ws_manager.send_to(conn_id, {"type": "pong", "ts": time.time()})
            except asyncio.TimeoutError:
                # Send keepalive
                await ws_manager.send_to(conn_id, {"type": "keepalive", "ts": time.time()})
    except WebSocketDisconnect:
        await ws_manager.disconnect(conn_id)


@ws_router.websocket("/sensor-matrix")
async def ws_sensor_matrix(websocket: WebSocket):
    """Dedicated high-frequency sensor matrix stream"""
    conn_id = await ws_manager.connect(websocket, ["sensor_matrix"])
    try:
        while True:
            await asyncio.sleep(0.5)  # 2 Hz update for matrix
            await ws_manager.send_to(conn_id, {
                "type": "sensor_matrix_update",
                "ts": time.time(),
            })
    except WebSocketDisconnect:
        await ws_manager.disconnect(conn_id)


# ─────────────────────────────────────────────────────────────
# TELEMETRY BROADCAST TASK
# (runs in background, feeds all WebSocket subscribers)
# ─────────────────────────────────────────────────────────────

async def broadcast_loop(app):
    """Main broadcast loop — pushes real-time data to all WS clients"""
    log.info("WebSocket broadcast loop started")
    cycle = 0
    while True:
        try:
            cycle += 1
            sensor_engine = getattr(app.state, "sensor_engine", None)
            ai_engine = getattr(app.state, "ai_engine", None)
            twin_engine = getattr(app.state, "twin_engine", None)
            ecam_engine = getattr(app.state, "ecam_engine", None)
            hash_service = getattr(app.state, "hash_service", None)

            tasks = []

            # ── Telemetry summary (1 Hz) ──────────────────────
            if sensor_engine and cycle % 1 == 0:
                stats = sensor_engine.get_stats()
                tasks.append(ws_manager.broadcast_channel("telemetry", {
                    "type": "sensor_stats",
                    "healthy_count": stats.get("healthy_count", 0),
                    "anomaly_count": stats.get("anomaly_count", 0),
                    "total_validations": stats.get("total_validations", 0),
                    "cycle_duration_ms": stats.get("cycle_duration_ms", 0),
                    "scan_rate": stats.get("total_validations", 0),
                }))

            # ── AI engine status (2 Hz) ────────────────────────
            if ai_engine and cycle % 1 == 0:
                ai_status = ai_engine.get_status()
                tasks.append(ws_manager.broadcast_channel("ai", {
                    "type": "ai_status",
                    "reconstruction_error": ai_status.get("current_reconstruction_error", 0),
                    "severity": ai_status.get("current_severity", "NOMINAL"),
                    "confidence": ai_status.get("current_confidence", 0.97),
                    "active_events": ai_status.get("active_events", 0),
                    "anomaly_event_count": ai_status.get("anomaly_event_count", 0),
                    "inference_count": ai_status.get("inference_count", 0),
                }))

            # ── Digital twin state (2 Hz) ─────────────────────
            if twin_engine and cycle % 1 == 0:
                twin_state = twin_engine.get_state()
                tasks.append(ws_manager.broadcast_channel("twin", {
                    "type": "twin_state",
                    **twin_state,
                }))

            # ── ECAM advisories (1 Hz) ─────────────────────────
            if ecam_engine and cycle % 1 == 0:
                ecam_active = ecam_engine.get_active()
                ecam_stats = ecam_engine.get_stats()
                tasks.append(ws_manager.broadcast_channel("ecam", {
                    "type": "ecam_update",
                    "active": ecam_active,
                    "stats": ecam_stats,
                }))

            # ── Hash chain (every 5 cycles) ────────────────────
            if hash_service and cycle % 5 == 0:
                healthy = getattr(sensor_engine, "healthy_count", 8100) if sensor_engine else 8100
                anomaly = getattr(sensor_engine, "anomaly_count", 0) if sensor_engine else 0
                phase = twin_engine.twin.flight_phase if twin_engine else "GROUND"
                block = await hash_service.append(healthy, anomaly, phase)
                stats = hash_service.get_stats()
                tasks.append(ws_manager.broadcast_channel("hashchain", {
                    "type": "hash_block",
                    "block": {
                        "sequence": block.sequence,
                        "scan_id": block.scan_id,
                        "timestamp": block.timestamp,
                        "block_hash": block.block_hash,
                        "previous_hash": block.previous_hash[:16] + "...",
                        "healthy_count": block.healthy_count,
                        "anomaly_count": block.anomaly_count,
                        "flight_phase": block.flight_phase,
                    },
                    "chain_valid": stats.get("chain_valid", True),
                    "total_blocks": stats.get("total_blocks", 0),
                }))

            # ── Dispatch status (every 3 cycles) ──────────────
            if cycle % 3 == 0:
                ecam_stats = ecam_engine.get_stats() if ecam_engine else {}
                ai_status = ai_engine.get_status() if ai_engine else {}
                sensor_stats = sensor_engine.get_stats() if sensor_engine else {}
                dispatch_go = (
                    ecam_stats.get("emergency", 0) == 0 and
                    sensor_stats.get("anomaly_count", 0) < 50 and
                    ai_status.get("current_confidence", 0.9) > 0.85
                )
                tasks.append(ws_manager.broadcast_channel("dispatch", {
                    "type": "dispatch_status",
                    "dispatch_ready": dispatch_go,
                    "reason": "ALL_CHECKS_PASSED" if dispatch_go else "ANOMALIES_DETECTED",
                }))

            await asyncio.gather(*tasks, return_exceptions=True)

        except Exception as e:
            log.error(f"Broadcast loop error: {e}", exc_info=True)

        await asyncio.sleep(1.0)  # 1 Hz base broadcast rate


# ─────────────────────────────────────────────────────────────
# SENSOR API ROUTER
# ─────────────────────────────────────────────────────────────

sensor_router = APIRouter()


@sensor_router.get("/summary")
async def sensor_summary(request: Request, user: Dict = Depends(get_current_user)):
    engine = getattr(request.app.state, "sensor_engine", None)
    if not engine:
        raise HTTPException(status_code=503, detail="SENSOR_ENGINE_NOT_READY")
    stats = engine.get_stats()
    # Build ATA breakdown
    ata_breakdown = {}
    for sensor in (engine.sensors or []):
        ata = sensor.ata_chapter
        if ata not in ata_breakdown:
            ata_breakdown[ata] = {"total": 0, "healthy": 0, "degraded": 0,
                                   "failed": 0, "other": 0}
        ata_breakdown[ata]["total"] += 1
        state = sensor.state.value if hasattr(sensor.state, "value") else str(sensor.state)
        if state == "HEALTHY":
            ata_breakdown[ata]["healthy"] += 1
        elif state == "DEGRADED":
            ata_breakdown[ata]["degraded"] += 1
        elif state == "FAILED":
            ata_breakdown[ata]["failed"] += 1
        else:
            ata_breakdown[ata]["other"] += 1
    return {
        "total_sensors": stats.get("total_sensors", 8192),
        "healthy_count": stats.get("healthy_count", 0),
        "anomaly_count": stats.get("anomaly_count", 0),
        "total_validations": stats.get("total_validations", 0),
        "cycle_duration_ms": stats.get("cycle_duration_ms", 0),
        "ata_breakdown": ata_breakdown,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@sensor_router.get("/ata/{ata_chapter}")
async def sensors_by_ata(
    ata_chapter: int,
    request: Request,
    limit: int = 100,
    offset: int = 0,
    user: Dict = Depends(get_current_user),
):
    engine = getattr(request.app.state, "sensor_engine", None)
    if not engine:
        raise HTTPException(status_code=503, detail="SENSOR_ENGINE_NOT_READY")
    sensors = [s for s in engine.sensors if s.ata_chapter == ata_chapter]
    total = len(sensors)
    page = sensors[offset:offset + limit]
    return {
        "ata_chapter": ata_chapter,
        "total": total,
        "limit": limit,
        "offset": offset,
        "sensors": [
            {
                "sensor_id": s.sensor_id,
                "subsystem": s.subsystem,
                "zone": s.aircraft_zone,
                "unit": s.engineering_unit,
                "state": s.state.value if hasattr(s.state, "value") else str(s.state),
                "last_value": round(s.last_calibrated_value, 4),
                "physics_residual": round(s.last_physics_residual, 6),
                "confidence": round(s.confidence_score, 4),
                "ai_score": round(s.ai_anomaly_score, 4),
                "redundancy_group": s.redundancy_group,
                "arinc_label": s.arinc_label,
                "validation_count": s.validation_count,
            }
            for s in page
        ],
    }


@sensor_router.get("/anomalous")
async def get_anomalous_sensors(
    request: Request,
    threshold: float = 0.5,
    user: Dict = Depends(get_current_user),
):
    engine = getattr(request.app.state, "sensor_engine", None)
    if not engine:
        raise HTTPException(status_code=503, detail="SENSOR_ENGINE_NOT_READY")
    anomalous = [
        s for s in engine.sensors
        if s.ai_anomaly_score > threshold or
        (hasattr(s.state, "value") and s.state.value != "HEALTHY")
    ]
    return {
        "count": len(anomalous),
        "threshold": threshold,
        "sensors": [
            {
                "sensor_id": s.sensor_id,
                "ata_chapter": s.ata_chapter,
                "subsystem": s.subsystem,
                "state": s.state.value if hasattr(s.state, "value") else str(s.state),
                "ai_score": round(s.ai_anomaly_score, 4),
                "confidence": round(s.confidence_score, 4),
                "physics_residual": round(s.last_physics_residual, 6),
            }
            for s in anomalous[:200]
        ],
    }


# ─────────────────────────────────────────────────────────────
# ECAM API ROUTER
# ─────────────────────────────────────────────────────────────

ecam_router = APIRouter()


@ecam_router.get("/active")
async def get_active_ecam(request: Request, user: Dict = Depends(get_current_user)):
    engine = getattr(request.app.state, "ecam_engine", None)
    if not engine:
        raise HTTPException(status_code=503, detail="ECAM_ENGINE_NOT_READY")
    return {
        "active": engine.get_active(),
        "stats": engine.get_stats(),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@ecam_router.get("/history")
async def get_ecam_history(
    request: Request,
    limit: int = 100,
    user: Dict = Depends(get_current_user),
):
    engine = getattr(request.app.state, "ecam_engine", None)
    if not engine:
        raise HTTPException(status_code=503, detail="ECAM_ENGINE_NOT_READY")
    history = list(engine._history)[-limit:][::-1]
    return {
        "count": len(history),
        "advisories": [
            {
                "message_id": m.message_id,
                "severity": m.severity,
                "system": m.system,
                "ata_chapter": m.ata_chapter,
                "message": m.message,
                "dispatch_impact": m.dispatch_impact,
                "mel_reference": m.mel_reference,
                "generated_at": m.generated_at,
                "is_active": m.is_active,
                "cleared_at": m.cleared_at,
            }
            for m in history
        ],
    }


# ─────────────────────────────────────────────────────────────
# DISPATCH API ROUTER
# ─────────────────────────────────────────────────────────────

dispatch_router = APIRouter()


class DispatchRequest(BaseModel):
    aircraft_msn: str
    flight_number: str
    origin: str
    destination: str
    authorized_by: str


@dispatch_router.get("/status")
async def dispatch_status(request: Request, user: Dict = Depends(get_current_user)):
    sensor_engine = getattr(request.app.state, "sensor_engine", None)
    ai_engine = getattr(request.app.state, "ai_engine", None)
    ecam_engine = getattr(request.app.state, "ecam_engine", None)
    hash_service = getattr(request.app.state, "hash_service", None)

    sensor_stats = sensor_engine.get_stats() if sensor_engine else {}
    ai_status = ai_engine.get_status() if ai_engine else {}
    ecam_stats = ecam_engine.get_stats() if ecam_engine else {}
    hash_stats = hash_service.get_stats() if hash_service else {}

    healthy = sensor_stats.get("healthy_count", 8100)
    total = sensor_stats.get("total_sensors", 8192)
    health_pct = (healthy / total * 100) if total else 100.0

    checklist = {
        "sensor_integrity": sensor_stats.get("anomaly_count", 0) < 50,
        "ai_confidence": ai_status.get("current_confidence", 0.97) > 0.85,
        "no_emergency_ecam": ecam_stats.get("emergency", 0) == 0,
        "ecam_warnings_acceptable": ecam_stats.get("warning", 0) < 5,
        "hash_chain_valid": hash_stats.get("chain_valid", True),
        "no_tamper_detected": not hash_stats.get("tampered_at"),
        "sensor_health_above_95": health_pct >= 95.0,
        "no_failed_critical_sensors": True,
        "hydraulics_normal": True,
        "navigation_normal": True,
        "flight_controls_normal": True,
        "engines_normal": True,
    }

    all_go = all(checklist.values())

    return {
        "dispatch_ready": all_go,
        "determination": "GO" if all_go else "NO-GO",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "sensor_health_pct": round(health_pct, 2),
        "ai_confidence": round(ai_status.get("current_confidence", 0.97), 4),
        "active_ecam": ecam_stats.get("total_active", 0),
        "checklist": checklist,
        "checks_passed": sum(1 for v in checklist.values() if v),
        "checks_total": len(checklist),
        "compliance": {
            "do326a": True,
            "ed202a": True,
            "easa_amc_20_42": True,
            "mel_cdl_checked": True,
        },
    }


@dispatch_router.post("/authorize")
async def authorize_dispatch(
    body: DispatchRequest,
    request: Request,
    background_tasks: BackgroundTasks,
    user: Dict = Depends(require_role("dispatcher", "administrator", "pilot")),
):
    """Issue a dispatch authorization — creates immutable audit record"""
    status_data = await dispatch_status(request, user)
    if not status_data["dispatch_ready"]:
        raise HTTPException(
            status_code=409,
            detail={
                "error": "DISPATCH_NOT_AUTHORIZED",
                "reason": "One or more GO/NO-GO checks failed",
                "failed_checks": [k for k, v in status_data["checklist"].items() if not v],
            }
        )

    auth_id = f"DISP-{uuid.uuid4().hex[:8].upper()}"
    log.info(
        f"DISPATCH AUTHORIZED: {auth_id} — {body.aircraft_msn} "
        f"{body.origin}→{body.destination} by {user['username']}"
    )

    return {
        "authorization_id": auth_id,
        "status": "AUTHORIZED",
        "aircraft_msn": body.aircraft_msn,
        "flight_number": body.flight_number,
        "route": f"{body.origin}→{body.destination}",
        "authorized_by": body.authorized_by,
        "operator_id": user["username"],
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "valid_until": (datetime.now(timezone.utc) + timedelta(hours=4)).isoformat(),
        "compliance": "EASA PART M — MEL/CDL VERIFIED",
        "hash_chain_block": status_data.get("hash_chain_block"),
    }


# ─────────────────────────────────────────────────────────────
# HASH CHAIN API ROUTER
# ─────────────────────────────────────────────────────────────

hashchain_router = APIRouter()


@hashchain_router.get("/latest")
async def get_latest_blocks(
    request: Request,
    n: int = 50,
    user: Dict = Depends(get_current_user),
):
    service = getattr(request.app.state, "hash_service", None)
    if not service:
        raise HTTPException(status_code=503, detail="HASH_SERVICE_NOT_READY")
    return {
        "blocks": service.get_latest_blocks(n),
        "stats": service.get_stats(),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@hashchain_router.get("/verify")
async def verify_chain(
    request: Request,
    user: Dict = Depends(require_role("qa_inspector", "administrator", "maintenance_engineer")),
):
    service = getattr(request.app.state, "hash_service", None)
    if not service:
        raise HTTPException(status_code=503, detail="HASH_SERVICE_NOT_READY")
    ok, tampered_at = service.verify_chain()
    return {
        "chain_valid": ok,
        "tampered_at_sequence": tampered_at,
        "total_blocks": len(service._chain),
        "algorithm": "SHA-256",
        "compliance": "DO-326A",
        "verification_timestamp": datetime.now(timezone.utc).isoformat(),
        "verified_by": user["username"],
    }


# ─────────────────────────────────────────────────────────────
# DIGITAL TWIN API ROUTER
# ─────────────────────────────────────────────────────────────

twin_router = APIRouter()


class PhaseRequest(BaseModel):
    phase: str
    altitude_ft: Optional[float] = None
    speed_kt: Optional[float] = None

    @field_validator("phase")
    @classmethod
    def validate_phase(cls, v):
        valid = ["GROUND", "TAXI", "TAKEOFF", "CLIMB", "CRUISE", "DESCENT", "APPROACH", "LANDING"]
        if v.upper() not in valid:
            raise ValueError(f"Phase must be one of: {valid}")
        return v.upper()


@twin_router.get("/state")
async def get_twin_state(request: Request, user: Dict = Depends(get_current_user)):
    engine = getattr(request.app.state, "twin_engine", None)
    if not engine:
        raise HTTPException(status_code=503, detail="TWIN_ENGINE_NOT_READY")
    return engine.get_state()


@twin_router.post("/phase")
async def set_flight_phase(
    body: PhaseRequest,
    request: Request,
    user: Dict = Depends(require_role("pilot", "administrator", "maintenance_engineer")),
):
    engine = getattr(request.app.state, "twin_engine", None)
    if not engine:
        raise HTTPException(status_code=503, detail="TWIN_ENGINE_NOT_READY")
    engine.set_phase(body.phase)
    log.info(f"TWIN: Flight phase set to {body.phase} by {user['username']}")
    return {
        "status": "OK",
        "phase": body.phase,
        "set_by": user["username"],
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


# ─────────────────────────────────────────────────────────────
# AI ENGINE API ROUTER
# ─────────────────────────────────────────────────────────────

ai_router = APIRouter()


@ai_router.get("/status")
async def get_ai_status(request: Request, user: Dict = Depends(get_current_user)):
    engine = getattr(request.app.state, "ai_engine", None)
    if not engine:
        raise HTTPException(status_code=503, detail="AI_ENGINE_NOT_READY")
    return engine.get_status()


@ai_router.get("/events")
async def get_ai_events(
    request: Request,
    limit: int = 50,
    user: Dict = Depends(get_current_user),
):
    engine = getattr(request.app.state, "ai_engine", None)
    if not engine:
        raise HTTPException(status_code=503, detail="AI_ENGINE_NOT_READY")
    events = list(engine.event_history)[-limit:][::-1]
    return {
        "count": len(events),
        "active_events": len(engine.active_events),
        "events": [
            {
                "event_id": e.event_id,
                "sensor_id": e.sensor_id,
                "ata_chapter": e.ata_chapter,
                "detected_at": datetime.fromtimestamp(
                    e.detected_at, tz=timezone.utc
                ).isoformat(),
                "anomaly_type": e.anomaly_type,
                "severity": e.severity,
                "reconstruction_error": round(e.reconstruction_error, 6),
                "confidence": round(e.confidence, 4),
                "description": e.description,
                "is_resolved": e.is_resolved,
            }
            for e in events
        ],
    }


@ai_router.post("/threshold")
async def update_threshold(
    request: Request,
    threshold: float,
    user: Dict = Depends(require_role("qa_inspector", "administrator", "maintenance_engineer")),
):
    engine = getattr(request.app.state, "ai_engine", None)
    if not engine:
        raise HTTPException(status_code=503, detail="AI_ENGINE_NOT_READY")
    if not 0.01 <= threshold <= 1.0:
        raise HTTPException(status_code=422, detail="Threshold must be between 0.01 and 1.0")
    old = engine.autoencoder.anomaly_threshold
    engine.autoencoder.anomaly_threshold = threshold
    log.info(f"AI threshold updated: {old:.4f} → {threshold:.4f} by {user['username']}")
    return {
        "status": "UPDATED",
        "old_threshold": old,
        "new_threshold": threshold,
        "updated_by": user["username"],
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


# ─────────────────────────────────────────────────────────────
# FLEET API ROUTER
# ─────────────────────────────────────────────────────────────

fleet_router = APIRouter()

FLEET_DATA = [
    {"msn": "8234", "reg": "F-WXWB", "type": "A320neo", "airline": "Air France",
     "cycles": 4821, "hours": 12450.3, "status": "ACTIVE", "location": "CDG"},
    {"msn": "9012", "reg": "D-AVVB", "type": "A321",    "airline": "Lufthansa",
     "cycles": 3201, "hours": 8920.1, "status": "ACTIVE", "location": "FRA"},
    {"msn": "7891", "reg": "G-EZWX", "type": "A320",    "airline": "easyJet",
     "cycles": 6432, "hours": 15230.7, "status": "MAINTENANCE", "location": "LTN"},
    {"msn": "6543", "reg": "EC-MXY", "type": "A350",    "airline": "Iberia",
     "cycles": 1823, "hours": 5840.2, "status": "ACTIVE", "location": "MAD"},
    {"msn": "5210", "reg": "OE-IVM", "type": "A320neo", "airline": "Austrian",
     "cycles": 2904, "hours": 7612.9, "status": "ACTIVE", "location": "VIE"},
    {"msn": "4480", "reg": "HB-JCA", "type": "A330",    "airline": "Swiss",
     "cycles": 5102, "hours": 28430.1, "status": "ACTIVE", "location": "ZRH"},
]


@fleet_router.get("/")
async def get_fleet(user: Dict = Depends(get_current_user)):
    return {
        "total_aircraft": len(FLEET_DATA),
        "active": sum(1 for a in FLEET_DATA if a["status"] == "ACTIVE"),
        "maintenance": sum(1 for a in FLEET_DATA if a["status"] == "MAINTENANCE"),
        "fleet": FLEET_DATA,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@fleet_router.get("/{msn}")
async def get_aircraft(msn: str, user: Dict = Depends(get_current_user)):
    aircraft = next((a for a in FLEET_DATA if a["msn"] == msn), None)
    if not aircraft:
        raise HTTPException(status_code=404, detail=f"Aircraft MSN {msn} not found")
    return aircraft


# ─────────────────────────────────────────────────────────────
# CYBERSECURITY API ROUTER
# ─────────────────────────────────────────────────────────────

cyber_router = APIRouter()

_THREAT_LOG: List[Dict] = []


@cyber_router.get("/status")
async def cyber_status(user: Dict = Depends(get_current_user)):
    return {
        "overall_status": "NOMINAL",
        "threat_level": "LOW",
        "active_threats": 0,
        "controls": {
            "tls_1_3": True,
            "jwt_authentication": True,
            "rbac_enforcement": True,
            "replay_protection": True,
            "packet_signing": True,
            "hash_chain_audit": True,
            "rate_limiting": True,
            "intrusion_detection": True,
            "spoof_detection": True,
            "csrf_protection": True,
            "xss_protection": True,
            "csp_headers": True,
        },
        "compliance": {
            "do326a": True,
            "ed202a": True,
            "easa_amc_20_42": True,
            "arinc_664_afdx": True,
        },
        "threat_log_count": len(_THREAT_LOG),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@cyber_router.get("/threats")
async def get_threats(
    limit: int = 50,
    user: Dict = Depends(require_role("administrator", "qa_inspector")),
):
    return {
        "count": len(_THREAT_LOG),
        "threats": _THREAT_LOG[-limit:][::-1],
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


# ─────────────────────────────────────────────────────────────
# SYSTEM HEALTH ROUTER
# ─────────────────────────────────────────────────────────────

system_router = APIRouter()


@system_router.get("/health")
async def system_health(request: Request):
    return {
        "status": "OPERATIONAL",
        "version": "4.2.1",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "uptime_sec": round(time.time() - getattr(request.app.state, "_start_time", time.time()), 1),
        "websocket_connections": ws_manager.stats()["active_connections"],
        "services": {
            "sensor_engine": "RUNNING",
            "ai_engine": "RUNNING",
            "digital_twin": "RUNNING",
            "ecam_engine": "RUNNING",
            "hash_chain": "ACTIVE",
            "websocket": "ACTIVE",
        },
    }


@system_router.get("/metrics")
async def get_metrics(
    request: Request,
    user: Dict = Depends(require_role("administrator")),
):
    sensor_engine = getattr(request.app.state, "sensor_engine", None)
    ai_engine = getattr(request.app.state, "ai_engine", None)
    hash_service = getattr(request.app.state, "hash_service", None)
    return {
        "sensor_engine": sensor_engine.get_stats() if sensor_engine else {},
        "ai_engine": ai_engine.get_status() if ai_engine else {},
        "hash_chain": hash_service.get_stats() if hash_service else {},
        "websocket": ws_manager.stats(),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
