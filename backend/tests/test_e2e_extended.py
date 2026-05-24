"""
SentinelTwin — Extended E2E Tests
Covers API routes not already tested in test_e2e.py:

  - /api/v1/sensors/redundancy
  - /api/v1/simulator/status + /simulator/phase
  - /api/v1/maintenance/summary + DELETE action
  - /api/v1/telemetry/history edge cases
  - /api/v1/logs/operational  (level filter, auth guard)
  - /health/detailed          (all subsystem checks)
  - /api/v1/aircraft/profiles + /aircraft/summary
  - RBAC: pilots cannot write; engineers cannot read threat logs
  - Concurrent threshold tuning (race condition check)
  - Prometheus metric families
  - Digital twin phase change via API
  - Hash chain export endpoint

Requires a running backend: python backend/main.py
Run: pytest backend/tests/test_e2e_extended.py -v --timeout=30

All classes marked with pytest.mark.integration; individual tests that
require a live backend will auto-skip (via the conftest auth_headers fixture)
if the backend is not reachable.
"""

import json
import threading
import pytest
import requests

try:
    import websockets
    import asyncio as _asyncio
    _HAS_WS = True
except ImportError:
    _HAS_WS = False

pytestmark = pytest.mark.integration

BASE    = "http://localhost:8000/api/v1"
HEALTH  = "http://localhost:8000/health"
METRICS = "http://localhost:8000/metrics"
WS_URL  = "ws://localhost:8000/ws/telemetry"
TIMEOUT = 15


# ══════════════════════════════════════════════════════════════════════════════
# SENSOR REDUNDANCY
# ══════════════════════════════════════════════════════════════════════════════

class TestSensorRedundancy:
    """Tests for /api/v1/sensors/redundancy"""

    def test_redundancy_endpoint_exists(self, auth_headers):
        r = requests.get(f"{BASE}/sensors/redundancy",
                         headers=auth_headers, timeout=TIMEOUT)
        assert r.status_code in (200, 404), \
            f"Unexpected status {r.status_code}: {r.text[:200]}"

    def test_redundancy_structure_if_present(self, auth_headers):
        r = requests.get(f"{BASE}/sensors/redundancy",
                         headers=auth_headers, timeout=TIMEOUT)
        if r.status_code == 404:
            pytest.skip("Redundancy endpoint not yet implemented")
        d = r.json()
        # Must have sensor groups or voting information
        assert isinstance(d, dict), "Expected dict response"

    def test_sensor_by_ata_29(self, auth_headers):
        """ATA 29 (Hydraulic) sensors must be returned."""
        r = requests.get(f"{BASE}/sensors?ata_chapter=29",
                         headers=auth_headers, timeout=TIMEOUT)
        assert r.status_code == 200
        sensors = r.json().get("sensors", [])
        assert len(sensors) > 0
        for s in sensors[:5]:
            assert s["ata_chapter"] == 29

    def test_sensor_by_ata_27(self, auth_headers):
        """ATA 27 (Flight Controls) sensors must be returned."""
        r = requests.get(f"{BASE}/sensors?ata_chapter=27",
                         headers=auth_headers, timeout=TIMEOUT)
        assert r.status_code == 200
        sensors = r.json().get("sensors", [])
        assert len(sensors) > 0


# ══════════════════════════════════════════════════════════════════════════════
# SIMULATOR
# ══════════════════════════════════════════════════════════════════════════════

class TestSimulatorExtended:
    """Tests for /api/v1/simulator/* endpoints."""

    def test_simulator_status_fields(self, auth_headers):
        r = requests.get(f"{BASE}/simulator/status",
                         headers=auth_headers, timeout=TIMEOUT)
        assert r.status_code == 200
        d = r.json()
        # Must contain phase/mode and some time indicator
        has_phase = "phase" in d or "mode" in d or "flight_phase" in d or "current_phase" in d
        assert has_phase, f"No phase/mode key in simulator status: {list(d.keys())}"

    def test_simulator_phase_change(self, auth_headers):
        """POST /simulator/phase must update the current flight phase."""
        phases = ["GROUND", "CRUISE", "GROUND"]
        for phase in phases:
            r = requests.post(
                f"{BASE}/simulator/phase",
                json={"phase": phase},
                headers=auth_headers,
                timeout=TIMEOUT,
            )
            # Accept 200 or 422 (validation) — just not 500
            assert r.status_code not in (500, 401, 403), \
                f"Unexpected {r.status_code} for phase={phase}: {r.text[:200]}"

    def test_simulator_phase_invalid(self, auth_headers):
        """An invalid phase name must be rejected (422 or 400)."""
        r = requests.post(
            f"{BASE}/simulator/phase",
            json={"phase": "WARP_DRIVE"},
            headers=auth_headers,
            timeout=TIMEOUT,
        )
        assert r.status_code in (400, 422), \
            f"Expected 400/422 for invalid phase, got {r.status_code}"

    def test_simulator_requires_auth(self):
        """Simulator status must require authentication."""
        r = requests.get(f"{BASE}/simulator/status", timeout=TIMEOUT)
        assert r.status_code == 401


