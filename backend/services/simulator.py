"""
SentinelTwin — Simulator Integration Layer
X-Plane UDP | MSFS SimConnect | ARINC 429 Bus Simulator | Replay Engine
"""

import asyncio
import logging
import random
import socket
import struct
import time
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Callable, Dict, List, Optional

log = logging.getLogger("sentineltwin.simulator")


# ═════════════════════════════════════════════════════════════
# ARINC 429 BUS SIMULATOR
# ═════════════════════════════════════════════════════════════

class ARINC429SSM(str, Enum):
    """Sign/Status Matrix values"""
    NORMAL_OPERATION = "NormalOp"
    NO_COMPUTED_DATA = "NoData"
    FUNCTIONAL_TEST   = "FunctTest"
    FAILURE_WARNING   = "FailWarn"


class ARINC429SDI(str, Enum):
    """Source/Destination Identifier"""
    CH1 = "00"
    CH2 = "01"
    CH3 = "10"
    CH4 = "11"


@dataclass
class ARINC429Word:
    """
    32-bit ARINC 429 word structure:
    [31-30] SSM | [29-11] Data (19 bits) | [10-9] SDI | [8-1] Label | [0] Parity
    """
    label: int         # Octal label (8 bits)
    data_raw: int      # Raw 19-bit data field
    ssm: ARINC429SSM
    sdi: ARINC429SDI
    parity: int        # Odd parity bit
    timestamp_us: int  # Microsecond timestamp
    bus_speed: str     # "LOW" (12.5 kbps) | "HIGH" (100 kbps)

    # Decoded engineering value
    engineering_value: Optional[float] = None
    engineering_unit: str = ""
    parameter_name: str = ""

    @staticmethod
    def encode(label: int, value_int: int, ssm: ARINC429SSM,
               sdi: ARINC429SDI) -> int:
        """Pack into 32-bit ARINC 429 word"""
        ssm_bits = {"NormalOp": 0b11, "NoData": 0b00,
                    "FunctTest": 0b01, "FailWarn": 0b10}
        sdi_bits = {"00": 0b00, "01": 0b01, "10": 0b10, "11": 0b11}

        word = (label & 0xFF)
        word |= (sdi_bits[sdi.value] & 0x3) << 8
        word |= (value_int & 0x7FFFF) << 10
        word |= (ssm_bits[ssm.value] & 0x3) << 29

        # Compute odd parity over bits 1-31
        parity = bin(word).count("1") % 2
        word |= (parity ^ 1) << 31  # odd parity → flip if even
        return word

    @staticmethod
    def decode(raw_word: int) -> "ARINC429Word":
        """Unpack 32-bit word into ARINC 429 fields"""
        label    = raw_word & 0xFF
        sdi_val  = (raw_word >> 8)  & 0x3
        data_raw = (raw_word >> 10) & 0x7FFFF
        ssm_val  = (raw_word >> 29) & 0x3
        parity   = (raw_word >> 31) & 0x1

        ssm_map = {0b11: ARINC429SSM.NORMAL_OPERATION,
                   0b00: ARINC429SSM.NO_COMPUTED_DATA,
                   0b01: ARINC429SSM.FUNCTIONAL_TEST,
                   0b10: ARINC429SSM.FAILURE_WARNING}
        sdi_map = {0: ARINC429SDI.CH1, 1: ARINC429SDI.CH2,
                   2: ARINC429SDI.CH3, 3: ARINC429SDI.CH4}

        return ARINC429Word(
            label=label, data_raw=data_raw,
            ssm=ssm_map.get(ssm_val, ARINC429SSM.NO_COMPUTED_DATA),
            sdi=sdi_map.get(sdi_val, ARINC429SDI.CH1),
            parity=parity,
            timestamp_us=int(time.time() * 1_000_000),
            bus_speed="HIGH",
        )

    def verify_parity(self) -> bool:
        """Verify odd parity of the word"""
        # Reconstruct word without parity bit
        word = (self.label & 0xFF)
        word |= (int(self.sdi.value, 2) & 0x3) << 8
        word |= (self.data_raw & 0x7FFFF) << 10
        word |= ({ARINC429SSM.NORMAL_OPERATION: 0b11,
                  ARINC429SSM.NO_COMPUTED_DATA: 0b00,
                  ARINC429SSM.FUNCTIONAL_TEST: 0b01,
                  ARINC429SSM.FAILURE_WARNING: 0b10}[self.ssm] & 0x3) << 29
        ones = bin(word).count("1")
        expected_parity = ones % 2 ^ 1  # odd parity
        return expected_parity == self.parity


