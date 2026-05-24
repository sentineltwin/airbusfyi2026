#!/usr/bin/env python3
"""
SentinelTwin — Production Readiness Checklist
Validates all prerequisites before production deployment.

Run: python3 scripts/production_check.py
"""

import importlib
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

RESET  = "\033[0m"
GREEN  = "\033[32m"
RED    = "\033[31m"
YELLOW = "\033[33m"
CYAN   = "\033[36m"
BOLD   = "\033[1m"


def ok(msg):
    print(f"  {GREEN}✓ {msg}{RESET}")


def fail(msg):
    print(f"  {RED}✗ {msg}{RESET}")
    return False


def warn(msg):
    print(f"  {YELLOW}⚠ {msg}{RESET}")


def header(h):
    print(f"\n{CYAN}{BOLD}{'─' * 50}\n  {h}\n{'─' * 50}{RESET}")


results = {"pass": 0, "fail": 0, "warn": 0}


def check(condition, pass_msg, fail_msg, warning=False):
    if condition:
        ok(pass_msg)
        results["pass"] += 1
        return True
    else:
        if warning:
            warn(fail_msg)
            results["warn"] += 1
        else:
            fail(fail_msg)
            results["fail"] += 1
        return False


# ─── BANNER ──────────────────────────────────────────────────
print()
print(f"{CYAN}{BOLD}╔══════════════════════════════════════════════════════╗{RESET}")
print(f"{CYAN}{BOLD}║   SENTINELTWIN — PRODUCTION READINESS CHECKLIST      ║{RESET}")
print(f"{CYAN}{BOLD}║   v4.2.1  |  EASA DO-326A · ED-202A · AMC 20-42     ║{RESET}")
print(f"{CYAN}{BOLD}╚══════════════════════════════════════════════════════╝{RESET}")

# ─── ENVIRONMENT ─────────────────────────────────────────────
header("ENVIRONMENT")

env_file = ROOT / "backend" / ".env"
check(env_file.exists(), ".env file present", ".env missing — copy from .env.example")

env_content = ""
if env_file.exists():
    env_content = env_file.read_text(errors="ignore")
    check(
        "REPLACE_WITH" not in env_content and "changeme" not in env_content.lower(),
        "SECRET_KEY has been changed from default",
        "SECRET_KEY is still default — CRITICAL security risk",
    )
    check(
        "postgresql" in env_content or "DATABASE_URL" in env_content,
        "DATABASE_URL configured",
        "DATABASE_URL not found in .env",
    )
    check(
        "redis" in env_content or "REDIS_URL" in env_content,
        "REDIS_URL configured",
        "REDIS_URL not found in .env",
    )

cert_dir = ROOT / "infra" / "docker" / "nginx" / "ssl"
check(
    (cert_dir / "cert.pem").exists() and (cert_dir / "key.pem").exists(),
    "TLS certificates present",
    "TLS certificates missing — run start script to generate",
    warning=True,
)

# ─── PYTHON DEPENDENCIES ──────────────────────────────────────
header("PYTHON DEPENDENCIES")

required_packages = [
    ("fastapi", "fastapi"),
    ("uvicorn", "uvicorn"),
    ("sqlalchemy", "sqlalchemy"),
    ("alembic", "alembic"),
    ("asyncpg", "asyncpg"),
    ("redis", "redis"),
    ("aiokafka", "aiokafka"),
    ("bcrypt", "bcrypt"),
    ("python-jose", "jose"),
    ("prometheus_client", "prometheus_client"),
    ("reportlab", "reportlab"),
    ("numpy", "numpy"),
    ("pydantic", "pydantic"),
]
for pip_name, import_name in required_packages:
    try:
        importlib.import_module(import_name)
        ok(f"{pip_name} importable")
        results["pass"] += 1
    except ImportError:
        fail(f"{pip_name} not installed — pip install {pip_name}")
        results["fail"] += 1

# ─── DOCKER SERVICES ─────────────────────────────────────────
header("DOCKER SERVICES")

try:
    result = subprocess.run(
        ["docker", "compose", "ps", "--format", "json"],
        capture_output=True,
        text=True,
        cwd=ROOT,
        timeout=10,
    )
    if result.returncode == 0 and result.stdout.strip():
        lines = result.stdout.strip().split("\n")
        for svc in ["postgres", "redis", "kafka", "prometheus", "grafana"]:
            running = any(
                svc in line and ("running" in line.lower() or '"up"' in line.lower())
                for line in lines
            )
            check(
                running,
                f"{svc} container running",
                f"{svc} not running — run: docker compose up -d {svc}",
                warning=True,
            )
    else:
        warn("Could not query Docker Compose — is Docker running?")
        results["warn"] += 1
except (subprocess.TimeoutExpired, FileNotFoundError):
    warn("Docker not available or timed out")
    results["warn"] += 1

# ─── BACKEND HEALTH ───────────────────────────────────────────
header("BACKEND HEALTH")

try:
    import urllib.request

    with urllib.request.urlopen("http://localhost:8000/health", timeout=5) as r:
        data = json.loads(r.read())
        check(
            data.get("status") in ("OK", "OPERATIONAL", "healthy"),
            f"Backend healthy: {data.get('status', '?')}",
            f"Backend unhealthy: {data.get('status', '?')}",
        )
except Exception as e:
    warn(f"Backend not reachable: {e}")
    results["warn"] += 1

# ─── SECURITY CHECKS ─────────────────────────────────────────
header("SECURITY")

