"""
SentinelTwin — ECAM Advisory Engine
Airbus-style Electronic Centralized Aircraft Monitor
Generates STATUS | CAUTION | WARNING | EMERGENCY advisories
"""

import asyncio
import logging
import random
import time
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

log = logging.getLogger("sentineltwin.ecam_engine")


@dataclass
class ECAMMessage:
    message_id: str
    severity: str
    system: str
    ata_chapter: int
    message: str
    procedure: Optional[str]
    dispatch_impact: bool
    mel_reference: Optional[str]
    generated_at: str
    is_active: bool = True
    cleared_at: Optional[str] = None


ECAM_LOGIC_TABLE = [
    ("hyd_green_press_lo",  "WARNING",   "HYD",  29, "HYD SYS GREEN PRESS LO",
     "HYD G PUMP 1+2 OFF - CHECK ACCUMULATOR", True, "MEL 29-001"),
    ("hyd_blue_press_lo",   "CAUTION",   "HYD",  29, "HYD SYS BLUE PRESS LO",
     "MONITOR BLUE SYSTEM - CHECK ELEC PUMP", False, "MEL 29-002"),
    ("hyd_yellow_press_lo", "CAUTION",   "HYD",  29, "HYD SYS YELLOW PRESS LO",
     "CHECK YELLOW ENG PUMP", False, "MEL 29-003"),
    ("eng1_oil_temp_hi",    "CAUTION",   "ENG",  71, "ENG 1 OIL TEMP HIGH",
     "REDUCE THRUST ENG 1 - MONITOR", False, "MEL 79-001"),
    ("eng2_oil_temp_hi",    "CAUTION",   "ENG",  71, "ENG 2 OIL TEMP HIGH",
     "REDUCE THRUST ENG 2 - MONITOR", False, "MEL 79-001"),
    ("eng1_oil_press_lo",   "WARNING",   "ENG",  71, "ENG 1 OIL PRESS LOW",
     "ENG 1 MASTER OFF IF PRESS < 13 PSI", True, "MEL 79-002"),
    ("eng2_oil_press_lo",   "WARNING",   "ENG",  71, "ENG 2 OIL PRESS LOW",
     "ENG 2 MASTER OFF IF PRESS < 13 PSI", True, "MEL 79-002"),
    ("nav_adr_disagree",    "WARNING",   "NAV",  34, "NAV ADR 1/2/3 DISAGREE",
     "ADR CHECK PROC - SELECT VALID ADR", True, "MEL 34-001"),
    ("fuel_imbalance",      "CAUTION",   "FUEL", 28, "FUEL IMBALANCE L-R > 500KG",
     "X-FEED VALVE OPEN - BALANCE FUEL", False, "MEL 28-001"),
    ("slat_fault",          "WARNING",   "FLT",  27, "SLAT FAULT - ASYMMETRY",
     "CONFIG 0 ONLY - INCREASE VREF", True, "MEL 27-001"),
    ("elac_fault",          "CAUTION",   "FLT",  27, "ELAC 1+2 FAULT",
     "ALTERNATE LAW - NO AUTOLAND", True, "MEL 27-002"),
    ("gen1_fault",          "CAUTION",   "ELEC", 24, "GEN 1 FAULT",
     "GEN 1 OFF - CHECK BUS TIE", False, "MEL 24-001"),
    ("gen2_fault",          "CAUTION",   "ELEC", 24, "GEN 2 FAULT",
     "GEN 2 OFF - CHECK BUS TIE", False, "MEL 24-001"),
    ("apu_bleed_fault",     "STATUS",    "APU",  49, "APU BLEED FAULT",
     "APU BLEED OFF - X-BLEED OPEN", False, "MEL 36-001"),
    ("lgciu_fault",         "CAUTION",   "LGCIU",32, "L/G CTRL UNIT 1+2 FAULT",
     "GEAR GRAVITY EXTENSION AVAILABLE", True, "MEL 32-001"),
    ("pack1_fault",         "EMERGENCY", "PACK", 21, "PACK 1 FAULT - BLEED OFF AUTO",
     "PACK 1 OFF - CABIN ALT MONITOR - DESCEND FL100", True, "MEL 21-001"),
    ("afdx_timing",         "CAUTION",   "AFDX", 31, "AFDX VIRTUAL LINK TIMING FAULT",
     "REDUNDANT PATH CHECK", False, "MEL 31-001"),
    ("fadec_disagree",      "WARNING",   "ENG",  71, "FADEC 1+2 CHANNEL DISAGREE",
     "FADEC AUTO RECONFIG - MONITOR ENG", True, "MEL 73-001"),
    ("irs1_fault",          "CAUTION",   "IRS",  34, "IRS 1 FAULT",
     "IRS 1 OFF ON - CHECK ATT/HDG", False, "MEL 34-002"),
    ("brake_temp_hi",       "CAUTION",   "BRAKES",32, "BRAKE TEMP HIGH - MULTIPLE",
     "COOLING TIME REQUIRED", True, "MEL 32-002"),
    ("adr_spoof_detected",  "EMERGENCY", "SEC",  34, "ADR DATA INTEGRITY FAULT - SPOOF",
     "CROSS-CHECK ALL ADR - NOTIFY SECURITY", True, None),
]


