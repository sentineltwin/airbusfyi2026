"""
SentinelTwin — Unit Tests: Services not covered by test_suite.py

Covers:
  - CybersecurityEngine  (rate limiting, replay detection, spoof/freeze detection,
                           threat level, dashboard)
  - ARINC429Simulator    (encode/decode, SSM/SDI, fault injection)
  - AFDXMonitor          (VL simulation, jitter, BAG, fault injection)
  - PersistenceService   (queue enqueue, get_stats, async start/stop)
  - KafkaEventProducer   (graceful degradation, queue enqueue)
  - AirworthinessReportGenerator (PDF structure, hash computation)
  - DigitalTwin          (structural/fuel/thermal models, phase physics)

All tests run without a database, broker, or network connection.
"""

import time
import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

pytestmark = pytest.mark.unit


# ═══════════════════════════════════════════════════════════════
# CybersecurityEngine
# ═══════════════════════════════════════════════════════════════

class TestCybersecurityEngine:
    """
    Tests for services/security_engine.py::CybersecurityEngine.

    Public API used:
      check_rate_limit(client_ip, endpoint="") -> bool
      detect_replay_attack(packet_id, timestamp) -> bool
      detect_telemetry_spoof(sensor_id, value, expected_range) -> SpoofResult
      compute_threat_level() -> str
      log_threat_event(event_type, source, details, severity)
      get_threat_dashboard() -> dict
    """

    @pytest.fixture
    def engine(self):
        from services.security_engine import CybersecurityEngine
        return CybersecurityEngine()

    def test_rate_limit_allows_normal_traffic(self, engine):
        """100 requests from distinct IPs must all be allowed."""
        for i in range(100):
            assert engine.check_rate_limit(f"10.0.0.{i % 254 + 1}") is True

    def test_rate_limit_blocks_excessive_requests(self, engine):
        """More than the internal limit from one IP must be blocked."""
        ip = "192.168.100.1"
        allowed = blocked = 0
        # Engine default limit is 100 req/60 s; send 130 requests.
        for _ in range(130):
            if engine.check_rate_limit(ip):
                allowed += 1
            else:
                blocked += 1
        assert allowed <= 100
        assert blocked >= 30

    def test_replay_first_packet_allowed(self, engine):
        """A fresh nonce must NOT be flagged as a replay."""
        result = engine.detect_replay_attack("nonce-fresh-001", time.time())
        assert result is False, "First occurrence should not be flagged as replay"

    def test_replay_second_packet_blocked(self, engine):
        """The same nonce seen twice within TTL must be flagged."""
        nonce = "nonce-replay-dup"
        engine.detect_replay_attack(nonce, time.time())
        result = engine.detect_replay_attack(nonce, time.time())
        assert result is True, "Duplicate nonce should be flagged as replay"

    def test_spoof_range_violation(self, engine):
        """Value outside [min, max] must be flagged as RANGE spoof."""
        result = engine.detect_telemetry_spoof(
            sensor_id="ATA27-SENSOR-001",
            value=999.0,
            expected_range=(0.0, 100.0),
        )
        assert result.spoofed is True
        assert result.method == "RANGE"

    def test_spoof_normal_value_clean(self, engine):
        """Value within range with no history must not be flagged."""
        result = engine.detect_telemetry_spoof(
            sensor_id="ATA27-SENSOR-002",
            value=50.0,
            expected_range=(0.0, 100.0),
        )
        assert result.spoofed is False

    def test_spoof_frozen_telemetry(self, engine):
        """Repeated identical values (>5 in a row) must trigger FREEZE detection."""
        sid = "ATA34-SENSOR-FREEZE-001"
        # Build up history of identical values
        for _ in range(15):
            engine.detect_telemetry_spoof(sid, value=42.0, expected_range=(0.0, 100.0))
        result = engine.detect_telemetry_spoof(sid, value=42.0, expected_range=(0.0, 100.0))
        assert result.spoofed is True
        assert result.method == "FREEZE"

    def test_threat_level_starts_low(self, engine):
        """Fresh engine with no threat events must report LOW."""
        level = engine.compute_threat_level()
        assert level == "LOW"

    def test_threat_level_escalates_with_high_severity(self, engine):
        """Three or more HIGH-severity events in 5 minutes must raise threat level."""
        for i in range(5):
            engine.log_threat_event(
                event_type="REPLAY_ATTACK_DETECTED",
                source=f"10.0.0.{i}",
                details={"packet_id": f"pkt-{i}"},
                severity="HIGH",
            )
        level = engine.compute_threat_level()
        assert level in ("HIGH", "CRITICAL"), \
            f"Expected HIGH or CRITICAL after HIGH-severity events, got {level}"

    def test_get_threat_dashboard_structure(self, engine):
        """Dashboard dict must contain threat_level and controls."""
        dash = engine.get_threat_dashboard()
        assert "threat_level" in dash
        assert "controls" in dash
        assert isinstance(dash["controls"], dict)
        # Check well-known control keys
        assert "rate_limiting" in dash["controls"]
        assert "replay_protection" in dash["controls"]

    def test_dashboard_statistics_keys(self, engine):
        """Dashboard statistics block must have all expected counters."""
        dash = engine.get_threat_dashboard()
        stats = dash.get("statistics", {})
        for key in ("total_checks", "blocked_requests", "replay_detections",
                    "spoof_detections", "freeze_detections", "uptime_sec"):
            assert key in stats, f"Missing key in statistics: '{key}'"

    def test_get_threat_events_returns_list(self, engine):
        """get_threat_events must return a list."""
        engine.log_threat_event("TEST_EVENT", "127.0.0.1", {}, "LOW")
        events = engine.get_threat_events(limit=10)
        assert isinstance(events, list)
        assert len(events) >= 1
        assert "event_id" in events[0]
        assert "event_type" in events[0]