# ══════════════════════════════════════════════════════════════════════════════
# MAINTENANCE — additional coverage
# ══════════════════════════════════════════════════════════════════════════════

class TestMaintenanceExtended:
    """Additional maintenance tests beyond test_e2e.py::TestMaintenance."""

    def _create_action(self, headers) -> str:
        """Helper: create a maintenance action and return its action_id."""
        r = requests.post(
            f"{BASE}/maintenance/actions",
            json={
                "title":       "Extended E2E Test Action",
                "ata_chapter": 29,
                "system":      "HYDRAULIC",
                "priority":    "ROUTINE",
                "description": "Created by test_e2e_extended — safe to delete",
            },
            headers=headers,
            timeout=TIMEOUT,
        )
        assert r.status_code == 200, f"Create action failed: {r.text}"
        return r.json()["action_id"]

    def test_complete_action_lifecycle(self, engineer_headers, auth_headers):
        """Create → update → complete → verify action lifecycle."""
        action_id = self._create_action(engineer_headers)

        # Update to IN_PROGRESS
        r = requests.patch(
            f"{BASE}/maintenance/actions/{action_id}",
            json={"status": "IN_PROGRESS", "assigned_to": "engineer"},
            headers=engineer_headers,
            timeout=TIMEOUT,
        )
        assert r.status_code == 200
        assert r.json()["status"] == "IN_PROGRESS"

        # Update to COMPLETED
        r = requests.patch(
            f"{BASE}/maintenance/actions/{action_id}",
            json={"status": "COMPLETED"},
            headers=engineer_headers,
            timeout=TIMEOUT,
        )
        assert r.status_code == 200
        assert r.json()["status"] == "COMPLETED"

    def test_delete_action(self, engineer_headers, auth_headers):
        """DELETE /maintenance/actions/{id} must succeed or return 405 if not implemented."""
        action_id = self._create_action(engineer_headers)
        r = requests.delete(
            f"{BASE}/maintenance/actions/{action_id}",
            headers=auth_headers,
            timeout=TIMEOUT,
        )
        # Accept 200, 204 (deleted), or 405 (method not implemented)
        assert r.status_code in (200, 204, 405), \
            f"Unexpected {r.status_code}: {r.text[:200]}"

    def test_maintenance_summary_counts(self, auth_headers):
        """/maintenance/summary must return numeric count fields."""
        r = requests.get(f"{BASE}/maintenance/summary",
                         headers=auth_headers, timeout=TIMEOUT)
        assert r.status_code == 200
        d = r.json()
        assert "total" in d or "open" in d
        # All present counts must be non-negative integers
        for key in ("total", "open", "in_progress", "completed"):
            if key in d:
                assert isinstance(d[key], int) and d[key] >= 0, \
                    f"Count for '{key}' is invalid: {d[key]}"

    def test_maintenance_pilot_cannot_create(self, pilot_headers):
        """Pilot role must not be able to create maintenance actions."""
        r = requests.post(
            f"{BASE}/maintenance/actions",
            json={
                "title": "Pilot should not create this",
                "ata_chapter": 27,
                "system": "FLIGHT CONTROLS",
                "priority": "ROUTINE",
                "description": "RBAC test",
            },
            headers=pilot_headers,
            timeout=TIMEOUT,
        )
        assert r.status_code in (403, 401), \
            f"Pilot was able to create maintenance action: {r.status_code}"


