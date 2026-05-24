# mypy: disable-error-code="valid-type, misc, var-annotated"
"""
SentinelTwin — Database Models
PostgreSQL + TimescaleDB schema
Production-grade with indexing, partitioning, retention policies
"""

import enum
import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean, Column, DateTime, Enum, Float, ForeignKey,
    Index, Integer, LargeBinary, String, Text, UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship, declarative_base

Base = declarative_base()  # type: ignore[valid-type, misc, var-annotated]


def utcnow():
    return datetime.now(timezone.utc)


def new_uuid():
    return str(uuid.uuid4())


# ─────────────────────────────────────────────────────────────
# ENUMERATIONS
# ─────────────────────────────────────────────────────────────

class UserRole(str, enum.Enum):
    PILOT = "pilot"
    MAINTENANCE_ENGINEER = "maintenance_engineer"
    GROUND_CREW = "ground_crew"
    DISPATCHER = "dispatcher"
    QA_INSPECTOR = "qa_inspector"
    ADMINISTRATOR = "administrator"


class SensorState(str, enum.Enum):
    HEALTHY = "HEALTHY"
    DEGRADED = "DEGRADED"
    FAILED = "FAILED"
    DESYNCHRONIZED = "DESYNCHRONIZED"
    STALE = "STALE"
    SPOOFED = "SPOOFED"
    OFFLINE = "OFFLINE"
    MAINTENANCE = "MAINTENANCE"
    UNVERIFIED = "UNVERIFIED"


class AnomalySeverity(str, enum.Enum):
    INFO = "INFO"
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class FlightPhase(str, enum.Enum):
    GROUND = "GROUND"
    TAXI = "TAXI"
    TAKEOFF = "TAKEOFF"
    CLIMB = "CLIMB"
    CRUISE = "CRUISE"
    DESCENT = "DESCENT"
    APPROACH = "APPROACH"
    LANDING = "LANDING"


class ECAMSeverity(str, enum.Enum):
    STATUS = "STATUS"
    CAUTION = "CAUTION"
    WARNING = "WARNING"
    EMERGENCY = "EMERGENCY"


class DispatchStatus(str, enum.Enum):
    GO = "GO"
    NO_GO = "NO_GO"
    PENDING = "PENDING"
    DEFERRED = "DEFERRED"


class AircraftType(str, enum.Enum):
    A220 = "A220"
    A319 = "A319"
    A320 = "A320"
    A320NEO = "A320neo"
    A321 = "A321"
    A330 = "A330"
    A350 = "A350"


# ─────────────────────────────────────────────────────────────
# USER & AUTHENTICATION
# ─────────────────────────────────────────────────────────────

class User(Base):
    __tablename__ = "users"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    username = Column(String(64), unique=True, nullable=False, index=True)
    email = Column(String(255), unique=True, nullable=False)
    hashed_password = Column(String(255), nullable=False)
    full_name = Column(String(128))
    role = Column(Enum(UserRole), nullable=False, default=UserRole.GROUND_CREW)
    is_active = Column(Boolean, default=True, nullable=False)
    is_locked = Column(Boolean, default=False, nullable=False)
    failed_login_count = Column(Integer, default=0)
    last_login = Column(DateTime(timezone=True))
    last_ip = Column(String(45))
    mfa_enabled = Column(Boolean, default=False)
    mfa_secret = Column(String(64))
    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    sessions = relationship("UserSession", back_populates="user", cascade="all, delete-orphan")
    audit_logs = relationship("AuditLog", back_populates="user")

    __table_args__ = (
        Index("ix_users_role", "role"),
        Index("ix_users_is_active", "is_active"),
    )


class UserSession(Base):
    __tablename__ = "user_sessions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    refresh_token_hash = Column(String(255), unique=True, nullable=False)
    ip_address = Column(String(45))
    user_agent = Column(String(512))
    is_active = Column(Boolean, default=True)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)
    last_used = Column(DateTime(timezone=True), default=utcnow)

    user = relationship("User", back_populates="sessions")


# ─────────────────────────────────────────────────────────────
# AIRCRAFT & FLEET
# ─────────────────────────────────────────────────────────────

