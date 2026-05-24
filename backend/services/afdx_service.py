"""
SentinelTwin — AFDX (ARINC 664 Part 7) Virtual Link Monitor Service
Tracks: BAG enforcement, jitter, bandwidth, frame sequencing.
"""

import logging
import random
import time
from datetime import datetime, timezone
from typing import Any, Dict, List

log = logging.getLogger("sentineltwin.afdx")


class AFDXMonitor:
    """
    ARINC 664 Part 7 (AFDX) virtual-link monitoring.
    Tracks: BAG enforcement, jitter, bandwidth, frame sequencing.
    """

    VIRTUAL_LINKS: List[Dict[str, Any]] = [
        {
            "vl_id": "VL-0100", "bag_ms": 4, "max_frame_bytes": 1518,
            "bw_kbps": 3000, "publisher": "ADIRU-1",
            "subscribers": ["FMS", "EFIS"],
        },
        {
            "vl_id": "VL-0200", "bag_ms": 8, "max_frame_bytes": 512,
            "bw_kbps": 500, "publisher": "FADEC-1",
            "subscribers": ["ECAM", "FWC"],
        },
        {
            "vl_id": "VL-0300", "bag_ms": 16, "max_frame_bytes": 256,
            "bw_kbps": 128, "publisher": "LGCIU-1",
            "subscribers": ["BSCU", "SFCC"],
        },
        {
            "vl_id": "VL-0400", "bag_ms": 2, "max_frame_bytes": 256,
            "bw_kbps": 1000, "publisher": "FCDC-1",
            "subscribers": ["ELAC", "SEC"],
        },
        {
            "vl_id": "VL-0500", "bag_ms": 32, "max_frame_bytes": 1024,
            "bw_kbps": 256, "publisher": "AIDS",
            "subscribers": ["ACARS", "QAR"],
        },
    ]

    def __init__(self):
        self._seq_nums: Dict[str, int] = {}
        self._jitter_history: Dict[str, List[float]] = {}
        self._last_frame_time: Dict[str, float] = {}
        self._active_faults: Dict[str, str] = {}
        self._frame_count: int = 0
        self._violation_count: int = 0
        self._start_time: float = time.time()

        # Initialize tracking for each VL
        for vl in self.VIRTUAL_LINKS:
            vl_id = vl["vl_id"]
            self._seq_nums[vl_id] = 0
            self._jitter_history[vl_id] = []
            self._last_frame_time[vl_id] = time.time()

        log.info("AFDXMonitor initialized with %d virtual links", len(self.VIRTUAL_LINKS))

    def simulate_frame(self, vl: Dict) -> Dict:
        """
        Simulate a single AFDX frame for a virtual link.
        Returns frame metadata with timing analysis.
        """
        vl_id = vl["vl_id"]
        now = time.time()
        bag_ms = vl["bag_ms"]
        self._seq_nums[vl_id] += 1
        seq_num = self._seq_nums[vl_id]

        # Calculate actual BAG timing
        last = self._last_frame_time.get(vl_id, now)
        actual_interval_ms = (now - last) * 1000

        # Apply fault injection
        fault = self._active_faults.get(vl_id)
        if fault == "LATE":
            actual_interval_ms += bag_ms * 0.6  # 60% late
        elif fault == "EARLY":
            actual_interval_ms = max(0.1, actual_interval_ms - bag_ms * 0.4)
        elif fault == "DUPLICATE":
            seq_num = max(0, seq_num - 1)  # Duplicate previous seq
        elif fault == "MISSING":
            # Skip this frame entirely
            return {
                "vl_id": vl_id,
                "status": "MISSING",
                "seq_num": seq_num,
                "timestamp_utc": datetime.now(timezone.utc).isoformat(),
                "jitter_us": 0,
                "actual_bag_ms": 0,
                "frame_bytes": 0,
                "bag_violation": True,
                "jitter_violation": False,
                "publisher": vl.get("publisher", ""),
                "subscribers": vl.get("subscribers", []),
            }

        # Calculate jitter (deviation from nominal BAG)
        jitter_us = abs(actual_interval_ms - bag_ms) * 1000  # convert ms diff to µs
        # Add realistic jitter noise
        jitter_us += random.gauss(0, 5)
        jitter_us = max(0, abs(jitter_us))

        # Store jitter history (last 100 samples)
        self._jitter_history[vl_id].append(jitter_us)
        if len(self._jitter_history[vl_id]) > 100:
            self._jitter_history[vl_id] = self._jitter_history[vl_id][-100:]

        # Frame size (randomize within max)
        frame_bytes = random.randint(
            max(64, vl["max_frame_bytes"] // 2),
            vl["max_frame_bytes"],
        )

        # Check violations
        bag_violation = self.check_bag_violation(vl_id, actual_interval_ms, bag_ms)
        jitter_violation = self.check_jitter_violation(jitter_us)

        if bag_violation or jitter_violation:
            self._violation_count += 1

        # Determine status
        if fault == "DUPLICATE":
            status = "DUPLICATE"
        elif bag_violation and jitter_violation:
            status = "FAILED"
        elif bag_violation or jitter_violation:
            status = "DEGRADED"
        else:
            status = "NOMINAL"

        self._last_frame_time[vl_id] = now
        self._frame_count += 1

        return {
            "vl_id": vl_id,
            "jitter_us": round(jitter_us, 1),
            "actual_bag_ms": round(actual_interval_ms, 2),
            "nominal_bag_ms": bag_ms,
            "frame_bytes": frame_bytes,
            "max_frame_bytes": vl["max_frame_bytes"],
            "seq_num": seq_num,
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
            "status": status,
            "bag_violation": bag_violation,
            "jitter_violation": jitter_violation,
            "bw_kbps": vl["bw_kbps"],
            "bw_utilization_pct": round(
                (frame_bytes * 8 / 1000) / max(1, vl["bw_kbps"]) * 100 *
                (1000 / max(1, bag_ms)), 1
            ),
            "publisher": vl.get("publisher", ""),
            "subscribers": vl.get("subscribers", []),
        }

    @staticmethod
    def check_bag_violation(vl_id: str, actual_bag_ms: float,
                            nominal_bag_ms: float) -> bool:
        """Check if actual BAG timing violates the nominal BAG constraint."""
        if nominal_bag_ms <= 0:
            return False
        deviation_pct = abs(actual_bag_ms - nominal_bag_ms) / nominal_bag_ms
        return deviation_pct > 0.5  # >50% deviation is a violation

    @staticmethod
    def check_jitter_violation(jitter_us: float,
                               threshold_us: float = 125.0) -> bool:
        """Check if jitter exceeds the ARINC 664 threshold."""
        return jitter_us > threshold_us

    def inject_timing_fault(self, vl_id: str,
                            fault_type: str) -> Dict:
        """
        Inject a timing fault on a virtual link.
        fault_type: "LATE" | "EARLY" | "DUPLICATE" | "MISSING"
        """
        valid_faults = {"LATE", "EARLY", "DUPLICATE", "MISSING"}
        if fault_type not in valid_faults:
            return {"error": f"Invalid fault type. Must be one of: {valid_faults}"}

        # Find the VL
        vl = next((v for v in self.VIRTUAL_LINKS if v["vl_id"] == vl_id), None)
        if not vl:
            return {"error": f"Unknown virtual link: {vl_id}"}

        self._active_faults[vl_id] = fault_type
        log.warning(f"AFDX timing fault injected: {fault_type} on {vl_id}")
        return {
            "status": "FAULT_INJECTED",
            "vl_id": vl_id,
            "fault_type": fault_type,
            "publisher": vl["publisher"],
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    def clear_fault(self, vl_id: str) -> Dict:
        """Clear a previously injected fault."""
        fault = self._active_faults.pop(vl_id, None)
        return {
            "status": "FAULT_CLEARED" if fault else "NO_FAULT_ACTIVE",
            "vl_id": vl_id,
            "previous_fault": fault,
        }

    def get_all_vl_status(self) -> List[Dict]:
        """Simulate and return status for all virtual links."""
        results = []
        for vl in self.VIRTUAL_LINKS:
            frame = self.simulate_frame(vl)
            # Augment with jitter history
            vl_id = vl["vl_id"]
            history = self._jitter_history.get(vl_id, [])
            frame["jitter_history"] = history[-20:] if history else []
            frame["avg_jitter_us"] = round(
                sum(history[-20:]) / max(1, len(history[-20:])), 1
            ) if history else 0.0
            frame["max_jitter_us"] = round(max(history[-20:])) if history else 0.0
            results.append(frame)
        return results

    def get_network_stats(self) -> Dict:
        """Return aggregate AFDX network statistics."""
        all_status = []
        for vl in self.VIRTUAL_LINKS:
            vl_id = vl["vl_id"]
            history = self._jitter_history.get(vl_id, [])
            last_jitter = history[-1] if history else 0
            is_nominal = last_jitter <= 125 and vl_id not in self._active_faults
            is_failed = vl_id in self._active_faults and self._active_faults[vl_id] in ("MISSING",)
            all_status.append({
                "vl_id": vl_id,
                "nominal": is_nominal and not is_failed,
                "failed": is_failed,
            })

        nominal_count = sum(1 for s in all_status if s["nominal"])
        failed_count = sum(1 for s in all_status if s["failed"])
        degraded_count = len(all_status) - nominal_count - failed_count

        total_bw_alloc = sum(vl["bw_kbps"] for vl in self.VIRTUAL_LINKS)
        elapsed = max(1, time.time() - self._start_time)

        return {
            "total_virtual_links": len(self.VIRTUAL_LINKS),
            "nominal_count": nominal_count,
            "degraded_count": degraded_count,
            "failed_count": failed_count,
            "total_utilization_pct": round(
                random.uniform(35, 65), 1  # Simulated aggregate utilization
            ),
            "total_bw_allocated_kbps": total_bw_alloc,
            "network_speed_mbps": 100,
            "total_frames": self._frame_count,
            "total_violations": self._violation_count,
            "violation_rate_pct": round(
                self._violation_count / max(1, self._frame_count) * 100, 3
            ),
            "active_faults": len(self._active_faults),
            "uptime_sec": round(elapsed, 1),
            "switch_a_status": "OPERATIONAL",
            "switch_b_status": "OPERATIONAL",
            "redundant_path": "ACTIVE",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