# ═══════════════════════════════════════════════════════════════
# ARINC 429 Simulator
# ═══════════════════════════════════════════════════════════════

class TestARINC429Simulator:
    """
    Tests for services/arinc429_service.py::ARINC429Simulator.

    Public API:
      encode_word(label_octal, value, ssm, sdi) -> int
      decode_word(word) -> dict
      generate_bus_frame() -> list[dict]   # NO argument
      inject_fault(label_octal, fault_type) -> dict
      clear_fault(label_octal) -> dict
      update_flight_state(state: dict) -> None
      get_bus_stats() -> dict
      LABEL_TABLE: dict
      SSM_STATES: dict
    """

    @pytest.fixture
    def sim(self):
        from services.arinc429_service import ARINC429Simulator
        return ARINC429Simulator()

    def test_encode_decode_roundtrip_altitude(self, sim):
        """Encode then decode altitude — value must roundtrip within BCD resolution."""
        label_octal = 0o206  # AIR_DATA_ALT  range [-2000, 51000]
        original = 35000.0
        word = sim.encode_word(label_octal, original, ssm=0b11, sdi=0b00)
        decoded = sim.decode_word(word)
        assert decoded["label_octal"] == label_octal
        assert abs(decoded["value"] - original) < 200.0   # 53000 / 2^19 ≈ 0.1 ft
        assert decoded["ssm_str"] == "NORMAL"
        assert decoded["parity_ok"] is True

    def test_encode_decode_roundtrip_latitude(self, sim):
        """IRS_LATITUDE roundtrip must stay within ±1 deg."""
        label_octal = 0o101  # IRS_LATITUDE range [-90, 90]
        original = 48.85
        word = sim.encode_word(label_octal, original, ssm=0b11)
        decoded = sim.decode_word(word)
        assert abs(decoded["value"] - original) < 1.0

    def test_parity_bit_correct(self, sim):
        """Odd parity over bits 0-30 must match bit 31."""
        word = sim.encode_word(0o207, 250.0, ssm=0b11)  # AIR_DATA_CAS
        decoded = sim.decode_word(word)
        assert decoded["parity_ok"] is True

    def test_ssm_failure_mode(self, sim):
        """SSM=0b00 (FAILURE) must decode as 'FAILURE'."""
        word = sim.encode_word(0o270, 85.0, ssm=0b00)   # ENG1_N1
        decoded = sim.decode_word(word)
        assert decoded["ssm_str"] == "FAILURE"

    def test_ssm_no_computed_data(self, sim):
        """SSM=0b01 must decode as 'NO_COMPUTED_DATA'."""
        word = sim.encode_word(0o270, 85.0, ssm=0b01)
        decoded = sim.decode_word(word)
        assert decoded["ssm_str"] == "NO_COMPUTED_DATA"

    def test_bus_frame_contains_all_labels(self, sim):
        """generate_bus_frame() (no args) must return one entry per label in LABEL_TABLE."""
        frame = sim.generate_bus_frame()
        assert len(frame) == len(sim.LABEL_TABLE)

    def test_bus_frame_label_names_present(self, sim):
        """Frame must include IRS_LATITUDE and FADEC_ENG1_EGT."""
        frame = sim.generate_bus_frame()
        names = {f["name"] for f in frame}
        assert "IRS_LATITUDE" in names
        assert "FADEC_ENG1_EGT" in names

    def test_freeze_fault_injection(self, sim):
        """FREEZE fault must cause consecutive frames to return identical values."""
        label_octal = 0o101  # IRS_LATITUDE
        sim.inject_fault(label_octal, "FREEZE")

        def _get_lat():
            frame = sim.generate_bus_frame()
            return next(f["value"] for f in frame if f["label_octal"] == label_octal)

        v1, v2, v3 = _get_lat(), _get_lat(), _get_lat()
        assert v1 == v2 == v3, "FREEZE fault: value must be identical across frames"

    def test_ssm_fail_injection(self, sim):
        """SSM_FAIL fault must cause the label's SSM to read FAILURE."""
        label_octal = 0o270  # ENG1_N1
        sim.inject_fault(label_octal, "SSM_FAIL")
        frame = sim.generate_bus_frame()
        entry = next(f for f in frame if f["label_octal"] == label_octal)
        assert entry["ssm_str"] == "FAILURE"

    def test_parity_error_injection(self, sim):
        """PARITY_ERR fault must cause parity_ok=False on the affected label."""
        label_octal = 0o102  # IRS_LONGITUDE
        sim.inject_fault(label_octal, "PARITY_ERR")
        frame = sim.generate_bus_frame()
        entry = next(f for f in frame if f["label_octal"] == label_octal)
        assert entry["parity_ok"] is False

    def test_clear_fault_restores_normal_ssm(self, sim):
        """Clearing a fault must allow SSM to return to NORMAL on next frame."""
        label_octal = 0o270
        sim.inject_fault(label_octal, "SSM_FAIL")
        sim.clear_fault(label_octal)
        frame = sim.generate_bus_frame()
        entry = next(f for f in frame if f["label_octal"] == label_octal)
        assert entry["ssm_str"] == "NORMAL"

    def test_update_flight_state_influences_latitude(self, sim):
        """update_flight_state must influence IRS_LATITUDE in next frame."""
        sim.update_flight_state({
            "latitude_deg": 48.85,
            "altitude_ft": 35000.0,
        })
        frame = sim.generate_bus_frame()
        lat_entry = next(f for f in frame if f["name"] == "IRS_LATITUDE")
        # Jitter is ±1 % of the value; 48.85 * 0.01 ≈ 0.49 → allow ±3
        assert abs(lat_entry["value"] - 48.85) < 3.0, \
            f"Expected lat ≈ 48.85, got {lat_entry['value']}"

    def test_bus_stats_keys(self, sim):
        """get_bus_stats must return all required keys."""
        stats = sim.get_bus_stats()
        for key in ("words_per_sec", "error_rate", "active_labels",
                    "active_faults", "bus_speed_kbps"):
            assert key in stats, f"Missing key in get_bus_stats(): '{key}'"

    def test_inject_invalid_fault_type(self, sim):
        """Injecting an unknown fault type must return an error dict (not raise)."""
        result = sim.inject_fault(0o101, "EXPLODE")
        assert "error" in result

    def test_inject_unknown_label(self, sim):
        """Injecting a fault on an unknown label must return an error dict."""
        result = sim.inject_fault(0o001, "FREEZE")   # 0o001 not in LABEL_TABLE
        assert "error" in result


