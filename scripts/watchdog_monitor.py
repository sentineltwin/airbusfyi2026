#!/usr/bin/env python3
"""
SentinelTwin — Standalone Health Monitor & Watchdog
====================================================
Lightweight CLI tool that monitors a running SentinelTwin instance
and provides continuous health reporting.

Usage:
  python scripts/watchdog_monitor.py              # Live dashboard
  python scripts/watchdog_monitor.py --once       # Single health check
  python scripts/watchdog_monitor.py --report     # Write RUNTIME_STATUS.md
  python scripts/watchdog_monitor.py --interval 5 # Check every 5 seconds
"""

from __future__ import annotations

import argparse
import io
import json
import os
import socket
import sys
import time
import urllib.request
import urllib.error
from datetime import datetime, timezone
from pathlib import Path

# Windows encoding fix
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parent.parent
DOCS = ROOT / "docs"

# ANSI colours
RED    = "\033[91m"
GREEN  = "\033[92m"
YELLOW = "\033[93m"
CYAN   = "\033[96m"
BOLD   = "\033[1m"
DIM    = "\033[2m"
RESET  = "\033[0m"

# ─── Service definitions ───────────────────────────────────────────────────

SERVICES = [
    {"name": "Backend API",      "url": "http://localhost:8000/health",         "port": 8000},
    {"name": "Frontend UI",      "url": "http://localhost:5173",                "port": 5173},
    {"name": "API Docs",         "url": "http://localhost:8000/api/docs",       "port": 8000},
    {"name": "Grafana",          "url": "http://localhost:3001",                "port": 3001},
    {"name": "Prometheus",       "url": "http://localhost:9090",                "port": 9090},
]

DOCKER_SERVICES = ["postgres", "redis", "kafka", "zookeeper"]

# ─── Helpers ──────────────────────────────────────────────────────────────

def _ts() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

def _local_time() -> str:
    return datetime.now().strftime("%H:%M:%S")

def _fetch(url: str, timeout: float = 4.0):
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            return json.loads(r.read()), r.status
    except urllib.error.HTTPError as e:
        return None, e.code
    except Exception:
        return None, None

def _port_open(port: int, host: str = "localhost", timeout: float = 1.0) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except Exception:
        return False

def _docker_status() -> dict[str, str]:
    """Return dict of container_name -> status string."""
    try:
        import subprocess
        r = subprocess.run(
            ["docker", "compose", "ps", "--format", "json"],
            capture_output=True, text=True, cwd=ROOT, timeout=8,
        )
        if r.returncode != 0:
            return {}
        result = {}
        for line in r.stdout.strip().splitlines():
            try:
                obj = json.loads(line)
                name = obj.get("Service", obj.get("Name", "?"))
                state = obj.get("State", obj.get("Status", "?")).lower()
                result[name] = state
            except Exception:
                pass
        return result
    except Exception:
        return {}

# ─── Health check ─────────────────────────────────────────────────────────

def run_health_check() -> dict:
    results = {}
    for svc in SERVICES:
        port_ok = _port_open(svc["port"])
        data, status = _fetch(svc["url"]) if port_ok else (None, None)
        healthy = port_ok and status is not None and status < 500
        results[svc["name"]] = {
            "healthy": healthy,
            "status": status,
            "port": port_ok,
            "data": data,
        }

    # Docker containers
    docker_states = _docker_status()
    for svc in DOCKER_SERVICES:
        state = docker_states.get(svc, "unknown")
        results[f"Docker:{svc}"] = {
            "healthy": "running" in state or "up" in state,
            "status": state,
            "port": None,
            "data": None,
        }

    return results

# ─── Display ──────────────────────────────────────────────────────────────