class Aircraft(Base):
    __tablename__ = "aircraft"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    msn = Column(String(16), unique=True, nullable=False, index=True)
    registration = Column(String(16), unique=True, nullable=False)
    aircraft_type = Column(Enum(AircraftType), nullable=False)
    airline = Column(String(128))
    line_number = Column(Integer)
    first_flight = Column(DateTime(timezone=True))
    cycles = Column(Integer, default=0)
    flight_hours = Column(Float, default=0.0)
    is_active = Column(Boolean, default=True)
    profile = Column(JSONB)  # full avionics profile
    created_at = Column(DateTime(timezone=True), default=utcnow)
    updated_at = Column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    flights = relationship("Flight", back_populates="aircraft")
    sensor_registry = relationship("SensorDefinition", back_populates="aircraft")
    dispatch_reports = relationship("DispatchReport", back_populates="aircraft")


class Flight(Base):
    __tablename__ = "flights"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    aircraft_id = Column(UUID(as_uuid=True), ForeignKey("aircraft.id"), nullable=False)
    flight_number = Column(String(16))
    origin = Column(String(4))   # ICAO
    destination = Column(String(4))
    scheduled_departure = Column(DateTime(timezone=True))
    actual_departure = Column(DateTime(timezone=True))
    actual_arrival = Column(DateTime(timezone=True))
    phase = Column(Enum(FlightPhase), default=FlightPhase.GROUND)
    block_fuel_kg = Column(Float)
    trip_fuel_kg = Column(Float)
    cruise_altitude_ft = Column(Integer)
    pilot_in_command = Column(String(128))
    first_officer = Column(String(128))
    created_at = Column(DateTime(timezone=True), default=utcnow)
    updated_at = Column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    aircraft = relationship("Aircraft", back_populates="flights")
    anomaly_events = relationship("AnomalyEvent", back_populates="flight")
    dispatch_reports = relationship("DispatchReport", back_populates="flight")


# ─────────────────────────────────────────────────────────────
# SENSOR DEFINITIONS & TELEMETRY
# ─────────────────────────────────────────────────────────────

class SensorDefinition(Base):
    __tablename__ = "sensor_definitions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    aircraft_id = Column(UUID(as_uuid=True), ForeignKey("aircraft.id"), nullable=False)
    sensor_id = Column(String(32), nullable=False)   # e.g. ATA27-0001
    ata_chapter = Column(Integer, nullable=False)
    subsystem = Column(String(64))
    zone = Column(String(32))
    description = Column(String(256))
    engineering_unit = Column(String(16))
    sampling_rate_hz = Column(Float, default=20.0)
    min_limit = Column(Float)
    max_limit = Column(Float)
    warning_limit = Column(Float)
    critical_limit = Column(Float)
    redundancy_group = Column(String(64))
    calibration_profile = Column(JSONB)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), default=utcnow)

    aircraft = relationship("Aircraft", back_populates="sensor_registry")
    telemetry = relationship("TelemetryRecord", back_populates="sensor")

    __table_args__ = (
        UniqueConstraint("aircraft_id", "sensor_id", name="uq_sensor_per_aircraft"),
        Index("ix_sensor_ata", "ata_chapter"),
        Index("ix_sensor_redundancy_group", "redundancy_group"),
    )


class TelemetryRecord(Base):
    """TimescaleDB hypertable — partitioned by timestamp"""
    __tablename__ = "telemetry"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    sensor_id_ref = Column(UUID(as_uuid=True), ForeignKey("sensor_definitions.id"), nullable=False)
    sensor_id = Column(String(32), nullable=False)
    ata_chapter = Column(Integer, nullable=False)
    timestamp = Column(DateTime(timezone=True), nullable=False, default=utcnow)
    raw_value = Column(Float)
    calibrated_value = Column(Float)
    physics_residual = Column(Float)
    state = Column(Enum(SensorState), default=SensorState.HEALTHY)
    confidence_score = Column(Float, default=1.0)
    ai_anomaly_score = Column(Float, default=0.0)
    packet_hash = Column(String(64))
    arinc_label = Column(String(8))
    ssm = Column(String(16))
    sdi = Column(String(4))
    flags = Column(JSONB)

    sensor = relationship("SensorDefinition", back_populates="telemetry")

    __table_args__ = (
        Index("ix_telemetry_timestamp", "timestamp"),
        Index("ix_telemetry_sensor_ts", "sensor_id_ref", "timestamp"),
        Index("ix_telemetry_ata_ts", "ata_chapter", "timestamp"),
        Index("ix_telemetry_anomaly", "ai_anomaly_score"),
    )


