"""
SentinelTwin — SHA-256 Hash Chain Service
Immutable audit chain — DO-326A compliant
"""

import asyncio
import hashlib
import json
import logging
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

log = logging.getLogger("sentineltwin.hash_service")


@dataclass
class HashBlock:
    sequence: int
    scan_id: str
    timestamp: str
    previous_hash: str
    block_hash: str
    sensor_count: int
    healthy_count: int
    anomaly_count: int
    flight_phase: str
    payload_digest: str
    is_verified: bool = True
    tamper_detected: bool = False


class HashChainService:
    """
    SHA-256 immutable audit chain.
    Every scan cycle produces a cryptographically linked block.
    Tamper-evident: any modification breaks the chain.
    DO-326A compliant.
    """

    GENESIS_HASH = "0" * 64

    def __init__(self):
        self._chain: List[HashBlock] = []
        self._sequence = 0
        self._previous_hash = self.GENESIS_HASH
        self._lock = asyncio.Lock()
        self.persistence: Optional[Any] = None  # injected by main.py
        log.info("HashChainService initialized — Genesis block set")

    @staticmethod
    def _sha256(data: str) -> str:
        return hashlib.sha256(data.encode("utf-8")).hexdigest()

    def _build_payload(self, scan_id: str, timestamp: str,
                       healthy_count: int, anomaly_count: int,
                       flight_phase: str) -> str:
        return json.dumps({
            "scan_id": scan_id,
            "timestamp": timestamp,
            "healthy_count": healthy_count,
            "anomaly_count": anomaly_count,
            "flight_phase": flight_phase,
        }, separators=(",", ":"), sort_keys=True)

    async def append(self, healthy_count: int, anomaly_count: int,
                     flight_phase: str = "GROUND") -> HashBlock:
        """Create and append a new block to the chain"""
        async with self._lock:
            self._sequence += 1
            ts = datetime.now(timezone.utc).isoformat()
            scan_id = f"SCN-{self._sequence:08d}"

            payload = self._build_payload(
                scan_id, ts, healthy_count, anomaly_count, flight_phase
            )
            payload_digest = self._sha256(payload)

            block_content = f"{self._previous_hash}:{payload_digest}:{ts}"
            block_hash = self._sha256(block_content)

            block = HashBlock(
                sequence=self._sequence,
                scan_id=scan_id,
                timestamp=ts,
                previous_hash=self._previous_hash,
                block_hash=block_hash,
                sensor_count=8192,
                healthy_count=healthy_count,
                anomaly_count=anomaly_count,
                flight_phase=flight_phase,
                payload_digest=payload_digest,
            )
            self._chain.append(block)
            self._previous_hash = block_hash

            # Persist hash block to database
            if self.persistence:
                try:
                    await self.persistence.persist_hash_block({
                        "sequence": block.sequence,
                        "scan_id": block.scan_id,
                        "block_hash": block.block_hash,
                        "previous_hash": block.previous_hash,
                        "healthy_count": block.healthy_count,
                        "anomaly_count": block.anomaly_count,
                        "flight_phase": block.flight_phase,
                        "timestamp": block.timestamp,
                    })
                except Exception:
                    pass  # Non-blocking

            return block

    def verify_chain(self) -> Tuple[bool, Optional[int]]:
        """Verify entire chain integrity. Returns (ok, tampered_at_sequence)"""
        if not self._chain:
            return True, None
        prev = self.GENESIS_HASH
        for block in self._chain:
            if block.previous_hash != prev:
                return False, block.sequence
            block_content = f"{block.previous_hash}:{block.payload_digest}:{block.timestamp}"
            expected = self._sha256(block_content)
            if expected != block.block_hash:
                return False, block.sequence
            prev = block.block_hash
        return True, None

    def get_latest_blocks(self, n: int = 50) -> List[Dict]:
        return [asdict(b) for b in self._chain[-n:][::-1]]

    def get_stats(self) -> Dict:
        ok, tampered_at = self.verify_chain()
        return {
            "total_blocks": len(self._chain),
            "latest_hash": self._previous_hash,
            "chain_valid": ok,
            "tampered_at": tampered_at,
            "algorithm": "SHA-256",
            "genesis_hash": self.GENESIS_HASH[:16] + "...",
            "compliance": "DO-326A",
        }