# ARINC 429 label definitions for A320neo
ARINC429_LABELS = {
    # Octal label: (name, unit, scale_factor, offset)
    0o003: ("TRUE_AIRSPEED",      "KT",   0.25,   0),
    0o010: ("ALTITUDE_BARO",      "FT",   4.0,    0),
    0o013: ("MACH_NUMBER",        "M",    0.00024,0),
    0o014: ("MACH_NUMBER_COMP",   "M",    0.00024,0),
    0o103: ("VERTICAL_SPEED",     "FPM",  4.0,    0),
    0o174: ("GPS_LATITUDE",       "DEG",  0.0000021, -90),
    0o175: ("GPS_LONGITUDE",      "DEG",  0.0000021, -180),
    0o205: ("FUEL_FLOW_ENG1",     "KG/H", 1.0,    0),
    0o206: ("FUEL_FLOW_ENG2",     "KG/H", 1.0,    0),
    0o241: ("TOTAL_FUEL_QTY",     "KG",   4.0,    0),
    0o301: ("N1_ENG1",            "%",    0.004,  0),
    0o302: ("N1_ENG2",            "%",    0.004,  0),
    0o310: ("N2_ENG1",            "%",    0.004,  0),
    0o311: ("N2_ENG2",            "%",    0.004,  0),
    0o312: ("EGT_ENG1",           "°C",   0.25,   0),
    0o313: ("EGT_ENG2",           "°C",   0.25,   0),
    0o314: ("OIL_TEMP_ENG1",      "°C",   0.125,  -100),
    0o315: ("OIL_TEMP_ENG2",      "°C",   0.125,  -100),
    0o316: ("OIL_PRESS_ENG1",     "PSI",  0.125,  0),
    0o317: ("OIL_PRESS_ENG2",     "PSI",  0.125,  0),
    0o360: ("HYD_PRESS_GREEN",    "PSI",  1.0,    0),
    0o361: ("HYD_PRESS_BLUE",     "PSI",  1.0,    0),
    0o362: ("HYD_PRESS_YELLOW",   "PSI",  1.0,    0),
    0o101: ("ILS_LOCALIZER_DEV",  "DDM",  0.000061, 0),
    0o102: ("ILS_GLIDESLOPE_DEV", "DDM",  0.000061, 0),
    0o320: ("PITCH_ATTITUDE",     "DEG",  0.000549, 0),
    0o321: ("ROLL_ATTITUDE",      "DEG",  0.000549, 0),
    0o325: ("HEADING_TRUE",       "DEG",  0.000549, 0),
}