class ECAMEngine:
    """Airbus-style ECAM advisory generation engine."""

    def __init__(self):
        self._active: Dict[str, ECAMMessage] = {}
        self._history: List[ECAMMessage] = []
        self._running = False
        self._lock = asyncio.Lock()
        self.persistence: Optional[Any] = None  # injected by main.py
        self.kafka: Optional[Any] = None  # injected by main.py
        self._trigger_states: Dict[str, bool] = {
            row[0]: False for row in ECAM_LOGIC_TABLE
        }
        log.info(f"ECAMEngine initialized - {len(ECAM_LOGIC_TABLE)} logic rules loaded")

    def trigger(self, condition_key: str, active: bool = True):
        self._trigger_states[condition_key] = active

    def _build_message(self, row: tuple) -> ECAMMessage:
        key, sev, sys, ata, msg, proc, dispatch, mel = row
        return ECAMMessage(
            message_id=f"ECAM-{key.upper()}-{int(time.time()*1000)%99999:05d}",
            severity=sev, system=sys, ata_chapter=ata, message=msg,
            procedure=proc, dispatch_impact=dispatch, mel_reference=mel,
            generated_at=datetime.now(timezone.utc).isoformat(),
        )

    async def _evaluate_rules(self):
        async with self._lock:
            # Stochastic trigger simulation
            for row in ECAM_LOGIC_TABLE:
                key = row[0]
                if not self._trigger_states.get(key) and random.random() < 0.003:
                    self._trigger_states[key] = True
                elif self._trigger_states.get(key) and random.random() < 0.05:
                    self._trigger_states[key] = False

            for row in ECAM_LOGIC_TABLE:
                key = row[0]
                if self._trigger_states.get(key):
                    if key not in self._active:
                        msg = self._build_message(row)
                        self._active[key] = msg
                        self._history.append(msg)
                        log.info(f"ECAM {msg.severity}: {msg.message}")
                        # Persist ECAM advisory
                        if self.persistence:
                            try:
                                await self.persistence.persist_ecam_advisory({
                                    "message_id": msg.message_id,
                                    "severity": msg.severity,
                                    "system": msg.system,
                                    "ata_chapter": msg.ata_chapter,
                                    "message": msg.message,
                                    "is_active": True,
                                    "generated_at": msg.generated_at,
                                })
                            except Exception:
                                pass  # Non-blocking — don't break ECAM for persistence
                        # Publish to Kafka
                        if self.kafka:
                            try:
                                self.kafka.publish_ecam(
                                    message_id=msg.message_id,
                                    severity=msg.severity,
                                    message=msg.message,
                                    ata_chapter=msg.ata_chapter,
                                    dispatch_impact=msg.dispatch_impact,
                                )
                            except Exception:
                                pass  # Non-blocking
                else:
                    if key in self._active:
                        self._active[key].is_active = False
                        self._active[key].cleared_at = datetime.now(timezone.utc).isoformat()
                        del self._active[key]

    async def run(self):
        self._running = True
        log.info("ECAMEngine RUNNING")
        while self._running:
            try:
                await self._evaluate_rules()
            except Exception as e:
                log.error(f"ECAM evaluation error: {e}")
            await asyncio.sleep(2.0)

    async def stop(self):
        self._running = False
        log.info("ECAMEngine stopped")

    def get_active(self) -> List[Dict]:
        msgs = list(self._active.values())
        order = {"EMERGENCY": 0, "WARNING": 1, "CAUTION": 2, "STATUS": 3}
        msgs.sort(key=lambda m: order.get(m.severity, 9))
        return [asdict(m) for m in msgs]

    def get_stats(self) -> Dict:
        active = list(self._active.values())
        return {
            "total_active": len(active),
            "emergency": sum(1 for m in active if m.severity == "EMERGENCY"),
            "warning": sum(1 for m in active if m.severity == "WARNING"),
            "caution": sum(1 for m in active if m.severity == "CAUTION"),
            "status": sum(1 for m in active if m.severity == "STATUS"),
            "total_history": len(self._history),
            "dispatch_impact": any(m.dispatch_impact for m in active),
        }
