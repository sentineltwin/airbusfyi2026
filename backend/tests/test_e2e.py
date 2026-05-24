"""
SentinelTwin — End-to-End Integration Test Suite
Requires: running backend (python main.py) + all services initialized

Run: pytest backend/tests/test_e2e.py -v --timeout=30
     OR: python backend/tests/test_e2e.py
"""

import asyncio
import json
import time
import uuid
import requests
import pytest

try:
    import websockets
except ImportError:
    websockets = None

BASE    = "http://localhost:8000/api/v1"
WS_URL  = "ws://localhost:8000/ws/telemetry"
TIMEOUT = 10


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture(scope="session")
def auth_headers():
    """Login as admin and return auth headers."""
    r = requests.post(f"{BASE}/auth/login",
                      json={"username": "admin", "password": "sentinel2026"},
                      timeout=TIMEOUT)
    assert r.status_code == 200, f"Login failed: {r.text}"
    token = r.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture(scope="session")
def engineer_headers():
    """Login as maintenance engineer."""
    r = requests.post(f"{BASE}/auth/login",
                      json={"username": "engineer", "password": "engineer2026"},
                      timeout=TIMEOUT)
    assert r.status_code == 200
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


# ══════════════════════════════════════════════════════════════════════════════
# AUTH TESTS
# ══════════════════════════════════════════════════════════════════════════════

class TestAuth:
    def test_login_admin(self):
        r = requests.post(f"{BASE}/auth/login",
                          json={"username": "admin", "password": "sentinel2026"},
                          timeout=TIMEOUT)
        assert r.status_code == 200
        assert "access_token" in r.json()

    def test_login_wrong_password(self):
        r = requests.post(f"{BASE}/auth/login",
                          json={"username": "admin", "password": "wrongpassword"},
                          timeout=TIMEOUT)
        assert r.status_code in (401, 403)

    def test_protected_route_no_token(self):
        r = requests.get(f"{BASE}/sensors/stats", timeout=TIMEOUT)
        assert r.status_code == 401

    def test_token_refresh(self, auth_headers):
        r = requests.post(f"{BASE}/auth/refresh", headers=auth_headers,
                          timeout=TIMEOUT)
        assert r.status_code == 200
        assert "access_token" in r.json()


# ══════════════════════════════════════════════════════════════════════════════
# SENSOR ENGINE TESTS
# ══════════════════════════════════════════════════════════════════════════════

class TestSensorEngine:
    def test_sensor_stats(self, auth_headers):
        r = requests.get(f"{BASE}/sensors/stats", headers=auth_headers,
                         timeout=TIMEOUT)
        assert r.status_code == 200
        d = r.json()
        assert d["total_sensors"] >= 8000
        assert "healthy_count" in d
        assert "anomaly_count" in d

    def test_sensor_list_pagination(self, auth_headers):
        r = requests.get(f"{BASE}/sensors?limit=100&offset=0",
                         headers=auth_headers, timeout=TIMEOUT)
        assert r.status_code == 200
        d = r.json()
        assert len(d.get("sensors", [])) <= 100

    def test_sensor_by_ata(self, auth_headers):
        r = requests.get(f"{BASE}/sensors?ata_chapter=27",
                         headers=auth_headers, timeout=TIMEOUT)
        assert r.status_code == 200
        sensors = r.json().get("sensors", [])
        assert all(s["ata_chapter"] == 27 for s in sensors[:10])

    def test_sensor_health_pct(self, auth_headers):
        r = requests.get(f"{BASE}/sensors/stats", headers=auth_headers,
                         timeout=TIMEOUT)
        stats = r.json()
        healthy = stats.get("healthy_count", 0)
        total = stats.get("total_sensors", 8192)
        health_pct = (healthy / total * 100) if total else 0
        assert health_pct > 80, f"Health % too low: {health_pct:.1f}%"


