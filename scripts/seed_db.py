#!/usr/bin/env python3
"""
SentinelTwin — Database Seed Script
Populates: Users, Aircraft fleet, AI model record, Maintenance actions, Hash chain genesis
"""

import asyncio
import hashlib
import json
import sys
import uuid
from datetime import datetime, timezone, timedelta

import bcrypt

sys.path.insert(0, "..")

# ─────────────────────────────────────────────────────────────
# TERMINAL COLORS
# ─────────────────────────────────────────────────────────────

RESET  = "\033[0m"; GREEN = "\033[32m"; CYAN = "\033[36m"
YELLOW = "\033[33m"; RED = "\033[31m"; BOLD = "\033[1m"

def log(msg, color=CYAN):
    print(f"  {color}{msg}{RESET}")

def ok(msg):
    print(f"  {GREEN}✓ {msg}{RESET}")

def fail(msg):
    print(f"  {RED}✗ {msg}{RESET}")


# ─────────────────────────────────────────────────────────────
# 1. USERS — 6 roles
# ─────────────────────────────────────────────────────────────

USERS = [
    {
        "username": "admin",
        "email": "admin@sentineltwin.airbus.internal",
        "password": "sentinel2026",
        "full_name": "System Administrator",
        "role": "administrator",
    },
    {
        "username": "pilot",
        "email": "j.renaud@airbus.com",
        "password": "pilot2026",
        "full_name": "Capt. J. Renaud",
        "role": "pilot",
    },
    {
        "username": "engineer",
        "email": "m.bouchard@airbus.com",
        "password": "engineer2026",
        "full_name": "M. Bouchard — Avionics",
        "role": "maintenance_engineer",
    },
    {
        "username": "dispatcher",
        "email": "a.martin@airfrance.com",
        "password": "dispatcher2026",
        "full_name": "A. Martin — Operations",
        "role": "dispatcher",
    },
    {
        "username": "ground",
        "email": "ground@airbus.com",
        "password": "ground2026",
        "full_name": "Ground Crew Operator",
        "role": "ground_crew",
    },
    {
        "username": "inspector",
        "email": "p.leconte@airbus.com",
        "password": "inspector2026",
        "full_name": "P. Leconte — Quality Assurance",
        "role": "qa_inspector",
    },
]


# ─────────────────────────────────────────────────────────────
# 2. AIRCRAFT FLEET — 7 types
# ─────────────────────────────────────────────────────────────

AIRCRAFT_FLEET = [
    {
        "msn": "5001", "registration": "C-GJVX", "aircraft_type": "A220",
        "airline": "Air Canada", "line_number": 5001,
        "cycles": 2104, "flight_hours": 6812.4, "is_active": True,
        "profile": {
            "engines": ["PW1524G", "PW1524G"], "mtow_kg": 67585,
            "oew_kg": 37080, "max_pax": 160, "range_nm": 3400,
            "avionics": "AIRBUS A220 — ROCKWELL COLLINS PRO LINE FUSION",
        },
    },
    {
        "msn": "3201", "registration": "D-AIBF", "aircraft_type": "A319",
        "airline": "Lufthansa", "line_number": 3201,
        "cycles": 9321, "flight_hours": 22050.8, "is_active": True,
        "profile": {
            "engines": ["CFM56-5B6/3", "CFM56-5B6/3"], "mtow_kg": 75500,
            "max_pax": 138, "range_nm": 3750,
            "avionics": "AIRBUS A319 — CPIOM-B3",
        },
    },
    {
        "msn": "4892", "registration": "G-EUYA", "aircraft_type": "A320",
        "airline": "British Airways", "line_number": 4892,
        "cycles": 7210, "flight_hours": 17840.2, "is_active": True,
        "profile": {
            "engines": ["CFM56-5B4/P", "CFM56-5B4/P"], "mtow_kg": 77000,
            "max_pax": 180, "range_nm": 3300,
            "avionics": "AIRBUS A320 — CPIOM-B4",
        },
    },
    {
        "msn": "8234", "registration": "F-WXWB", "aircraft_type": "A320neo",
        "airline": "Air France", "line_number": 8234,
        "cycles": 4821, "flight_hours": 12450.3, "is_active": True,
        "profile": {
            "engines": ["LEAP-1A26", "LEAP-1A26"], "mtow_kg": 79000,
            "oew_kg": 42600, "max_pax": 180, "range_nm": 3400,
            "avionics": "AIRBUS A320 FAMILY — CPIOM-B4",
            "fadec": "LEAP-1A26 FADEC REV 5.2",
            "fms": "THALES FMS SMART.S",
        },
    },
    {
        "msn": "7103", "registration": "EC-MXV", "aircraft_type": "A321",
        "airline": "Iberia", "line_number": 7103,
        "cycles": 5891, "flight_hours": 15420.7, "is_active": False,   # MAINTENANCE
        "profile": {
            "engines": ["CFM56-5B3/3", "CFM56-5B3/3"], "mtow_kg": 93500,
            "max_pax": 220, "range_nm": 3200,
            "avionics": "AIRBUS A321 — CPIOM-B4",
        },
    },
    {
        "msn": "1687", "registration": "A6-EKT", "aircraft_type": "A330",
        "airline": "Emirates", "line_number": 1687,
        "cycles": 5102, "flight_hours": 28430.1, "is_active": True,
        "profile": {
            "engines": ["Trent 772B-60", "Trent 772B-60"], "mtow_kg": 233000,
            "max_pax": 277, "range_nm": 6350,
            "avionics": "AIRBUS A330 — CPIOM-B5",
        },
    },
    {
        "msn": "0401", "registration": "B-LRB", "aircraft_type": "A350",
        "airline": "Cathay Pacific", "line_number": 401,
        "cycles": 1823, "flight_hours": 5840.2, "is_active": True,
        "profile": {
            "engines": ["Trent XWB-84", "Trent XWB-84"], "mtow_kg": 280000,
            "max_pax": 350, "range_nm": 8100,
            "avionics": "AIRBUS A350 — CPIOM-B6",
        },
    },
]


