"""
SentinelTwin — pytest shared configuration and fixtures
Applies to both test_suite.py (unit) and test_e2e.py (integration).
"""

import os
import sys
import pytest
from pathlib import Path

# Ensure backend/ is on sys.path for all test modules
BACKEND_DIR = Path(__file__).parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

# ── Environment defaults for offline unit tests ───────────────────────────────
os.environ.setdefault("DATABASE_URL",
    "postgresql+asyncpg://sentineltwin:sentinel_secure_pw@localhost:5432/sentineltwin")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
os.environ.setdefault("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
os.environ.setdefault("SECRET_KEY", "test-secret-key-not-for-production-use")
os.environ.setdefault("DEBUG", "true")
os.environ.setdefault("LOG_LEVEL", "WARNING")   # suppress noise in tests

# ── asyncio mode for async test support ──────────────────────────────────────
# asyncio_mode = auto is configured in pytest.ini [pytest-asyncio] section.
# No event_loop_policy override needed — Python 3.14 uses its own default.

# ── Shared constants ──────────────────────────────────────────────────────────
BASE    = "http://localhost:8000/api/v1"
WS_URL  = "ws://localhost:8000/ws/telemetry"
TIMEOUT = 10

@pytest.fixture(scope="session")
def base_url():
    return BASE

@pytest.fixture(scope="session")
def ws_url():
    return WS_URL

# ── Admin auth token (session-scoped — obtained once) ────────────────────────
@pytest.fixture(scope="session")
def auth_headers():
    """Login as admin and return Authorization headers. Skip if backend offline."""
    import requests
    try:
        r = requests.post(
            f"{BASE}/auth/login",
            json={"username": "admin", "password": "sentinel2026"},
            timeout=5,
        )
        if r.status_code != 200:
            pytest.skip(f"Backend login failed ({r.status_code}) — is backend running?")
        return {"Authorization": f"Bearer {r.json()['access_token']}"}
    except Exception as e:
        pytest.skip(f"Backend not reachable: {e}")

@pytest.fixture(scope="session")
def engineer_headers():
    """Login as maintenance engineer."""
    import requests
    try:
        r = requests.post(
            f"{BASE}/auth/login",
            json={"username": "engineer", "password": "engineer2026"},
            timeout=5,
        )
        if r.status_code != 200:
            pytest.skip(f"Engineer login failed ({r.status_code})")
        return {"Authorization": f"Bearer {r.json()['access_token']}"}
    except Exception as e:
        pytest.skip(f"Backend not reachable: {e}")

@pytest.fixture(scope="session")
def pilot_headers():
    """Login as pilot (read-only access)."""
    import requests
    try:
        r = requests.post(
            f"{BASE}/auth/login",
            json={"username": "pilot", "password": "pilot2026"},
            timeout=5,
        )
        if r.status_code != 200:
            pytest.skip(f"Pilot login failed ({r.status_code})")
        return {"Authorization": f"Bearer {r.json()['access_token']}"}
    except Exception as e:
        pytest.skip(f"Backend not reachable: {e}")

# ── Markers ───────────────────────────────────────────────────────────────────
def pytest_configure(config):
    config.addinivalue_line("markers",
        "unit: pure unit tests — no backend required")
    config.addinivalue_line("markers",
        "integration: requires running backend + services")
    config.addinivalue_line("markers",
        "slow: tests that take > 5 seconds")
    config.addinivalue_line("markers",
        "websocket: tests that require WebSocket connection")