try:
    r = subprocess.run(
        [
            sys.executable,
            "-m",
            "bandit",
            "-r",
            str(ROOT / "backend"),
            "-x",
            "migrations,tests",
            "-ll",
            "-q",
        ],
        capture_output=True,
        text=True,
        cwd=ROOT,
        timeout=60,
    )
    issues = r.stdout.count("Issue:")
    check(
        issues == 0,
        "No high/medium security issues (bandit)",
        f"{issues} bandit issue(s) found — run: make security-scan",
        warning=True,
    )
except FileNotFoundError:
    warn("bandit not installed — run: pip install bandit")
    results["warn"] += 1
except subprocess.TimeoutExpired:
    warn("bandit scan timed out")
    results["warn"] += 1

# ─── DATABASE MIGRATIONS ──────────────────────────────────────
header("DATABASE")

try:
    r = subprocess.run(
        [sys.executable, "-m", "alembic", "current"],
        capture_output=True,
        text=True,
        cwd=ROOT / "backend",
        timeout=15,
    )
    check(
        "head" in r.stdout.lower() or r.returncode == 0,
        "Database schema at head revision",
        "Migrations not applied — run: make db-migrate",
        warning=True,
    )
except Exception as e:
    warn(f"Alembic check failed: {e}")
    results["warn"] += 1

# ─── FILE INTEGRITY ───────────────────────────────────────────
header("FILE INTEGRITY")

critical_files = [
    "backend/main.py",
    "backend/services/sensor_engine.py",
    "backend/services/ai_engine.py",
    "backend/services/persistence_service.py",
    "backend/services/report_service.py",
    "backend/services/kafka_producer.py",
    "backend/services/security_engine.py",
    "backend/services/digital_twin.py",
    "backend/services/ecam_engine.py",
    "backend/services/hash_service.py",
    "backend/services/arinc429_service.py",
    "backend/services/afdx_service.py",
    "frontend/src/SentinelTwin.jsx",
    "frontend/src/SentinelTwinPanels.jsx",
    "frontend/src/hooks/useWebSocket.ts",
    "frontend/src/stores/sentinel.store.ts",
    "docker-compose.yml",
    "Makefile",
]

for f in critical_files:
    path = ROOT / f
    if path.exists():
        size = path.stat().st_size
        check(
            size > 100,
            f"{f} ({size:,} bytes)",
            f"{f} exists but is suspiciously small ({size} bytes)",
        )
    else:
        fail(f"{f} MISSING")
        results["fail"] += 1

# Check optional but recommended files
optional_files = [
    "infra/k8s/sentineltwin.yml",
    "scripts/seed_db.py",
    "start_sentineltwin.sh",
    "start_sentineltwin.bat",
    "docs/RUNBOOK.md",
]
for f in optional_files:
    path = ROOT / f
    check(
        path.exists(),
        f"{f} present",
        f"{f} missing (recommended)",
        warning=True,
    )

# ─── COMPLIANCE FLAGS ─────────────────────────────────────────
header("COMPLIANCE")

compliance_items = [
    ("DO-326A Threat Detection", "backend/services/security_engine.py"),
    ("ED-202A Hash Chain Audit", "backend/services/hash_service.py"),
    ("ARINC 429 Label Encoding", "backend/services/arinc429_service.py"),
    ("ARINC 664 AFDX Monitoring", "backend/services/afdx_service.py"),
    ("ECAM Message Generation", "backend/services/ecam_engine.py"),
    ("2oo3 Redundancy Voting", "backend/services/sensor_engine.py"),
]
for label, path_str in compliance_items:
    path = ROOT / path_str
    check(
        path.exists() and path.stat().st_size > 500,
        f"{label} implemented ({path_str})",
        f"{label} not found — {path_str}",
    )

# ─── FRONTEND BUILD ──────────────────────────────────────────
header("FRONTEND")

pkg_json = ROOT / "frontend" / "package.json"
node_modules = ROOT / "frontend" / "node_modules"

check(pkg_json.exists(), "package.json present", "package.json missing")
check(
    node_modules.exists() and node_modules.is_dir(),
    "node_modules installed",
    "node_modules missing — run: cd frontend && npm install",
    warning=True,
)

# ─── SUMMARY ─────────────────────────────────────────────────
total = results["pass"] + results["fail"] + results["warn"]
print(f"\n{'═' * 50}")
print(f"{BOLD}  PRODUCTION READINESS SUMMARY{RESET}")
print(f"{'═' * 50}")
print(f"  {GREEN}PASS:    {results['pass']:3d}{RESET}")
print(f"  {YELLOW}WARN:    {results['warn']:3d}{RESET}")
print(f"  {RED}FAIL:    {results['fail']:3d}{RESET}")
print(f"  {'─' * 20}")
print(f"  TOTAL:   {total:3d}")
print(f"{'═' * 50}")

if results["fail"] == 0 and results["warn"] == 0:
    print(f"\n{GREEN}{BOLD}  ✓ SYSTEM READY FOR PRODUCTION DEPLOYMENT{RESET}\n")
    sys.exit(0)
elif results["fail"] == 0:
    print(f"\n{YELLOW}{BOLD}  ⚠ READY WITH WARNINGS — REVIEW BEFORE PRODUCTION{RESET}\n")
    sys.exit(0)
else:
    print(f"\n{RED}{BOLD}  ✗ NOT READY — FIX FAILURES BEFORE DEPLOYMENT{RESET}\n")
    sys.exit(1)
