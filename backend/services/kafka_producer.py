"""
SentinelTwin — Kafka Event Producer
Publishes anomaly and ECAM events to Kafka topics for downstream consumers.
Gracefully degrades if Kafka is unavailable.
"""

import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional

log = logging.getLogger("sentineltwin.kafka")

TOPIC_ANOMALIES = "sentineltwin.anomalies"
TOPIC_ECAM      = "sentineltwin.ecam"
TOPIC_DISPATCH  = "sentineltwin.dispatch"
TOPIC_HASHCHAIN = "sentineltwin.hashchain"


class KafkaEventProducer:
    """
    Async Kafka producer using aiokafka.
    Falls back to no-op logging if Kafka broker is unreachable.
    """

    def __init__(self, bootstrap_servers: str = "localhost:9092"):
        self._bootstrap = bootstrap_servers
        self._producer = None
        self._available = False
        self._send_queue: asyncio.Queue = asyncio.Queue(maxsize=5000)

    async def start(self) -> None:
        try:
            from aiokafka import AIOKafkaProducer
            self._producer = AIOKafkaProducer(
                bootstrap_servers=self._bootstrap,
                value_serializer=lambda v: json.dumps(v).encode("utf-8"),
                compression_type="gzip",
                request_timeout_ms=5000,
                connections_max_idle_ms=30000,
            )
            await self._producer.start()
            self._available = True
            log.info("Kafka producer connected to %s", self._bootstrap)
            asyncio.create_task(self._send_worker(), name="kafka_send_worker")
        except Exception as exc:
            log.warning("Kafka unavailable (%s) — operating without event streaming", exc)
            self._available = False

    async def stop(self) -> None:
        if self._producer and self._available:
            try:
                await self._producer.stop()
            except Exception:
                pass

    async def _send_worker(self) -> None:
        while True:
            try:
                topic, event = await self._send_queue.get()
                if self._producer and self._available:
                    await self._producer.send_and_wait(topic, event)
            except Exception as exc:
                log.debug("Kafka send error: %s", exc)

    def _enqueue(self, topic: str, event: Dict[str, Any]) -> None:
        event["_kafka_ts"] = datetime.now(timezone.utc).isoformat()
        try:
            self._send_queue.put_nowait((topic, event))
        except asyncio.QueueFull:
            log.debug("Kafka queue full — dropping event for topic %s", topic)

    def publish_anomaly(self, sensor_id: str, ata_chapter: int, score: float,
                        severity: str, description: str) -> None:
        self._enqueue(TOPIC_ANOMALIES, {
            "event_type":   "SENSOR_ANOMALY",
            "sensor_id":    sensor_id,
            "ata_chapter":  ata_chapter,
            "score":        score,
            "severity":     severity,
            "description":  description,
        })

    def publish_ecam(self, message_id: str, severity: str, message: str,
                     ata_chapter: int, dispatch_impact: bool) -> None:
        self._enqueue(TOPIC_ECAM, {
            "event_type":      "ECAM_ADVISORY",
            "message_id":      message_id,
            "severity":        severity,
            "message":         message,
            "ata_chapter":     ata_chapter,
            "dispatch_impact": dispatch_impact,
        })

    def publish_dispatch(self, ready: bool, score: float, blockers: list) -> None:
        self._enqueue(TOPIC_DISPATCH, {
            "event_type": "DISPATCH_STATUS",
            "ready":      ready,
            "score":      score,
            "blockers":   blockers,
        })

    def publish_hash_block(self, block_id: int, block_hash: str,
                           healthy: int, anomaly: int) -> None:
        self._enqueue(TOPIC_HASHCHAIN, {
            "event_type":  "HASH_BLOCK",
            "block_id":    block_id,
            "block_hash":  block_hash,
            "healthy":     healthy,
            "anomaly":     anomaly,
        })

    @property
    def is_available(self) -> bool:
        return self._available

    def get_stats(self) -> Dict[str, Any]:
        return {
            "available":     self._available,
            "bootstrap":     self._bootstrap,
            "queue_depth":   self._send_queue.qsize(),
            "topics": [TOPIC_ANOMALIES, TOPIC_ECAM, TOPIC_DISPATCH, TOPIC_HASHCHAIN],
        }