# ─────────────────────────────────────────────────────────────
# 3. AI MODEL RECORD
# ─────────────────────────────────────────────────────────────

AI_MODEL = {
    "version": "v2.4.1",
    "model_type": "SparseAutoencoder",
    "input_features": 256,
    "latent_dim": 32,
    "encoder_config": {
        "architecture": "256→128→64→32",
        "encoder_layers": [256, 128, 64, 32],
        "decoder_layers": [32, 64, 128, 256],
        "activation": "relu",
        "output_activation": "linear",
        "sparsity_target": 0.05,
        "sparsity_weight": 0.1,
        "input_type": "physics_normalised_residuals",
        "training_scope": "GROUND",
    },
    "training_samples": 50000,
    "validation_loss": 0.00023,
    "false_positive_rate": 0.004,
    "true_positive_rate": 0.94,
    "anomaly_threshold": 0.15,
    "is_active": True,
    "notes": "Production model — trained on A320 family ground-phase telemetry. "
             "Physics-normalised residuals with statistical anomaly layer.",
}


# ─────────────────────────────────────────────────────────────
# 4. MAINTENANCE ACTIONS — 5 for A320neo (MSN 8234)
# ─────────────────────────────────────────────────────────────

MAINTENANCE_ACTIONS = [
    {
        "title": "Replace ENG1 Oil Filter",
        "ata_chapter": 71,
        "action_type": "REPLACEMENT",
        "description": "ENG1 oil filter — pressure differential exceeded limit. "
                       "Replace oil filter element per AMM 79-11-01.",
        "priority": "ROUTINE",
        "status": "OPEN",
        "mel_reference": "MEL 79-001",
        "assigned_to": "R. Schmidt",
        "is_completed": False,
    },
    {
        "title": "HYD Green Pump Check",
        "ata_chapter": 29,
        "action_type": "INSPECTION",
        "description": "HYD GREEN pump 1 pressure transducer — calibration drift detected "
                       "by SentinelTwin AI. Inspect and recalibrate.",
        "priority": "URGENT",
        "status": "IN_PROGRESS",
        "mel_reference": "MEL 29-001",
        "assigned_to": "J. Martin",
        "is_completed": False,
    },
    {
        "title": "NAV ADR 1 Calibration",
        "ata_chapter": 34,
        "action_type": "CALIBRATION",
        "description": "IRS-1 heading drift — gyro bias recalibration required per "
                       "SentinelTwin anomaly event AE-20260510-0042.",
        "priority": "ROUTINE",
        "status": "OPEN",
        "mel_reference": "MEL 34-002",
        "assigned_to": "P. Dubois",
        "is_completed": False,
    },
    {
        "title": "FADEC Software Update",
        "ata_chapter": 71,
        "action_type": "SOFTWARE_UPDATE",
        "description": "FADEC software update to REV 5.3 — addresses intermittent N1 "
                       "overshoot anomaly during takeoff phase transition.",
        "priority": "DEFERRED",
        "status": "OPEN",
        "mel_reference": None,
        "assigned_to": "M. Bouchard",
        "is_completed": False,
    },
    {
        "title": "Landing Gear Inspection",
        "ata_chapter": 32,
        "action_type": "INSPECTION",
        "description": "MLG bogie beam — routine inspection completed per "
                       "scheduled maintenance. No defects found.",
        "priority": "IMMEDIATE",
        "status": "COMPLETED",
        "mel_reference": None,
        "assigned_to": "T. Moreau",
        "is_completed": True,
    },
]


