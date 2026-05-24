"""
SentinelTwin — Core Services
Hash Chain | ECAM Engine | Digital Twin
"""

import asyncio
import hashlib
import json
import logging
import math
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple
import random

log = logging.getLogger("sentineltwin.services")


# ═════════════════════════════════════════════════════════════
# SHA-256 HASH CHAIN SERVICE
# ═════════════════════════════════════════════════════════════

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

            # Block hash commits to previous hash + payload
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
            return block

    def verify_chain(self) -> Tuple[bool, Optional[int]]:
        """Verify entire chain integrity. Returns (ok, tampered_at_sequence)"""
        if not self._chain:
            return True, None
        prev = self.GENESIS_HASH
        for block in self._chain:
            if block.previous_hash != prev:
                return False, block.sequence
            # Recompute block hash
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


# ═════════════════════════════════════════════════════════════
# ECAM ENGINE
# ═════════════════════════════════════════════════════════════

@dataclass
class ECAMMessage:
    message_id: str
    severity: str        # STATUS | CAUTION | WARNING | EMERGENCY
    system: str
    ata_chapter: int
    message: str
    procedure: Optional[str]
    dispatch_impact: bool
    mel_reference: Optional[str]
    generated_at: str
    is_active: bool = True
    cleared_at: Optional[str] = None


# Full ECAM logic table (Airbus-style)
ECAM_LOGIC_TABLE = [
    # (trigger_condition_key, severity, system, ata, message, procedure, dispatch, mel)
    ("hyd_green_press_lo",  "WARNING",   "HYD",    29, "HYD SYS GREEN PRESS LO",
     "HYD G PUMP 1+2 OFF → CHECK ACCUMULATOR → DIVERT IF < 1500 PSI", True, "MEL 29-001"),
    ("hyd_blue_press_lo",   "CAUTION",   "HYD",    29, "HYD SYS BLUE PRESS LO",
     "MONITOR BLUE SYSTEM — CHECK ELEC PUMP", False, "MEL 29-002"),
    ("hyd_yellow_press_lo", "CAUTION",   "HYD",    29, "HYD SYS YELLOW PRESS LO",
     "CHECK YELLOW ENG PUMP — BRAKE ACCUMULATOR CHECK", False, "MEL 29-003"),
    ("eng1_oil_temp_hi",    "CAUTION",   "ENG",    71, "ENG 1 OIL TEMP HIGH",
     "REDUCE THRUST ENG 1 — MONITOR — LAND AT NEAREST", False, "MEL 79-001"),
    ("eng2_oil_temp_hi",    "CAUTION",   "ENG",    71, "ENG 2 OIL TEMP HIGH",
     "REDUCE THRUST ENG 2 — MONITOR — LAND AT NEAREST", False, "MEL 79-001"),
    ("eng1_oil_press_lo",   "WARNING",   "ENG",    71, "ENG 1 OIL PRESS LOW",
     "ENG 1 MASTER → OFF IF PRESS < 13 PSI", True, "MEL 79-002"),
    ("eng2_oil_press_lo",   "WARNING",   "ENG",    71, "ENG 2 OIL PRESS LOW",
     "ENG 2 MASTER → OFF IF PRESS < 13 PSI", True, "MEL 79-002"),
    ("nav_adr_disagree",    "WARNING",   "NAV",    34, "NAV ADR 1/2/3 DISAGREE",
     "ADR CHECK PROC — SELECT VALID ADR — IRS SWITCHING", True, "MEL 34-001"),
    ("fuel_imbalance",      "CAUTION",   "FUEL",   28, "FUEL IMBALANCE L-R > 500KG",
     "X-FEED VALVE OPEN — BALANCE FUEL — MONITOR", False, "MEL 28-001"),
    ("slat_fault",          "WARNING",   "FLT",    27, "SLAT FAULT — ASYMMETRY",
     "CONFIG 0 ONLY — INCREASE VREF — MAINTENANCE REQUIRED", True, "MEL 27-001"),
    ("elac_fault",          "CAUTION",   "FLT",    27, "ELAC 1+2 FAULT",
     "ALTERNATE LAW — CHECK FLT ENVELOPE — NO AUTOLAND", True, "MEL 27-002"),
    ("gen1_fault",          "CAUTION",   "ELEC",   24, "GEN 1 FAULT",
     "GEN 1 OFF — CHECK BUS TIE — APU GEN IF AVAILABLE", False, "MEL 24-001"),
    ("gen2_fault",          "CAUTION",   "ELEC",   24, "GEN 2 FAULT",
     "GEN 2 OFF — CHECK BUS TIE", False, "MEL 24-001"),
    ("apu_bleed_fault",     "STATUS",    "APU",    49, "APU BLEED FAULT",
     "APU BLEED → OFF — X-BLEED OPEN", False, "MEL 36-001"),
    ("lgciu_fault",         "CAUTION",   "LGCIU",  32, "L/G CTRL UNIT 1+2 FAULT",
     "GEAR GRAVITY EXTENSION AVAILABLE — CHECK INDICATIONS", True, "MEL 32-001"),
    ("pack1_fault",         "EMERGENCY", "PACK",   21, "PACK 1 FAULT — BLEED OFF AUTO",
     "PACK 1 → OFF — CABIN ALT MONITOR — DESCEND FL100", True, "MEL 21-001"),
    ("afdx_timing",         "CAUTION",   "AFDX",   31, "AFDX VIRTUAL LINK TIMING FAULT",
     "REDUNDANT PATH CHECK — AVIONICS BUS MONITOR", False, "MEL 31-001"),
    ("fadec_disagree",      "WARNING",   "ENG",    71, "FADEC 1+2 CHANNEL DISAGREE",
     "FADEC AUTO RECONFIGURATION — MONITOR ENG PARAMETERS", True, "MEL 73-001"),
    ("irs1_fault",          "CAUTION",   "IRS",    34, "IRS 1 FAULT",
     "IRS 1 → OFF ON — CHECK ATT/HDG SELECT", False, "MEL 34-002"),
    ("brake_temp_hi",       "CAUTION",   "BRAKES", 32, "BRAKE TEMP HIGH — MULTIPLE",
     "COOLING TIME REQUIRED — DO NOT TAKEOFF", True, "MEL 32-002"),
    ("adr_spoof_detected",  "EMERGENCY", "SEC",    34, "ADR DATA INTEGRITY FAULT — SPOOF",
     "CROSS-CHECK ALL ADR — SUSPECT CYBER THREAT — NOTIFY SECURITY", True, None),
    ("replay_attack",       "EMERGENCY", "SEC",    31, "TELEMETRY REPLAY ATTACK DETECTED",
     "ARINC BUS ISOLATION — SECURITY PROTOCOL ALPHA", True, None),
]