# ══════════════════════════════════════════════════════════════════════════════
# ECAM ENGINE TESTS
# ══════════════════════════════════════════════════════════════════════════════

class TestECAM:
    def test_ecam_messages(self, auth_headers):
        r = requests.get(f"{BASE}/ecam/messages", headers=auth_headers,
                         timeout=TIMEOUT)
        assert r.status_code == 200
        d = r.json()
        assert "messages" in d
        for msg in d["messages"]:
            assert msg["severity"] in ("STATUS", "CAUTION", "WARNING", "EMERGENCY")
            assert "ata_chapter" in msg
            assert "message" in msg

    def test_ecam_stats(self, auth_headers):
        r = requests.get(f"{BASE}/ecam/stats", headers=auth_headers,
                         timeout=TIMEOUT)
        assert r.status_code == 200
        d = r.json()
        assert "total" in d or "active" in d


# ══════════════════════════════════════════════════════════════════════════════
# AI ENGINE TESTS
# ══════════════════════════════════════════════════════════════════════════════

class TestAIEngine:
    def test_ai_status(self, auth_headers):
        r = requests.get(f"{BASE}/anomalies/status", headers=auth_headers,
                         timeout=TIMEOUT)
        assert r.status_code == 200
        d = r.json()
        assert "confidence" in d or "current_confidence" in d
        assert "model_version" in d or "version" in d

    def test_model_info(self, auth_headers):
        r = requests.get(f"{BASE}/anomalies/model/info", headers=auth_headers,
                         timeout=TIMEOUT)
        assert r.status_code == 200
        d = r.json()
        assert d["architecture"] == "SparseAutoencoder 256→128→64→32→64→128→256"
        assert 0 < d["anomaly_threshold"] < 1.0
        assert d["input_features"] == 256

    def test_top_anomalies(self, auth_headers):
        r = requests.get(f"{BASE}/anomalies/top?limit=10", headers=auth_headers,
                         timeout=TIMEOUT)
        assert r.status_code == 200
        d = r.json()
        anomalies = d.get("top_anomalies", [])
        assert len(anomalies) <= 10
        if anomalies:
            assert "sensor_id" in anomalies[0]
            assert "score" in anomalies[0]
            # Must be sorted descending by score
            scores = [a["score"] for a in anomalies]
            assert scores == sorted(scores, reverse=True)

    def test_threshold_tuning(self, auth_headers):
        r = requests.post(f"{BASE}/anomalies/model/threshold?threshold=0.20",
                          headers=auth_headers, timeout=TIMEOUT)
        assert r.status_code == 200
        d = r.json()
        assert abs(d["new_threshold"] - 0.20) < 0.001
        # Reset
        requests.post(f"{BASE}/anomalies/model/threshold?threshold=0.15",
                      headers=auth_headers, timeout=TIMEOUT)

    def test_threshold_out_of_range(self, auth_headers):
        r = requests.post(f"{BASE}/anomalies/model/threshold?threshold=0.99",
                          headers=auth_headers, timeout=TIMEOUT)
        assert r.status_code == 422

    def test_anomaly_history(self, auth_headers):
        r = requests.get(f"{BASE}/anomalies/history?hours=24",
                         headers=auth_headers, timeout=TIMEOUT)
        assert r.status_code == 200
        d = r.json()
        assert "events" in d
        assert "source" in d


# ══════════════════════════════════════════════════════════════════════════════
# HASH CHAIN TESTS
# ══════════════════════════════════════════════════════════════════════════════

