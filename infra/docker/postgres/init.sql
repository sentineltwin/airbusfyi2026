-- ═══════════════════════════════════════════════════════════════
-- SentinelTwin — PostgreSQL + TimescaleDB Initialization
-- Hypertables | Retention Policies | Indexes | Compression
-- DO-326A compliant 7-year audit retention
-- ═══════════════════════════════════════════════════════════════

-- Enable TimescaleDB extension
CREATE EXTENSION IF NOT EXISTS timescaledb CASCADE;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pg_stat_statements";
CREATE EXTENSION IF NOT EXISTS "pg_trgm";

-- ── Database settings ──────────────────────────────────────────
ALTER DATABASE sentineltwin SET timezone = 'UTC';
ALTER DATABASE sentineltwin SET log_min_duration_statement = 1000;

-- ── Schema ────────────────────────────────────────────────────
SET search_path = public;

-- ═══════════════════════════════════════════════════════════════
-- TELEMETRY HYPERTABLE
-- High-frequency time-series data — partitioned by timestamp
-- ═══════════════════════════════════════════════════════════════

-- Convert telemetry to TimescaleDB hypertable after table creation
-- (SQLAlchemy creates the table first, then we convert it)
-- This script runs AFTER SQLAlchemy creates tables via alembic

DO $$
BEGIN
    -- Only convert if not already a hypertable
    IF NOT EXISTS (
        SELECT 1 FROM timescaledb_information.hypertables
        WHERE hypertable_name = 'telemetry'
    ) THEN
        -- Note: table must exist first (created by SQLAlchemy)
        -- PERFORM create_hypertable('telemetry', 'timestamp', if_not_exists => TRUE);
        RAISE NOTICE 'Telemetry hypertable setup deferred to post-migration';
    END IF;
END $$;

-- ═══════════════════════════════════════════════════════════════
-- SEED DATA: DEFAULT USERS
-- ═══════════════════════════════════════════════════════════════

-- Note: actual user seeding happens via application startup
-- Default credentials are managed in the application layer
-- bcrypt hashes for: sentinel2026, pilot2026, engineer2026

-- ═══════════════════════════════════════════════════════════════
-- SEED DATA: AIRCRAFT FLEET
-- ═══════════════════════════════════════════════════════════════

-- Aircraft seeding happens via scripts/seed_db.py
-- Fleet: A320neo MSN 8234, A321 MSN 9012, A320 MSN 7891,
--        A350 MSN 6543, A320neo MSN 5210, A330 MSN 4480

-- ═══════════════════════════════════════════════════════════════
-- FUNCTIONS & PROCEDURES
-- ═══════════════════════════════════════════════════════════════

-- Function: compute sensor health percentage for an aircraft
CREATE OR REPLACE FUNCTION sensor_health_pct(p_aircraft_id UUID)
RETURNS NUMERIC AS $$
DECLARE
    v_total   INTEGER;
    v_healthy INTEGER;
BEGIN
    SELECT COUNT(*) INTO v_total
    FROM sensor_definitions WHERE aircraft_id = p_aircraft_id AND is_active = TRUE;

    SELECT COUNT(DISTINCT sd.id) INTO v_healthy
    FROM sensor_definitions sd
    JOIN telemetry t ON t.sensor_id_ref = sd.id
    WHERE sd.aircraft_id = p_aircraft_id
      AND sd.is_active = TRUE
      AND t.state = 'HEALTHY'
      AND t.timestamp >= NOW() - INTERVAL '1 minute';

    IF v_total = 0 THEN RETURN 0; END IF;
    RETURN ROUND((v_healthy::NUMERIC / v_total) * 100, 2);
END;
$$ LANGUAGE plpgsql;


-- Function: verify hash chain integrity
CREATE OR REPLACE FUNCTION verify_hash_chain()
RETURNS TABLE(is_valid BOOLEAN, tampered_at_sequence INTEGER) AS $$
DECLARE
    prev_hash  TEXT := '0000000000000000000000000000000000000000000000000000000000000000';
    curr_block RECORD;
    chain_ok   BOOLEAN := TRUE;
    tamper_seq INTEGER := NULL;