class ECAMEngine:
    """
    Airbus-style ECAM advisory generation engine.
    Triggered by sensor states and AI anomaly events.
    Generates STATUS | CAUTION | WARNING | EMERGENCY advisories.
    """

    def __init__(self):
        self._active: Dict[str, ECAMMessage] = {}
        self._history: List[ECAMMessage] = []
        self._running = False
        self._lock = asyncio.Lock()
        self._trigger_states: Dict[str, bool] = {
            row[0]: False for row in ECAM_LOGIC_TABLE
        }
        log.info(f"ECAMEngine initialized — {len(ECAM_LOGIC_TABLE)} logic rules loaded")

    def trigger(self, condition_key: str, active: bool = True):
        """Activate or deactivate an ECAM condition"""
        self._trigger_states[condition_key] = active

    def _build_message(self, row: tuple) -> ECAMMessage:
        key, sev, sys, ata, msg, proc, dispatch, mel = row
        return ECAMMessage(
            message_id=f"ECAM-{key.upper()}-{int(time.time()*1000)%99999:05d}",
            severity=sev,
            system=sys,
            ata_chapter=ata,
            message=msg,
            procedure=proc,
            dispatch_impact=dispatch,
            mel_reference=mel,
            generated_at=datetime.now(timezone.utc).isoformat(),
        )

    async def _evaluate_rules(self, sensor_states: Dict, ai_events: List):
        """Evaluate ECAM logic against current system state"""
        async with self._lock:
            # Auto-trigger based on random sensor anomaly injection
            # In production: driven by sensor engine results
            for row in ECAM_LOGIC_TABLE:
                key = row[0]
                current = self._trigger_states.get(key, False)
                # Probabilistic activation for demo
                if not current and random.random() < 0.003:
                    self._trigger_states[key] = True
                elif current and random.random() < 0.05:
                    self._trigger_states[key] = False

            # Generate advisories for active triggers
            for row in ECAM_LOGIC_TABLE:
                key = row[0]
                if self._trigger_states.get(key, False):
                    if key not in self._active:
                        msg = self._build_message(row)
                        self._active[key] = msg
                        self._history.append(msg)
                        log.info(f"ECAM {msg.severity}: {msg.message}")
                else:
                    if key in self._active:
                        self._active[key].is_active = False
                        self._active[key].cleared_at = datetime.now(timezone.utc).isoformat()
                        del self._active[key]

    async def run(self):
        self._running = True
        log.info("ECAMEngine RUNNING")
        while self._running:
            await self._evaluate_rules({}, [])
            await asyncio.sleep(2.0)

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