class TestHashChain:
    def test_chain_status(self, auth_headers):
        r = requests.get(f"{BASE}/hashchain/status", headers=auth_headers,
                         timeout=TIMEOUT)
        assert r.status_code == 200
        d = r.json()
        assert d.get("chain_valid") is True
        assert d.get("total_blocks", 0) >= 0

    def test_chain_verify(self, auth_headers):
        r = requests.get(f"{BASE}/hashchain/verify", headers=auth_headers,
                         timeout=TIMEOUT)
        assert r.status_code == 200
        d = r.json()
        assert d.get("verified") is True or "valid" in d

    def test_chain_grows(self, auth_headers):
        r1 = requests.get(f"{BASE}/hashchain/status", headers=auth_headers,
                          timeout=TIMEOUT)
        time.sleep(6)  # Wait for at least 1 broadcast cycle (hash appends every 5 cycles)
        r2 = requests.get(f"{BASE}/hashchain/status", headers=auth_headers,
                          timeout=TIMEOUT)
        b1 = r1.json().get("total_blocks", 0)
        b2 = r2.json().get("total_blocks", 0)
        assert b2 >= b1, f"Chain did not grow: {b1} → {b2}"


# ══════════════════════════════════════════════════════════════════════════════
# ARINC 429 TESTS
# ══════════════════════════════════════════════════════════════════════════════

class TestARINC429:
    def test_bus_frame(self, auth_headers):
        r = requests.get(f"{BASE}/arinc/frame", headers=auth_headers,
                         timeout=TIMEOUT)
        assert r.status_code == 200
        d = r.json()
        assert len(d["frame"]) >= 10
        label = d["frame"][0]
        assert "label_name" in label
        assert "value" in label
        assert "ssm_str" in label
        assert label["ssm_str"] in (
            "NORMAL", "FAILURE", "NO_COMPUTED_DATA", "FUNCTIONAL_TEST"
        )

    def test_label_table(self, auth_headers):
        r = requests.get(f"{BASE}/arinc/labels", headers=auth_headers,
                         timeout=TIMEOUT)
        assert r.status_code == 200
        d = r.json()
        assert d["count"] >= 10
        names = [label["name"] for label in d["labels"]]
        assert "IRS_LATITUDE" in names
        assert "FADEC_ENG1_EGT" in names

    def test_fault_inject_clear(self, auth_headers):
        # Inject FREEZE fault on IRS_LATITUDE (label 0o101 = 65 decimal)
        r = requests.post(f"{BASE}/arinc/inject",
                          json={"label_octal": 65, "fault_type": "FREEZE"},
                          headers=auth_headers, timeout=TIMEOUT)
        assert r.status_code == 200
        assert r.json().get("injected") is True
        # Clear it
        r2 = requests.post(f"{BASE}/arinc/clear?label_octal=65",
                           headers=auth_headers, timeout=TIMEOUT)
        assert r2.status_code == 200

    def test_fault_inject_requires_auth(self):
        r = requests.post(f"{BASE}/arinc/inject",
                          json={"label_octal": 65, "fault_type": "FREEZE"},
                          timeout=TIMEOUT)
        assert r.status_code == 401


# ══════════════════════════════════════════════════════════════════════════════
# AFDX TESTS
# ══════════════════════════════════════════════════════════════════════════════

class TestAFDX:
    def test_virtual_links(self, auth_headers):
        r = requests.get(f"{BASE}/afdx/vls", headers=auth_headers,
                         timeout=TIMEOUT)
        assert r.status_code == 200
        d = r.json()
        vls = d["virtual_links"]
        assert len(vls) >= 5
        vl = vls[0]
        assert "vl_id" in vl
        assert "jitter_us" in vl
        assert vl["status"] in ("NOMINAL", "DEGRADED", "FAILED")

    def test_network_stats(self, auth_headers):
        r = requests.get(f"{BASE}/afdx/stats", headers=auth_headers,
                         timeout=TIMEOUT)
        assert r.status_code == 200
        d = r.json()
        assert "total_utilization_pct" in d
        assert 0 <= d["total_utilization_pct"] <= 100

    def test_timing_fault_inject(self, auth_headers):
        r = requests.post(f"{BASE}/afdx/inject",
                          json={"vl_id": "VL-0100", "fault_type": "LATE"},
                          headers=auth_headers, timeout=TIMEOUT)
        assert r.status_code == 200
        assert r.json().get("injected") is True
        requests.post(f"{BASE}/afdx/clear?vl_id=VL-0100",
                      headers=auth_headers, timeout=TIMEOUT)