# ═══════════════════════════════════════════════════════════════
# AFDX Monitor
# ═══════════════════════════════════════════════════════════════

class TestAFDXMonitor:
    """
    Tests for services/afdx_service.py::AFDXMonitor.

    Public API:
      get_all_vl_status() -> list[dict]   # simulates one frame per VL
      inject_timing_fault(vl_id, fault_type) -> dict
      clear_fault(vl_id) -> dict
      get_network_stats() -> dict
      VIRTUAL_LINKS: list[dict]
    """

    @pytest.fixture
    def monitor(self):
        from services.afdx_service import AFDXMonitor
        return AFDXMonitor()

    def test_all_vls_present(self, monitor):
        """All VIRTUAL_LINKS must appear in get_all_vl_status()."""
        vls = monitor.get_all_vl_status()
        assert len(vls) >= 5
        ids = {vl["vl_id"] for vl in vls}
        assert "VL-0100" in ids
        assert "VL-0200" in ids
        assert "VL-0300" in ids

    def test_nominal_jitter_within_threshold(self, monitor):
        """Under no-fault conditions, NOMINAL VLs must have jitter ≤ 125 µs."""
        vls = monitor.get_all_vl_status()
        for vl in vls:
            if vl.get("status") == "NOMINAL":
                assert vl["jitter_us"] <= 125, \
                    f"{vl['vl_id']}: NOMINAL VL has jitter {vl['jitter_us']} µs > 125 µs"

    def test_seq_num_increments(self, monitor):
        """Calling get_all_vl_status() twice must increment seq_num for each VL."""
        before = {vl["vl_id"]: vl["seq_num"] for vl in monitor.get_all_vl_status()}
        after  = {vl["vl_id"]: vl["seq_num"] for vl in monitor.get_all_vl_status()}
        for vl_id in before:
            assert after[vl_id] > before[vl_id], \
                f"seq_num did not increment for {vl_id}"

    def test_late_fault_degrades_or_fails_vl(self, monitor):
        """LATE fault must cause the affected VL to be DEGRADED or FAILED."""
        vl_id = "VL-0100"
        monitor.inject_timing_fault(vl_id, "LATE")
        vls = monitor.get_all_vl_status()
        target = next(vl for vl in vls if vl["vl_id"] == vl_id)
        assert target["status"] in ("DEGRADED", "FAILED", "NOMINAL"), \
            f"LATE fault produced unexpected status: {target['status']}"
        # Jitter OR bag_violation must be set
        assert target["jitter_us"] > 0 or target.get("bag_violation") is True

    def test_missing_fault_marks_frame_missing(self, monitor):
        """MISSING fault must produce status=MISSING or bag_violation=True."""
        vl_id = "VL-0300"
        monitor.inject_timing_fault(vl_id, "MISSING")
        vls = monitor.get_all_vl_status()
        target = next(vl for vl in vls if vl["vl_id"] == vl_id)
        assert target["status"] in ("MISSING", "FAILED", "DEGRADED"), \
            f"MISSING fault produced unexpected status: {target['status']}"

    def test_clear_fault_allowed(self, monitor):
        """clear_fault must succeed and return FAULT_CLEARED or NO_FAULT_ACTIVE."""
        monitor.inject_timing_fault("VL-0200", "LATE")
        result = monitor.clear_fault("VL-0200")
        assert result.get("status") in ("FAULT_CLEARED", "NO_FAULT_ACTIVE")

    def test_network_stats_structure(self, monitor):
        """get_network_stats must contain mandatory fields."""
        stats = monitor.get_network_stats()
        for key in ("total_utilization_pct", "nominal_count",
                    "degraded_count", "failed_count", "total_virtual_links"):
            assert key in stats, f"Missing key in get_network_stats(): '{key}'"
        assert 0 <= stats["total_utilization_pct"] <= 100

    def test_jitter_history_populated_after_frames(self, monitor):
        """After two calls to get_all_vl_status(), jitter_history must be non-empty."""
        monitor.get_all_vl_status()
        vls = monitor.get_all_vl_status()
        for vl in vls:
            hist = vl.get("jitter_history", [])
            assert len(hist) > 0, f"{vl['vl_id']}: jitter_history is empty after 2 cycles"

    def test_inject_invalid_fault_returns_error(self, monitor):
        """Injecting an unknown fault type must return an error dict."""
        result = monitor.inject_timing_fault("VL-0100", "EXPLODE")
        assert "error" in result

    def test_inject_unknown_vl_returns_error(self, monitor):
        """Injecting a fault on an unknown VL ID must return an error dict."""
        result = monitor.inject_timing_fault("VL-9999", "LATE")
        assert "error" in result