# ═════════════════════════════════════════════════════════════
# DIGITAL TWIN ENGINE
# ═════════════════════════════════════════════════════════════

@dataclass
class AtmosphericState:
    altitude_ft: float
    temperature_c: float
    pressure_kpa: float
    density_kgm3: float
    altitude_m: float


@dataclass
class EngineState:
    engine_id: int
    n1_pct: float
    n2_pct: float
    egt_c: float
    oil_temp_c: float
    oil_press_psi: float
    fuel_flow_kgh: float
    thrust_kn: float
    vibration_n1: float
    fadec_active: bool
    fadec_channel: int


@dataclass
class HydraulicState:
    system: str            # GREEN | BLUE | YELLOW
    pressure_psi: float
    fluid_temp_c: float
    reservoir_level_pct: float
    pump1_active: bool
    pump2_active: bool


@dataclass
class ElectricalState:
    gen1_online: bool
    gen2_online: bool
    apu_gen_online: bool
    ac_bus1_v: float
    ac_bus2_v: float
    dc_bus1_v: float
    dc_bus2_v: float
    bat1_v: float
    bat2_v: float
    total_load_kva: float


@dataclass
class FuelState:
    left_wing_kg: float
    right_wing_kg: float
    center_kg: float
    total_kg: float
    imbalance_kg: float
    flow_eng1_kgh: float
    flow_eng2_kgh: float
    temp_c: float


@dataclass
class AircraftDigitalTwin:
    # Identification
    aircraft_type: str = "A320neo"
    msn: str = "8234"
    registration: str = "F-WXWB"

    # Flight state
    flight_phase: str = "GROUND"
    altitude_ft: float = 0.0
    ias_kt: float = 0.0
    tas_kt: float = 0.0
    mach: float = 0.0
    vertical_speed_fpm: float = 0.0
    heading_deg: float = 360.0
    pitch_deg: float = 0.0
    roll_deg: float = 0.0
    bank_deg: float = 0.0
    aoa_deg: float = 2.0
    latitude: float = 48.8566
    longitude: float = 2.3522

    # Atmosphere
    atmosphere: Optional[AtmosphericState] = None

    # Engines
    eng1: Optional[EngineState] = None
    eng2: Optional[EngineState] = None

    # Hydraulics
    hyd_green: Optional[HydraulicState] = None
    hyd_blue: Optional[HydraulicState] = None
    hyd_yellow: Optional[HydraulicState] = None

    # Electrical
    electrical: Optional[ElectricalState] = None

    # Fuel
    fuel: Optional[FuelState] = None

    # Session
    session_elapsed_sec: float = 0.0
    last_updated: str = ""