# ─────────────────────────────────────────────────────────────
# ANOMALY EVENTS
# ─────────────────────────────────────────────────────────────

class AnomalyEvent(Base):
    __tablename__ = "anomaly_events"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    flight_id = Column(UUID(as_uuid=True), ForeignKey("flights.id"))
    sensor_id = Column(String(32))
    ata_chapter = Column(Integer)
    detected_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)
    resolved_at = Column(DateTime(timezone=True))
    anomaly_type = Column(String(64), nullable=False)
    severity = Column(Enum(AnomalySeverity), nullable=False)
    description = Column(Text)
    reconstruction_error = Column(Float)
    confidence = Column(Float)
    raw_evidence = Column(JSONB)
    maintenance_action = Column(String(256))
    is_resolved = Column(Boolean, default=False)
    false_positive = Column(Boolean, default=False)
    reviewed_by = Column(String(128))

    flight = relationship("Flight", back_populates="anomaly_events")

    __table_args__ = (
        Index("ix_anomaly_detected_at", "detected_at"),
        Index("ix_anomaly_severity", "severity"),
        Index("ix_anomaly_ata", "ata_chapter"),
        Index("ix_anomaly_unresolved", "is_resolved"),
    )


# ─────────────────────────────────────────────────────────────
# ECAM ADVISORIES
# ─────────────────────────────────────────────────────────────

class ECAMAdvisory(Base):
    __tablename__ = "ecam_advisories"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    flight_id = Column(UUID(as_uuid=True), ForeignKey("flights.id"))
    generated_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)
    cleared_at = Column(DateTime(timezone=True))
    severity = Column(Enum(ECAMSeverity), nullable=False)
    system = Column(String(16))
    ata_chapter = Column(Integer)
    message = Column(String(256), nullable=False)
    procedure = Column(Text)
    dispatch_impact = Column(Boolean, default=False)
    mel_reference = Column(String(64))
    is_active = Column(Boolean, default=True)

    __table_args__ = (
        Index("ix_ecam_generated_at", "generated_at"),
        Index("ix_ecam_severity", "severity"),
        Index("ix_ecam_active", "is_active"),
    )


# ─────────────────────────────────────────────────────────────
# DISPATCH REPORTS
# ─────────────────────────────────────────────────────────────

class DispatchReport(Base):
    __tablename__ = "dispatch_reports"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    aircraft_id = Column(UUID(as_uuid=True), ForeignKey("aircraft.id"), nullable=False)
    flight_id = Column(UUID(as_uuid=True), ForeignKey("flights.id"))
    generated_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)
    generated_by = Column(String(128))
    status = Column(Enum(DispatchStatus), nullable=False)
    sensor_health_pct = Column(Float)
    ai_confidence = Column(Float)
    active_ecam_count = Column(Integer, default=0)
    anomaly_count = Column(Integer, default=0)
    failed_sensor_count = Column(Integer, default=0)
    checklist_results = Column(JSONB)
    maintenance_actions = Column(JSONB)
    hash_chain_ref = Column(String(64))
    pdf_path = Column(String(512))
    signature = Column(LargeBinary)
    is_valid = Column(Boolean, default=True)

    aircraft = relationship("Aircraft", back_populates="dispatch_reports")
    flight = relationship("Flight", back_populates="dispatch_reports")

    __table_args__ = (
        Index("ix_dispatch_generated_at", "generated_at"),
        Index("ix_dispatch_status", "status"),
        Index("ix_dispatch_aircraft", "aircraft_id"),
    )


# ─────────────────────────────────────────────────────────────
# HASH CHAIN
# ─────────────────────────────────────────────────────────────

class HashChainBlock(Base):
    __tablename__ = "hash_chain"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    sequence = Column(Integer, unique=True, nullable=False, index=True)
    scan_id = Column(String(32), unique=True, nullable=False)
    timestamp = Column(DateTime(timezone=True), default=utcnow, nullable=False, index=True)
    previous_hash = Column(String(64), nullable=False)
    block_hash = Column(String(64), unique=True, nullable=False)
    sensor_count = Column(Integer, default=8192)
    healthy_count = Column(Integer)
    anomaly_count = Column(Integer)
    payload_summary = Column(JSONB)
    is_verified = Column(Boolean, default=True)
    tamper_detected = Column(Boolean, default=False)


# ─────────────────────────────────────────────────────────────
# MAINTENANCE ACTIONS
# ─────────────────────────────────────────────────────────────

