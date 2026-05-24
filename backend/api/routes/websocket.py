"""SentinelTwin — WebSocket Routes + Broadcast Engine"""
import asyncio
import json
import logging
import time
import uuid
from datetime import datetime, timezone
from typing import Dict, List, Set

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

log = logging.getLogger("sentineltwin.ws")
router = APIRouter()


class ConnectionManager:
    def __init__(self):
        self._connections: Dict[str, WebSocket] = {}
        self._subscriptions: Dict[str, Set[str]] = {}
        self._channels: Dict[str, Set[str]] = {}
        self._lock = asyncio.Lock()
        self.total_messages_sent = 0
        self.total_connections = 0

    async def connect(self, ws: WebSocket, channels: List[str] = None) -> str:
        await ws.accept()
        conn_id = str(uuid.uuid4())
        async with self._lock:
            self._connections[conn_id] = ws
            subs = set(channels or ["telemetry", "ecam", "ai", "hashchain", "twin"])
            self._subscriptions[conn_id] = subs
            for ch in subs:
                self._channels.setdefault(ch, set()).add(conn_id)
        self.total_connections += 1
        return conn_id

    async def disconnect(self, conn_id: str):
        async with self._lock:
            self._connections.pop(conn_id, None)
            subs = self._subscriptions.pop(conn_id, set())
            for ch in subs:
                self._channels.get(ch, set()).discard(conn_id)

    async def broadcast_channel(self, channel: str, data: Dict):
        message = json.dumps({"channel": channel,
                              "timestamp": datetime.now(timezone.utc).isoformat(), "data": data})
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
        return {"active_connections": len(self._connections),
                "total_connections": self.total_connections,
                "total_messages_sent": self.total_messages_sent,
                "channels": {ch: len(ids) for ch, ids in self._channels.items()}}


ws_manager = ConnectionManager()