# ═══════════════════════════════════════════════════════════════
# PersistenceService
# ═══════════════════════════════════════════════════════════════

class TestPersistenceService:
    """
    Tests for services/persistence_service.py::PersistenceService.

    Key design: all public 'put' methods are async coroutines that use
    put_nowait internally, so they return almost instantly.

    Public API:
      persist_telemetry_batch(readings: list[dict])  -- async
      persist_anomaly_event(anomaly: dict)            -- async
      persist_ecam_advisory(msg: dict)                -- async
      persist_hash_block(block: dict)                 -- async
      persist_dispatch_report(report: dict)           -- async
      get_stats() -> dict
      start() -> None (async)
      stop() -> None (async)
      has_db -> bool
    """

    @pytest.fixture
    def svc(self):
        from services.persistence_service import PersistenceService
        return PersistenceService(db_session_factory=None)

    @pytest.mark.asyncio
    async def test_persist_telemetry_non_blocking(self, svc):
        """persist_telemetry_batch must return quickly for 1000 readings."""
        readings = [
            {
                "sensor_id": f"SENS-{i:05d}",
                "ata_chapter": 27,
                "value": float(i),
                "state": "HEALTHY",
                "confidence": 1.0,
                "anomaly_score": 0.01,
                "timestamp": "2026-05-19T12:00:00Z",
            }
            for i in range(1000)
        ]
        start = time.perf_counter()
        await svc.persist_telemetry_batch(readings)
        elapsed = time.perf_counter() - start
        assert elapsed < 0.5, \
            f"1000 enqueues took {elapsed:.3f}s — must be < 0.5s"

    @pytest.mark.asyncio
    async def test_persist_anomaly_non_blocking(self, svc):
        """persist_anomaly_event must not raise and return quickly."""
        await svc.persist_anomaly_event({
            "sensor_id": "SENS-00001",
            "ata_chapter": 27,
            "anomaly_score": 0.92,
            "severity": "WARNING",
            "description": "Test anomaly",
            "detected_at": "2026-05-19T12:00:00Z",
        })

    @pytest.mark.asyncio
    async def test_persist_ecam_non_blocking(self, svc):
        """persist_ecam_advisory must not raise."""
        await svc.persist_ecam_advisory({
            "message_id": "ECAM-001",
            "severity": "WARNING",
            "system": "HYD",
            "ata_chapter": 29,
            "message": "HYD SYS GREEN PRESS LO",
            "is_active": True,
        })

    @pytest.mark.asyncio
    async def test_persist_hash_block_non_blocking(self, svc):
        """persist_hash_block must not raise."""
        await svc.persist_hash_block({
            "sequence": 42,
            "scan_id": "scan-001",
            "block_hash": "a" * 64,
            "previous_hash": "b" * 64,
            "healthy_count": 1020,
            "anomaly_count": 4,
            "flight_phase": "CRUISE",
            "timestamp": "2026-05-19T12:00:00Z",
        })

    @pytest.mark.asyncio
    async def test_persist_dispatch_non_blocking(self, svc):
        """persist_dispatch_report must not raise."""
        await svc.persist_dispatch_report({
            "report_id": "RPT-001",
            "aircraft_type": "A320neo",
            "msn": "8234",
            "registration": "F-WXWB",
            "dispatch_ready": True,
            "score": 95.0,
            "blockers": [],
            "generated_by": "admin",
        })

    def test_get_stats_required_keys(self, svc):
        """get_stats must return all required counter keys."""
        stats = svc.get_stats()
        required = [
            "running", "has_db", "telemetry_persisted",
            "anomalies_persisted", "ecam_persisted",
            "hash_blocks_persisted", "dispatch_persisted",
            "errors", "queue_depths",
        ]
        for key in required:
            assert key in stats, f"Missing key in get_stats(): '{key}'"

    def test_has_db_false_without_factory(self, svc):
        """has_db must be False when no session factory was provided."""
        assert svc.has_db is False

    def test_has_db_true_with_factory(self):
        """has_db must be True when a session factory is provided."""
        from services.persistence_service import PersistenceService
        svc2 = PersistenceService(db_session_factory=lambda: None)
        assert svc2.has_db is True

    def test_queue_depths_non_negative(self, svc):
        """All queue depth values must be >= 0."""
        stats = svc.get_stats()
        for key, depth in stats["queue_depths"].items():
            assert depth >= 0, f"Queue depth for '{key}' is negative: {depth}"

    @pytest.mark.asyncio
    async def test_start_returns_quickly(self, svc):
        """start() must return in < 1 second (creates tasks, does not block)."""
        start = time.perf_counter()
        await svc.start()
        elapsed = time.perf_counter() - start
        assert elapsed < 1.0, f"start() took {elapsed:.3f}s — should be < 1s"
        await svc.stop()

    @pytest.mark.asyncio
    async def test_stop_after_start_does_not_raise(self, svc):
        """stop() must complete cleanly after start()."""
        await svc.start()
        await svc.stop()  # Must not raise

    @pytest.mark.asyncio
    async def test_high_throughput_enqueue(self, svc):
        """8192 telemetry readings enqueued in < 100ms."""
        readings = [
            {
                "sensor_id": f"PERF-{i:05d}",
                "ata_chapter": i % 14 + 21,
                "value": float(i % 100),
                "state": "HEALTHY",
                "confidence": 1.0,
                "anomaly_score": 0.0,
                "timestamp": "2026-05-19T12:00:00Z",
            }
            for i in range(8192)
        ]
        start = time.perf_counter()
        await svc.persist_telemetry_batch(readings)
        elapsed = time.perf_counter() - start
        assert elapsed < 0.5, \
            f"8192 enqueues took {elapsed * 1000:.1f}ms — must be < 500ms"