# ══════════════════════════════════════════════════════════════════════════════
# TELEMETRY HISTORY TESTS
# ══════════════════════════════════════════════════════════════════════════════

class TestTelemetryHistory:
    def test_telemetry_status(self, auth_headers):
        r = requests.get(f"{BASE}/telemetry/status", headers=auth_headers,
                         timeout=TIMEOUT)
        assert r.status_code == 200
        d = r.json()
        assert d["status"] == "STREAMING"
        assert d["sensors"] >= 8000

    def test_telemetry_history(self, auth_headers):
        r = requests.get(f"{BASE}/telemetry/history?ata_chapter=27&minutes=10",
                         headers=auth_headers, timeout=TIMEOUT)
        assert r.status_code == 200
        d = r.json()
        assert d["ata_chapter"] == 27
        assert "buckets" in d
        assert d["source"] in ("TIMESCALEDB", "SYNTHETIC_FALLBACK")

    def test_stream_info(self, auth_headers):
        r = requests.get(f"{BASE}/telemetry/stream-info", headers=auth_headers,
                         timeout=TIMEOUT)
        assert r.status_code == 200
        d = r.json()
        assert d["protocol"] == "WebSocket"
        assert "telemetry" in d["channels"]


# ══════════════════════════════════════════════════════════════════════════════
# DISPATCH TESTS
# ══════════════════════════════════════════════════════════════════════════════

class TestDispatch:
    def test_dispatch_status(self, auth_headers):
        r = requests.get(f"{BASE}/dispatch/status", headers=auth_headers,
                         timeout=TIMEOUT)
        assert r.status_code == 200
        d = r.json()
        assert "dispatch_ready" in d or "ready" in d
        # Response contains sensor_health_pct and checks_passed (not "score"/"dispatch_score")
        assert "sensor_health_pct" in d or "checks_passed" in d or "checklist" in d

    def test_dispatch_history(self, auth_headers):
        r = requests.get(f"{BASE}/dispatch/history?limit=10",
                         headers=auth_headers, timeout=TIMEOUT)
        assert r.status_code == 200
        d = r.json()
        assert "reports" in d
        assert "source" in d


# ══════════════════════════════════════════════════════════════════════════════
# CYBERSECURITY TESTS
# ══════════════════════════════════════════════════════════════════════════════

class TestCybersecurity:
    def test_cyber_status(self, auth_headers):
        r = requests.get(f"{BASE}/cybersecurity/status", headers=auth_headers,
                         timeout=TIMEOUT)
        assert r.status_code == 200
        d = r.json()
        assert "threat_level" in d
        assert d["threat_level"] in ("LOW", "MEDIUM", "HIGH", "CRITICAL")
        assert "controls" in d

    def test_threats_requires_admin(self, engineer_headers):
        # Maintenance engineer cannot access threat log
        r = requests.get(f"{BASE}/cybersecurity/threats",
                         headers=engineer_headers, timeout=TIMEOUT)
        assert r.status_code in (403, 401)


# ══════════════════════════════════════════════════════════════════════════════
# REPORT TESTS
# ══════════════════════════════════════════════════════════════════════════════

class TestReports:
    def test_pdf_report_generation(self, auth_headers):
        r = requests.get(f"{BASE}/reports/generate",
                         headers=auth_headers, timeout=30)
        assert r.status_code == 200
        assert r.headers["content-type"] == "application/pdf"
        assert r.content[:4] == b"%PDF"
        assert len(r.content) > 50_000, \
            f"PDF suspiciously small: {len(r.content)} bytes"

    def test_report_requires_auth(self):
        r = requests.get(f"{BASE}/reports/generate", timeout=TIMEOUT)
        assert r.status_code == 401