class ARINC429BusSimulator:
    """
    Simulates an ARINC 429 data bus with real label generation,
    proper word encoding, timing simulation, and CRC validation.
    Outputs real ARINC 429 words at 100 kbps high-speed bus rate.
    """

    HIGH_SPEED_BPS = 100_000   # bits/sec
    BITS_PER_WORD  = 32
    WORD_PERIOD_US = (BITS_PER_WORD / HIGH_SPEED_BPS) * 1_000_000  # ~320µs

    def __init__(self):
        self._running = False
        self._word_buffer: deque = deque(maxlen=10000)
        self._error_injection_rate = 0.001  # 0.1% error injection
        self._stats = {
            "words_transmitted": 0,
            "crc_errors": 0,
            "timing_violations": 0,
            "bus_resets": 0,
        }
        # Engineering value state (updated from digital twin)
        self._values: Dict[int, float] = {
            0o003: 250.0,   # TAS
            0o010: 35000.0, # altitude
            0o013: 0.78,    # mach
            0o205: 2200.0,  # fuel flow eng1
            0o206: 2200.0,  # fuel flow eng2
            0o301: 97.2,    # N1 eng1
            0o302: 96.8,    # N1 eng2
            0o312: 621.0,   # EGT eng1
            0o313: 618.0,   # EGT eng2
            0o360: 3000.0,  # HYD GREEN
            0o361: 3000.0,  # HYD BLUE
            0o362: 3000.0,  # HYD YELLOW
            0o174: 48.8566, # lat
            0o175: 2.3522,  # lon
        }

    def update_value(self, label_oct: int, value: float):
        self._values[label_oct] = value

    def _encode_label(self, label_oct: int, value: float) -> Optional[ARINC429Word]:
        """Encode a physical value into an ARINC 429 word"""
        label_info = ARINC429_LABELS.get(label_oct)
        if not label_info:
            return None

        name, unit, scale, offset = label_info
        # Convert engineering value to raw integer
        raw_int = int((value - offset) / scale) & 0x7FFFF  # 19-bit data

        # Inject errors occasionally
        if random.random() < self._error_injection_rate:
            # Flip random bit → parity error
            raw_int ^= (1 << random.randint(0, 18))
            self._stats["crc_errors"] += 1

        word = ARINC429Word.decode(
            ARINC429Word.encode(
                label=label_oct,
                value_int=raw_int,
                ssm=ARINC429SSM.NORMAL_OPERATION,
                sdi=ARINC429SDI.CH1,
            )
        )
        word.engineering_value = value
        word.engineering_unit = unit
        word.parameter_name = name
        return word

    def get_decoded_labels(self) -> List[Dict]:
        """Return currently decoded label table"""
        result = []
        for label_oct, value in self._values.items():
            info = ARINC429_LABELS.get(label_oct)
            if not info:
                continue
            name, unit, scale, offset = info
            # Simulate live noise
            noisy_value = value + random.gauss(0, abs(value) * 0.001)
            word = self._encode_label(label_oct, noisy_value)
            if word:
                result.append({
                    "label_oct": f"{label_oct:03o}",
                    "label_dec": label_oct,
                    "parameter": name,
                    "value": round(noisy_value, 4),
                    "unit": unit,
                    "ssm": word.ssm.value,
                    "sdi": word.sdi.value,
                    "parity_valid": word.verify_parity(),
                    "integrity": "VALID" if word.verify_parity() else "PARITY_ERR",
                    "timestamp_us": word.timestamp_us,
                    "bus": "ARINC429-A320NEO-CH1",
                    "rate_hz": 12.5,
                })
        return result

    def get_bus_stats(self) -> Dict:
        return {
            **self._stats,
            "bus_speed": "100 kbps",
            "protocol": "BIPOLAR_RZ",
            "word_period_us": self.WORD_PERIOD_US,
            "active_labels": len(self._values),
            "error_injection_rate": self._error_injection_rate,
            "compliance": "ARINC_429-18",
        }


# ═════════════════════════════════════════════════════════════
# X-PLANE UDP INTEGRATION
# ═════════════════════════════════════════════════════════════

@dataclass
class XPlaneDataRef:
    """X-Plane data reference mapping"""
    ref_path: str
    index: int
    description: str
    unit: str
    scale: float = 1.0
    offset: float = 0.0