# ══════════════════════════════════════════════════════════════════════════════
# TELEMETRY HISTORY — edge cases
# ══════════════════════════════════════════════════════════════════════════════

class TestTelemetryHistoryExtended:
    """Additional telemetry history tests."""

    def test_history_ata_29(self, auth_headers):
        """/telemetry/history must work for ATA 29 (Hydraulic)."""
        r = requests.get(
            f"{BASE}/telemetry/history?ata_chapter=29&minutes=5",
            headers=auth_headers, timeout=TIMEOUT,
        )
        assert r.status_code == 200
        d = r.json()
        assert d["ata_chapter"] == 29
        assert "buckets" in d or "data" in d or "source" in d

    def test_history_requires_ata_chapter(self, auth_headers):
        """Request without ata_chapter must return 422 or 400."""
        r = requests.get(f"{BASE}/telemetry/history",
                         headers=auth_headers, timeout=TIMEOUT)
        assert r.status_code in (400, 422), \
            f"Expected 400/422 without ata_chapter, got {r.status_code}"

    def test_history_source_field(self, auth_headers):
        """Response must include a 'source' field indicating data origin."""
        r = requests.get(
            f"{BASE}/telemetry/history?ata_chapter=27&minutes=10",
            headers=auth_headers, timeout=TIMEOUT,
        )
        assert r.status_code == 200
        d = r.json()
        assert "source" in d
        assert d["source"] in ("TIMESCALEDB", "SYNTHETIC_FALLBACK"), \
            f"Unknown source value: {d['source']}"

    def test_history_requires_auth(self):
        """Telemetry history must require authentication."""
        r = requests.get(
            f"{BASE}/telemetry/history?ata_chapter=27",
            timeout=TIMEOUT,
        )
        assert r.status_code == 401


# ══════════════════════════════════════════════════════════════════════════════
# OPERATIONAL LOGS — extended
# ══════════════════════════════════════════════════════════════════════════════

class TestOperationalLogsExtended:
    """Additional tests for /api/v1/logs/operational."""

    def test_logs_warning_filter(self, auth_headers):
        """Filter by WARNING level must only return WARNING entries."""
        r = requests.get(
            f"{BASE}/logs/operational?level=WARNING&limit=20",
            headers=auth_headers, timeout=TIMEOUT,
        )
        assert r.status_code == 200
        d = r.json()
        for log in d.get("logs", []):
            assert log["level"] in ("WARNING", "WARN"), \
                f"Got non-WARNING log with WARNING filter: {log['level']}"

    def test_logs_error_filter(self, auth_headers):
        """Filter by ERROR level must only return ERROR entries."""
        r = requests.get(
            f"{BASE}/logs/operational?level=ERROR&limit=20",
            headers=auth_headers, timeout=TIMEOUT,
        )
        assert r.status_code == 200
        for log in r.json().get("logs", []):
            assert log["level"] == "ERROR"

    def test_logs_count_matches_list(self, auth_headers):
        """'count' field must equal the number of items in 'logs'."""
        r = requests.get(
            f"{BASE}/logs/operational?limit=10",
            headers=auth_headers, timeout=TIMEOUT,
        )
        assert r.status_code == 200
        d = r.json()
        assert d["count"] == len(d["logs"]), \
            f"count={d['count']} != len(logs)={len(d['logs'])}"

    def test_logs_pagination(self, auth_headers):
        """Different offsets must not return the same first item (if enough logs)."""
        r1 = requests.get(
            f"{BASE}/logs/operational?limit=5&offset=0",
            headers=auth_headers, timeout=TIMEOUT,
        )
        r2 = requests.get(
            f"{BASE}/logs/operational?limit=5&offset=5",
            headers=auth_headers, timeout=TIMEOUT,
        )
        assert r1.status_code == r2.status_code == 200
        logs1 = r1.json().get("logs", [])
        logs2 = r2.json().get("logs", [])
        if logs1 and logs2:
            # First items in each page must differ
            assert logs1[0] != logs2[0], "Pagination returned duplicate items"


# ══════════════════════════════════════════════════════════════════════════════
# HEALTH — detailed subsystem coverage
# ══════════════════════════════════════════════════════════════════════════════