class MaintenanceAction(Base):
    __tablename__ = "maintenance_actions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    aircraft_id = Column(UUID(as_uuid=True), ForeignKey("aircraft.id"), nullable=False)
    anomaly_id = Column(UUID(as_uuid=True), ForeignKey("anomaly_events.id"))
    ata_chapter = Column(Integer)
    action_type = Column(String(64))
    description = Column(Text, nullable=False)
    priority = Column(String(16))
    mel_reference = Column(String(64))
    assigned_to = Column(String(128))
    due_by = Column(DateTime(timezone=True))
    completed_at = Column(DateTime(timezone=True))
    is_completed = Column(Boolean, default=False)
    sign_off = Column(String(128))
    part_number = Column(String(64))
    notes = Column(Text)
    created_at = Column(DateTime(timezone=True), default=utcnow)

    __table_args__ = (
        Index("ix_maintenance_ata", "ata_chapter"),
        Index("ix_maintenance_priority", "priority"),
        Index("ix_maintenance_pending", "is_completed"),
    )


# ─────────────────────────────────────────────────────────────
# AI MODELS
# ─────────────────────────────────────────────────────────────

class AIModel(Base):
    __tablename__ = "ai_models"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    version = Column(String(32), unique=True, nullable=False)
    model_type = Column(String(64), default="SPARSE_AUTOENCODER")
    input_features = Column(Integer, default=8192)
    latent_dim = Column(Integer, default=32)
    encoder_config = Column(JSONB)
    training_samples = Column(Integer)
    validation_loss = Column(Float)
    false_positive_rate = Column(Float)
    true_positive_rate = Column(Float)
    anomaly_threshold = Column(Float, default=0.15)
    trained_at = Column(DateTime(timezone=True))
    deployed_at = Column(DateTime(timezone=True))
    is_active = Column(Boolean, default=False)
    model_path = Column(String(512))
    checksum = Column(String(64))
    notes = Column(Text)
    created_at = Column(DateTime(timezone=True), default=utcnow)


# ─────────────────────────────────────────────────────────────
# AUDIT LOG
# ─────────────────────────────────────────────────────────────

class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"))
    username = Column(String(64))
    action = Column(String(128), nullable=False)
    resource_type = Column(String(64))
    resource_id = Column(String(64))
    ip_address = Column(String(45))
    user_agent = Column(String(512))
    request_path = Column(String(512))
    request_method = Column(String(8))
    response_status = Column(Integer)
    details = Column(JSONB)
    timestamp = Column(DateTime(timezone=True), default=utcnow, nullable=False, index=True)
    session_id = Column(String(64))

    user = relationship("User", back_populates="audit_logs")

    __table_args__ = (
        Index("ix_audit_timestamp", "timestamp"),
        Index("ix_audit_user", "user_id"),
        Index("ix_audit_action", "action"),
    )


# ─────────────────────────────────────────────────────────────
# SIMULATOR SESSIONS
# ─────────────────────────────────────────────────────────────

class SimulatorSession(Base):
    __tablename__ = "simulator_sessions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    aircraft_id = Column(UUID(as_uuid=True), ForeignKey("aircraft.id"))
    simulator_type = Column(String(32))  # XPLANE | MSFS | REPLAY | LIVE
    host = Column(String(256))
    port = Column(Integer)
    connected_at = Column(DateTime(timezone=True), default=utcnow)
    disconnected_at = Column(DateTime(timezone=True))
    packets_received = Column(Integer, default=0)
    packets_dropped = Column(Integer, default=0)
    is_active = Column(Boolean, default=True)
    session_config = Column(JSONB)


# ─────────────────────────────────────────────────────────────
# REPLAY ARCHIVES
# ─────────────────────────────────────────────────────────────

class ReplayArchive(Base):
    __tablename__ = "replay_archives"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    aircraft_id = Column(UUID(as_uuid=True), ForeignKey("aircraft.id"))
    flight_id = Column(UUID(as_uuid=True), ForeignKey("flights.id"))
    name = Column(String(128))
    description = Column(Text)
    recorded_at = Column(DateTime(timezone=True))
    duration_sec = Column(Integer)
    sensor_count = Column(Integer)
    file_path = Column(String(512))
    file_size_bytes = Column(Integer)
    checksum = Column(String(64))
    anomaly_count = Column(Integer, default=0)
    created_at = Column(DateTime(timezone=True), default=utcnow)