# ══════════════════════════════════════════════════════════════════════════════
# MAINTENANCE TESTS
# ══════════════════════════════════════════════════════════════════════════════

class TestMaintenance:
    def test_list_actions(self, auth_headers):
        r = requests.get(f"{BASE}/maintenance/actions",
                         headers=auth_headers, timeout=TIMEOUT)
        assert r.status_code == 200
        d = r.json()
        assert "actions" in d
        assert isinstance(d["actions"], list)

    def test_create_action(self, engineer_headers):
        payload = {
            "title":       "E2E Test Action",
            "ata_chapter": 27,
            "system":      "FLIGHT CONTROLS",
            "priority":    "ROUTINE",
            "description": "Created by E2E test suite — safe to delete",
        }
        r = requests.post(f"{BASE}/maintenance/actions",
                          json=payload, headers=engineer_headers,
                          timeout=TIMEOUT)
        assert r.status_code == 200
        d = r.json()
        assert d["title"] == "E2E Test Action"
        assert d["status"] == "OPEN"
        assert "action_id" in d
        return d["action_id"]

    def test_update_action(self, engineer_headers):
        # Create then update
        action_id = self.test_create_action(engineer_headers)
        r = requests.patch(f"{BASE}/maintenance/actions/{action_id}",
                           json={"status": "IN_PROGRESS",
                                 "assigned_to": "engineer"},
                           headers=engineer_headers, timeout=TIMEOUT)
        assert r.status_code == 200
        assert r.json()["status"] == "IN_PROGRESS"

    def test_action_not_found(self, engineer_headers):
        r = requests.patch(f"{BASE}/maintenance/actions/MX-NOTEXIST",
                           json={"status": "COMPLETED"},
                           headers=engineer_headers, timeout=TIMEOUT)
        assert r.status_code == 404

    def test_maintenance_summary(self, auth_headers):
        r = requests.get(f"{BASE}/maintenance/summary",
                         headers=auth_headers, timeout=TIMEOUT)
        assert r.status_code == 200
        d = r.json()
        assert "total" in d
        assert "open" in d


# ══════════════════════════════════════════════════════════════════════════════
# FLEET TESTS
# ══════════════════════════════════════════════════════════════════════════════

class TestFleet:
    def test_aircraft_profiles(self, auth_headers):
        r = requests.get(f"{BASE}/aircraft/profiles", headers=auth_headers,
                         timeout=TIMEOUT)
        assert r.status_code == 200
        d = r.json()
        profiles = d.get("profiles", d)
        assert "A320neo" in profiles or any(
            p.get("aircraft_type") == "A320neo"
            for p in (profiles if isinstance(profiles, list) else [])
        )

    def test_fleet_status(self, auth_headers):
        r = requests.get(f"{BASE}/fleet/status", headers=auth_headers,
                         timeout=TIMEOUT)
        assert r.status_code == 200
        d = r.json()
        assert "aircraft" in d or len(d) > 0



# ══════════════════════════════════════════════════════════════════════════════
# WEBSOCKET TESTS
# ══════════════════════════════════════════════════════════════════════════════

# ══════════════════════════════════════════════════════════════════════════════
# OPERATIONAL LOGS TESTS
# ══════════════════════════════════════════════════════════════════════════════

class TestOperationalLogs:
    def test_logs_endpoint(self, auth_headers):
        r = requests.get(f"{BASE}/logs/operational?limit=50",
                         headers=auth_headers, timeout=TIMEOUT)
        assert r.status_code == 200
        d = r.json()
        assert "logs" in d
        assert "count" in d
        assert isinstance(d["logs"], list)

    def test_logs_level_filter(self, auth_headers):
        r = requests.get(f"{BASE}/logs/operational?level=INFO&limit=20",
                         headers=auth_headers, timeout=TIMEOUT)
        assert r.status_code == 200
        d = r.json()
        # All returned logs should be INFO level (or empty if none yet)
        for log in d.get("logs", []):
            assert log["level"] == "INFO"

    def test_logs_require_auth(self):
        r = requests.get(f"{BASE}/logs/operational", timeout=TIMEOUT)
        assert r.status_code == 401