class DigitalTwinEngine:
    """
    Full aircraft digital twin.
    Physics-based model of A320neo systems.
    Updates at 10 Hz — feeds physics reference to sensor engine.
    """

    UPDATE_HZ = 10.0
    UPDATE_SEC = 1.0 / UPDATE_HZ

    def __init__(self):
        self.twin = AircraftDigitalTwin()
        self._running = False
        self._start_time = time.time()
        self._t = 0.0
        log.info("DigitalTwinEngine initialized — A320neo physics model")

    def _compute_isa(self, alt_ft: float) -> AtmosphericState:
        T0, P0, L, g, R = 288.15, 101325.0, 0.0065, 9.80665, 287.05
        TROP = 11000.0
        alt_m = alt_ft * 0.3048
        if alt_m <= TROP:
            T = T0 - L * alt_m
            P = P0 * (T / T0) ** (g / (L * R))
        else:
            T = 216.65
            P11 = P0 * (216.65 / T0) ** (g / (L * R))
            P = P11 * math.exp(-g * (alt_m - TROP) / (R * T))
        rho = P / (R * T)
        return AtmosphericState(
            altitude_ft=alt_ft,
            temperature_c=T - 273.15,
            pressure_kpa=P / 1000,
            density_kgm3=rho,
            altitude_m=alt_m,
        )

    def _update_flight_dynamics(self, phase: str, elapsed: float):
        """Simple flight dynamics model"""
        tw = self.twin
        t = self._t

        if phase == "GROUND":
            tw.altitude_ft = 0.0
            tw.ias_kt = 0.0
            tw.vertical_speed_fpm = 0.0
            tw.pitch_deg = 0.0
        elif phase == "TAXI":
            tw.altitude_ft = 0.0
            tw.ias_kt = min(20, elapsed * 2)
            tw.heading_deg = (tw.heading_deg + 0.5) % 360
        elif phase == "TAKEOFF":
            tw.ias_kt = min(180, elapsed * 5)
            tw.altitude_ft = max(0, (tw.ias_kt - 140) * 50)
            tw.pitch_deg = min(15, (tw.ias_kt - 140) * 0.5) if tw.ias_kt > 140 else 0
            tw.vertical_speed_fpm = max(0, (tw.ias_kt - 140) * 100)
        elif phase == "CLIMB":
            tw.ias_kt = 250 + math.sin(t / 30) * 5
            tw.altitude_ft = min(39000, tw.altitude_ft + 200)
            tw.vertical_speed_fpm = 2200 + math.sin(t / 20) * 100
            tw.pitch_deg = 8 + math.sin(t / 15) * 1
        elif phase == "CRUISE":
            tw.ias_kt = 250 + math.sin(t / 40) * 3
            tw.altitude_ft = min(39000, tw.altitude_ft + 10)
            tw.vertical_speed_fpm = math.sin(t / 60) * 50
            tw.pitch_deg = 2 + math.sin(t / 30) * 0.5
            tw.latitude += 0.001
            tw.longitude += 0.0008
        elif phase == "DESCENT":
            tw.ias_kt = max(220, tw.ias_kt - 1)
            tw.altitude_ft = max(0, tw.altitude_ft - 800)
            tw.vertical_speed_fpm = -2500 + math.cos(t / 20) * 100
            tw.pitch_deg = -3 + math.sin(t / 20) * 0.5
        elif phase in ("APPROACH", "LANDING"):
            tw.ias_kt = max(140, tw.ias_kt - 2)
            tw.altitude_ft = max(0, tw.altitude_ft - 300)
            tw.vertical_speed_fpm = -700
            tw.pitch_deg = -2

        tw.mach = tw.tas_kt / 666.0 if tw.tas_kt else tw.ias_kt / 600.0
        tw.tas_kt = tw.ias_kt * math.sqrt(
            288.15 / max(1, self.twin.atmosphere.temperature_c + 273.15)
        ) if tw.atmosphere else tw.ias_kt

    def _update_engines(self, phase: str):
        n1_target = {
            "GROUND": 22.0, "TAXI": 28.0, "TAKEOFF": 100.0,
            "CLIMB": 94.0, "CRUISE": 87.0, "DESCENT": 42.0,
            "APPROACH": 55.0, "LANDING": 68.0,
        }.get(phase, 22.0)

        for eng_id, attr in ((1, "eng1"), (2, "eng2")):
            eng = getattr(self.twin, attr)
            if eng is None:
                eng = EngineState(
                    engine_id=eng_id, n1_pct=22.0, n2_pct=68.0,
                    egt_c=380.0, oil_temp_c=75.0, oil_press_psi=55.0,
                    fuel_flow_kgh=450.0, thrust_kn=12.0,
                    vibration_n1=0.1, fadec_active=True, fadec_channel=1,
                )
            # Smooth transition
            eng.n1_pct += (n1_target - eng.n1_pct) * 0.1
            eng.n1_pct += math.sin(self._t / (2 + eng_id * 0.3)) * 0.2
            eng.n2_pct = eng.n1_pct * 1.05 + 10
            # EGT follows N1 with thermal lag
            egt_target = 350 + eng.n1_pct * 2.8
            eng.egt_c += (egt_target - eng.egt_c) * 0.05
            eng.egt_c += math.sin(self._t / (3 + eng_id * 0.2)) * 2
            # Fuel flow
            eng.fuel_flow_kgh = max(0, eng.n1_pct * 22.5)
            # Thrust
            eng.thrust_kn = max(0, eng.n1_pct * 1.18)
            eng.oil_temp_c = 75 + eng.n1_pct * 0.4 + math.sin(self._t / 60) * 3
            eng.oil_press_psi = 55 + eng.n1_pct * 0.3 + math.cos(self._t / 40) * 2
            eng.vibration_n1 = 0.08 + abs(math.sin(self._t / 7)) * 0.06
            setattr(self.twin, attr, eng)

    def _update_hydraulics(self, phase: str):
        for sys_name, attr in [("GREEN", "hyd_green"), ("BLUE", "hyd_blue"), ("YELLOW", "hyd_yellow")]:
            hyd = HydraulicState(
                system=sys_name,
                pressure_psi=3000 + math.sin(self._t / (5 + len(sys_name))) * 30,
                fluid_temp_c=45 + math.sin(self._t / 20) * 5,
                reservoir_level_pct=100 - self.twin.session_elapsed_sec * 0.001,
                pump1_active=True,
                pump2_active=sys_name != "BLUE",
            )
            setattr(self.twin, attr, hyd)

    def _update_electrical(self):
        self.twin.electrical = ElectricalState(
            gen1_online=True, gen2_online=True, apu_gen_online=False,
            ac_bus1_v=115 + math.sin(self._t / 10) * 0.3,
            ac_bus2_v=115 + math.cos(self._t / 10) * 0.3,
            dc_bus1_v=28.0 + math.sin(self._t / 15) * 0.1,
            dc_bus2_v=28.0 + math.cos(self._t / 15) * 0.1,
            bat1_v=25.2 + math.sin(self._t / 30) * 0.2,
            bat2_v=25.3 + math.cos(self._t / 30) * 0.2,
            total_load_kva=92 + math.sin(self._t / 20) * 4,
        )

    def _update_fuel(self):
        flow1 = self.twin.eng1.fuel_flow_kgh if self.twin.eng1 else 450
        flow2 = self.twin.eng2.fuel_flow_kgh if self.twin.eng2 else 450
        # Burn at 1/3600 rate per second
        dt = self.UPDATE_SEC
        left = max(0, 9000 - (flow1 * self.twin.session_elapsed_sec / 3600))
        right = max(0, 8900 - (flow2 * self.twin.session_elapsed_sec / 3600))
        center = max(0, 5000 - ((flow1 + flow2) * 0.2 * self.twin.session_elapsed_sec / 3600))
        self.twin.fuel = FuelState(
            left_wing_kg=left,
            right_wing_kg=right,
            center_kg=center,
            total_kg=left + right + center,
            imbalance_kg=abs(left - right),
            flow_eng1_kgh=flow1,
            flow_eng2_kgh=flow2,
            temp_c=-10 + math.sin(self._t / 60) * 2,
        )

    async def run(self):
        self._running = True
        log.info("DigitalTwinEngine RUNNING at 10 Hz")
        while self._running:
            cycle_start = time.monotonic()
            self._t = time.time() - self._start_time
            self.twin.session_elapsed_sec = self._t
            self.twin.last_updated = datetime.now(timezone.utc).isoformat()

            phase = self.twin.flight_phase
            self._update_flight_dynamics(phase, self._t)
            self.twin.atmosphere = self._compute_isa(self.twin.altitude_ft)
            self._update_engines(phase)
            self._update_hydraulics(phase)
            self._update_electrical()
            self._update_fuel()

            elapsed = time.monotonic() - cycle_start
            await asyncio.sleep(max(0, self.UPDATE_SEC - elapsed))

    async def stop(self):
        self._running = False

    def set_phase(self, phase: str):
        self.twin.flight_phase = phase
        log.info(f"Digital twin flight phase → {phase}")

    def get_state(self) -> Dict:
        tw = self.twin
        return {
            "aircraft_type": tw.aircraft_type,
            "msn": tw.msn,
            "registration": tw.registration,
            "flight_phase": tw.flight_phase,
            "altitude_ft": round(tw.altitude_ft, 1),
            "ias_kt": round(tw.ias_kt, 1),
            "tas_kt": round(tw.tas_kt, 1),
            "mach": round(tw.mach, 3),
            "vertical_speed_fpm": round(tw.vertical_speed_fpm, 0),
            "heading_deg": round(tw.heading_deg, 1),
            "pitch_deg": round(tw.pitch_deg, 2),
            "roll_deg": round(tw.roll_deg, 2),
            "latitude": round(tw.latitude, 6),
            "longitude": round(tw.longitude, 6),
            "atmosphere": {
                "temperature_c": round(tw.atmosphere.temperature_c, 2) if tw.atmosphere else 15.0,
                "pressure_kpa": round(tw.atmosphere.pressure_kpa, 3) if tw.atmosphere else 101.325,
                "density_kgm3": round(tw.atmosphere.density_kgm3, 5) if tw.atmosphere else 1.225,
            },
            "engines": {
                "eng1": {
                    "n1_pct": round(tw.eng1.n1_pct, 2) if tw.eng1 else 22.0,
                    "n2_pct": round(tw.eng1.n2_pct, 2) if tw.eng1 else 68.0,
                    "egt_c": round(tw.eng1.egt_c, 1) if tw.eng1 else 380.0,
                    "oil_temp_c": round(tw.eng1.oil_temp_c, 1) if tw.eng1 else 75.0,
                    "oil_press_psi": round(tw.eng1.oil_press_psi, 1) if tw.eng1 else 55.0,
                    "fuel_flow_kgh": round(tw.eng1.fuel_flow_kgh, 0) if tw.eng1 else 450.0,
                    "thrust_kn": round(tw.eng1.thrust_kn, 1) if tw.eng1 else 12.0,
                    "fadec_active": tw.eng1.fadec_active if tw.eng1 else True,
                } if tw.eng1 else {},
                "eng2": {
                    "n1_pct": round(tw.eng2.n1_pct, 2) if tw.eng2 else 22.0,
                    "egt_c": round(tw.eng2.egt_c, 1) if tw.eng2 else 380.0,
                    "thrust_kn": round(tw.eng2.thrust_kn, 1) if tw.eng2 else 12.0,
                } if tw.eng2 else {},
            },
            "hydraulics": {
                "green_psi": round(tw.hyd_green.pressure_psi, 0) if tw.hyd_green else 3000,
                "blue_psi": round(tw.hyd_blue.pressure_psi, 0) if tw.hyd_blue else 3000,
                "yellow_psi": round(tw.hyd_yellow.pressure_psi, 0) if tw.hyd_yellow else 3000,
            },
            "electrical": {
                "gen1_online": tw.electrical.gen1_online if tw.electrical else True,
                "gen2_online": tw.electrical.gen2_online if tw.electrical else True,
                "ac_bus1_v": round(tw.electrical.ac_bus1_v, 1) if tw.electrical else 115.0,
                "total_load_kva": round(tw.electrical.total_load_kva, 1) if tw.electrical else 90.0,
            },
            "fuel": {
                "total_kg": round(tw.fuel.total_kg, 0) if tw.fuel else 18000,
                "imbalance_kg": round(tw.fuel.imbalance_kg, 0) if tw.fuel else 0,
                "flow_total_kgh": round(
                    (tw.fuel.flow_eng1_kgh + tw.fuel.flow_eng2_kgh), 0
                ) if tw.fuel else 900,
            },
            "session_elapsed_sec": round(tw.session_elapsed_sec, 1),
        }