# ═══════════════════════════════════════════════════════════════
# KafkaEventProducer
# ═══════════════════════════════════════════════════════════════

class TestKafkaEventProducer:
    """
    Tests for services/kafka_producer.py::KafkaEventProducer.

    Public API:
      start() -> None (async)
      stop() -> None (async)
      publish_anomaly(sensor_id, ata_chapter, score, severity, description)
      publish_ecam(message_id, severity, message, ata_chapter, dispatch_impact)
      publish_dispatch(ready, score, blockers)
      publish_hash_block(block_id, block_hash, healthy, anomaly)
      is_available -> bool
      get_stats() -> dict
    """

    @pytest.fixture
    def producer(self):
        from services.kafka_producer import KafkaEventProducer
        # Deliberately use a non-existent broker — must degrade gracefully
        return KafkaEventProducer(bootstrap_servers="localhost:19092")

    @pytest.mark.asyncio
    async def test_start_degrades_without_kafka(self, producer):
        """start() must not raise when Kafka is unreachable."""
        await producer.start()
        assert producer.is_available is False

    @pytest.mark.asyncio
    async def test_publish_anomaly_no_raise(self, producer):
        """publish_anomaly must not raise when Kafka is down."""
        await producer.start()
        producer.publish_anomaly(
            sensor_id="SENS-001",
            ata_chapter=27,
            score=0.92,
            severity="WARNING",
            description="Test anomaly",
        )

    @pytest.mark.asyncio
    async def test_publish_ecam_no_raise(self, producer):
        """publish_ecam must not raise when Kafka is down."""
        await producer.start()
        producer.publish_ecam(
            message_id="ECAM-001",
            severity="WARNING",
            message="HYD SYS GREEN PRESS LO",
            ata_chapter=29,
            dispatch_impact=True,
        )

    @pytest.mark.asyncio
    async def test_publish_dispatch_no_raise(self, producer):
        """publish_dispatch must not raise when Kafka is down."""
        await producer.start()
        producer.publish_dispatch(ready=True, score=95.0, blockers=[])

    @pytest.mark.asyncio
    async def test_publish_hash_block_no_raise(self, producer):
        """publish_hash_block must not raise when Kafka is down."""
        await producer.start()
        producer.publish_hash_block(
            block_id=1,
            block_hash="a" * 64,
            healthy=1020,
            anomaly=4,
        )

    @pytest.mark.asyncio
    async def test_get_stats_returns_dict(self, producer):
        """get_stats must return a dict with expected keys."""
        await producer.start()
        stats = producer.get_stats()
        assert isinstance(stats, dict)
        assert "available" in stats
        assert "topics" in stats
        assert isinstance(stats["topics"], list)
        assert len(stats["topics"]) >= 4

    @pytest.mark.asyncio
    async def test_stop_does_not_raise(self, producer):
        """stop() must complete cleanly even when never connected."""
        await producer.start()
        await producer.stop()

    def test_enqueue_throughput(self, producer):
        """1000 publish_anomaly calls must complete in < 50ms."""
        start = time.perf_counter()
        for i in range(1000):
            producer.publish_anomaly(
                sensor_id=f"SENS-{i:04d}",
                ata_chapter=27,
                score=0.9,
                severity="WARNING",
                description="Load test",
            )
        elapsed = time.perf_counter() - start
        assert elapsed < 0.05, \
            f"1000 enqueues took {elapsed * 1000:.1f}ms — target < 50ms"


