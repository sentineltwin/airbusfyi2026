"""
SentinelTwin — ARINC 429 Bus Simulator Service
Simulates ARINC 429 bus with realistic Airbus label set.
Label encoding: 32-bit word = 8-bit label + 2-bit SSM + 19-bit data + 2-bit SDI + 1-bit parity
"""

import logging
import random
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Dict, List

log = logging.getLogger("sentineltwin.arinc429")


@dataclass
class FlightState:
    altitude_ft: float = 0.0
    airspeed_kts: float = 0.0
    mach: float = 0.0
    heading_deg: float = 360.0
    pitch_deg: float = 0.0
    roll_deg: float = 0.0
    latitude_deg: float = 48.85
    longitude_deg: float = 2.35
    eng1_n1_pct: float = 18.0
    eng2_n1_pct: float = 18.0
    eng1_egt_c: float = 420.0
    eng2_egt_c: float = 420.0
    fms_dist_nm: float = 0.0
    phase: str = "GROUND"


class ARINC429Simulator:
    """
    Simulates ARINC 429 bus with realistic Airbus label set.
    Label encoding: 32-bit word = 8-bit label + 2-bit SSM + 19-bit data + 2-bit SDI + 1-bit parity
    """

    LABEL_TABLE = {
        0o101: ("IRS_LATITUDE",        "deg",  -90,    90),
        0o102: ("IRS_LONGITUDE",       "deg",  -180,   180),
        0o103: ("IRS_TRUE_HEADING",    "deg",  0,      360),
        0o110: ("IRS_PITCH",           "deg",  -90,    90),
        0o111: ("IRS_ROLL",            "deg",  -180,   180),
        0o206: ("AIR_DATA_ALT",        "ft",   -2000,  51000),
        0o207: ("AIR_DATA_CAS",        "kts",  0,      450),
        0o210: ("AIR_DATA_MACH",       "mach", 0,      0.99),
        0o270: ("ENG1_N1",             "pct",  0,      110),
        0o271: ("ENG2_N1",             "pct",  0,      110),
        0o301: ("FMS_DIST_DEST",       "nm",   0,      9999),
        0o361: ("FADEC_ENG1_EGT",      "degC", 0,      1000),
        0o362: ("FADEC_ENG2_EGT",      "degC", 0,      1000),
    }

    # Map label → FlightState field for twin-driven values
    _LABEL_TO_FLIGHT_STATE = {
        0o101: "latitude_deg",
        0o102: "longitude_deg",
        0o103: "heading_deg",
        0o110: "pitch_deg",
        0o111: "roll_deg",
        0o206: "altitude_ft",
        0o207: "airspeed_kts",
        0o210: "mach",
        0o270: "eng1_n1_pct",
        0o271: "eng2_n1_pct",
        0o301: "fms_dist_nm",
        0o361: "eng1_egt_c",
        0o362: "eng2_egt_c",
    }

    SSM_STATES = {
        0b00: "FAILURE",
        0b01: "NO_COMPUTED_DATA",
        0b10: "FUNCTIONAL_TEST",
        0b11: "NORMAL",
    }

    def __init__(self):
        self._active_faults: Dict[int, str] = {}  # label_octal -> fault_type
        self._word_count: int = 0
        self._error_count: int = 0
        self._start_time: float = time.time()
        self._frozen_values: Dict[int, float] = {}
        self.flight_state = FlightState()
        # Current simulated values
        self._current_values: Dict[int, float] = {}
        self._initialize_values()
        log.info("ARINC429Simulator initialized with %d labels", len(self.LABEL_TABLE))

    def _initialize_values(self):
        """Set initial simulated values for all labels."""
        defaults = {
            0o101: 48.8566,     # IRS latitude (Paris CDG)
            0o102: 2.5479,      # IRS longitude
            0o103: 270.0,       # True heading
            0o110: 0.0,         # IRS pitch
            0o111: 0.0,         # IRS roll
            0o206: 35000.0,     # Altitude
            0o207: 250.0,       # Speed
            0o210: 0.78,        # Mach
            0o270: 97.2,        # ENG1 N1
            0o271: 96.8,        # ENG2 N1
            0o301: 456.0,       # Distance to destination
            0o361: 621.0,       # ENG1 EGT
            0o362: 618.0,       # ENG2 EGT
        }
        self._current_values = defaults.copy()

    @staticmethod
    def _compute_parity(word: int) -> int:
        """Compute odd parity for a 31-bit word. Returns the parity bit (0 or 1)."""
        parity = 0
        w = word & 0x7FFFFFFF  # 31 bits
        while w:
            parity ^= (w & 1)
            w >>= 1
        return parity ^ 1  # odd parity: total 1s including parity bit must be odd

    def encode_word(self, label_octal: int, value: float,
                    ssm: int = 0b11, sdi: int = 0b00) -> int:
        """
        Encode a value into a 32-bit ARINC 429 word.
        Bit layout (MSB to LSB):
          Bit 32:     Parity
          Bits 31-30: SSM (Sign/Status Matrix)
          Bits 29-11: Data (19 bits, BNR encoding)
          Bits 10-9:  SDI (Source/Destination Identifier)
          Bits 8-1:   Label (reversed octal)
        """
        info = self.LABEL_TABLE.get(label_octal)
        if not info:
            return 0

        _name, _unit, min_val, max_val = info
        # Clamp value to range
        clamped = max(min_val, min(max_val, value))

        # BNR encoding: normalize to 19-bit unsigned
        data_range = max_val - min_val
        if data_range > 0:
            normalized = (clamped - min_val) / data_range
        else:
            normalized = 0.0
        data_bits = int(normalized * ((1 << 19) - 1)) & 0x7FFFF

        # Reverse label bits (ARINC 429 labels are transmitted LSB first)
        label_byte = 0
        for bit in range(8):
            if label_octal & (1 << bit):
                label_byte |= (1 << (7 - bit))

        # Assemble word (without parity)
        word = 0
        word |= (label_byte & 0xFF)           # bits 1-8
        word |= ((sdi & 0b11) << 8)           # bits 9-10
        word |= ((data_bits & 0x7FFFF) << 10) # bits 11-29
        word |= ((ssm & 0b11) << 29)          # bits 30-31

        # Compute parity
        parity = self._compute_parity(word)
        word |= (parity << 31)                 # bit 32

        return word

    def decode_word(self, word: int) -> Dict:
        """
        Decode a 32-bit ARINC 429 word.
        Returns: { label, label_octal, name, value, unit, ssm, ssm_str, sdi, parity_ok }
        """
        # Extract fields
        label_reversed = word & 0xFF
        sdi = (word >> 8) & 0b11
        data_bits = (word >> 10) & 0x7FFFF
        ssm = (word >> 29) & 0b11
        parity_bit = (word >> 31) & 1

        # Check parity
        expected_parity = self._compute_parity(word & 0x7FFFFFFF)
        parity_ok = (parity_bit == expected_parity)

        # Reverse label bits back
        label_octal = 0
        for bit in range(8):
            if label_reversed & (1 << bit):
                label_octal |= (1 << (7 - bit))

        info = self.LABEL_TABLE.get(label_octal)
        if not info:
            return {
                "label": f"{label_octal:03o}",
                "label_octal": label_octal,
                "name": "UNKNOWN",
                "value": 0.0,
                "unit": "",
                "ssm": ssm,
                "ssm_str": self.SSM_STATES.get(ssm, "UNKNOWN"),
                "sdi": sdi,
                "parity_ok": parity_ok,
            }

        name, unit, min_val, max_val = info
        data_range = max_val - min_val
        normalized = data_bits / ((1 << 19) - 1) if data_range > 0 else 0
        value = min_val + normalized * data_range

        return {
            "label": f"{label_octal:03o}",
            "label_octal": label_octal,
            "name": name,
            "value": round(value, 6),
            "unit": unit,
            "ssm": ssm,
            "ssm_str": self.SSM_STATES.get(ssm, "UNKNOWN"),
            "sdi": sdi,
            "parity_ok": parity_ok,
        }

    def _simulate_value(self, label_octal: int) -> float:
        """
        Generate a realistic simulated value for a given label.
        Uses flight_state (twin-driven) with ±1% Gaussian jitter for mapped
        labels; falls back to sinusoidal drift + noise for unmapped labels.
        """
        # Apply fault injection first
        fault = self._active_faults.get(label_octal)
        if fault == "FREEZE":
            if label_octal not in self._frozen_values:
                self._frozen_values[label_octal] = self._current_values.get(label_octal, 0.0)
            return self._frozen_values[label_octal]

        # Read the base value from flight_state for twin-driven labels
        fs_field = self._LABEL_TO_FLIGHT_STATE.get(label_octal)
        if fs_field is not None:
            base = getattr(self.flight_state, fs_field)
            # Add ±2 % Gaussian jitter (std = 1 % of value)
            jittered = random.gauss(base, abs(base) * 0.01) if base != 0 else base
            # Update _current_values so frozen snapshots are realistic
            self._current_values[label_octal] = jittered
        else:
            # Fallback for any label not driven by the twin
            base = self._current_values.get(label_octal, 0.0)
            jittered = base

        if fault == "NOISE":
            return jittered + random.gauss(0, abs(jittered) * 0.1)
        elif fault == "SSM_FAIL":
            return jittered  # SSM handled separately
        elif fault == "PARITY_ERR":
            return jittered  # Parity handled in encode

        return jittered

    def update_flight_state(self, state: dict) -> None:
        """Called by broadcast_loop with twin engine state each cycle."""
        fs = self.flight_state
        fs.altitude_ft    = float(state.get("altitude_ft", fs.altitude_ft))
        fs.airspeed_kts   = float(state.get("airspeed_kts", fs.airspeed_kts))
        fs.mach           = float(state.get("mach", fs.mach))
        fs.heading_deg    = float(state.get("heading_deg", fs.heading_deg))
        fs.pitch_deg      = float(state.get("pitch_deg", fs.pitch_deg))
        fs.roll_deg       = float(state.get("roll_deg", fs.roll_deg))
        fs.latitude_deg   = float(state.get("latitude_deg", fs.latitude_deg))
        fs.longitude_deg  = float(state.get("longitude_deg", fs.longitude_deg))
        fs.eng1_n1_pct    = float(state.get("eng1_n1_pct", fs.eng1_n1_pct))
        fs.eng2_n1_pct    = float(state.get("eng2_n1_pct", fs.eng2_n1_pct))
        fs.eng1_egt_c     = float(state.get("eng1_egt_c", fs.eng1_egt_c))
        fs.eng2_egt_c     = float(state.get("eng2_egt_c", fs.eng2_egt_c))
        fs.fms_dist_nm    = float(state.get("fms_dist_nm", fs.fms_dist_nm))
        fs.phase          = state.get("phase", fs.phase)

    def generate_bus_frame(self) -> List[Dict]:
        """
        Generate a complete bus frame — one word per active label.
        Returns: list of decoded word dicts.
        """
        frame = []
        ts = datetime.now(timezone.utc).isoformat()

        for label_octal, info in self.LABEL_TABLE.items():
            value = self._simulate_value(label_octal)

            # Determine SSM
            fault = self._active_faults.get(label_octal)
            ssm = 0b11  # NORMAL
            if fault == "SSM_FAIL":
                ssm = 0b00  # FAILURE

            # Encode
            word = self.encode_word(label_octal, value, ssm=ssm)

            # Inject parity error if faulted
            if fault == "PARITY_ERR":
                word ^= (1 << 31)  # Flip parity bit
                self._error_count += 1

            # Decode for output
            decoded = self.decode_word(word)
            decoded["raw_word"] = f"0x{word:08X}"
            decoded["timestamp_utc"] = ts
            decoded["bus_rate_kbps"] = 12.5
            frame.append(decoded)

            self._word_count += 1

        return frame

    def inject_fault(self, label_octal: int,
                     fault_type: str) -> Dict:
        """
        Inject a fault on a specific label.
        fault_type: "FREEZE" | "NOISE" | "SSM_FAIL" | "PARITY_ERR"
        """
        valid_faults = {"FREEZE", "NOISE", "SSM_FAIL", "PARITY_ERR"}
        if fault_type not in valid_faults:
            return {"error": f"Invalid fault type. Must be one of: {valid_faults}"}

        if label_octal not in self.LABEL_TABLE:
            return {"error": f"Unknown label: {label_octal:03o}"}

        self._active_faults[label_octal] = fault_type
        name = self.LABEL_TABLE[label_octal][0]
        log.warning(f"ARINC429 fault injected: {fault_type} on label {label_octal:03o} ({name})")
        return {
            "status": "FAULT_INJECTED",
            "label": f"{label_octal:03o}",
            "name": name,
            "fault_type": fault_type,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    def clear_fault(self, label_octal: int) -> Dict:
        """Clear a previously injected fault."""
        fault = self._active_faults.pop(label_octal, None)
        self._frozen_values.pop(label_octal, None)
        return {
            "status": "FAULT_CLEARED" if fault else "NO_FAULT_ACTIVE",
            "label": f"{label_octal:03o}",
            "previous_fault": fault,
        }

    def get_bus_stats(self) -> Dict:
        """Return bus statistics."""
        elapsed = max(1, time.time() - self._start_time)
        return {
            "words_per_sec": round(self._word_count / elapsed, 1),
            "total_words": self._word_count,
            "error_count": self._error_count,
            "error_rate": round(self._error_count / max(1, self._word_count) * 100, 4),
            "active_labels": len(self.LABEL_TABLE),
            "active_faults": len(self._active_faults),
            "faulted_labels": [
                {"label": f"{label:03o}", "fault": fault}
                for label, fault in self._active_faults.items()
            ],
            "bus_speed_kbps": 12.5,
            "protocol": "BIPOLAR_RZ",
            "uptime_sec": round(elapsed, 1),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