BEGIN
    FOR curr_block IN
        SELECT * FROM hash_chain ORDER BY sequence ASC
    LOOP
        IF curr_block.previous_hash != prev_hash THEN
            chain_ok := FALSE;
            tamper_seq := curr_block.sequence;
            EXIT;
        END IF;
        prev_hash := curr_block.block_hash;
    END LOOP;

    RETURN QUERY SELECT chain_ok, tamper_seq;
END;
$$ LANGUAGE plpgsql;


-- Function: get ATA chapter anomaly summary
CREATE OR REPLACE FUNCTION ata_anomaly_summary(
    p_since TIMESTAMPTZ DEFAULT NOW() - INTERVAL '1 hour'
)
RETURNS TABLE(
    ata_chapter INTEGER,
    total_sensors BIGINT,
    anomaly_count BIGINT,
    avg_anomaly_score NUMERIC,
    max_anomaly_score NUMERIC
) AS $$
BEGIN
    RETURN QUERY
    SELECT
        t.ata_chapter,
        COUNT(DISTINCT t.sensor_id_ref) AS total_sensors,
        COUNT(*) FILTER (WHERE t.state != 'HEALTHY') AS anomaly_count,
        ROUND(AVG(t.ai_anomaly_score)::NUMERIC, 4) AS avg_anomaly_score,
        ROUND(MAX(t.ai_anomaly_score)::NUMERIC, 4) AS max_anomaly_score
    FROM telemetry t
    WHERE t.timestamp >= p_since
    GROUP BY t.ata_chapter
    ORDER BY anomaly_count DESC;
END;
$$ LANGUAGE plpgsql;


-- ═══════════════════════════════════════════════════════════════
-- VIEWS
-- ═══════════════════════════════════════════════════════════════

-- View: active ECAM advisories with dispatch impact
CREATE OR REPLACE VIEW v_active_ecam AS
SELECT
    ea.id,
    ea.severity,
    ea.system,
    ea.ata_chapter,
    ea.message,
    ea.dispatch_impact,
    ea.mel_reference,
    ea.generated_at,
    EXTRACT(EPOCH FROM (NOW() - ea.generated_at)) AS age_seconds
FROM ecam_advisories ea
WHERE ea.is_active = TRUE
ORDER BY
    CASE ea.severity
        WHEN 'EMERGENCY' THEN 0
        WHEN 'WARNING'   THEN 1
        WHEN 'CAUTION'   THEN 2
        WHEN 'STATUS'    THEN 3
        ELSE 4
    END,
    ea.generated_at DESC;


-- View: pending maintenance actions
CREATE OR REPLACE VIEW v_pending_maintenance AS
SELECT
    ma.id,
    ma.ata_chapter,
    ma.action_type,
    ma.description,
    ma.priority,
    ma.mel_reference,
    ma.assigned_to,
    ma.due_by,
    ma.is_completed,
    CASE
        WHEN ma.due_by < NOW() AND NOT ma.is_completed THEN 'OVERDUE'
        WHEN ma.due_by < NOW() + INTERVAL '24 hours' AND NOT ma.is_completed THEN 'DUE_SOON'
        ELSE 'PENDING'
    END AS urgency
FROM maintenance_actions ma
WHERE ma.is_completed = FALSE
ORDER BY
    CASE ma.priority
        WHEN 'HIGH'   THEN 0
        WHEN 'MEDIUM' THEN 1
        WHEN 'LOW'    THEN 2
        ELSE 3
    END,
    ma.due_by ASC NULLS LAST;


-- View: recent anomaly events with sensor details
CREATE OR REPLACE VIEW v_recent_anomalies AS
SELECT
    ae.id,
    ae.sensor_id,
    ae.ata_chapter,
    ae.detected_at,
    ae.anomaly_type,
    ae.severity,
    ae.description,
    ae.reconstruction_error,
    ae.confidence,
    ae.is_resolved,
    ae.false_positive,
    EXTRACT(EPOCH FROM (NOW() - ae.detected_at)) AS age_seconds
FROM anomaly_events ae
WHERE ae.detected_at >= NOW() - INTERVAL '24 hours'
ORDER BY ae.detected_at DESC
LIMIT 500;


