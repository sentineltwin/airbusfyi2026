"""
SentinelTwin — Cybersecurity Engine
Real-time threat detection: rate limiting, replay attacks, telemetry spoofing,
frozen telemetry detection, and threat level computation.
"""

import hashlib
import logging
import math
import random
import time
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, List, Optional, Set, Tuple

log = logging.getLogger("sentineltwin.security")


@dataclass
class SpoofResult:
    """Result of a telemetry spoof detection check."""
    spoofed: bool
    confidence: float
    method: str  # "RANGE" | "GRADIENT" | "FREEZE" | "STATISTICAL"
    details: str = ""


@dataclass
class ThreatEvent:
    """A logged security threat event."""
    event_id: str
    event_type: str
    source: str
    severity: str  # "LOW" | "MEDIUM" | "HIGH" | "CRITICAL"
    details: Dict
    timestamp: str
    status: str = "DETECTED"


class CybersecurityEngine:
    """
    Real-time cybersecurity engine for aerospace telemetry protection.
    Implements: rate limiting, replay detection, spoof detection,
    frozen telemetry detection, and composite threat level.
    """

    def __init__(self):
        # Rate limiter: {client_ip: deque of timestamps}
        self._rate_windows: Dict[str, deque] = {}
        self._rate_limit: int = 100  # requests per minute per IP
        self._rate_window_sec: float = 60.0

        # Replay detection: {packet_id: timestamp}
        self._nonce_cache: Dict[str, float] = {}
        self._nonce_ttl: float = 30.0  # seconds
        self._nonce_cleanup_counter: int = 0

        # Spoof detection: {sensor_id: deque of recent values}
        self._value_history: Dict[str, deque] = {}
        self._history_depth: int = 20

        # Threat log
        self._threat_log: List[ThreatEvent] = []
        self._max_log_size: int = 10000

        # Threat counters (sliding window)
        self._threat_counts: Dict[str, int] = {
            "LOW": 0, "MEDIUM": 0, "HIGH": 0, "CRITICAL": 0,
        }
        self._recent_threats: deque = deque(maxlen=1000)

        # Statistics
        self._total_checks: int = 0
        self._blocked_requests: int = 0
        self._replay_detections: int = 0
        self._spoof_detections: int = 0
        self._freeze_detections: int = 0
        self._start_time: float = time.time()

        log.info("CybersecurityEngine initialized")

    # ─────────────────────────────────────────────────────────
    # RATE LIMITING
    # ─────────────────────────────────────────────────────────

    def check_rate_limit(self, client_ip: str, endpoint: str = "") -> bool:
        """
        Sliding window rate limiter.
        Returns True if the request should be ALLOWED, False if rate-limited.
        """
        now = time.time()
        window_start = now - self._rate_window_sec

        if client_ip not in self._rate_windows:
            self._rate_windows[client_ip] = deque(maxlen=500)

        window = self._rate_windows[client_ip]

        # Remove expired entries
        while window and window[0] < window_start:
            window.popleft()

        # Check count
        if len(window) >= self._rate_limit:
            self._blocked_requests += 1
            self.log_threat_event(
                event_type="RATE_LIMIT_EXCEEDED",
                source=client_ip,
                details={"endpoint": endpoint, "count": len(window), "limit": self._rate_limit},
                severity="MEDIUM",
            )
            return False

        window.append(now)
        self._total_checks += 1
        return True

    # ─────────────────────────────────────────────────────────
    # REPLAY ATTACK DETECTION
    # ─────────────────────────────────────────────────────────

    def detect_replay_attack(self, packet_id: str, timestamp: float) -> bool:
        """
        Detect replay attacks using a nonce cache with TTL.
        Returns True if this is a REPLAY (attack detected).
        """
        now = time.time()

        # Periodic cleanup of expired nonces
        self._nonce_cleanup_counter += 1
        if self._nonce_cleanup_counter % 100 == 0:
            self._cleanup_nonces(now)

        # Check if packet_id was recently seen
        if packet_id in self._nonce_cache:
            age = now - self._nonce_cache[packet_id]
            if age < self._nonce_ttl:
                self._replay_detections += 1
                self.log_threat_event(
                    event_type="REPLAY_ATTACK_DETECTED",
                    source=packet_id[:32],
                    details={"packet_id": packet_id[:64], "age_sec": round(age, 2)},
                    severity="HIGH",
                )
                return True

        # Also check timestamp freshness
        if abs(now - timestamp) > self._nonce_ttl:
            self._replay_detections += 1
            self.log_threat_event(
                event_type="STALE_TIMESTAMP_DETECTED",
                source=packet_id[:32],
                details={"timestamp": timestamp, "drift_sec": round(abs(now - timestamp), 2)},
                severity="MEDIUM",
            )
            return True

        self._nonce_cache[packet_id] = now
        return False

    def _cleanup_nonces(self, now: float):
        """Remove expired nonces from cache."""
        expired = [k for k, v in self._nonce_cache.items() if now - v > self._nonce_ttl]
        for k in expired:
            del self._nonce_cache[k]

    # ─────────────────────────────────────────────────────────
    # TELEMETRY SPOOF DETECTION
    # ─────────────────────────────────────────────────────────

    def detect_telemetry_spoof(self, sensor_id: str, value: float,
                                expected_range: Tuple[float, float]) -> SpoofResult:
        """
        Multi-method telemetry spoof detection.
        Checks: range violation, gradient attack, freeze, statistical outlier.
        """
        min_val, max_val = expected_range

        # ── Method 1: Range check ──────────────────────────────
        if value < min_val or value > max_val:
            self._spoof_detections += 1
            result = SpoofResult(
                spoofed=True, confidence=0.95, method="RANGE",
                details=f"Value {value:.4f} outside [{min_val}, {max_val}]",
            )
            self.log_threat_event(
                event_type="TELEMETRY_SPOOF_RANGE",
                source=sensor_id,
                details={"value": value, "range": [min_val, max_val], "method": "RANGE"},
                severity="HIGH",
            )
            return result

        # Get/create value history
        if sensor_id not in self._value_history:
            self._value_history[sensor_id] = deque(maxlen=self._history_depth)
        history = self._value_history[sensor_id]

        if len(history) >= 3:
            # ── Method 2: Gradient attack (sudden jump) ─────────
            recent = list(history)[-5:]
            avg_delta = sum(
                abs(recent[i] - recent[i - 1]) for i in range(1, len(recent))
            ) / max(1, len(recent) - 1)
            current_delta = abs(value - recent[-1])
            range_span = max_val - min_val
            gradient_threshold = max(range_span * 0.05, avg_delta * 10)

            if current_delta > gradient_threshold and avg_delta > 0:
                self._spoof_detections += 1
                result = SpoofResult(
                    spoofed=True, confidence=0.8, method="GRADIENT",
                    details=f"Sudden jump: delta={current_delta:.4f}, avg_delta={avg_delta:.4f}",
                )
                self.log_threat_event(
                    event_type="TELEMETRY_SPOOF_GRADIENT",
                    source=sensor_id,
                    details={"delta": round(current_delta, 4), "avg_delta": round(avg_delta, 4)},
                    severity="HIGH",
                )
                return result

            # ── Method 3: Freeze detection (inline) ─────────────
            frozen = self._check_frozen_inline(recent, value)
            if frozen:
                self._spoof_detections += 1
                self._freeze_detections += 1
                result = SpoofResult(
                    spoofed=True, confidence=0.7, method="FREEZE",
                    details="Telemetry frozen — identical values for >5 cycles",
                )
                self.log_threat_event(
                    event_type="TELEMETRY_SPOOF_FREEZE",
                    source=sensor_id,
                    details={"frozen_value": value, "cycles": len(recent) + 1},
                    severity="MEDIUM",
                )
                return result

            # ── Method 4: Statistical outlier ───────────────────
            if len(history) >= 10:
                arr = list(history)[-10:]
                mean = sum(arr) / len(arr)
                variance = sum((x - mean) ** 2 for x in arr) / len(arr)
                std = math.sqrt(variance) if variance > 0 else 0
                if std > 0 and abs(value - mean) > 4 * std:
                    self._spoof_detections += 1
                    result = SpoofResult(
                        spoofed=True, confidence=0.65, method="STATISTICAL",
                        details=f"4-sigma outlier: value={value:.4f}, mean={mean:.4f}, std={std:.4f}",
                    )
                    self.log_threat_event(
                        event_type="TELEMETRY_SPOOF_STATISTICAL",
                        source=sensor_id,
                        details={"value": value, "mean": round(mean, 4), "std": round(std, 4)},
                        severity="MEDIUM",
                    )
                    return result

        history.append(value)
        return SpoofResult(spoofed=False, confidence=0.0, method="NONE")

    @staticmethod
    def _check_frozen_inline(recent: List[float], current: float) -> bool:
        """Check if values are frozen (all identical for >5 cycles)."""
        if len(recent) < 5:
            return False
        check_values = recent[-5:] + [current]
        return all(abs(v - check_values[0]) < 1e-12 for v in check_values)

    # ─────────────────────────────────────────────────────────
    # FROZEN TELEMETRY DETECTION
    # ─────────────────────────────────────────────────────────

    def detect_frozen_telemetry(self, sensor_id: str,
                                 value_history: deque) -> bool:
        """
        Detect frozen telemetry — all values identical for >5 cycles.
        Returns True if telemetry is frozen.
        """
        if len(value_history) < 6:
            return False

        recent = list(value_history)[-6:]
        is_frozen = all(abs(v - recent[0]) < 1e-12 for v in recent)

        if is_frozen:
            self._freeze_detections += 1

        return is_frozen

    # ─────────────────────────────────────────────────────────
    # THREAT LEVEL COMPUTATION
    # ─────────────────────────────────────────────────────────

    def compute_threat_level(self) -> str:
        """
        Compute composite threat level based on recent events.
        Returns: "LOW" | "MEDIUM" | "HIGH" | "CRITICAL"
        """
        now = time.time()
        window = 300.0  # 5-minute window

        # Count recent threats by severity
        counts = {"LOW": 0, "MEDIUM": 0, "HIGH": 0, "CRITICAL": 0}
        for threat in self._recent_threats:
            if now - threat.get("ts", 0) < window:
                sev = threat.get("severity", "LOW")
                counts[sev] = counts.get(sev, 0) + 1

        # Scoring
        score = (
            counts["LOW"] * 1 +
            counts["MEDIUM"] * 5 +
            counts["HIGH"] * 20 +
            counts["CRITICAL"] * 100
        )

        if score >= 100 or counts["CRITICAL"] > 0:
            return "CRITICAL"
        elif score >= 40 or counts["HIGH"] >= 3:
            return "HIGH"
        elif score >= 10 or counts["MEDIUM"] >= 5:
            return "MEDIUM"
        return "LOW"

    # ─────────────────────────────────────────────────────────
    # THREAT LOGGING
    # ─────────────────────────────────────────────────────────

    def log_threat_event(self, event_type: str, source: str,
                          details: Dict, severity: str = "LOW") -> None:
        """Log a threat event to the internal log."""
        event = ThreatEvent(
            event_id=f"THR-{int(time.time() * 1000):013d}-{random.randint(0, 999):03d}",
            event_type=event_type,
            source=source,
            severity=severity,
            details=details,
            timestamp=datetime.now(timezone.utc).isoformat(),
        )
        self._threat_log.append(event)
        if len(self._threat_log) > self._max_log_size:
            self._threat_log = self._threat_log[-self._max_log_size:]

        self._recent_threats.append({
            "ts": time.time(),
            "severity": severity,
            "type": event_type,
        })

        self._threat_counts[severity] = self._threat_counts.get(severity, 0) + 1

        log.warning(f"THREAT [{severity}] {event_type} from {source}: {details}")

    # ─────────────────────────────────────────────────────────
    # DASHBOARD DATA
    # ─────────────────────────────────────────────────────────

    def get_threat_dashboard(self) -> Dict:
        """Return comprehensive threat dashboard data."""
        threat_level = self.compute_threat_level()
        elapsed = max(1, time.time() - self._start_time)
        now = time.time()

        # Count events in last 24 hours
        events_24h = sum(
            1 for t in self._threat_log
            if now - self._parse_ts(t.timestamp) < 86400
        )

        # Top sources
        source_counts: Dict[str, int] = {}
        for t in self._threat_log[-500:]:
            source_counts[t.source] = source_counts.get(t.source, 0) + 1
        top_sources = sorted(source_counts.items(), key=lambda x: x[1], reverse=True)[:10]

        return {
            "threat_level": threat_level,
            "active_threats": sum(1 for t in self._recent_threats if now - t.get("ts", 0) < 300),
            "events_24h": events_24h,
            "events_total": len(self._threat_log),
            "top_sources": [{"source": s, "count": c} for s, c in top_sources],
            "threat_counts": dict(self._threat_counts),
            "statistics": {
                "total_checks": self._total_checks,
                "blocked_requests": self._blocked_requests,
                "replay_detections": self._replay_detections,
                "spoof_detections": self._spoof_detections,
                "freeze_detections": self._freeze_detections,
                "uptime_sec": round(elapsed, 1),
            },
            "controls": {
                "rate_limiting": True,
                "replay_protection": True,
                "spoof_detection": True,
                "freeze_detection": True,
                "hash_chain_audit": True,
                "tls_1_3": True,
                "jwt_authentication": True,
                "rbac_enforcement": True,
            },
            "compliance": {
                "do326a": True,
                "ed202a": True,
                "easa_amc_20_42": True,
            },
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    def get_threat_events(self, limit: int = 50) -> List[Dict]:
        """Return recent threat events as dicts."""
        events = self._threat_log[-limit:][::-1]
        return [
            {
                "event_id": e.event_id,
                "event_type": e.event_type,
                "source": e.source,
                "severity": e.severity,
                "details": e.details,
                "timestamp": e.timestamp,
                "status": e.status,
            }
            for e in events
        ]

    @staticmethod
    def _parse_ts(ts: str) -> float:
        """Parse ISO timestamp to unix time."""
        try:
            dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
            return dt.timestamp()
        except (ValueError, AttributeError):
            return 0.0