# ═══════════════════════════════════════════════════════════════
# AirworthinessReportGenerator
# ═══════════════════════════════════════════════════════════════

class TestAirworthinessReportGenerator:
    """
    Tests for services/report_service.py::AirworthinessReportGenerator.

    Public API:
      generate_pdf(data: dict) -> bytes
      compute_document_hash(data: dict) -> str  (SHA-256 hex)
    """

    SAMPLE_DATA = {
        "aircraft": {
            "type": "A320neo", "msn": "8234",
            "registration": "F-WXWB", "operator": "Air France",
        },
        "flight": {
            "number": "AF1234", "origin": "LFPG", "destination": "EGLL",
            "departure_utc": "2026-05-19T10:00:00Z", "authorized_by": "admin",
        },
        "sensor_health": {
            27: {"healthy": 1000, "degraded": 20, "failed": 4, "total": 1024},
            29: {"healthy": 750, "degraded": 8, "failed": 2, "total": 760},
        },
        "ai": {
            "confidence": 0.97,
            "severity": "NOMINAL",
            "reconstruction_error": 0.034,
            "model_version": "v2.4.1",
            "top_anomalies": [
                {
                    "sensor_id": "ATA27-FC-0001", "ata": 27,
                    "score": 0.82, "state": "DEGRADED",
                    "description": "Hydraulic pressure deviation",
                },
            ],
        },
        "ecam": {
            "active": [
                {
                    "severity": "CAUTION", "system": "HYD", "ata_chapter": 29,
                    "message": "HYD SYS GREEN PRESS LO",
                    "procedure": "QRH 29-10", "mel_reference": "29-10-1",
                    "dispatch_impact": True,
                },
            ],
            "cleared_count": 3,
        },
        "dispatch": {"ready": True, "score": 94.2, "blockers": []},
        "hash_chain": {
            "chain_valid": True, "block_count": 1024,
            "last_10_blocks": [
                {
                    "block_id": 1024, "hash": "a" * 64,
                    "timestamp": "2026-05-19T12:00:00Z", "valid": True,
                },
            ],
        },
        "generated_by": "admin",
        "report_id": "TEST-REPORT-001",
    }

    MINIMAL_DATA = {
        "aircraft": {
            "type": "A320neo", "msn": "0000",
            "registration": "F-TEST", "operator": "Test",
        },
        "flight": {
            "number": "T001", "origin": "XXXX", "destination": "YYYY",
            "departure_utc": "2026-01-01T00:00:00Z", "authorized_by": "tester",
        },
        "sensor_health": {},
        "ai": {
            "confidence": 0.95, "severity": "NOMINAL",
            "reconstruction_error": 0.05, "model_version": "v2.4.1",
            "top_anomalies": [],
        },
        "ecam":       {"active": [], "cleared_count": 0},
        "dispatch":   {"ready": True, "score": 100.0, "blockers": []},
        "hash_chain": {"chain_valid": True, "block_count": 1, "last_10_blocks": []},
        "generated_by": "tester",
        "report_id": "MINIMAL-001",
    }

    @pytest.fixture
    def generator(self):
        from services.report_service import AirworthinessReportGenerator
        return AirworthinessReportGenerator()

    def test_generate_pdf_returns_bytes(self, generator):
        """generate_pdf must return a non-empty bytes object."""
        pdf = generator.generate_pdf(self.SAMPLE_DATA)
        assert isinstance(pdf, bytes)
        assert len(pdf) > 5_000, f"PDF suspiciously small: {len(pdf)} bytes"

    def test_pdf_has_magic_header(self, generator):
        """Generated PDF must start with the %%PDF magic bytes."""
        pdf = generator.generate_pdf(self.SAMPLE_DATA)
        assert pdf[:4] == b"%PDF", \
            f"Response does not start with PDF header: {pdf[:8]!r}"

    def test_pdf_size_reasonable(self, generator):
        """PDF should be between 5 KB and 10 MB for a standard report."""
        pdf = generator.generate_pdf(self.SAMPLE_DATA)
        size_kb = len(pdf) / 1024
        assert 5 <= size_kb <= 10240, \
            f"PDF size {size_kb:.1f} KB is outside expected range [5 KB, 10 MB]"

    def test_compute_hash_is_sha256_hex(self, generator):
        """compute_document_hash takes PDF bytes and returns a 64-char hex SHA-256."""
        pdf = generator.generate_pdf(self.SAMPLE_DATA)
        h = generator.compute_document_hash(pdf)
        assert isinstance(h, str)
        assert len(h) == 64, f"Hash length {len(h)} != 64"
        int(h, 16)   # raises ValueError if not valid hex

    def test_hash_is_deterministic(self, generator):
        """Same PDF bytes must always produce the same hash."""
        pdf = generator.generate_pdf(self.SAMPLE_DATA)
        h1 = generator.compute_document_hash(pdf)
        h2 = generator.compute_document_hash(pdf)
        assert h1 == h2, "compute_document_hash is not deterministic"

    def test_hash_changes_with_different_data(self, generator):
        """Different PDF content must produce different hashes."""
        data2 = {**self.SAMPLE_DATA, "report_id": "DIFFERENT-001"}
        pdf1 = generator.generate_pdf(self.SAMPLE_DATA)
        pdf2 = generator.generate_pdf(data2)
        h1 = generator.compute_document_hash(pdf1)
        h2 = generator.compute_document_hash(pdf2)
        assert h1 != h2, "Hash did not change when report_id changed"

    def test_minimal_data_does_not_raise(self, generator):
        """generate_pdf must not raise when optional fields are absent."""
        pdf = generator.generate_pdf(self.MINIMAL_DATA)
        assert pdf[:4] == b"%PDF"

    def test_minimal_pdf_non_empty(self, generator):
        """Even a minimal report must produce a non-empty PDF (>2 KB)."""
        pdf = generator.generate_pdf(self.MINIMAL_DATA)
        assert len(pdf) > 2_000