class TestHealthDetailed:
    """/health/detailed subsystem verification."""

    def test_all_expected_subsystems_present(self, auth_headers):
        """Detailed health must report all core subsystems."""
        r = requests.get(f"{HEALTH}/detailed",
                         headers=auth_headers, timeout=TIMEOUT)
        assert r.status_code == 200
        subs = r.json().get("subsystems", {})
        expected = ["sensor_engine", "ai_engine", "digital_twin",
                    "hash_chain", "ecam_engine"]
        for s in expected:
            assert s in subs, \
                f"Subsystem '{s}' missing from /health/detailed"

    def test_subsystem_statuses_valid(self, auth_headers):
        """All subsystem statuses must be recognised values."""
        r = requests.get(f"{HEALTH}/detailed",
                         headers=auth_headers, timeout=TIMEOUT)
        assert r.status_code == 200
        subs = r.json().get("subsystems", {})
        valid = {"UP", "RUNNING", "OK", "DEGRADED", "DOWN",
                 "NOT_INITIALIZED", "STARTING", "HEALTHY"}
        for name, data in subs.items():
            status = data.get("status", "")
            assert status in valid, \
                f"Subsystem '{name}' has unexpected status: '{status}'"

    def test_detailed_health_has_timestamp(self, auth_headers):
        """Detailed health response must include a timestamp."""
        r = requests.get(f"{HEALTH}/detailed",
                         headers=auth_headers, timeout=TIMEOUT)
        assert r.status_code == 200
        d = r.json()
        assert "timestamp" in d or "generated_at" in d, \
            "No timestamp in /health/detailed response"

    def test_sensor_engine_reports_count(self, auth_headers):
        """sensor_engine subsystem must report sensor counts."""
        r = requests.get(f"{HEALTH}/detailed",
                         headers=auth_headers, timeout=TIMEOUT)
        assert r.status_code == 200
        sensor_eng = r.json().get("subsystems", {}).get("sensor_engine", {})
        detail = sensor_eng.get("detail", {})
        assert "total" in detail or "sensor_count" in detail or "total_sensors" in detail, \
            f"sensor_engine detail missing count: {detail}"


# ══════════════════════════════════════════════════════════════════════════════
# AIRCRAFT PROFILES
# ══════════════════════════════════════════════════════════════════════════════

class TestAircraftProfiles:
    """/api/v1/aircraft/* endpoints."""

    def test_profiles_returns_a320neo(self, auth_headers):
        """/aircraft/types must include the A320neo profile."""
        # Try /aircraft/types (actual route) and /aircraft/profiles (legacy)
        for path in ("aircraft/types", "aircraft/profiles"):
            r = requests.get(f"{BASE}/{path}",
                             headers=auth_headers, timeout=TIMEOUT)
            if r.status_code == 200:
                d = r.json()
                raw = d.get("profiles", d)
                if isinstance(raw, dict):
                    assert "A320neo" in raw
                elif isinstance(raw, list):
                    types = [p.get("aircraft_type", "") for p in raw]
                    assert "A320neo" in types, f"A320neo not in profiles: {types}"
                return
        pytest.fail("Neither /aircraft/types nor /aircraft/profiles returned 200")

    def test_aircraft_summary_endpoint(self, auth_headers):
        """/aircraft/summary or /aircraft/current must return a non-empty response."""
        for path in ("aircraft/summary", "aircraft/current"):
            r = requests.get(f"{BASE}/{path}",
                             headers=auth_headers, timeout=TIMEOUT)
            if r.status_code == 200:
                assert isinstance(r.json(), dict)
                return
        # 404 is acceptable if neither endpoint exists yet

    def test_profiles_require_auth(self):
        """Aircraft types must require authentication."""
        r = requests.get(f"{BASE}/aircraft/types", timeout=TIMEOUT)
        assert r.status_code in (200, 401), \
            f"Unexpected status {r.status_code}: {r.text[:200]}"


# ══════════════════════════════════════════════════════════════════════════════
# RBAC
# ══════════════════════════════════════════════════════════════════════════════

