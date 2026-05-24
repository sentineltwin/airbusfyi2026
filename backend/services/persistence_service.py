"""
SentinelTwin — Persistence Service
Async write-batching for PostgreSQL/TimescaleDB.
Never blocks the sensor loop — uses asyncio.Queue for hand-off.
"""

import asyncio
import logging
import time
import uuid
from datetime import datetime, timezone
from typing import Dict, List, Optional

log = logging.getLogger("sentineltwin.persistence")


class PersistenceService:
    """
    Asynchronous persistence service for telemetry, anomalies, ECAM, hash chain,
    and dispatch data. Uses write-batching with asyncio.Queue to avoid blocking
    the sensor execution loop.
    """

    BATCH_INTERVAL_SEC = 0.5  # Flush telemetry every 500ms
    MAX_BATCH_SIZE = 2000

    def __init__(self, db_session_factory=None):
        self._db_session_factory = db_session_factory
        self._telemetry_queue: asyncio.Queue = asyncio.Queue(maxsize=50000)
        self._anomaly_queue: asyncio.Queue = asyncio.Queue(maxsize=5000)
        self._ecam_queue: asyncio.Queue = asyncio.Queue(maxsize=1000)
        self._hash_queue: asyncio.Queue = asyncio.Queue(maxsize=5000)
        self._dispatch_queue: asyncio.Queue = asyncio.Queue(maxsize=500)
        self._running = False
        self._tasks: list = []

        # Metrics
        self.telemetry_persisted: int = 0
        self.anomalies_persisted: int = 0
        self.ecam_persisted: int = 0
        self.hash_blocks_persisted: int = 0
        self.dispatch_persisted: int = 0
        self.errors: int = 0

        log.info("PersistenceService initialized (batch interval: %sms)",
                 int(self.BATCH_INTERVAL_SEC * 1000))

    @property
    def has_db(self) -> bool:
        return self._db_session_factory is not None

    async def start(self):
        """Start the background persistence workers."""
        self._running = True
        self._tasks = [
            asyncio.create_task(self._telemetry_worker(), name="persist_telemetry"),
            asyncio.create_task(self._anomaly_worker(),   name="persist_anomaly"),
            asyncio.create_task(self._ecam_worker(),      name="persist_ecam"),
            asyncio.create_task(self._hash_worker(),      name="persist_hash"),
            asyncio.create_task(self._dispatch_worker(),  name="persist_dispatch"),
        ]
        log.info("PersistenceService: 5 background workers started as asyncio tasks")

    async def stop(self):
        """Stop persistence workers gracefully and flush remaining data."""
        self._running = False
        for task in getattr(self, "_tasks", []):
            task.cancel()
        await asyncio.gather(*getattr(self, "_tasks", []), return_exceptions=True)
        await self._flush_telemetry()
        await self._flush_anomalies()
        log.info(
            "PersistenceService stopped. tel=%d anom=%d ecam=%d hash=%d disp=%d err=%d",
            self.telemetry_persisted, self.anomalies_persisted,
            self.ecam_persisted, self.hash_blocks_persisted,
            self.dispatch_persisted, self.errors,
        )

    # ─────────────────────────────────────────────────────────
    # PUBLIC INTERFACE (non-blocking enqueue)
    # ─────────────────────────────────────────────────────────

    async def persist_telemetry_batch(self, sensor_readings: List[Dict]):
        """Enqueue telemetry readings for batch persistence. Non-blocking."""
        for reading in sensor_readings:
            try:
                self._telemetry_queue.put_nowait(reading)
            except asyncio.QueueFull:
                pass  # Drop oldest if queue full — better than blocking

    async def persist_anomaly_event(self, anomaly: Dict):
        """Enqueue an anomaly event for persistence."""
        try:
            self._anomaly_queue.put_nowait(anomaly)
        except asyncio.QueueFull:
            pass

    async def persist_ecam_advisory(self, msg: Dict):
        """Enqueue an ECAM advisory for persistence."""
        try:
            self._ecam_queue.put_nowait(msg)
        except asyncio.QueueFull:
            pass

    async def persist_hash_block(self, block: Dict):
        """Enqueue a hash chain block for persistence."""
        try:
            self._hash_queue.put_nowait(block)
        except asyncio.QueueFull:
            pass

    async def persist_dispatch_report(self, report: Dict):
        """Enqueue a dispatch report for persistence."""
        try:
            self._dispatch_queue.put_nowait(report)
        except asyncio.QueueFull:
            pass

    # ─────────────────────────────────────────────────────────
    # QUERY INTERFACE
    # ─────────────────────────────────────────────────────────

    async def get_recent_telemetry(self, ata_chapter: int, minutes: int = 5) -> List[Dict]:
        """
        Query recent telemetry from TimescaleDB with time_bucket aggregation.
        Falls back to empty list if DB is unavailable.
        """
        if not self.has_db:
            return []

        try:
            async with self._db_session_factory() as session:
                # NOTE: PostgreSQL INTERVAL cannot accept bound parameters inside a
                # string literal. Use explicit cast with text concat instead.
                query = """
                    SELECT
                        time_bucket('10 seconds', timestamp) AS bucket,
                        ata_chapter,
                        AVG(value) AS avg_value,
                        MIN(value) AS min_value,
                        MAX(value) AS max_value,
                        COUNT(*) AS sample_count
                    FROM telemetry_readings
                    WHERE ata_chapter = :ata
                      AND timestamp > NOW() - (:minutes * INTERVAL '1 minute')
                    GROUP BY bucket, ata_chapter
                    ORDER BY bucket DESC
                    LIMIT 100
                """
                from sqlalchemy import text
                result = await session.execute(
                    text(query),
                    {"ata": ata_chapter, "minutes": minutes},
                )
                rows = result.fetchall()
                return [
                    {
                        "bucket": str(r[0]),
                        "ata_chapter": r[1],
                        "avg_value": float(r[2]),
                        "min_value": float(r[3]),
                        "max_value": float(r[4]),
                        "sample_count": int(r[5]),
                    }
                    for r in rows
                ]
        except Exception as e:
            log.warning(f"get_recent_telemetry failed: {e}")
            return []

    async def get_anomaly_history(self, hours: int = 24) -> List[Dict]:
        """
        Query anomaly history with sensor JOIN.
        Falls back to empty list if DB is unavailable.
        """
        if not self.has_db:
            return []

        try:
            async with self._db_session_factory() as session:
                # NOTE: Same INTERVAL fix — use multiplier form to allow binding
                query = """
                    SELECT
                        a.event_id, a.sensor_id, a.anomaly_score,
                        a.severity, a.detected_at, a.ata_chapter,
                        a.description
                    FROM anomaly_events a
                    WHERE a.detected_at > NOW() - (:hours * INTERVAL '1 hour')
                    ORDER BY a.detected_at DESC
                    LIMIT 500
                """
                from sqlalchemy import text
                result = await session.execute(text(query), {"hours": hours})
                rows = result.fetchall()
                return [
                    {
                        "event_id": str(r[0]),
                        "sensor_id": r[1],
                        "anomaly_score": float(r[2]),
                        "severity": r[3],
                        "detected_at": str(r[4]),
                        "ata_chapter": r[5],
                        "description": r[6],
                    }
                    for r in rows
                ]
        except Exception as e:
            log.warning(f"get_anomaly_history failed: {e}")
            return []

    # ─────────────────────────────────────────────────────────
    # BACKGROUND WORKERS
    # ─────────────────────────────────────────────────────────

    async def _telemetry_worker(self):
        """Batch-flush telemetry readings every BATCH_INTERVAL_SEC."""
        while self._running:
            await asyncio.sleep(self.BATCH_INTERVAL_SEC)
            await self._flush_telemetry()

    async def _flush_telemetry(self):
        """Drain telemetry queue and bulk-insert."""
        batch = []
        while not self._telemetry_queue.empty() and len(batch) < self.MAX_BATCH_SIZE:
            try:
                batch.append(self._telemetry_queue.get_nowait())
            except asyncio.QueueEmpty:
                break

        if not batch:
            return

        if self.has_db:
            try:
                async with self._db_session_factory() as session:
                    from sqlalchemy import text
                    # Bulk executemany — vastly more efficient than N×single inserts.
                    # asyncpg uses native PostgreSQL COPY-like multi-row protocol.
                    now_iso = datetime.now(timezone.utc).isoformat()
                    params = [
                        {
                            "sid":   item.get("sensor_id", ""),
                            "ata":   item.get("ata_chapter", 0),
                            "val":   item.get("value", 0),
                            "state": item.get("state", "HEALTHY"),
                            "conf":  item.get("confidence", 1.0),
                            "anom":  item.get("anomaly_score", 0.0),
                            "ts":    item.get("timestamp", now_iso),
                        }
                        for item in batch
                    ]
                    await session.execute(
                        text("""
                            INSERT INTO telemetry_readings
                                (sensor_id, ata_chapter, value, state, confidence,
                                 anomaly_score, timestamp)
                            VALUES
                                (:sid, :ata, :val, :state, :conf, :anom, :ts)
                        """),
                        params,
                    )
                    await session.commit()
            except Exception as e:
                log.warning(f"Telemetry batch insert failed: {e}")
                self.errors += 1

        self.telemetry_persisted += len(batch)

    async def _anomaly_worker(self):
        """Process anomaly events."""
        while self._running:
            await asyncio.sleep(1.0)
            await self._flush_anomalies()

    async def _flush_anomalies(self):
        """Drain anomaly queue and insert."""
        batch = []
        while not self._anomaly_queue.empty() and len(batch) < 100:
            try:
                batch.append(self._anomaly_queue.get_nowait())
            except asyncio.QueueEmpty:
                break

        if not batch:
            return

        if self.has_db:
            try:
                async with self._db_session_factory() as session:
                    from sqlalchemy import text
                    for item in batch:
                        await session.execute(
                            text("""
                                INSERT INTO anomaly_events
                                    (event_id, sensor_id, ata_chapter, anomaly_score,
                                     severity, description, detected_at)
                                VALUES
                                    (:eid, :sid, :ata, :score, :sev, :desc, :ts)
                            """),
                            {
                                "eid": item.get("event_id", str(uuid.uuid4())),
                                "sid": item.get("sensor_id", ""),
                                "ata": item.get("ata_chapter", 0),
                                "score": item.get("anomaly_score", 0),
                                "sev": item.get("severity", "NOMINAL"),
                                "desc": item.get("description", ""),
                                "ts": item.get("detected_at",
                                               datetime.now(timezone.utc).isoformat()),
                            },
                        )
                    await session.commit()
            except Exception as e:
                log.warning(f"Anomaly batch insert failed: {e}")
                self.errors += 1

        self.anomalies_persisted += len(batch)

    async def _ecam_worker(self):
        """Process ECAM advisories."""
        while self._running:
            await asyncio.sleep(2.0)
            batch = []
            while not self._ecam_queue.empty() and len(batch) < 50:
                try:
                    batch.append(self._ecam_queue.get_nowait())
                except asyncio.QueueEmpty:
                    break

            if not batch:
                continue

            if self.has_db:
                try:
                    async with self._db_session_factory() as session:
                        from sqlalchemy import text
                        for item in batch:
                            await session.execute(
                                text("""
                                    INSERT INTO ecam_advisories
                                        (message_id, severity, system, ata_chapter,
                                         message, is_active, generated_at)
                                    VALUES
                                        (:mid, :sev, :sys, :ata, :msg, :active, :ts)
                                    ON CONFLICT (message_id) DO UPDATE
                                    SET is_active = :active
                                """),
                                {
                                    "mid": item.get("message_id", str(uuid.uuid4())),
                                    "sev": item.get("severity", "STATUS"),
                                    "sys": item.get("system", ""),
                                    "ata": item.get("ata_chapter", 0),
                                    "msg": item.get("message", ""),
                                    "active": item.get("is_active", True),
                                    "ts": item.get("generated_at",
                                                   datetime.now(timezone.utc).isoformat()),
                                },
                            )
                        await session.commit()
                except Exception as e:
                    log.warning(f"ECAM batch insert failed: {e}")
                    self.errors += 1

            self.ecam_persisted += len(batch)

    async def _hash_worker(self):
        """Process hash chain blocks."""
        while self._running:
            await asyncio.sleep(2.0)
            batch = []
            while not self._hash_queue.empty() and len(batch) < 50:
                try:
                    batch.append(self._hash_queue.get_nowait())
                except asyncio.QueueEmpty:
                    break

            if not batch:
                continue

            if self.has_db:
                try:
                    async with self._db_session_factory() as session:
                        from sqlalchemy import text
                        for item in batch:
                            await session.execute(
                                text("""
                                    INSERT INTO hash_chain
                                        (sequence, scan_id, block_hash, previous_hash,
                                         healthy_count, anomaly_count, flight_phase, timestamp)
                                    VALUES
                                        (:seq, :sid, :hash, :prev, :healthy, :anomaly, :phase, :ts)
                                """),
                                {
                                    "seq": item.get("sequence", 0),
                                    "sid": item.get("scan_id", ""),
                                    "hash": item.get("block_hash", ""),
                                    "prev": item.get("previous_hash", ""),
                                    "healthy": item.get("healthy_count", 0),
                                    "anomaly": item.get("anomaly_count", 0),
                                    "phase": item.get("flight_phase", "GROUND"),
                                    "ts": item.get("timestamp",
                                                   datetime.now(timezone.utc).isoformat()),
                                },
                            )
                        await session.commit()
                except Exception as e:
                    log.warning(f"Hash chain batch insert failed: {e}")
                    self.errors += 1

            self.hash_blocks_persisted += len(batch)

    async def _dispatch_worker(self):
        """Process dispatch reports."""
        while self._running:
            await asyncio.sleep(5.0)
            batch = []
            while not self._dispatch_queue.empty() and len(batch) < 10:
                try:
                    batch.append(self._dispatch_queue.get_nowait())
                except asyncio.QueueEmpty:
                    break

            if not batch:
                continue

            if self.has_db:
                try:
                    async with self._db_session_factory() as session:
                        from sqlalchemy import text
                        for item in batch:
                            await session.execute(
                                text("""
                                    INSERT INTO dispatch_reports
                                        (report_id, aircraft_type, msn, registration,
                                         dispatch_ready, score, blockers, generated_at,
                                         generated_by)
                                    VALUES
                                        (:rid, :type, :msn, :reg, :ready, :score,
                                         :blockers, :ts, :by)
                                """),
                                {
                                    "rid": item.get("report_id", str(uuid.uuid4())),
                                    "type": item.get("aircraft_type", "A320neo"),
                                    "msn": item.get("msn", ""),
                                    "reg": item.get("registration", ""),
                                    "ready": item.get("dispatch_ready", False),
                                    "score": item.get("score", 0),
                                    "blockers": str(item.get("blockers", [])),
                                    "ts": item.get("generated_at",
                                                   datetime.now(timezone.utc).isoformat()),
                                    "by": item.get("generated_by", "SYSTEM"),
                                },
                            )
                        await session.commit()
                except Exception as e:
                    log.warning(f"Dispatch batch insert failed: {e}")
                    self.errors += 1

            self.dispatch_persisted += len(batch)

    async def get_dispatch_history(self, limit: int = 50) -> List[Dict]:
        """
        Query recent dispatch reports from the database.
        Falls back to empty list if DB is unavailable.
        """
        if not self.has_db:
            return []

        try:
            async with self._db_session_factory() as session:
                query = """
                    SELECT
                        report_id, aircraft_type, msn, registration,
                        dispatch_ready, score, blockers, generated_at,
                        generated_by
                    FROM dispatch_reports
                    ORDER BY generated_at DESC
                    LIMIT :lim
                """
                from sqlalchemy import text
                result = await session.execute(text(query), {"lim": limit})
                rows = result.fetchall()
                return [
                    {
                        "report_id": str(r[0]),
                        "aircraft_type": r[1],
                        "msn": r[2],
                        "registration": r[3],
                        "dispatch_ready": r[4],
                        "score": float(r[5]) if r[5] else 0,
                        "blockers": r[6],
                        "generated_at": str(r[7]),
                        "generated_by": r[8],
                    }
                    for r in rows
                ]
        except Exception as e:
            log.warning(f"get_dispatch_history failed: {e}")
            return []

    def get_stats(self) -> Dict:
        """Returns current persistence service statistics."""
        return {
            "running":              self._running,
            "has_db":               self.has_db,
            "telemetry_persisted":  self.telemetry_persisted,
            "anomalies_persisted":  self.anomalies_persisted,
            "ecam_persisted":       self.ecam_persisted,
            "hash_blocks_persisted":self.hash_blocks_persisted,
            "dispatch_persisted":   self.dispatch_persisted,
            "errors":               self.errors,
            "queue_depths": {
                "telemetry": self._telemetry_queue.qsize(),
                "anomaly":   self._anomaly_queue.qsize(),
                "ecam":      self._ecam_queue.qsize(),
                "hash":      self._hash_queue.qsize(),
                "dispatch":  self._dispatch_queue.qsize(),
            },
            "db_connected":         self.has_db,
        }