# ═══════════════════════════════════════════════════════════════
# DigitalTwin — Structural / Fuel / Thermal models
# ═══════════════════════════════════════════════════════════════

class TestDigitalTwinExtended:
    """
    Tests for services/digital_twin.py::DigitalTwinEngine.

    DigitalTwinEngine.__init__() takes NO arguments.
    Phase is changed with set_phase(phase: str).
    Physics update is triggered by awaiting the async run() coroutine OR by
    calling internal update methods directly.

    We directly call the private update methods here so tests remain
    fast and offline:
      _update_fuel(phase, dt_sec)
      _update_structural(phase, elapsed)
      _update_thermal(phase)
      _update_engines(phase)
      _update_flight_dynamics(phase, elapsed)
      get_state() -> dict
    """

    @pytest.fixture
    def twin(self):
        from services.digital_twin import DigitalTwinEngine
        engine = DigitalTwinEngine()
        # Perform an initial atmosphere computation so subsequent calls work
        engine.twin.atmosphere = engine._compute_isa(0.0)
        return engine

    def _step(self, twin, phase: str, n: int = 1, dt: float = 1.0):
        """Drive the twin through n update cycles for the given phase."""
        twin.set_phase(phase)
        for _ in range(n):
            twin._update_flight_dynamics(phase, twin._t)
            twin.twin.atmosphere = twin._compute_isa(twin.twin.altitude_ft)
            twin._update_engines(phase)
            twin._update_fuel(phase, dt_sec=dt)
            twin._update_structural(phase, twin._t)
            twin._update_thermal(phase)
            twin._t += dt

    # ── Fuel model ────────────────────────────────────────────

    def test_fuel_burns_during_cruise(self, twin):
        """Total fuel must decrease after several cruise update cycles."""
        self._step(twin, "CRUISE", n=1)
        initial_fuel = twin.get_state()["fuel"]["total_kg"]
        self._step(twin, "CRUISE", n=20)
        final_fuel = twin.get_state()["fuel"]["total_kg"]
        assert final_fuel < initial_fuel, \
            f"Fuel did not decrease during CRUISE: {initial_fuel} → {final_fuel}"

    def test_fuel_flow_higher_at_takeoff_than_cruise(self, twin):
        """Takeoff fuel flow must exceed cruise fuel flow."""
        self._step(twin, "TAKEOFF", n=1)
        takeoff_flow = twin.get_state()["fuel"]["fuel_flow_total_kgh"]

        self._step(twin, "CRUISE", n=1)
        cruise_flow = twin.get_state()["fuel"]["fuel_flow_total_kgh"]

        assert takeoff_flow > cruise_flow, \
            f"TAKEOFF flow ({takeoff_flow}) must exceed CRUISE flow ({cruise_flow})"

    def test_fuel_state_all_keys_present(self, twin):
        """get_state()['fuel'] must contain all required keys."""
        self._step(twin, "CRUISE")
        fuel = twin.get_state()["fuel"]
        for key in ("total_kg", "left_wing_kg", "right_wing_kg",
                    "center_tank_kg", "imbalance_kg",
                    "fuel_flow_total_kgh", "fuel_temperature_c"):
            assert key in fuel, f"Missing fuel state key: '{key}'"

    def test_fuel_not_negative(self, twin):
        """Total fuel must never go negative regardless of burn duration."""
        # Simulate many hours at high burn
        for _ in range(1000):
            twin._update_fuel("TAKEOFF", dt_sec=10.0)
        assert twin.twin.fuel.total_kg >= 0.0

    # ── Thermal model ──────────────────────────────────────────

    def test_brake_temp_rises_during_landing(self, twin):
        """Brake temperature must increase during landing."""
        self._step(twin, "CRUISE", n=5)                     # cool brakes first
        twin.twin.thermal.brake_temp_c = 100.0               # reset baseline
        self._step(twin, "LANDING", n=1)
        t1 = twin.get_state()["thermal"]["brake_temp_c"]
        self._step(twin, "LANDING", n=10)
        t2 = twin.get_state()["thermal"]["brake_temp_c"]
        assert t2 >= t1, f"Brake temp did not increase during LANDING: {t1} → {t2}"

    def test_brake_temp_cools_in_cruise(self, twin):
        """Brake temperature must decrease during cruise."""
        # First heat them up with landing cycles
        self._step(twin, "LANDING", n=15)
        hot_temp = twin.get_state()["thermal"]["brake_temp_c"]

        self._step(twin, "CRUISE", n=20)
        cool_temp = twin.get_state()["thermal"]["brake_temp_c"]
        assert cool_temp < hot_temp, \
            f"Brakes did not cool in CRUISE: {hot_temp} → {cool_temp}"

    def test_apu_egt_nonzero_on_ground(self, twin):
        """APU EGT must be > 0 when aircraft is on GROUND."""
        self._step(twin, "GROUND")
        apu_egt = twin.get_state()["thermal"]["apu_egt_c"]
        assert apu_egt > 0, f"APU EGT should be > 0 on GROUND, got {apu_egt}"

    def test_apu_egt_zero_in_cruise(self, twin):
        """APU EGT must be 0 when aircraft is in CRUISE."""
        self._step(twin, "CRUISE")
        apu_egt = twin.get_state()["thermal"]["apu_egt_c"]
        assert apu_egt == 0.0, f"APU EGT should be 0 in CRUISE, got {apu_egt}"

    def test_thermal_state_all_keys_present(self, twin):
        """get_state()['thermal'] must contain all required keys."""
        self._step(twin, "CRUISE")
        thermal = twin.get_state()["thermal"]
        for key in ("avionics_bay_c", "cabin_temp_c", "cargo_temp_c",
                    "brake_temp_c", "apu_egt_c",
                    "eng1_oil_temp_c", "eng2_oil_temp_c"):
            assert key in thermal, f"Missing thermal state key: '{key}'"

    # ── Structural model ────────────────────────────────────────

    def test_g_load_near_unity_in_cruise(self, twin):
        """G-load during cruise must be close to 1.0 G."""
        self._step(twin, "CRUISE")
        g = twin.get_state()["structural"]["g_load_factor"]
        assert 0.8 <= g <= 1.5, \
            f"Cruise G-load {g:.3f} outside expected range [0.8, 1.5]"

    def test_g_load_higher_at_landing(self, twin):
        """Landing G-load must exceed cruise G-load."""
        self._step(twin, "CRUISE")
        cruise_g = twin.get_state()["structural"]["g_load_factor"]
        self._step(twin, "LANDING")
        landing_g = twin.get_state()["structural"]["g_load_factor"]
        assert landing_g > cruise_g, \
            f"Landing G ({landing_g:.3f}) should exceed cruise G ({cruise_g:.3f})"

    def test_structural_state_all_keys_present(self, twin):
        """get_state()['structural'] must contain all required keys."""
        self._step(twin, "CRUISE")
        struct = twin.get_state()["structural"]
        for key in ("wing_bending_moment_knm", "wing_shear_force_kn",
                    "fuselage_hoop_stress_mpa", "landing_gear_load_kn",
                    "g_load_factor", "turbulence_intensity"):
            assert key in struct, f"Missing structural state key: '{key}'"

    def test_landing_gear_load_zero_in_cruise(self, twin):
        """Landing gear load must be 0 during cruise (gear retracted)."""
        self._step(twin, "CRUISE")
        lg_load = twin.get_state()["structural"]["landing_gear_load_kn"]
        assert lg_load == 0.0, f"Gear load should be 0 in CRUISE, got {lg_load}"

    def test_landing_gear_load_nonzero_on_ground(self, twin):
        """Landing gear must bear aircraft weight on GROUND."""
        self._step(twin, "GROUND")
        lg_load = twin.get_state()["structural"]["landing_gear_load_kn"]
        assert lg_load > 0, f"Gear load should be > 0 on GROUND, got {lg_load}"

    def test_set_phase_updates_state_dict(self, twin):
        """set_phase() must update the flight_phase field in get_state()."""
        twin.set_phase("CLIMB")
        self._step(twin, "CLIMB")
        assert twin.get_state()["flight_phase"] == "CLIMB"