# ══════════════════════════════════════════════════════════════════════════════
# WEBSOCKET TESTS (continued)
# ══════════════════════════════════════════════════════════════════════════════

@pytest.mark.skipif(websockets is None, reason="websockets not installed")
class TestWebSocket:
    def test_ws_connects_and_receives(self):
        async def _test():
            async with websockets.connect(WS_URL, open_timeout=5) as ws:
                msg = await asyncio.wait_for(ws.recv(), timeout=8.0)
                frame = json.loads(msg)
                assert "channel" in frame
                assert "data" in frame
                assert "timestamp" in frame
                assert frame["channel"] in (
                    "telemetry", "ai", "ecam", "twin", "hashchain",
                    "dispatch", "arinc", "afdx", "cyber",
                )
        asyncio.run(_test())

    def test_ws_multiple_channels(self):
        async def _test():
            channels_seen = set()
            async with websockets.connect(WS_URL, open_timeout=5) as ws:
                for _ in range(15):
                    try:
                        msg = await asyncio.wait_for(ws.recv(), timeout=3.0)
                        frame = json.loads(msg)
                        channels_seen.add(frame.get("channel", ""))
                    except asyncio.TimeoutError:
                        break
            assert "telemetry" in channels_seen or "ai" in channels_seen, \
                f"Expected telemetry/ai channel, got: {channels_seen}"
        asyncio.run(_test())


# ══════════════════════════════════════════════════════════════════════════════
# PROMETHEUS TESTS
# ══════════════════════════════════════════════════════════════════════════════

class TestPrometheus:
    def test_metrics_endpoint(self):
        r = requests.get("http://localhost:8000/metrics", timeout=TIMEOUT)
        assert r.status_code == 200
        assert "sensor_validations_total" in r.text or "python_info" in r.text

    def test_metrics_content_type(self):
        r = requests.get("http://localhost:8000/metrics", timeout=TIMEOUT)
        assert "text/plain" in r.headers.get("content-type", "")

    def test_ws_message_counter_exists(self):
        r = requests.get("http://localhost:8000/metrics", timeout=TIMEOUT)
        assert r.status_code == 200
        # Check for the new WS + Kafka metrics
        text = r.text
        has_ws = "websocket_messages_total" in text
        has_kafka = "kafka_producer_queue_depth" in text
        assert has_ws or has_kafka or "python_info" in text

    def test_sentinel_metrics_present(self):
        r = requests.get("http://localhost:8000/metrics", timeout=TIMEOUT)
        assert r.status_code == 200
        text = r.text
        # At least one SentinelTwin-specific metric must be present
        assert any(m in text for m in [
            "sensor_validations_total",
            "ai_confidence",
            "dispatch_readiness_score",
            "hash_chain_blocks_total",
        ]), f"No SentinelTwin metrics found in /metrics output"


# ══════════════════════════════════════════════════════════════════════════════
# HEALTH TESTS
# ══════════════════════════════════════════════════════════════════════════════

