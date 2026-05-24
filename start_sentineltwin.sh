#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════════════
#  SENTINELTWIN v4.2.1 — ONE-CLICK UNIX LAUNCHER
#  Aerospace Assurance Platform — EASA DO-326A / ED-202A Compliant
#
#  Usage:
#    chmod +x start_sentineltwin.sh && ./start_sentineltwin.sh
#    ./start_sentineltwin.sh --local      (local dev mode)
#    ./start_sentineltwin.sh --docker     (Docker full-stack)
#    ./start_sentineltwin.sh --stop       (stop all services)
#    ./start_sentineltwin.sh --check      (health check only)
#    ./start_sentineltwin.sh --no-browser (skip auto-open)
# ═══════════════════════════════════════════════════════════════════════════

set -euo pipefail

# ── Colours ────────────────────────────────────────────────────────────────
RED="\033[91m"; GREEN="\033[92m"; YELLOW="\033[93m"
CYAN="\033[96m"; BOLD="\033[1m"; RESET="\033[0m"; DIM="\033[2m"

ok()   { echo -e "  ${GREEN}✓${RESET} $1"; }
warn() { echo -e "  ${YELLOW}⚠${RESET} $1"; }
fail() { echo -e "  ${RED}✗${RESET} $1"; exit 1; }
info() { echo -e "  ${CYAN}›${RESET} $1"; }

# ── Resolve project root ───────────────────────────────────────────────────
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "${PROJECT_ROOT}"
LAUNCH_PY="${PROJECT_ROOT}/launch.py"

# ── Parse args ─────────────────────────────────────────────────────────────
MODE_ARG=""
NO_BROWSER=""
for arg in "$@"; do
    case "$arg" in
        --local)      MODE_ARG="--mode local" ;;
        --docker)     MODE_ARG="--mode docker" ;;
        --no-browser) NO_BROWSER="--no-browser" ;;
        --stop)
            echo -e "\n  ${CYAN}Stopping SentinelTwin...${RESET}"
            python3 "${LAUNCH_PY}" --stop 2>/dev/null || \
                docker compose stop 2>/dev/null || true
            # Kill by port as fallback
            for port in 8000 5173; do
                fuser -k "${port}/tcp" 2>/dev/null || true
            done
            echo -e "  ${GREEN}✓ SentinelTwin stopped${RESET}\n"
            exit 0
            ;;
        --check)
            python3 "${LAUNCH_PY}" --check-only
            exit $?
            ;;
    esac
done

# ── Banner ─────────────────────────────────────────────────────────────────
echo ""
echo -e "  ${CYAN}╔══════════════════════════════════════════════════════════╗${RESET}"
echo -e "  ${CYAN}║                                                          ║${RESET}"
echo -e "  ${CYAN}║       ${BOLD}S E N T I N E L T W I N  v4.2.1${RESET}${CYAN}                ║${RESET}"
echo -e "  ${CYAN}║                                                          ║${RESET}"
echo -e "  ${CYAN}║  Airworthiness Assurance Platform                       ║${RESET}"
echo -e "  ${CYAN}║  EASA DO-326A / ED-202A / ARINC 664 Compliant          ║${RESET}"
echo -e "  ${CYAN}║  8,192 Sensors · AI Anomaly Detection · SHA-256 Audit   ║${RESET}"
echo -e "  ${CYAN}║                                                          ║${RESET}"
echo -e "  ${CYAN}╚══════════════════════════════════════════════════════════╝${RESET}"
echo ""

# ── Detect Python ──────────────────────────────────────────────────────────
PYTHON_CMD=""
for cmd in python3 python; do
    if command -v "$cmd" &>/dev/null; then
        ver=$("$cmd" --version 2>&1)
        if echo "$ver" | grep -q "Python 3"; then
            PYTHON_CMD="$cmd"
            ok "Python: $ver"
            break
        fi
    fi
done

if [ -z "$PYTHON_CMD" ]; then
    fail "Python 3.9+ not found. Install from https://python.org"
fi

# ── Check launch.py exists ─────────────────────────────────────────────────
if [ ! -f "${LAUNCH_PY}" ]; then
    fail "launch.py not found at: ${LAUNCH_PY}"
fi

# ── Activate venv if present ───────────────────────────────────────────────
if [ -f "backend/.venv/bin/activate" ]; then
    source "backend/.venv/bin/activate"
    ok "Virtual environment activated: backend/.venv"
elif [ -f ".venv/bin/activate" ]; then
    source ".venv/bin/activate"
    ok "Virtual environment activated: .venv"
fi

# ── Ensure logs directory ─────────────────────────────────────────────────
mkdir -p "${PROJECT_ROOT}/logs"

# ── Delegate to launch.py ─────────────────────────────────────────────────
info "Launching SentinelTwin orchestrator..."
echo ""

exec "${PYTHON_CMD}" "${LAUNCH_PY}" ${MODE_ARG} ${NO_BROWSER}