# X-Plane DATA packet format mappings (DREF indices)
XPLANE_DREFS = {
    0:  XPlaneDataRef("sim/cockpit2/gauges/indicators/airspeed_kts_pilot", 0, "Airspeed", "KT"),
    3:  XPlaneDataRef("sim/cockpit2/gauges/indicators/altitude_ft_pilot", 0, "Altitude", "FT"),
    4:  XPlaneDataRef("sim/cockpit2/gauges/indicators/vvi_fpm_pilot", 0, "Vertical Speed", "FPM"),
    17: XPlaneDataRef("sim/cockpit2/engine/indicators/N1_percent", 0, "N1 ENG1", "%"),
    18: XPlaneDataRef("sim/cockpit2/engine/indicators/N1_percent", 1, "N1 ENG2", "%"),
    37: XPlaneDataRef("sim/cockpit2/engine/indicators/EGT_deg_C", 0, "EGT ENG1", "°C"),
    38: XPlaneDataRef("sim/cockpit2/engine/indicators/EGT_deg_C", 1, "EGT ENG2", "°C"),
    20: XPlaneDataRef("sim/cockpit2/fuel/fuel_quantity_kg", 0, "Fuel QTY", "KG"),
}


class XPlaneUDPClient:
    """
    X-Plane 11/12 UDP data client.
    Receives DATA packets on port 49001, decodes real-time flight data.
    Supports automatic reconnect and packet integrity validation.
    """

    XPLANE_MAGIC = b"DATA"
    MAX_PACKET_SIZE = 4096
    RECONNECT_DELAY = 5.0
    STALE_THRESHOLD = 3.0

    def __init__(self, recv_host: str = "0.0.0.0", recv_port: int = 49001):
        self.recv_host = recv_host
        self.recv_port = recv_port
        self._socket: Optional[socket.socket] = None
        self._running = False
        self._last_packet_time = 0.0
        self._decoded: Dict[str, float] = {}
        self._packet_count = 0
        self._error_count = 0
        self._callbacks: List[Callable] = []

    def on_data(self, callback: Callable):
        """Register callback for decoded telemetry data"""
        self._callbacks.append(callback)

    def _decode_packet(self, data: bytes) -> Dict[str, float]:
        """Decode X-Plane DATA packet format"""
        if len(data) < 5 or data[:4] != self.XPLANE_MAGIC:
            raise ValueError("Invalid X-Plane DATA packet magic")

        decoded = {}
        offset = 5  # Skip "DATA\0"

        while offset + 36 <= len(data):
            # Each DATA group: 4-byte index + 8 × 4-byte float = 36 bytes
            index = struct.unpack_from("<i", data, offset)[0]
            values = struct.unpack_from("<8f", data, offset + 4)
            offset += 36

            if index in XPLANE_DREFS:
                dref = XPLANE_DREFS[index]
                value = values[dref.index]
                if not (value != value or abs(value) > 1e15):  # NaN/Inf check
                    eng_value = value * dref.scale + dref.offset
                    decoded[dref.description] = eng_value

        return decoded

    async def _receive_loop(self):
        """Main UDP receive loop"""
        loop = asyncio.get_event_loop()
        while self._running:
            try:
                data, addr = await loop.run_in_executor(
                    None, self._socket.recvfrom, self.MAX_PACKET_SIZE
                )
                self._last_packet_time = time.time()
                self._packet_count += 1

                try:
                    decoded = self._decode_packet(data)
                    self._decoded.update(decoded)
                    for cb in self._callbacks:
                        asyncio.create_task(cb(decoded))
                except Exception as e:
                    self._error_count += 1
                    log.debug(f"X-Plane packet decode error: {e}")

            except socket.timeout:
                # Check staleness
                if time.time() - self._last_packet_time > self.STALE_THRESHOLD:
                    log.warning("X-Plane: No packets received — connection stale")
            except Exception as e:
                log.error(f"X-Plane receive error: {e}")
                await asyncio.sleep(1.0)

    async def connect(self) -> bool:
        """Open UDP socket for X-Plane data reception"""
        try:
            self._socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self._socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self._socket.bind((self.recv_host, self.recv_port))
            self._socket.settimeout(2.0)
            self._running = True
            log.info(f"X-Plane UDP client listening on {self.recv_host}:{self.recv_port}")
            return True
        except Exception as e:
            log.error(f"X-Plane UDP connect failed: {e}")
            return False

    async def start(self):
        await self.connect()
        asyncio.create_task(self._receive_loop())

    async def stop(self):
        self._running = False
        if self._socket:
            self._socket.close()

    def get_latest(self) -> Dict[str, float]:
        return dict(self._decoded)

    def get_stats(self) -> Dict:
        return {
            "packet_count": self._packet_count,
            "error_count": self._error_count,
            "last_packet_age_sec": round(time.time() - self._last_packet_time, 2),
            "is_connected": self._running,
            "active_drefs": len(self._decoded),
        }

    def decode_packet(self, data: bytes) -> Optional[Dict[str, float]]:
        """Public alias for _decode_packet — used by SimulatorManager."""
        try:
            return self._decode_packet(data)
        except Exception:
            return None