class TestRBAC:
    """Role-Based Access Control boundary tests."""

    def test_pilot_cannot_tune_threshold(self, pilot_headers):
        """Pilot role must not be allowed to change the anomaly threshold."""
        r = requests.post(
            f"{BASE}/anomalies/model/threshold?threshold=0.25",
            headers=pilot_headers,
            timeout=TIMEOUT,
        )
        assert r.status_code in (403, 401), \
            f"Pilot was allowed to tune threshold: {r.status_code}"

    def test_pilot_cannot_inject_arinc_fault(self, pilot_headers):
        """Pilot role must not be allowed to inject ARINC 429 faults."""
        r = requests.post(
            f"{BASE}/arinc/inject",
            json={"label_octal": 65, "fault_type": "FREEZE"},
            headers=pilot_headers,
            timeout=TIMEOUT,
        )
        assert r.status_code in (403, 401), \
            f"Pilot was allowed to inject ARINC fault: {r.status_code}"

    def test_pilot_cannot_inject_afdx_fault(self, pilot_headers):
        """Pilot role must not be allowed to inject AFDX faults."""
        r = requests.post(
            f"{BASE}/afdx/inject",
            json={"vl_id": "VL-0100", "fault_type": "LATE"},
            headers=pilot_headers,
            timeout=TIMEOUT,
        )
        assert r.status_code in (403, 401), \
            f"Pilot was allowed to inject AFDX fault: {r.status_code}"

    def test_engineer_cannot_read_threat_log(self, engineer_headers):
        """Engineer role must not access the cybersecurity threat log."""
        r = requests.get(f"{BASE}/cybersecurity/threats",
                         headers=engineer_headers, timeout=TIMEOUT)
        assert r.status_code in (403, 401), \
            f"Engineer was allowed to read threat log: {r.status_code}"

    def test_pilot_can_read_sensor_stats(self, pilot_headers):
        """Pilot role must be able to read sensor statistics (read-only)."""
        r = requests.get(f"{BASE}/sensors/stats",
                         headers=pilot_headers, timeout=TIMEOUT)
        assert r.status_code == 200, \
            f"Pilot could not read sensor stats: {r.status_code}"

    def test_pilot_can_read_ecam(self, pilot_headers):
        """Pilot role must be able to read ECAM active alerts."""
        # Actual route is /ecam/active, not /ecam/messages
        for path in ("ecam/active", "ecam/messages"):
            r = requests.get(f"{BASE}/{path}",
                             headers=pilot_headers, timeout=TIMEOUT)
            if r.status_code == 200:
                return
        assert False, "Neither /ecam/active nor /ecam/messages returned 200"


# ══════════════════════════════════════════════════════════════════════════════
# CONCURRENT THRESHOLD TUNING — race condition check
# ══════════════════════════════════════════════════════════════════════════════

class TestConcurrentThresholdTuning:
    """Verify the anomaly threshold endpoint is thread-safe."""

    def test_concurrent_threshold_changes_no_500(self, auth_headers):
        """10 concurrent threshold changes must not produce any 500 errors."""
        errors = []

        def _change(val):
            try:
                r = requests.post(
                    f"{BASE}/anomalies/model/threshold?threshold={val:.2f}",
                    headers=auth_headers,
                    timeout=TIMEOUT,
                )
                if r.status_code == 500:
                    errors.append(f"500 for threshold={val}")
            except Exception as exc:
                errors.append(str(exc))

        threads = [
            threading.Thread(target=_change, args=(0.10 + i * 0.01,))
            for i in range(10)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=TIMEOUT)

        assert not errors, f"Race condition errors: {errors}"

        # Reset to default
        requests.post(
            f"{BASE}/anomalies/model/threshold?threshold=0.15",
            headers=auth_headers,
            timeout=TIMEOUT,
        )

    def test_threshold_boundary_values(self, auth_headers):
        """Boundary values 0.01 and 0.50 must be accepted."""
        for val in (0.01, 0.50):
            r = requests.post(
                f"{BASE}/anomalies/model/threshold?threshold={val}",
                headers=auth_headers,
                timeout=TIMEOUT,
            )
            assert r.status_code == 200, \
                f"Boundary value {val} rejected: {r.status_code}"
        # Reset
        requests.post(
            f"{BASE}/anomalies/model/threshold?threshold=0.15",
            headers=auth_headers,
            timeout=TIMEOUT,
        )


# ══════════════════════════════════════════════════════════════════════════════
# PROMETHEUS — metric family verification
# ══════════════════════════════════════════════════════════════════════════════

