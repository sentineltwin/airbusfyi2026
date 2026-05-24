#!/usr/bin/env python3
"""
SentinelTwin — TimescaleDB Post-Migration Setup
Run AFTER alembic upgrade head to convert tables to hypertables
and apply retention + compression policies.

Usage:
    python3 scripts/setup_timescaledb.py
    python3 scripts/setup_timescaledb.py --check   (verify only, no changes)
"""

import asyncio
import sys
import os
from pathlib import Path

# Allow importing from backend/
sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))

DB_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+asyncpg://sentineltwin:sentinel_secure_pw@localhost:5432/sentineltwin",
)

# ── Hypertable configuration ──────────────────────────────────────────────────
HYPERTABLES = [
    {
        "table":          "telemetry_readings",
        "time_col":       "timestamp",
        "chunk_time":     "1 day",
        "compress_after": "7 days",
        "drop_after":     "90 days",
    },
    {
        "table":          "anomaly_events",
        "time_col":       "detected_at",
        "chunk_time":     "7 days",
        "compress_after": "30 days",
        "drop_after":     None,     # Anomaly events kept forever
    },
    {
        "table":          "operational_logs",
        "time_col":       "timestamp",
        "chunk_time":     "1 day",
        "compress_after": "3 days",
        "drop_after":     "90 days",
    },
]

# Hash chain and audit logs are NEVER dropped — EASA Part M mandates 7-year retention.
PERMANENT_TABLES = ["hash_chain", "audit_logs"]

CHECK_ONLY = "--check" in sys.argv

# ── ANSI colour helpers ───────────────────────────────────────────────────────
RESET  = "\033[0m"
GREEN  = "\033[92m"
YELLOW = "\033[93m"
CYAN   = "\033[96m"
RED    = "\033[91m"

def ok(m):   print(f"  {GREEN}✓{RESET} {m}")
def warn(m): print(f"  {YELLOW}⚠{RESET} {m}")
def info(m): print(f"  {CYAN}›{RESET} {m}")
def err(m):  print(f"  {RED}✗{RESET} {m}")


# ── Main setup coroutine ──────────────────────────────────────────────────────
async def setup() -> None:
    try:
        from sqlalchemy.ext.asyncio import create_async_engine
        from sqlalchemy import text
    except ImportError:
        err("sqlalchemy / asyncpg not installed — run: pip install sqlalchemy asyncpg")
        sys.exit(1)

    engine = create_async_engine(DB_URL, echo=False)

    print(f"\n{CYAN}SentinelTwin — TimescaleDB Setup{RESET}")
    print("─" * 50)

    async with engine.connect() as conn:

        # 1. Verify TimescaleDB extension is installed
        result = await conn.execute(
            text("SELECT extversion FROM pg_extension WHERE extname='timescaledb'")
        )
        ts_ver = result.scalar()
        if ts_ver:
            ok(f"TimescaleDB extension: v{ts_ver}")
        else:
            warn("TimescaleDB extension not found — skipping hypertable setup")
            warn("Install guide: https://docs.timescale.com/self-hosted/latest/install/")
            await engine.dispose()
            return

        # 2. Process each hypertable
        for ht in HYPERTABLES:
            tbl  = ht["table"]
            tcol = ht["time_col"]

            # Check the underlying Postgres table exists
            exists_result = await conn.execute(text(
                "SELECT EXISTS ("
                "  SELECT FROM information_schema.tables"
                f" WHERE table_name='{tbl}'"
                ")"
            ))
            if not exists_result.scalar():
                warn(f"Table '{tbl}' does not exist — run alembic upgrade head first")
                continue

            # Check if already configured as a hypertable
            ht_result = await conn.execute(text(
                "SELECT COUNT(*) FROM timescaledb_information.hypertables"
                f" WHERE hypertable_name='{tbl}'"
            ))
            already = (ht_result.scalar() or 0) > 0

            if already:
                ok(f"Hypertable '{tbl}' already configured")
            elif CHECK_ONLY:
                warn(f"Hypertable '{tbl}' NOT configured (run without --check to fix)")
                continue
            else:
                await conn.execute(text(
                    f"SELECT create_hypertable('{tbl}', '{tcol}',"
                    f" chunk_time_interval => INTERVAL '{ht['chunk_time']}',"
                    f" if_not_exists => TRUE)"
                ))
                await conn.commit()
                ok(f"Hypertable '{tbl}' created  (chunk: {ht['chunk_time']})")

            if CHECK_ONLY:
                continue

            # 3. Enable column-level compression
            try:
                await conn.execute(text(
                    f"ALTER TABLE {tbl} SET ("
                    f"  timescaledb.compress,"
                    f"  timescaledb.compress_orderby = '{tcol} DESC'"
                    f")"
                ))
                await conn.commit()
                ok(f"  Compression enabled on '{tbl}'")
            except Exception as exc:
                warn(f"  Compression setup failed for '{tbl}': {exc}")

            # 4. Attach compression policy
            if ht["compress_after"]:
                try:
                    await conn.execute(text(
                        f"SELECT add_compression_policy('{tbl}',"
                        f" INTERVAL '{ht['compress_after']}',"
                        f" if_not_exists => TRUE)"
                    ))
                    await conn.commit()
                    ok(f"  Compress after: {ht['compress_after']}")
                except Exception as exc:
                    warn(f"  Compression policy failed for '{tbl}': {exc}")

            # 5. Attach data-retention policy (WHERE applicable)
            if ht["drop_after"]:
                try:
                    await conn.execute(text(
                        f"SELECT add_retention_policy('{tbl}',"
                        f" INTERVAL '{ht['drop_after']}',"
                        f" if_not_exists => TRUE)"
                    ))
                    await conn.commit()
                    ok(f"  Retention policy: drop after {ht['drop_after']}")
                except Exception as exc:
                    warn(f"  Retention policy failed for '{tbl}': {exc}")

        # 6. Document permanent tables (no retention — regulatory requirement)
        print()
        for tbl in PERMANENT_TABLES:
            info(f"Table '{tbl}': PERMANENT — no retention policy applied (EASA Part M §M.A.305)")

        # 7. Summary
        print()
        print("─" * 50)
        if CHECK_ONLY:
            info("Check complete. Re-run without --check to apply changes.")
        else:
            ok("TimescaleDB setup complete")
            ok("Hypertables, compression policies, and retention policies applied")

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(setup())