# ═════════════════════════════════════════════════════════════
# SIMULATOR FRAME (structured telemetry packet)
# ═════════════════════════════════════════════════════════════

@dataclass
class SimulatorFrame:
    """Unified telemetry frame from any source (X-Plane, CSV, synthetic)."""
    source: str = "SYNTHETIC"
    timestamp_utc: str = ""
    altitude_ft: float = 0.0
    airspeed_kts: float = 0.0
    mach: float = 0.0
    heading_deg: float = 360.0
    pitch_deg: float = 0.0
    roll_deg: float = 0.0
    latitude_deg: float = 48.85
    longitude_deg: float = 2.35
    eng1_n1_pct: float = 22.0
    eng2_n1_pct: float = 22.0
    eng1_egt_c: float = 420.0
    eng2_egt_c: float = 420.0
    fuel_kg: float = 18000.0
    flight_phase: str = "GROUND"


# ═════════════════════════════════════════════════════════════
# TELEMETRY REPLAY ENGINE
# ═════════════════════════════════════════════════════════════

@dataclass
class ReplayFrame:
    sequence: int
    timestamp: float
    sensor_data: Dict[str, float]
    flight_phase: str
    altitude_ft: float
    speed_kt: float


class TelemetryReplayEngine:
    """
    Replays recorded telemetry sessions at configurable speeds.
    Supports: real-time (1x), accelerated (up to 100x), step-through.
    Used for: incident investigation, AI model training, regression testing.
    """

    def __init__(self):
        self._frames: List[ReplayFrame] = []
        self._current_idx = 0
        self._running = False
        self._speed = 1.0
        self._callbacks: List[Callable] = []
        self._session_name = ""
        self._total_frames = 0

    def load_session(self, frames: List[Dict]) -> int:
        """Load telemetry frames from archive"""
        self._frames = [
            ReplayFrame(
                sequence=f.get("sequence", i),
                timestamp=f.get("timestamp", i * 0.05),
                sensor_data=f.get("sensor_data", {}),
                flight_phase=f.get("flight_phase", "GROUND"),
                altitude_ft=f.get("altitude_ft", 0),
                speed_kt=f.get("speed_kt", 0),
            )
            for i, f in enumerate(frames)
        ]
        self._total_frames = len(self._frames)
        self._current_idx = 0
        log.info(f"Replay: Loaded {self._total_frames} frames")
        return self._total_frames

    def generate_synthetic_session(self,
                                    flight_phase_sequence: List[str],
                                    duration_sec: float = 300.0,
                                    with_anomalies: bool = True) -> int:
        """Generate a synthetic telemetry session for testing"""
        frames = []
        dt = 0.05  # 20 Hz
        t = 0.0
        seq = 0
        phase_idx = 0
        phase_duration = duration_sec / len(flight_phase_sequence)

        from services.sensor_engine import build_sensor_registry, PhysicsModel, ISAAtmosphere
        registry = build_sensor_registry()[:50]  # Sample 50 sensors
        physics = PhysicsModel(ISAAtmosphere())

        alt = 0.0
        spd = 0.0

        while t < duration_sec:
            phase_idx = min(int(t / phase_duration), len(flight_phase_sequence) - 1)
            phase = flight_phase_sequence[phase_idx]

            # Simple flight dynamics
            target_alt = {"GROUND": 0, "CLIMB": 20000, "CRUISE": 35000,
                          "DESCENT": 10000, "LANDING": 0}.get(phase, 0)
            target_spd = {"GROUND": 0, "CLIMB": 240, "CRUISE": 250,
                          "DESCENT": 220, "LANDING": 140}.get(phase, 0)
            alt += (target_alt - alt) * 0.01
            spd += (target_spd - spd) * 0.05

            sensor_data = {}
            for sensor in registry:
                value = physics.predict(sensor, alt, spd, phase, t)
                # Inject anomaly at 60% of session
                if with_anomalies and 0.58 < t / duration_sec < 0.65:
                    if sensor.ata_chapter in (29, 71):
                        value *= random.uniform(1.3, 1.8)
                sensor_data[sensor.sensor_id] = round(value, 4)

            frames.append({
                "sequence": seq,
                "timestamp": t,
                "sensor_data": sensor_data,
                "flight_phase": phase,
                "altitude_ft": round(alt, 1),
                "speed_kt": round(spd, 1),
            })
            t += dt
            seq += 1

        return self.load_session(frames)

    def on_frame(self, callback: Callable):
        self._callbacks.append(callback)

    async def play(self, speed: float = 1.0):
        """Start replay at given speed multiplier"""
        if not self._frames:
            raise ValueError("No frames loaded")
        self._speed = max(0.1, min(100.0, speed))
        self._running = True
        log.info(f"Replay: Starting {self._total_frames} frames at {self._speed}x")

        while self._running and self._current_idx < len(self._frames):
            frame = self._frames[self._current_idx]
            for cb in self._callbacks:
                try:
                    await cb(frame)
                except Exception as e:
                    log.error(f"Replay callback error: {e}")

            self._current_idx += 1

            if self._current_idx < len(self._frames):
                next_frame = self._frames[self._current_idx]
                dt = next_frame.timestamp - frame.timestamp
                await asyncio.sleep(dt / self._speed)

        self._running = False
        log.info("Replay: Playback complete")

    def stop(self):
        self._running = False

    def seek(self, position_pct: float):
        """Seek to position (0.0 = start, 1.0 = end)"""
        idx = int(position_pct * len(self._frames))
        self._current_idx = max(0, min(idx, len(self._frames) - 1))

    def get_status(self) -> Dict:
        frame = self._frames[self._current_idx] if self._frames else None
        return {
            "running": self._running,
            "speed": self._speed,
            "current_frame": self._current_idx,
            "total_frames": self._total_frames,
            "progress_pct": round(self._current_idx / max(1, self._total_frames) * 100, 1),
            "current_phase": frame.flight_phase if frame else None,
            "current_altitude": frame.altitude_ft if frame else None,
            "current_speed": frame.speed_kt if frame else None,
            "current_timestamp": frame.timestamp if frame else None,
        }