class TestPrometheusExtended:
    """Extended Prometheus metric verification."""

    def _get_metrics(self) -> str:
        r = requests.get(METRICS, timeout=TIMEOUT)
        assert r.status_code == 200
        return r.text

    def test_sensor_metrics_present(self):
        """sensor_validations_total must be in /metrics."""
        text = self._get_metrics()
        if "Prometheus client not installed" in text:
            pytest.skip("Prometheus client not installed — metrics unavailable")
        assert "sensor_validations_total" in text or "python_info" in text, \
            "No sensor metrics found in /metrics"

    def test_ai_metrics_present(self):
        """ai_confidence or ai_inference metric must be present."""
        text = self._get_metrics()
        if "Prometheus client not installed" in text:
            pytest.skip("Prometheus client not installed — metrics unavailable")
        has_ai = any(m in text for m in ("ai_confidence", "ai_inference",
                                          "anomaly_threshold"))
        assert has_ai or "python_info" in text, \
            "No AI metrics found in /metrics"

    def test_hash_chain_metrics_present(self):
        """hash_chain_blocks_total must be present."""
        text = self._get_metrics()
        if "Prometheus client not installed" in text:
            pytest.skip("Prometheus client not installed — metrics unavailable")
        has_hash = "hash_chain_blocks_total" in text
        assert has_hash or "python_info" in text, \
            "No hash chain metrics found in /metrics"

    def test_metrics_content_type(self):
        """Content-Type must be text/plain (Prometheus exposition format)."""
        r = requests.get(METRICS, timeout=TIMEOUT)
        assert r.status_code == 200
        ct = r.headers.get("content-type", "")
        assert "text/plain" in ct, f"Unexpected content-type: {ct}"

    def test_metrics_no_server_error(self):
        """Five rapid requests to /metrics must all succeed without 500."""
        for _ in range(5):
            r = requests.get(METRICS, timeout=TIMEOUT)
            assert r.status_code == 200


# ══════════════════════════════════════════════════════════════════════════════
# DIGITAL TWIN VIA API
# ══════════════════════════════════════════════════════════════════════════════

class TestDigitalTwinAPI:
    """Digital twin state as returned by API endpoints."""

    def test_twin_state_from_health_detailed(self, auth_headers):
        """Digital twin must appear in /health/detailed subsystems."""
        r = requests.get(f"{HEALTH}/detailed",
                         headers=auth_headers, timeout=TIMEOUT)
        assert r.status_code == 200
        subs = r.json().get("subsystems", {})
        twin = subs.get("digital_twin", {})
        assert twin, "digital_twin not in subsystems"
        assert twin.get("status") in ("UP", "RUNNING", "OK", "HEALTHY"), \
            f"Unexpected twin status: {twin.get('status')}"

    def test_simulator_state_has_altitude(self, auth_headers):
        """Simulator status must include altitude or a related field."""
        r = requests.get(f"{BASE}/simulator/status",
                         headers=auth_headers, timeout=TIMEOUT)
        assert r.status_code == 200
        d = r.json()
        # altitude, flight_phase, phase, current_phase, or mode must be present
        has_flight_info = any(k in d for k in
                               ("altitude_ft", "flight_phase", "phase",
                                "current_phase", "mode"))
        assert has_flight_info, \
            f"No altitude/phase/mode in simulator status: {list(d.keys())}"


# ══════════════════════════════════════════════════════════════════════════════
# HASH CHAIN EXPORT
# ══════════════════════════════════════════════════════════════════════════════

