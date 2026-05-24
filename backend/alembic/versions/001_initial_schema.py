"""Initial schema — SentinelTwin v4.2.1

Revision ID: 001_initial_schema
Revises: 
Create Date: 2026-05-13 00:00:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = '001_initial_schema'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── Enums ──────────────────────────────────────────────────
    op.execute("CREATE TYPE userrole AS ENUM ('pilot','maintenance_engineer','ground_crew','dispatcher','qa_inspector','administrator')")
    op.execute("CREATE TYPE sensorstate AS ENUM ('HEALTHY','DEGRADED','FAILED','DESYNCHRONIZED','STALE','SPOOFED','OFFLINE','MAINTENANCE','UNVERIFIED')")
    op.execute("CREATE TYPE anomalyseverity AS ENUM ('INFO','LOW','MEDIUM','HIGH','CRITICAL')")
    op.execute("CREATE TYPE flightphase AS ENUM ('GROUND','TAXI','TAKEOFF','CLIMB','CRUISE','DESCENT','APPROACH','LANDING')")
    op.execute("CREATE TYPE ecamseverity AS ENUM ('STATUS','CAUTION','WARNING','EMERGENCY')")
    op.execute("CREATE TYPE dispatchstatus AS ENUM ('GO','NO_GO','PENDING','DEFERRED')")
    op.execute("CREATE TYPE aircrafttype AS ENUM ('A220','A319','A320','A320neo','A321','A330','A350')")

    # ── Users ──────────────────────────────────────────────────
    op.create_table('users',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('username', sa.String(64), nullable=False),
        sa.Column('email', sa.String(255), nullable=False),
        sa.Column('hashed_password', sa.String(255), nullable=False),
        sa.Column('full_name', sa.String(128), nullable=True),
        sa.Column('role', sa.Enum('pilot','maintenance_engineer','ground_crew','dispatcher','qa_inspector','administrator', name='userrole'), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('is_locked', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('failed_login_count', sa.Integer(), nullable=True, server_default='0'),
        sa.Column('last_login', sa.DateTime(timezone=True), nullable=True),
        sa.Column('last_ip', sa.String(45), nullable=True),
        sa.Column('mfa_enabled', sa.Boolean(), nullable=True, server_default='false'),
        sa.Column('mfa_secret', sa.String(64), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('username'),
        sa.UniqueConstraint('email'),
    )
    op.create_index('ix_users_role', 'users', ['role'])
    op.create_index('ix_users_is_active', 'users', ['is_active'])
    op.create_index('ix_users_username', 'users', ['username'])

    # ── User Sessions ──────────────────────────────────────────
    op.create_table('user_sessions',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('refresh_token_hash', sa.String(255), nullable=False),
        sa.Column('ip_address', sa.String(45), nullable=True),
        sa.Column('user_agent', sa.String(512), nullable=True),
        sa.Column('is_active', sa.Boolean(), server_default='true'),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('last_used', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('refresh_token_hash'),
    )

    # ── Aircraft ───────────────────────────────────────────────
    op.create_table('aircraft',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('msn', sa.String(16), nullable=False),
        sa.Column('registration', sa.String(16), nullable=False),
        sa.Column('aircraft_type', sa.Enum('A220','A319','A320','A320neo','A321','A330','A350', name='aircrafttype'), nullable=False),
        sa.Column('airline', sa.String(128), nullable=True),
        sa.Column('line_number', sa.Integer(), nullable=True),
        sa.Column('first_flight', sa.DateTime(timezone=True), nullable=True),
        sa.Column('cycles', sa.Integer(), server_default='0'),
        sa.Column('flight_hours', sa.Float(), server_default='0.0'),
        sa.Column('is_active', sa.Boolean(), server_default='true'),
        sa.Column('profile', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('msn'),
        sa.UniqueConstraint('registration'),
    )
    op.create_index('ix_aircraft_msn', 'aircraft', ['msn'])

    # ── Flights ────────────────────────────────────────────────
    op.create_table('flights',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('aircraft_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('flight_number', sa.String(16), nullable=True),
        sa.Column('origin', sa.String(4), nullable=True),
        sa.Column('destination', sa.String(4), nullable=True),
        sa.Column('scheduled_departure', sa.DateTime(timezone=True), nullable=True),
        sa.Column('actual_departure', sa.DateTime(timezone=True), nullable=True),
        sa.Column('actual_arrival', sa.DateTime(timezone=True), nullable=True),
        sa.Column('phase', sa.Enum('GROUND','TAXI','TAKEOFF','CLIMB','CRUISE','DESCENT','APPROACH','LANDING', name='flightphase'), server_default='GROUND'),
        sa.Column('block_fuel_kg', sa.Float(), nullable=True),
        sa.Column('trip_fuel_kg', sa.Float(), nullable=True),
        sa.Column('cruise_altitude_ft', sa.Integer(), nullable=True),
        sa.Column('pilot_in_command', sa.String(128), nullable=True),
        sa.Column('first_officer', sa.String(128), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['aircraft_id'], ['aircraft.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_flights_aircraft', 'flights', ['aircraft_id'])

    # ── Sensor Definitions ─────────────────────────────────────
    op.create_table('sensor_definitions',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('aircraft_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('sensor_id', sa.String(32), nullable=False),
        sa.Column('ata_chapter', sa.Integer(), nullable=False),
        sa.Column('subsystem', sa.String(64), nullable=True),
        sa.Column('zone', sa.String(32), nullable=True),
        sa.Column('description', sa.String(256), nullable=True),
        sa.Column('engineering_unit', sa.String(16), nullable=True),
        sa.Column('sampling_rate_hz', sa.Float(), server_default='20.0'),
        sa.Column('min_limit', sa.Float(), nullable=True),
        sa.Column('max_limit', sa.Float(), nullable=True),
        sa.Column('warning_limit', sa.Float(), nullable=True),
        sa.Column('critical_limit', sa.Float(), nullable=True),
        sa.Column('redundancy_group', sa.String(64), nullable=True),
        sa.Column('calibration_profile', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('is_active', sa.Boolean(), server_default='true'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()')),
        sa.ForeignKeyConstraint(['aircraft_id'], ['aircraft.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('aircraft_id', 'sensor_id', name='uq_sensor_per_aircraft'),
    )
    op.create_index('ix_sensor_ata', 'sensor_definitions', ['ata_chapter'])
    op.create_index('ix_sensor_redundancy_group', 'sensor_definitions', ['redundancy_group'])

    # ── Telemetry (will become TimescaleDB hypertable) ─────────
    op.create_table('telemetry',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('sensor_id_ref', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('sensor_id', sa.String(32), nullable=False),
        sa.Column('ata_chapter', sa.Integer(), nullable=False),
        sa.Column('timestamp', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.Column('raw_value', sa.Float(), nullable=True),
        sa.Column('calibrated_value', sa.Float(), nullable=True),
        sa.Column('physics_residual', sa.Float(), nullable=True),
        sa.Column('state', sa.Enum('HEALTHY','DEGRADED','FAILED','DESYNCHRONIZED','STALE','SPOOFED','OFFLINE','MAINTENANCE','UNVERIFIED', name='sensorstate'), server_default='HEALTHY'),
        sa.Column('confidence_score', sa.Float(), server_default='1.0'),
        sa.Column('ai_anomaly_score', sa.Float(), server_default='0.0'),
        sa.Column('packet_hash', sa.String(64), nullable=True),
        sa.Column('arinc_label', sa.String(8), nullable=True),
        sa.Column('ssm', sa.String(16), nullable=True),
        sa.Column('sdi', sa.String(4), nullable=True),
        sa.Column('flags', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.ForeignKeyConstraint(['sensor_id_ref'], ['sensor_definitions.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_telemetry_timestamp', 'telemetry', ['timestamp'])
    op.create_index('ix_telemetry_sensor_ts', 'telemetry', ['sensor_id_ref', 'timestamp'])
    op.create_index('ix_telemetry_ata_ts', 'telemetry', ['ata_chapter', 'timestamp'])
    op.create_index('ix_telemetry_anomaly', 'telemetry', ['ai_anomaly_score'])

    # Convert telemetry to TimescaleDB hypertable
    op.execute("SELECT create_hypertable('telemetry', 'timestamp', if_not_exists => TRUE, migrate_data => TRUE)")
    op.execute("ALTER TABLE telemetry SET (timescaledb.compress, timescaledb.compress_segmentby = 'ata_chapter,sensor_id')")
    op.execute("SELECT add_compression_policy('telemetry', INTERVAL '7 days', if_not_exists => TRUE)")
    op.execute("SELECT add_retention_policy('telemetry', INTERVAL '90 days', if_not_exists => TRUE)")

    # ── Anomaly Events ─────────────────────────────────────────
    op.create_table('anomaly_events',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('flight_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('sensor_id', sa.String(32), nullable=True),
        sa.Column('ata_chapter', sa.Integer(), nullable=True),
        sa.Column('detected_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('resolved_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('anomaly_type', sa.String(64), nullable=False),
        sa.Column('severity', sa.Enum('INFO','LOW','MEDIUM','HIGH','CRITICAL', name='anomalyseverity'), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('reconstruction_error', sa.Float(), nullable=True),
        sa.Column('confidence', sa.Float(), nullable=True),
        sa.Column('raw_evidence', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('maintenance_action', sa.String(256), nullable=True),
        sa.Column('is_resolved', sa.Boolean(), server_default='false'),
        sa.Column('false_positive', sa.Boolean(), server_default='false'),
        sa.Column('reviewed_by', sa.String(128), nullable=True),
        sa.ForeignKeyConstraint(['flight_id'], ['flights.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_anomaly_detected_at', 'anomaly_events', ['detected_at'])
    op.create_index('ix_anomaly_severity', 'anomaly_events', ['severity'])
    op.create_index('ix_anomaly_ata', 'anomaly_events', ['ata_chapter'])

    # ── ECAM Advisories ────────────────────────────────────────
    op.create_table('ecam_advisories',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('flight_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('generated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('cleared_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('severity', sa.Enum('STATUS','CAUTION','WARNING','EMERGENCY', name='ecamseverity'), nullable=False),
        sa.Column('system', sa.String(16), nullable=True),
        sa.Column('ata_chapter', sa.Integer(), nullable=True),
        sa.Column('message', sa.String(256), nullable=False),
        sa.Column('procedure', sa.Text(), nullable=True),
        sa.Column('dispatch_impact', sa.Boolean(), server_default='false'),
        sa.Column('mel_reference', sa.String(64), nullable=True),
        sa.Column('is_active', sa.Boolean(), server_default='true'),
        sa.ForeignKeyConstraint(['flight_id'], ['flights.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_ecam_generated_at', 'ecam_advisories', ['generated_at'])
    op.create_index('ix_ecam_severity', 'ecam_advisories', ['severity'])
    op.create_index('ix_ecam_active', 'ecam_advisories', ['is_active'])

    # ── Dispatch Reports ───────────────────────────────────────
    op.create_table('dispatch_reports',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('aircraft_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('flight_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('generated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('generated_by', sa.String(128), nullable=True),
        sa.Column('status', sa.Enum('GO','NO_GO','PENDING','DEFERRED', name='dispatchstatus'), nullable=False),
        sa.Column('sensor_health_pct', sa.Float(), nullable=True),
        sa.Column('ai_confidence', sa.Float(), nullable=True),
        sa.Column('active_ecam_count', sa.Integer(), server_default='0'),
        sa.Column('anomaly_count', sa.Integer(), server_default='0'),
        sa.Column('failed_sensor_count', sa.Integer(), server_default='0'),
        sa.Column('checklist_results', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('maintenance_actions', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('hash_chain_ref', sa.String(64), nullable=True),
        sa.Column('pdf_path', sa.String(512), nullable=True),
        sa.Column('signature', sa.LargeBinary(), nullable=True),
        sa.Column('is_valid', sa.Boolean(), server_default='true'),
        sa.ForeignKeyConstraint(['aircraft_id'], ['aircraft.id']),
        sa.ForeignKeyConstraint(['flight_id'], ['flights.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_dispatch_generated_at', 'dispatch_reports', ['generated_at'])
    op.create_index('ix_dispatch_status', 'dispatch_reports', ['status'])

    # ── Hash Chain ─────────────────────────────────────────────
    op.create_table('hash_chain',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('sequence', sa.Integer(), nullable=False),
        sa.Column('scan_id', sa.String(32), nullable=False),
        sa.Column('timestamp', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('previous_hash', sa.String(64), nullable=False),
        sa.Column('block_hash', sa.String(64), nullable=False),
        sa.Column('sensor_count', sa.Integer(), server_default='8192'),
        sa.Column('healthy_count', sa.Integer(), nullable=True),
        sa.Column('anomaly_count', sa.Integer(), nullable=True),
        sa.Column('payload_summary', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('is_verified', sa.Boolean(), server_default='true'),
        sa.Column('tamper_detected', sa.Boolean(), server_default='false'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('sequence'),
        sa.UniqueConstraint('scan_id'),
        sa.UniqueConstraint('block_hash'),
    )
    op.create_index('ix_hash_chain_sequence', 'hash_chain', ['sequence'])
    op.create_index('ix_hash_chain_timestamp', 'hash_chain', ['timestamp'])

    # ── Maintenance Actions ────────────────────────────────────
    op.create_table('maintenance_actions',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('aircraft_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('anomaly_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('ata_chapter', sa.Integer(), nullable=True),
        sa.Column('action_type', sa.String(64), nullable=True),
        sa.Column('description', sa.Text(), nullable=False),
        sa.Column('priority', sa.String(16), nullable=True),
        sa.Column('mel_reference', sa.String(64), nullable=True),
        sa.Column('assigned_to', sa.String(128), nullable=True),
        sa.Column('due_by', sa.DateTime(timezone=True), nullable=True),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('is_completed', sa.Boolean(), server_default='false'),
        sa.Column('sign_off', sa.String(128), nullable=True),
        sa.Column('part_number', sa.String(64), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()')),
        sa.ForeignKeyConstraint(['aircraft_id'], ['aircraft.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_maintenance_ata', 'maintenance_actions', ['ata_chapter'])
    op.create_index('ix_maintenance_priority', 'maintenance_actions', ['priority'])

    # ── AI Models ──────────────────────────────────────────────
    op.create_table('ai_models',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('version', sa.String(32), nullable=False),
        sa.Column('model_type', sa.String(64), server_default='SPARSE_AUTOENCODER'),
        sa.Column('input_features', sa.Integer(), server_default='8192'),
        sa.Column('latent_dim', sa.Integer(), server_default='32'),
        sa.Column('encoder_config', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('training_samples', sa.Integer(), nullable=True),
        sa.Column('validation_loss', sa.Float(), nullable=True),
        sa.Column('false_positive_rate', sa.Float(), nullable=True),
        sa.Column('true_positive_rate', sa.Float(), nullable=True),
        sa.Column('anomaly_threshold', sa.Float(), server_default='0.15'),
        sa.Column('trained_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('deployed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('is_active', sa.Boolean(), server_default='false'),
        sa.Column('model_path', sa.String(512), nullable=True),
        sa.Column('checksum', sa.String(64), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()')),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('version'),
    )

    # ── Audit Logs ─────────────────────────────────────────────
    op.create_table('audit_logs',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('username', sa.String(64), nullable=True),
        sa.Column('action', sa.String(128), nullable=False),
        sa.Column('resource_type', sa.String(64), nullable=True),
        sa.Column('resource_id', sa.String(64), nullable=True),
        sa.Column('ip_address', sa.String(45), nullable=True),
        sa.Column('user_agent', sa.String(512), nullable=True),
        sa.Column('request_path', sa.String(512), nullable=True),
        sa.Column('request_method', sa.String(8), nullable=True),
        sa.Column('response_status', sa.Integer(), nullable=True),
        sa.Column('details', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('timestamp', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('session_id', sa.String(64), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_audit_timestamp', 'audit_logs', ['timestamp'])
    op.create_index('ix_audit_user', 'audit_logs', ['user_id'])
    op.create_index('ix_audit_action', 'audit_logs', ['action'])

    # ── Simulator Sessions ─────────────────────────────────────
    op.create_table('simulator_sessions',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('aircraft_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('simulator_type', sa.String(32), nullable=True),
        sa.Column('host', sa.String(256), nullable=True),
        sa.Column('port', sa.Integer(), nullable=True),
        sa.Column('connected_at', sa.DateTime(timezone=True), server_default=sa.text('now()')),
        sa.Column('disconnected_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('packets_received', sa.Integer(), server_default='0'),
        sa.Column('packets_dropped', sa.Integer(), server_default='0'),
        sa.Column('is_active', sa.Boolean(), server_default='true'),
        sa.Column('session_config', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.ForeignKeyConstraint(['aircraft_id'], ['aircraft.id']),
        sa.PrimaryKeyConstraint('id'),
    )

    # ── Replay Archives ────────────────────────────────────────
    op.create_table('replay_archives',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('aircraft_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('flight_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('name', sa.String(128), nullable=True),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('recorded_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('duration_sec', sa.Integer(), nullable=True),
        sa.Column('sensor_count', sa.Integer(), nullable=True),
        sa.Column('file_path', sa.String(512), nullable=True),
        sa.Column('file_size_bytes', sa.Integer(), nullable=True),
        sa.Column('checksum', sa.String(64), nullable=True),
        sa.Column('anomaly_count', sa.Integer(), server_default='0'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()')),
        sa.ForeignKeyConstraint(['aircraft_id'], ['aircraft.id']),
        sa.ForeignKeyConstraint(['flight_id'], ['flights.id']),
        sa.PrimaryKeyConstraint('id'),
    )


def downgrade() -> None:
    op.drop_table('replay_archives')
    op.drop_table('simulator_sessions')
    op.drop_table('audit_logs')
    op.drop_table('ai_models')
    op.drop_table('maintenance_actions')
    op.drop_table('hash_chain')
    op.drop_table('dispatch_reports')
    op.drop_table('ecam_advisories')
    op.drop_table('anomaly_events')
    op.drop_table('telemetry')
    op.drop_table('sensor_definitions')
    op.drop_table('flights')
    op.drop_table('aircraft')
    op.drop_table('user_sessions')
    op.drop_table('users')
    # Drop enums
    for enum in ['aircrafttype','dispatchstatus','ecamseverity','flightphase',
                 'anomalyseverity','sensorstate','userrole']:
        op.execute(f'DROP TYPE IF EXISTS {enum}')
