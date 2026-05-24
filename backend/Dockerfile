# ═══════════════════════════════════════════════════════════════
# SentinelTwin Backend — Production Dockerfile
# Multi-stage: Builder → Runtime
# Python 3.12 | Non-root | Minimal attack surface
# ═══════════════════════════════════════════════════════════════

# ── Stage 1: Builder ────────────────────────────────────────
FROM python:3.12-slim AS builder
WORKDIR /build

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc libpq-dev libffi-dev curl \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies into /install
COPY requirements.txt .
RUN pip install --upgrade pip \
    && pip install --prefix=/install --no-cache-dir -r requirements.txt

# ── Stage 2: Runtime ────────────────────────────────────────
FROM python:3.12-slim AS runtime
WORKDIR /app

# Runtime system deps only
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 curl \
    && rm -rf /var/lib/apt/lists/* \
    && useradd -m -u 1001 -s /bin/sh sentinel

# Copy installed packages
COPY --from=builder /install /usr/local

# Copy application
COPY --chown=sentinel:sentinel . .

# Create runtime directories
RUN mkdir -p /app/logs /app/reports /app/models \
    && chown -R sentinel:sentinel /app

# Drop root
USER sentinel

# Environment defaults (override via ConfigMap/Secret)
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PORT=8000 \
    WORKERS=4 \
    LOG_LEVEL=INFO \
    PROMETHEUS_ENABLED=true

EXPOSE 8000

HEALTHCHECK --interval=15s --timeout=5s --start-period=30s --retries=3 \
    CMD curl -sf http://localhost:8000/health || exit 1

CMD ["python", "main.py"]