def print_health_table(results: dict, elapsed_ms: float):
    os.system("cls" if sys.platform == "win32" else "clear")

    healthy_count = sum(1 for v in results.values() if v["healthy"])
    total_count   = len(results)
    all_ok        = healthy_count == total_count

    status_color = GREEN if all_ok else (YELLOW if healthy_count > total_count // 2 else RED)
    status_label = "OPERATIONAL" if all_ok else ("DEGRADED" if healthy_count > 0 else "OFFLINE")

    print(f"""
{CYAN}{BOLD}  SentinelTwin — Health Monitor{RESET}
  {DIM}Updated: {_local_time()}  |  Check time: {elapsed_ms:.0f}ms{RESET}

  System Status: {status_color}{BOLD}{status_label}{RESET}
  {healthy_count}/{total_count} services healthy

  {'─' * 58}
  {'SERVICE':<28} {'STATUS':<14} {'DETAILS'}
  {'─' * 58}""")

    for name, info in results.items():
        ok   = info["healthy"]
        col  = GREEN if ok else RED
        icon = "[OK]" if ok else "[!!]"
        detail = ""
        if info.get("data") and isinstance(info["data"], dict):
            detail = info["data"].get("status", "")
        elif info.get("status") and isinstance(info["status"], str):
            detail = info["status"]
        elif info.get("status") and isinstance(info["status"], int):
            detail = f"HTTP {info['status']}"
        print(f"  {col}{icon}{RESET} {name:<25} {col}{'HEALTHY' if ok else 'OFFLINE':<14}{RESET} {DIM}{detail}{RESET}")

    print(f"\n  {'─' * 58}")
    print(f"  {DIM}URLs:{RESET}")
    print(f"  Dashboard:  http://localhost:5173")
    print(f"  API:        http://localhost:8000")
    print(f"  API Docs:   http://localhost:8000/api/docs")
    print(f"  Grafana:    http://localhost:3001")
    print(f"\n  {DIM}Press Ctrl+C to exit{RESET}\n")

# ─── RUNTIME_STATUS.MD writer ─────────────────────────────────────────────

def write_runtime_status(results: dict):
    DOCS.mkdir(parents=True, exist_ok=True)
    now = _ts()
    healthy_count = sum(1 for v in results.values() if v["healthy"])
    total_count   = len(results)
    status_label  = "OPERATIONAL" if healthy_count == total_count else "DEGRADED"

    rows = "\n".join(
        f"| {name} | {'HEALTHY' if v['healthy'] else 'OFFLINE'} |"
        for name, v in results.items()
    )

    content = f"""# SentinelTwin — Runtime Status

> **Last updated:** `{now}`
> **System Status:** **{status_label}**
> **Services:** {healthy_count}/{total_count} healthy

---

## Service Health

| Service | Status |
|---------|--------|
{rows}

---

## Quick Access

| Interface | URL |
|-----------|-----|
| Operational Dashboard | http://localhost:5173 |
| REST API | http://localhost:8000 |
| API Documentation | http://localhost:8000/api/docs |
| Grafana | http://localhost:3001 |
| Prometheus | http://localhost:9090 |

---

*Auto-updated by `watchdog_monitor.py` — {now}*
"""
    (DOCS / "RUNTIME_STATUS.md").write_text(content, encoding="utf-8")
    print(f"  [OK] RUNTIME_STATUS.md updated ({len(content):,} bytes)")

# ─── Main ─────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="SentinelTwin health monitor")
    parser.add_argument("--once",     action="store_true", help="Single check and exit")
    parser.add_argument("--report",   action="store_true", help="Write RUNTIME_STATUS.md and exit")
    parser.add_argument("--interval", type=int, default=10, help="Check interval in seconds (default: 10)")
    args = parser.parse_args()

    if args.once or args.report:
        t0 = time.time()
        results = run_health_check()
        elapsed = (time.time() - t0) * 1000
        if args.report:
            write_runtime_status(results)
        else:
            print_health_table(results, elapsed)
        healthy = sum(1 for v in results.values() if v["healthy"])
        total   = len(results)
        sys.exit(0 if healthy == total else 1)

    # Continuous loop
    print(f"\n  {CYAN}SentinelTwin Health Monitor — checking every {args.interval}s{RESET}")
    print(f"  {DIM}Ctrl+C to stop{RESET}\n")
    try:
        while True:
            t0 = time.time()
            results = run_health_check()
            elapsed = (time.time() - t0) * 1000
            print_health_table(results, elapsed)
            write_runtime_status(results)
            time.sleep(args.interval)
    except KeyboardInterrupt:
        print(f"\n  {YELLOW}Monitor stopped.{RESET}\n")


if __name__ == "__main__":
    main()