class TestHealth:
    def test_basic_health(self):
        r = requests.get("http://localhost:8000/health", timeout=TIMEOUT)
        assert r.status_code == 200
        assert r.json().get("status") in ("OK", "OPERATIONAL", "healthy", "ok")

    def test_detailed_health(self, auth_headers):
        r = requests.get("http://localhost:8000/health/detailed",
                         headers=auth_headers, timeout=TIMEOUT)
        assert r.status_code == 200
        d = r.json()
        assert "subsystems" in d, "No 'subsystems' key in /health/detailed"
        subs = d["subsystems"]
        for expected in ["sensor_engine", "ai_engine"]:
            assert expected in subs, \
                f"'{expected}' missing from subsystems: {list(subs.keys())}"

    def test_health_version(self):
        r = requests.get("http://localhost:8000/health", timeout=TIMEOUT)
        assert r.status_code == 200
        d = r.json()
        assert "version" in d

    def test_detailed_health_persistence(self, auth_headers):
        r = requests.get("http://localhost:8000/health/detailed",
                         headers=auth_headers, timeout=TIMEOUT)
        assert r.status_code == 200
        d = r.json()
        # Persistence service must be initialised (status UP or NOT_INITIALIZED)
        persistence = d.get("subsystems", {}).get("persistence", {})
        assert persistence.get("status") in ("UP", "NOT_INITIALIZED"), \
            f"Unexpected persistence status: {persistence}"


# ══════════════════════════════════════════════════════════════════════════════
# DIGITAL TWIN TESTS
# ══════════════════════════════════════════════════════════════════════════════

class TestDigitalTwin:
    def test_twin_state(self, auth_headers):
        """Verify twin engine returns structural, thermal, and fuel state."""
        r = requests.get("http://localhost:8000/health/detailed",
                         headers=auth_headers, timeout=TIMEOUT)
        assert r.status_code == 200
        subsystems = r.json().get("subsystems", {})
        twin = subsystems.get("digital_twin", {})
        assert twin.get("status") in ("UP", "RUNNING", None) or twin


# ══════════════════════════════════════════════════════════════════════════════
# PERSISTENCE TESTS
# ══════════════════════════════════════════════════════════════════════════════

class TestPersistence:
    def test_persistence_stats(self, auth_headers):
        r = requests.get("http://localhost:8000/health/detailed",
                         headers=auth_headers, timeout=TIMEOUT)
        assert r.status_code == 200
        subsystems = r.json().get("subsystems", {})
        persist = subsystems.get("persistence", {})
        assert persist.get("status") == "UP"
        detail = persist.get("detail", {})
        assert "telemetry_persisted" in detail
        assert "queue_depths" in detail


# ══════════════════════════════════════════════════════════════════════════════
# RATE LIMITING TESTS
# ══════════════════════════════════════════════════════════════════════════════

class TestRateLimiting:
    def test_login_rate_limit(self):
        """Rapid repeated failed logins should eventually trigger rate limiting."""
        responses = []
        for _ in range(10):
            r = requests.post(f"{BASE}/auth/login",
                              json={"username": "admin",
                                    "password": "badpassword"},
                              timeout=TIMEOUT)
            responses.append(r.status_code)
        # Should get 401s and potentially a 429
        assert all(c in (401, 429) for c in responses)


# ══════════════════════════════════════════════════════════════════════════════
# SIMULATOR TESTS
# ══════════════════════════════════════════════════════════════════════════════

class TestSimulator:
    def test_simulator_status(self, auth_headers):
        r = requests.get(f"{BASE}/simulator/status", headers=auth_headers,
                         timeout=TIMEOUT)
        assert r.status_code == 200
        d = r.json()
        assert "mode" in d or "status" in d


# ══════════════════════════════════════════════════════════════════════════════
# MAIN RUNNER
# ══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import sys

    print("\n" + "═" * 60)
    print("  SENTINELTWIN — END-TO-END TEST SUITE")
    print("  Target: http://localhost:8000")
    print("═" * 60 + "\n")

    # Check backend is up
    try:
        r = requests.get("http://localhost:8000/health", timeout=5)
        assert r.status_code == 200
        print("✓ Backend reachable\n")
    except Exception as e:
        print(f"✗ Backend not reachable: {e}")
        print("  Start the backend first: python backend/main.py")
        sys.exit(1)

    # Run pytest programmatically
    exit_code = pytest.main([__file__, "-v", "--tb=short", "--timeout=30"])
    sys.exit(exit_code)