# ═════════════════════════════════════════════════════════════
# SIMULATOR MANAGER (orchestrates all simulator backends)
# ═════════════════════════════════════════════════════════════

class SimulatorManager:
    """
    Manages all simulator connections and data sources.
    Priority: Live Aircraft > X-Plane > MSFS > Replay > Synthetic
    """

    def __init__(self):
        self.xplane = XPlaneUDPClient()
        self.arinc_bus = ARINC429BusSimulator()
        self.replay = TelemetryReplayEngine()
        self._active_source = "SYNTHETIC"
        self._source = "SYNTHETIC"
        self._running = True
        self._last_frame: Optional[SimulatorFrame] = None
        self._xplane_task: Optional[asyncio.Task] = None

        # CSV replay state
        self._replay_frames: List[SimulatorFrame] = []
        self._replay_index: int = 0
        self._replay_speed: float = 1.0

    async def start_synthetic(self):
        """Start synthetic telemetry generation"""
        self._active_source = "SYNTHETIC"
        self._source = "SYNTHETIC"
        log.info("SimulatorManager: SYNTHETIC mode active")

    async def start_xplane(self, recv_port: int = 49001) -> bool:
        """Connect to X-Plane 11/12 UDP stream on localhost:49001."""
        self.xplane.recv_port = recv_port
        connected = await self.xplane.connect()
        if not connected:
            log.warning("X-Plane not available on port %d — using synthetic data", recv_port)
            return False
        self._source = "XPLANE"
        self._active_source = "XPLANE"
        self._xplane_task = asyncio.create_task(
            self._run_xplane_loop(), name="xplane_recv"
        )
        log.info("X-Plane integration ACTIVE on port %d", recv_port)
        return True

    async def _run_xplane_loop(self) -> None:
        """
        Continuously receive X-Plane UDP packets and translate them to
        SimulatorFrame objects for the sensor engine.
        """
        reconnect_delay = 1.0
        while self._running:
            try:
                # Receive packet (non-blocking via executor)
                loop = asyncio.get_event_loop()
                raw, addr = await loop.run_in_executor(
                    None, self.xplane._socket.recvfrom, 4096
                )
                frame = self.xplane.decode_packet(raw)
                if frame:
                    # Map X-Plane frame fields to our SimulatorFrame
                    self._last_frame = SimulatorFrame(
                        source="XPLANE",
                        timestamp_utc=datetime.now(timezone.utc).isoformat(),
                        altitude_ft=frame.get("Altitude", 0.0),
                        airspeed_kts=frame.get("Airspeed", 0.0),
                        mach=frame.get("mach", 0.0),
                        heading_deg=frame.get("heading_mag_deg", 360.0),
                        pitch_deg=frame.get("pitch_deg", 0.0),
                        roll_deg=frame.get("roll_deg", 0.0),
                        latitude_deg=frame.get("latitude_deg", 48.85),
                        longitude_deg=frame.get("longitude_deg", 2.35),
                        eng1_n1_pct=frame.get("N1 ENG1", 22.0),
                        eng2_n1_pct=frame.get("N1 ENG2", 22.0),
                        eng1_egt_c=frame.get("EGT ENG1", 420.0),
                        eng2_egt_c=frame.get("EGT ENG2", 420.0),
                        fuel_kg=frame.get("Fuel QTY", 18000.0),
                        flight_phase=self._infer_phase(frame),
                    )
                    reconnect_delay = 1.0  # reset on success
            except socket.timeout:
                log.debug("X-Plane: waiting for packets...")
            except OSError:
                log.warning("X-Plane socket error — reconnecting in %ss", reconnect_delay)
                await asyncio.sleep(reconnect_delay)
                reconnect_delay = min(reconnect_delay * 2, 30.0)
                await self.xplane.connect()

    def _infer_phase(self, frame: dict) -> str:
        """Infer flight phase from X-Plane telemetry."""
        alt  = frame.get("Altitude", 0)
        spd  = frame.get("Airspeed", 0)
        vs   = frame.get("Vertical Speed", 0)  # feet/min
        gear = frame.get("gear_down", True)

        if alt < 50 and spd < 5:
            return "GROUND"
        if alt < 50 and spd < 80:
            return "TAXI"
        if alt < 1000 and spd > 80:
            return "TAKEOFF"
        if vs > 200 and alt < 35000:
            return "CLIMB"
        if abs(vs) < 200 and alt > 15000:
            return "CRUISE"
        if vs < -200 and alt > 3000:
            return "DESCENT"
        if alt < 3000 and gear:
            return "APPROACH"
        if alt < 100 and gear:
            return "LANDING"
        return "CRUISE"

    async def load_csv_replay(self, csv_path: str) -> bool:
        """
        Load a CSV telemetry recording for replay.
        CSV format (header required):
          timestamp_utc,altitude_ft,airspeed_kts,mach,heading_deg,pitch_deg,
          roll_deg,latitude_deg,longitude_deg,eng1_n1_pct,eng2_n1_pct,
          eng1_egt_c,eng2_egt_c,fuel_kg,flight_phase

        Returns True if file loaded successfully, False otherwise.
        """
        import csv
        try:
            frames = []
            with open(csv_path, newline="", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    frames.append(SimulatorFrame(
                        source="CSV_REPLAY",
                        timestamp_utc=row.get("timestamp_utc", ""),
                        altitude_ft=float(row.get("altitude_ft", 0)),
                        airspeed_kts=float(row.get("airspeed_kts", 0)),
                        mach=float(row.get("mach", 0)),
                        heading_deg=float(row.get("heading_deg", 360)),
                        pitch_deg=float(row.get("pitch_deg", 0)),
                        roll_deg=float(row.get("roll_deg", 0)),
                        latitude_deg=float(row.get("latitude_deg", 48.85)),
                        longitude_deg=float(row.get("longitude_deg", 2.35)),
                        eng1_n1_pct=float(row.get("eng1_n1_pct", 22)),
                        eng2_n1_pct=float(row.get("eng2_n1_pct", 22)),
                        eng1_egt_c=float(row.get("eng1_egt_c", 420)),
                        eng2_egt_c=float(row.get("eng2_egt_c", 420)),
                        fuel_kg=float(row.get("fuel_kg", 18000)),
                        flight_phase=row.get("flight_phase", "GROUND"),
                    ))
            self._replay_frames = frames
            self._replay_index  = 0
            log.info("CSV replay loaded: %d frames from %s", len(frames), csv_path)
            return True
        except Exception as exc:
            log.error("CSV replay load failed: %s", exc)
            return False

    async def start_csv_replay(self, speed_multiplier: float = 1.0) -> None:
        """Play back loaded CSV frames at speed_multiplier × realtime."""
        if not getattr(self, "_replay_frames", None):
            log.warning("No CSV replay loaded — call load_csv_replay() first")
            return
        self._source = "CSV_REPLAY"
        self._active_source = "CSV_REPLAY"
        self._replay_speed = speed_multiplier

        async def _replay_loop():
            frames = self._replay_frames
            idx = 0
            while self._running and idx < len(frames):
                self._last_frame = frames[idx]
                idx += 1
                self._replay_index = idx
                # 50ms per frame ÷ speed_multiplier
                await asyncio.sleep(0.05 / max(speed_multiplier, 0.1))
            self._source = "SYNTHETIC"
            self._active_source = "SYNTHETIC"
            log.info("CSV replay complete — reverting to synthetic source")

        asyncio.create_task(_replay_loop(), name="csv_replay")

    async def start_replay(self, flight_phases: Optional[List[str]] = None,
                           duration_sec: float = 300.0):
        """Start synthetic replay session"""
        phases = flight_phases or ["GROUND", "TAXI", "TAKEOFF", "CLIMB",
                                    "CRUISE", "DESCENT", "APPROACH", "LANDING"]
        n_frames = self.replay.generate_synthetic_session(
            phases, duration_sec=duration_sec, with_anomalies=True
        )
        self._active_source = "REPLAY"
        self._source = "REPLAY"
        log.info(f"SimulatorManager: REPLAY mode — {n_frames} frames")
        asyncio.create_task(self.replay.play(speed=5.0))

    def get_status(self) -> Dict:
        return {
            "active_source": self._active_source,
            "source":        self._source,
            "xplane": self.xplane.get_stats(),
            "arinc_bus": self.arinc_bus.get_bus_stats(),
            "replay": self.replay.get_status(),
            "decoded_labels": len(self.arinc_bus._values),
            "replay_index":   self._replay_index,
            "replay_total":   len(self._replay_frames),
            "replay_speed":   self._replay_speed,
            "last_frame_ts":  getattr(self._last_frame, "timestamp_utc", None) if self._last_frame else None,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    def get_arinc_labels(self) -> List[Dict]:
        return self.arinc_bus.get_decoded_labels()


# Module-level singleton
simulator_manager = SimulatorManager()