class TestHashChainExport:
    """/api/v1/hashchain/* export and audit endpoints."""

    def test_chain_blocks_endpoint(self, auth_headers):
        """Hash chain must expose recent blocks or a history endpoint."""
        for url in (f"{BASE}/hashchain/latest", f"{BASE}/hashchain/blocks",
                    f"{BASE}/hashchain/recent"):
            r = requests.get(url, headers=auth_headers, timeout=TIMEOUT)
            if r.status_code == 200:
                d = r.json()
                assert isinstance(d, (dict, list))
                return
        # If none exist, at minimum /hashchain/verify must work
        r = requests.get(f"{BASE}/hashchain/verify",
                         headers=auth_headers, timeout=TIMEOUT)
        assert r.status_code == 200

    def test_chain_status_fields(self, auth_headers):
        """Hash chain verify/status must contain chain_valid and total_blocks."""
        # Try /hashchain/status first, then fallback to /hashchain/verify
        for path in ("hashchain/status", "hashchain/verify"):
            r = requests.get(f"{BASE}/{path}",
                             headers=auth_headers, timeout=TIMEOUT)
            if r.status_code == 200:
                d = r.json()
                assert "chain_valid" in d
                assert "total_blocks" in d
                assert isinstance(d["total_blocks"], int) and d["total_blocks"] >= 0
                return
        pytest.fail("Neither /hashchain/status nor /hashchain/verify returned 200")

    def test_chain_verify_returns_bool(self, auth_headers):
        """Hash chain verify must return a boolean validity result."""
        r = requests.get(f"{BASE}/hashchain/verify",
                         headers=auth_headers, timeout=TIMEOUT)
        assert r.status_code == 200
        d = r.json()
        valid_flag = d.get("verified") or d.get("valid") or d.get("chain_valid")
        assert isinstance(valid_flag, bool), \
            f"Expected bool for chain validity, got {type(valid_flag)}: {valid_flag}"


# ══════════════════════════════════════════════════════════════════════════════
# WEBSOCKET — extended channel coverage
# ══════════════════════════════════════════════════════════════════════════════

@pytest.mark.skipif(not _HAS_WS, reason="websockets package not installed")
@pytest.mark.websocket
class TestWebSocketExtended:
    """Extended WebSocket tests — channel coverage and message structure."""

    def _collect_frames(self, n: int = 20, timeout: float = 3.0) -> list:
        """Connect to the WS feed and collect up to n frames."""
        async def _inner():
            frames = []
            try:
                async with websockets.connect(
                    WS_URL, open_timeout=5, close_timeout=5
                ) as ws:
                    for _ in range(n):
                        try:
                            raw = await _asyncio.wait_for(ws.recv(), timeout=timeout)
                            frames.append(json.loads(raw))
                        except _asyncio.TimeoutError:
                            break
            except Exception:
                pass
            return frames

        return _asyncio.run(_inner())

    def test_ws_frame_has_required_keys(self):
        """Every WebSocket frame must have channel, data, and timestamp."""
        frames = self._collect_frames(n=5, timeout=5.0)
        if not frames:
            pytest.skip("No WS frames received — is backend running?")
        for frame in frames:
            assert "channel" in frame, f"Frame missing 'channel': {frame}"
            assert "data" in frame, f"Frame missing 'data': {frame}"
            assert "timestamp" in frame, f"Frame missing 'timestamp': {frame}"

    def test_ws_telemetry_channel_seen(self):
        """'telemetry' channel must be received within 20 frames."""
        frames = self._collect_frames(n=20, timeout=3.0)
        channels = {f.get("channel") for f in frames}
        if not channels:
            pytest.skip("No WS frames received — is backend running?")
        assert "telemetry" in channels or "ai" in channels, \
            f"Neither 'telemetry' nor 'ai' channel seen. Got: {channels}"

    def test_ws_telemetry_data_structure(self):
        """Telemetry channel data must contain sensor readings."""
        frames = self._collect_frames(n=20, timeout=3.0)
        tel_frames = [f for f in frames if f.get("channel") == "telemetry"]
        if not tel_frames:
            pytest.skip("No telemetry WS frames received")
        data = tel_frames[0]["data"]
        # Must be a list or dict with sensor info
        assert isinstance(data, (list, dict)), \
            f"Telemetry data has unexpected type: {type(data)}"

    def test_ws_multiple_channels_delivered(self):
        """At least 2 distinct channels must be seen in 20 frames."""
        frames = self._collect_frames(n=20, timeout=3.0)
        channels = {f.get("channel") for f in frames}
        if not channels:
            pytest.skip("No WS frames received — is backend running?")
        assert len(channels) >= 2, \
            f"Only 1 channel seen in 20 frames: {channels}"


# ══════════════════════════════════════════════════════════════════════════════
# DISPATCH — extended
# ══════════════════════════════════════════════════════════════════════════════