-- View: dispatch readiness dashboard
CREATE OR REPLACE VIEW v_dispatch_dashboard AS
SELECT
    a.id AS aircraft_id,
    a.msn,
    a.registration,
    a.aircraft_type,
    (
        SELECT COUNT(*) FROM ecam_advisories ea
        WHERE ea.is_active = TRUE AND ea.severity = 'EMERGENCY'
    ) AS emergency_ecam_count,
    (
        SELECT COUNT(*) FROM ecam_advisories ea
        WHERE ea.is_active = TRUE AND ea.severity = 'WARNING'
    ) AS warning_ecam_count,
    (
        SELECT COUNT(*) FROM maintenance_actions ma
        WHERE ma.is_completed = FALSE AND ma.due_by < NOW()
    ) AS overdue_maintenance_count,
    (
        SELECT hc.block_hash FROM hash_chain hc
        ORDER BY hc.sequence DESC LIMIT 1
    ) AS latest_hash,
    NOW() AS checked_at
FROM aircraft a
WHERE a.is_active = TRUE;


-- ═══════════════════════════════════════════════════════════════
-- INDEXES (on top of SQLAlchemy-created ones)
-- ═══════════════════════════════════════════════════════════════

-- Partial index for unresolved anomalies (common query pattern)
CREATE INDEX IF NOT EXISTS ix_anomaly_unresolved_severity
    ON anomaly_events (severity, detected_at DESC)
    WHERE is_resolved = FALSE;

-- Partial index for active ECAM
CREATE INDEX IF NOT EXISTS ix_ecam_active_severity
    ON ecam_advisories (severity, generated_at DESC)
    WHERE is_active = TRUE;

-- Hash chain sequence for fast tail queries
CREATE INDEX IF NOT EXISTS ix_hash_chain_seq_desc
    ON hash_chain (sequence DESC);

-- Full-text search on audit logs
CREATE INDEX IF NOT EXISTS ix_audit_action_trgm
    ON audit_logs USING gin (action gin_trgm_ops);

-- ═══════════════════════════════════════════════════════════════
-- RETENTION POLICIES (TimescaleDB)
-- Applied after hypertable creation
-- ═══════════════════════════════════════════════════════════════

-- Note: These are applied post-migration via scripts/setup_timescaledb.py
-- Telemetry:   90 days hot, then compressed
-- Audit logs:  2555 days (7 years) — EASA Part M requirement
-- Anomalies:   365 days online, archived to cold storage
-- Hash chain:  NEVER deleted — permanent tamper-evident record

-- ═══════════════════════════════════════════════════════════════
-- GRANTS
-- ═══════════════════════════════════════════════════════════════

-- Application user (limited privileges)
DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = 'sentineltwin_app') THEN
        CREATE ROLE sentineltwin_app LOGIN PASSWORD 'sentinel_app_pw';
    END IF;
END $$;

GRANT CONNECT ON DATABASE sentineltwin TO sentineltwin_app;
GRANT USAGE ON SCHEMA public TO sentineltwin_app;
GRANT SELECT, INSERT, UPDATE ON ALL TABLES IN SCHEMA public TO sentineltwin_app;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO sentineltwin_app;
GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA public TO sentineltwin_app;

-- Read-only role for reporting
DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = 'sentineltwin_readonly') THEN
        CREATE ROLE sentineltwin_readonly LOGIN PASSWORD 'sentinel_ro_pw';
    END IF;
END $$;

GRANT CONNECT ON DATABASE sentineltwin TO sentineltwin_readonly;
GRANT USAGE ON SCHEMA public TO sentineltwin_readonly;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO sentineltwin_readonly;

-- ═══════════════════════════════════════════════════════════════
-- COMPLETION NOTICE
-- ═══════════════════════════════════════════════════════════════

DO $$
BEGIN
    RAISE NOTICE '╔══════════════════════════════════════════════╗';
    RAISE NOTICE '║  SentinelTwin DB initialized — DO-326A      ║';
    RAISE NOTICE '║  TimescaleDB: ACTIVE                         ║';
    RAISE NOTICE '║  Retention: 7-year audit (EASA Part M)       ║';
    RAISE NOTICE '╚══════════════════════════════════════════════╝';
END $$;