# ─────────────────────────────────────────────────────────────
# SEED FUNCTIONS
# ─────────────────────────────────────────────────────────────

async def seed_users(conn):
    log("Seeding users (6 roles)...")
    count = 0
    for u in USERS:
        uid = str(uuid.uuid4())
        hashed = bcrypt.hashpw(
            u["password"].encode(), bcrypt.gensalt(rounds=12)
        ).decode()
        result = await conn.execute("""
            INSERT INTO users (id, username, email, hashed_password, full_name, role, is_active, created_at)
            VALUES ($1, $2, $3, $4, $5, $6, true, now())
            ON CONFLICT (username) DO NOTHING
        """, uid, u["username"], u["email"], hashed, u["full_name"], u["role"])
        if result == "INSERT 0 1":
            ok(f"User: {u['username']:12s} ({u['role']})")
            count += 1
        else:
            log(f"  Skipped (exists): {u['username']}", color=YELLOW)
    return count


async def seed_aircraft(conn):
    log("\nSeeding aircraft fleet (7 types)...")
    aircraft_ids = {}
    count = 0
    for a in AIRCRAFT_FLEET:
        aid = str(uuid.uuid4())
        aircraft_ids[a["msn"]] = aid
        result = await conn.execute("""
            INSERT INTO aircraft (id, msn, registration, aircraft_type, airline,
                                  line_number, cycles, flight_hours, is_active,
                                  profile, created_at)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, now())
            ON CONFLICT (msn) DO NOTHING
        """, aid, a["msn"], a["registration"], a["aircraft_type"], a["airline"],
            a.get("line_number", 0), a.get("cycles", 0), a.get("flight_hours", 0.0),
            a.get("is_active", True), json.dumps(a.get("profile", {})))
        if result == "INSERT 0 1":
            status = "ACTIVE" if a.get("is_active", True) else "MAINTENANCE"
            ok(f"Aircraft: {a['registration']:8s} {a['aircraft_type']:8s} MSN {a['msn']} — {a['airline']} [{status}]")
            count += 1
        else:
            log(f"  Skipped (exists): MSN {a['msn']}", color=YELLOW)
    return aircraft_ids, count


async def seed_ai_model(conn):
    log("\nSeeding AI model record...")
    m = AI_MODEL
    mid = str(uuid.uuid4())
    result = await conn.execute("""
        INSERT INTO ai_models (id, version, model_type, input_features, latent_dim,
                               encoder_config, training_samples, validation_loss,
                               false_positive_rate, true_positive_rate, anomaly_threshold,
                               is_active, notes, created_at)
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, now())
        ON CONFLICT (version) DO NOTHING
    """, mid, m["version"], m["model_type"], m["input_features"], m["latent_dim"],
        json.dumps(m.get("encoder_config", {})), m.get("training_samples", 0),
        m.get("validation_loss", 0.0), m.get("false_positive_rate", 0.0),
        m.get("true_positive_rate", 0.0), m.get("anomaly_threshold", 0.15),
        m.get("is_active", False), m.get("notes", ""))
    if result == "INSERT 0 1":
        ok(f"AI Model: {m['version']} — {m['model_type']} "
           f"(FPR={m['false_positive_rate']:.4f}, TPR={m['true_positive_rate']:.3f})")
        return 1
    else:
        log(f"  Skipped (exists): {m['version']}", color=YELLOW)
        return 0