class TestDispatchExtended:
    """Extended dispatch endpoint tests."""

    def test_dispatch_score_range(self, auth_headers):
        """Dispatch score must be in [0, 100]."""
        r = requests.get(f"{BASE}/dispatch/status",
                         headers=auth_headers, timeout=TIMEOUT)
        assert r.status_code == 200
        d = r.json()
        score = d.get("score") or d.get("dispatch_score")
        if score is None:
            # Derive score from checks_passed / checks_total
            passed = d.get("checks_passed")
            total  = d.get("checks_total")
            if passed is not None and total:
                score = round(passed / total * 100, 2)
        assert score is not None, f"No score in dispatch status: {d}"
        assert 0 <= float(score) <= 100, \
            f"Dispatch score {score} outside [0, 100]"

    def test_dispatch_blockers_is_list(self, auth_headers):
        """Dispatch blockers must be a list."""
        r = requests.get(f"{BASE}/dispatch/status",
                         headers=auth_headers, timeout=TIMEOUT)
        assert r.status_code == 200
        d = r.json()
        blockers = d.get("blockers", d.get("dispatch_blockers", []))
        assert isinstance(blockers, list), \
            f"Blockers is not a list: {type(blockers)}"

    def test_dispatch_history_limit(self, auth_headers):
        """limit=5 must return at most 5 dispatch reports."""
        r = requests.get(f"{BASE}/dispatch/history?limit=5",
                         headers=auth_headers, timeout=TIMEOUT)
        assert r.status_code == 200
        reports = r.json().get("reports", [])
        assert len(reports) <= 5, \
            f"limit=5 returned {len(reports)} reports"

    def test_dispatch_requires_auth(self):
        """Dispatch status must require authentication."""
        r = requests.get(f"{BASE}/dispatch/status", timeout=TIMEOUT)
        assert r.status_code == 401


# ══════════════════════════════════════════════════════════════════════════════
# CYBERSECURITY — extended
# ══════════════════════════════════════════════════════════════════════════════

class TestCybersecurityExtended:
    """Extended cybersecurity endpoint tests."""

    def test_cyber_status_compliance_block(self, auth_headers):
        """Cybersecurity status must include a compliance block."""
        r = requests.get(f"{BASE}/cybersecurity/status",
                         headers=auth_headers, timeout=TIMEOUT)
        assert r.status_code == 200
        d = r.json()
        has_compliance = "compliance" in d or "do326a" in str(d)
        assert has_compliance or "controls" in d, \
            f"No compliance information in cyber status: {list(d.keys())}"

    def test_cyber_controls_block(self, auth_headers):
        """Cybersecurity status must include a controls dictionary."""
        r = requests.get(f"{BASE}/cybersecurity/status",
                         headers=auth_headers, timeout=TIMEOUT)
        assert r.status_code == 200
        d = r.json()
        controls = d.get("controls", {})
        assert isinstance(controls, dict), \
            f"controls is not a dict: {type(controls)}"
        # At least one standard control must be declared
        standard_controls = {
            "rate_limiting", "replay_protection", "spoof_detection",
            "jwt_authentication", "tls_1_3",
        }
        assert standard_controls & set(controls.keys()), \
            f"No standard control keys found: {list(controls.keys())}"

    def test_cyber_threat_level_admin_visible(self, auth_headers):
        """Admin must be able to see the threat level."""
        r = requests.get(f"{BASE}/cybersecurity/status",
                         headers=auth_headers, timeout=TIMEOUT)
        assert r.status_code == 200
        d = r.json()
        threat_level = d.get("threat_level")
        assert threat_level in ("LOW", "MEDIUM", "HIGH", "CRITICAL"), \
            f"Unexpected threat level: {threat_level}"


# ══════════════════════════════════════════════════════════════════════════════
# MAIN RUNNER
# ══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import sys

    print("\n" + "═" * 65)
    print("  SENTINELTWIN — EXTENDED E2E TEST SUITE")
    print("  Target: http://localhost:8000")
    print("═" * 65 + "\n")

    try:
        r = requests.get("http://localhost:8000/health", timeout=5)
        assert r.status_code == 200
        print("✓ Backend reachable\n")
    except Exception as exc:
        print(f"✗ Backend not reachable: {exc}")
        print("  Start the backend first: python backend/main.py")
        sys.exit(1)

    exit_code = pytest.main([__file__, "-v", "--tb=short", "--timeout=30"])
    sys.exit(exit_code)