@router.websocket("/telemetry")
async def ws_telemetry(websocket: WebSocket):
    conn_id = await ws_manager.connect(websocket,
        ["telemetry", "ecam", "ai", "hashchain", "twin", "dispatch", "cyber"])
    try:
        while True:
            try:
                msg = await asyncio.wait_for(websocket.receive_text(), timeout=30.0)
                data = json.loads(msg)
                if data.get("cmd") == "set_phase":
                    await ws_manager.send_to(conn_id, {"type": "ack", "cmd": "set_phase", "phase": data.get("phase")})
                elif data.get("cmd") == "ping":
                    await ws_manager.send_to(conn_id, {"type": "pong", "ts": time.time()})
            except asyncio.TimeoutError:
                await ws_manager.send_to(conn_id, {"type": "keepalive", "ts": time.time()})
    except WebSocketDisconnect:
        await ws_manager.disconnect(conn_id)


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
            arinc_service = getattr(app.state, "arinc_service", None)
            afdx_service = getattr(app.state, "afdx_service", None)
            security_engine = getattr(app.state, "security_engine", None)
            tasks = []
            if sensor_engine:
                stats = sensor_engine.get_stats()
                tasks.append(ws_manager.broadcast_channel("telemetry", {
                    "type": "sensor_stats",
                    "aircraft_type": stats.get("aircraft_type", "A320neo"),
                    "total_sensors": stats.get("total_sensors", 8192),
                    "healthy_count": stats.get("healthy_count", 0),
                    "anomaly_count": stats.get("anomaly_count", 0),
                    "total_validations": stats.get("total_validations", 0),
                    "cycle_duration_ms": stats.get("cycle_duration_ms", 0),
                    # scan_rate_hz is the instantaneous validations/sec from the engine;
                    # fall back to the legacy "scan_rate" key, then 0.
                    "scan_rate": stats.get("scan_rate_hz") or stats.get("scan_rate", 0),
                }))
            if ai_engine:
                ai_status = ai_engine.get_status()
                tasks.append(ws_manager.broadcast_channel("ai", {
                    "type": "ai_status",
                    "reconstruction_error": ai_status.get("current_reconstruction_error", 0),
                    "severity": ai_status.get("current_severity", "NOMINAL"),
                    "confidence": ai_status.get("current_confidence", 0.97),
                    "active_events": ai_status.get("active_events", 0),
                    "inference_count": ai_status.get("inference_count", 0),
                }))
            if twin_engine:
                tasks.append(ws_manager.broadcast_channel("twin", {
                    "type": "twin_state", **twin_engine.get_state()}))
            if ecam_engine:
                tasks.append(ws_manager.broadcast_channel("ecam", {
                    "type": "ecam_update",
                    "active": ecam_engine.get_active(),
                    "stats": ecam_engine.get_stats(),
                }))
            if hash_service and cycle % 5 == 0:
                healthy = getattr(sensor_engine, "healthy_count", 8100) if sensor_engine else 8100
                anomaly = getattr(sensor_engine, "anomaly_count", 0) if sensor_engine else 0
                phase = twin_engine.twin.flight_phase if twin_engine else "GROUND"
                block = await hash_service.append(healthy, anomaly, phase)
                tasks.append(ws_manager.broadcast_channel("hashchain", {
                    "type": "hash_block",
                    "block": {"sequence": block.sequence, "scan_id": block.scan_id,
                              "timestamp": block.timestamp,
                              "block_hash": block.block_hash,
                              "previous_hash": block.previous_hash[:16] + "...",
                              "healthy_count": block.healthy_count,
                              "anomaly_count": block.anomaly_count,
                              "flight_phase": block.flight_phase},
                    "chain_valid": True, "total_blocks": block.sequence,
                }))
            if cycle % 3 == 0:
                ecam_stats = ecam_engine.get_stats() if ecam_engine else {}
                ai_status = ai_engine.get_status() if ai_engine else {}
                sensor_stats = sensor_engine.get_stats() if sensor_engine else {}
                dispatch_go = (ecam_stats.get("emergency", 0) == 0 and
                               sensor_stats.get("anomaly_count", 0) < 50 and
                               ai_status.get("current_confidence", 0.9) > 0.85)
                tasks.append(ws_manager.broadcast_channel("dispatch", {
                    "type": "dispatch_status", "dispatch_ready": dispatch_go,
                    "reason": "ALL_CHECKS_PASSED" if dispatch_go else "ANOMALIES_DETECTED",
                }))
            # ── Update ARINC 429 flight state from twin ─────
            if arinc_service and twin_engine:
                twin_state = twin_engine.get_state()
                engines = twin_state.get("engines", {})
                eng1 = engines.get("eng1", {})
                eng2 = engines.get("eng2", {})
                arinc_service.update_flight_state({
                    "altitude_ft": twin_state.get("altitude_ft", 0),
                    "airspeed_kts": twin_state.get("ias_kt", 0),
                    "mach": twin_state.get("mach", 0),
                    "heading_deg": twin_state.get("heading_deg", 360),
                    "pitch_deg": twin_state.get("pitch_deg", 0),
                    "roll_deg": twin_state.get("roll_deg", 0),
                    "latitude_deg": twin_state.get("latitude", 48.85),
                    "longitude_deg": twin_state.get("longitude", 2.35),
                    "eng1_n1_pct": eng1.get("n1_pct", 18),
                    "eng2_n1_pct": eng2.get("n1_pct", 18),
                    "eng1_egt_c": eng1.get("egt_c", 420),
                    "eng2_egt_c": eng2.get("egt_c", 420),
                    "fms_dist_nm": 0,
                    "phase": twin_state.get("flight_phase", "GROUND"),
                })
            # ── ARINC 429 bus frame (every 2 cycles) ──────────
            if arinc_service and cycle % 2 == 0:
                frame = arinc_service.generate_bus_frame()
                bus_stats = arinc_service.get_bus_stats()
                tasks.append(ws_manager.broadcast_channel("arinc", {
                    "type": "arinc_frame",
                    "frame": frame,
                    "bus_stats": bus_stats,
                }))
            # ── AFDX virtual link status (every 3 cycles) ────
            if afdx_service and cycle % 3 == 0:
                vls = afdx_service.get_all_vl_status()
                net_stats = afdx_service.get_network_stats()
                tasks.append(ws_manager.broadcast_channel("afdx", {
                    "type": "afdx_status",
                    "virtual_links": vls,
                    "network_stats": net_stats,
                }))
            # ── Cybersecurity events (every 5 cycles) ─────────
            if security_engine and cycle % 5 == 0:
                dashboard = security_engine.get_threat_dashboard()
                tasks.append(ws_manager.broadcast_channel("cyber", {
                    "type": "cyber_status",
                    "threat_level": dashboard.get("threat_level", "LOW"),
                    "active_threats": dashboard.get("active_threats", 0),
                    "statistics": dashboard.get("statistics", {}),
                }))
            # ── Structural + thermal alert check (every 5 cycles) ────
            if twin_engine and cycle % 5 == 0:
                state = twin_engine.get_state()
                struct = state.get("structural", {})
                thermal = state.get("thermal", {})
                alerts = []
                if struct.get("turbulence_intensity") in ("MODERATE", "SEVERE"):
                    alerts.append({"type": "TURBULENCE", "severity": "CAUTION", "value": struct["turbulence_intensity"]})
                if thermal.get("brake_temp_c", 0) > 300:
                    alerts.append({"type": "BRAKE_TEMP", "severity": "WARNING", "value": thermal["brake_temp_c"]})
                if thermal.get("avionics_bay_c", 0) > 55:
                    alerts.append({"type": "AVIONICS_OVERHEAT", "severity": "WARNING", "value": thermal["avionics_bay_c"]})
                if alerts:
                    tasks.append(ws_manager.broadcast_channel("ecam", {
                        "type": "structural_alerts",
                        "alerts": alerts,
                    }))
            await asyncio.gather(*tasks, return_exceptions=True)
            # ── Update Prometheus metrics (graceful) ────────
            try:
                from main import PROMETHEUS_AVAILABLE
                if PROMETHEUS_AVAILABLE:
                    from main import ws_msg_rate, kafka_queue_depth
                    ws_msg_rate.inc(len(tasks))
                    kafka_producer = getattr(app.state, "kafka_producer", None)
                    if kafka_producer and hasattr(kafka_producer, '_send_queue'):
                        kafka_queue_depth.set(kafka_producer._send_queue.qsize())
            except Exception:
                pass
        except Exception as e:
            log.error(f"Broadcast loop error: {e}", exc_info=True)
        await asyncio.sleep(1.0)