async def seed_maintenance_actions(conn, aircraft_ids):
    log("\nSeeding maintenance actions (5 for A320neo MSN 8234)...")
    target_msn = "8234"
    # Look up the real aircraft ID from DB if we don't have it in aircraft_ids
    aircraft_uuid = aircraft_ids.get(target_msn)
    if not aircraft_uuid:
        row = await conn.fetchrow(
            "SELECT id FROM aircraft WHERE msn = $1", target_msn
        )
        if row:
            aircraft_uuid = str(row["id"])
        else:
            fail(f"Aircraft MSN {target_msn} not found — skipping maintenance actions")
            return 0

    count = 0
    for ma in MAINTENANCE_ACTIONS:
        maid = str(uuid.uuid4())
        completed_at = datetime.now(timezone.utc) if ma["is_completed"] else None
        await conn.execute("""
            INSERT INTO maintenance_actions
                (id, aircraft_id, ata_chapter, action_type, description,
                 priority, mel_reference, assigned_to, is_completed,
                 completed_at, created_at)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, now())
        """, maid, aircraft_uuid, ma["ata_chapter"], ma["action_type"],
            ma["description"], ma["priority"], ma.get("mel_reference"),
            ma["assigned_to"], ma["is_completed"], completed_at)
        status_icon = "✓" if ma["is_completed"] else "○"
        ok(f"[{status_icon}] {ma['title']} (ATA {ma['ata_chapter']}, {ma['priority']})")
        count += 1
    return count


async def seed_hash_chain_genesis(conn):
    log("\nSeeding hash chain genesis block...")
    genesis_hash = "0" * 64
    block_content = f"{genesis_hash}:GENESIS:SentinelTwin-v4.2.1"
    block_hash = hashlib.sha256(block_content.encode()).hexdigest()
    block_id = str(uuid.uuid4())

    result = await conn.execute("""
        INSERT INTO hash_chain
            (id, sequence, scan_id, timestamp, previous_hash, block_hash,
             sensor_count, healthy_count, anomaly_count, is_verified, tamper_detected)
        VALUES ($1, 0, 'SCN-GENESIS', now(), $2, $3, 8192, 8192, 0, true, false)
        ON CONFLICT (sequence) DO NOTHING
    """, block_id, genesis_hash, block_hash)

    if result == "INSERT 0 1":
        ok(f"Genesis block: {block_hash[:32]}...")
        return 1
    else:
        log("  Skipped (exists): Genesis block", color=YELLOW)
        return 0


# ─────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────

DB_URL = "postgresql://sentineltwin:sentinel_secure_pw@localhost:5432/sentineltwin"


async def main():
    print(f"\n{BOLD}{CYAN}")
    print("╔══════════════════════════════════════════════════════════╗")
    print("║     SENTINELTWIN — DATABASE SEED SCRIPT                 ║")
    print("║     Users · Fleet · AI Model · Maintenance · Hash Chain ║")
    print("╚══════════════════════════════════════════════════════════╝")
    print(f"{RESET}")

    try:
        import asyncpg
    except ImportError:
        log("asyncpg not installed — run: pip install asyncpg", color=YELLOW)
        log("Seed data defined. Run after PostgreSQL is ready.", color=YELLOW)
        return

    try:
        conn = await asyncpg.connect(DB_URL)
        log(f"Connected to PostgreSQL ({DB_URL.split('@')[1]})")
    except Exception as e:
        fail(f"Connection failed: {e}")
        log("Ensure PostgreSQL is running and migrations have been applied.", color=YELLOW)
        raise

    try:
        n_users = await seed_users(conn)
        aircraft_ids, n_aircraft = await seed_aircraft(conn)
        n_models = await seed_ai_model(conn)
        n_maint = await seed_maintenance_actions(conn, aircraft_ids)
        n_hash = await seed_hash_chain_genesis(conn)

        await conn.close()

        print(f"\n{GREEN}{BOLD}")
        print("  ╔══════════════════════════════════════════════════════╗")
        print("  ║  DATABASE SEED COMPLETE                              ║")
        print(f"  ║  Users:        {n_users}                                     ║")
        print(f"  ║  Aircraft:     {n_aircraft}                                     ║")
        print(f"  ║  AI Models:    {n_models}                                     ║")
        print(f"  ║  Maintenance:  {n_maint}                                     ║")
        print(f"  ║  Hash Genesis: {n_hash}                                     ║")
        print("  ╚══════════════════════════════════════════════════════╝")
        print(f"{RESET}")

    except Exception as e:
        await conn.close()
        fail(f"Seed error: {e}")
        raise


if __name__ == "__main__":
    asyncio.run(main())
