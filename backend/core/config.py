"""
SentinelTwin — Core Configuration
Environment-driven, production-grade settings management
"""

import secrets
from functools import lru_cache
from pathlib import Path
from typing import List, Optional

from pydantic import AnyHttpUrl, field_validator
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # ── Application ────────────────────────────────────────────
    APP_NAME: str = "SentinelTwin"
    VERSION: str = "4.4.0"
    DEBUG: bool = False
    HOST: str = "0.0.0.0"
    PORT: int = 8000
    WORKERS: int = 4

    # ── Security ───────────────────────────────────────────────
    SECRET_KEY: str = secrets.token_urlsafe(64)
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    BCRYPT_ROUNDS: int = 12

    # ── TLS ────────────────────────────────────────────────────
    SSL_ENABLED: bool = False
    SSL_KEYFILE: Optional[str] = None
    SSL_CERTFILE: Optional[str] = None

    # ── CORS ───────────────────────────────────────────────────
    CORS_ORIGINS: List[str] = [
        "http://localhost:5173",
        "http://localhost:3000",
        "https://sentineltwin.airbus.internal",
    ]

    # ── Database ───────────────────────────────────────────────
    DATABASE_URL: str = "postgresql+asyncpg://sentineltwin:sentinel_secure_pw@localhost:5432/sentineltwin"
    DB_POOL_SIZE: int = 20
    DB_MAX_OVERFLOW: int = 40
    DB_POOL_TIMEOUT: int = 30
    DB_ECHO: bool = False

    # ── Redis ──────────────────────────────────────────────────
    REDIS_URL: str = "redis://localhost:6379/0"
    REDIS_MAX_CONNECTIONS: int = 100
    REDIS_SOCKET_TIMEOUT: float = 5.0

    # ── Kafka ──────────────────────────────────────────────────
    KAFKA_BOOTSTRAP_SERVERS: str = "localhost:9092"
    KAFKA_TELEMETRY_TOPIC: str = "sentineltwin.telemetry"
    KAFKA_ANOMALY_TOPIC: str = "sentineltwin.anomalies"
    KAFKA_ECAM_TOPIC: str = "sentineltwin.ecam"
    KAFKA_AUDIT_TOPIC: str = "sentineltwin.audit"
    KAFKA_GROUP_ID: str = "sentineltwin-consumers"

    # ── Sensor Engine ──────────────────────────────────────────
    SENSOR_COUNT: int = 8192
    SENSOR_SAMPLE_RATE_HZ: float = 20.0
    SENSOR_BATCH_SIZE: int = 512
    SENSOR_WORKER_COUNT: int = 16
    STALE_PACKET_THRESHOLD_SEC: float = 5.0
    REPLAY_WINDOW_SEC: float = 30.0

    # ── AI Engine ─────────────────────────────────────────────
    AI_MODEL_PATH: str = "./models/autoencoder_v2.4.pkl"
    AI_ANOMALY_THRESHOLD: float = 0.15
    AI_INFERENCE_BATCH_SIZE: int = 256
    AI_RETRAIN_INTERVAL_HOURS: int = 24
    AI_LATENT_DIM: int = 32
    AI_ENCODER_LAYERS: List[int] = [256, 128, 64, 32]
    AI_DECODER_LAYERS: List[int] = [32, 64, 128, 256]

    # ── Hash Chain ────────────────────────────────────────────
    HASH_ALGORITHM: str = "SHA-256"
    HASH_CHAIN_PERSIST_INTERVAL: int = 10  # every N scans
    HASH_ARCHIVE_RETENTION_DAYS: int = 2555  # 7 years

    # ── X-Plane Simulator ─────────────────────────────────────
    XPLANE_HOST: str = "127.0.0.1"
    XPLANE_PORT: int = 49000
    XPLANE_RECV_PORT: int = 49001

    # ── Rate Limiting ─────────────────────────────────────────
    RATE_LIMIT_REQUESTS: int = 1000
    RATE_LIMIT_WINDOW_SEC: int = 60
    RATE_LIMIT_AUTH_REQUESTS: int = 10
    RATE_LIMIT_AUTH_WINDOW_SEC: int = 300

    # ── Logging ───────────────────────────────────────────────
    LOG_LEVEL: str = "INFO"
    LOG_FORMAT: str = "json"
    LOG_FILE: str = "./logs/sentineltwin.log"
    LOG_ROTATION: str = "midnight"
    LOG_RETENTION_DAYS: int = 90

    # ── Monitoring ────────────────────────────────────────────
    PROMETHEUS_ENABLED: bool = True
    PROMETHEUS_PORT: int = 9090

    # ── Report Generation ─────────────────────────────────────
    REPORT_OUTPUT_DIR: str = "./reports"
    REPORT_SIGNATURE_KEY: str = "SENTINELTWIN_REPORT_SIGNING_KEY"

    # ── Compliance ────────────────────────────────────────────
    COMPLIANCE_DO326A: bool = True
    COMPLIANCE_ED202A: bool = True
    COMPLIANCE_EASA_AMC_20_42: bool = True
    COMPLIANCE_ARINC_429: bool = True
    COMPLIANCE_ARINC_664: bool = True

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = True

    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def assemble_cors_origins(cls, v):
        if isinstance(v, str):
            return [i.strip() for i in v.split(",")]
        return v


@lru_cache()
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
