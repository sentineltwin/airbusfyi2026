"""
SentinelTwin — Digital Twin Engine
Full aircraft physics model — A320neo systems
"""

import asyncio
import logging
import math
import random
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, Optional

log = logging.getLogger("sentineltwin.digital_twin")


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
    system: str
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
    total_kg: float = 18000.0
    left_wing_kg: float = 7500.0
    right_wing_kg: float = 7500.0
    center_tank_kg: float = 3000.0
    imbalance_kg: float = 0.0
    fuel_flow_total_kgh: float = 900.0
    fuel_temperature_c: float = 15.0
    crossfeed_valve: bool = False
    # Legacy compat
    flow_eng1_kgh: float = 450.0
    flow_eng2_kgh: float = 450.0


@dataclass
class StructuralState:
    wing_bending_moment_knm: float = 0.0
    wing_shear_force_kn: float = 0.0
    fuselage_hoop_stress_mpa: float = 0.0
    landing_gear_load_kn: float = 0.0
    g_load_factor: float = 1.0
    turbulence_intensity: str = "NIL"  # NIL|LIGHT|MODERATE|SEVERE


@dataclass
class ThermalState:
    avionics_bay_c: float = 35.0
    cabin_temp_c: float = 22.0
    cargo_temp_c: float = 10.0
    brake_temp_c: float = 100.0
    apu_egt_c: float = 0.0
    eng1_oil_temp_c: float = 75.0
    eng2_oil_temp_c: float = 75.0


@dataclass
class AircraftDigitalTwin:
    aircraft_type: str = "A320neo"
    msn: str = "8234"
    registration: str = "F-WXWB"
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
    airspeed_kts: float = 0.0  # Alias for external consumers
    atmosphere: Optional[AtmosphericState] = None
    eng1: Optional[EngineState] = None
    eng2: Optional[EngineState] = None
    hyd_green: Optional[HydraulicState] = None
    hyd_blue: Optional[HydraulicState] = None
    hyd_yellow: Optional[HydraulicState] = None
    electrical: Optional[ElectricalState] = None
    fuel: Optional[FuelState] = None
    structural: Optional[StructuralState] = None
    thermal: Optional[ThermalState] = None
    session_elapsed_sec: float = 0.0
    last_updated: str = ""


class DigitalTwinEngine:
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
            altitude_ft=alt_ft, temperature_c=T - 273.15,
            pressure_kpa=P / 1000, density_kgm3=rho, altitude_m=alt_m,
        )

    def _update_flight_dynamics(self, phase: str, elapsed: float):
        tw = self.twin
        t = self._t
        if phase == "GROUND":
            tw.altitude_ft = 0.0; tw.ias_kt = 0.0; tw.vertical_speed_fpm = 0.0; tw.pitch_deg = 0.0
        elif phase == "TAXI":
            tw.altitude_ft = 0.0; tw.ias_kt = min(20, elapsed * 2); tw.heading_deg = (tw.heading_deg + 0.5) % 360
        elif phase == "TAKEOFF":
            tw.ias_kt = min(180, elapsed * 5); tw.altitude_ft = max(0, (tw.ias_kt - 140) * 50)
            tw.pitch_deg = min(15, (tw.ias_kt - 140) * 0.5) if tw.ias_kt > 140 else 0
            tw.vertical_speed_fpm = max(0, (tw.ias_kt - 140) * 100)
        elif phase == "CLIMB":
            tw.ias_kt = 250 + math.sin(t / 30) * 5; tw.altitude_ft = min(39000, tw.altitude_ft + 200)
            tw.vertical_speed_fpm = 2200 + math.sin(t / 20) * 100; tw.pitch_deg = 8 + math.sin(t / 15)
        elif phase == "CRUISE":
            tw.ias_kt = 250 + math.sin(t / 40) * 3; tw.altitude_ft = min(39000, tw.altitude_ft + 10)
            tw.vertical_speed_fpm = math.sin(t / 60) * 50; tw.pitch_deg = 2 + math.sin(t / 30) * 0.5
            tw.latitude += 0.001; tw.longitude += 0.0008
        elif phase == "DESCENT":
            tw.ias_kt = max(220, tw.ias_kt - 1); tw.altitude_ft = max(0, tw.altitude_ft - 800)
            tw.vertical_speed_fpm = -2500 + math.cos(t / 20) * 100; tw.pitch_deg = -3 + math.sin(t / 20) * 0.5
        elif phase in ("APPROACH", "LANDING"):
            tw.ias_kt = max(140, tw.ias_kt - 2); tw.altitude_ft = max(0, tw.altitude_ft - 300)
            tw.vertical_speed_fpm = -700; tw.pitch_deg = -2
        # Compute TAS first — Mach depends on it, not the other way around.
        tw.tas_kt = tw.ias_kt * math.sqrt(
            288.15 / max(1, self.twin.atmosphere.temperature_c + 273.15)
        ) if tw.atmosphere else tw.ias_kt
        tw.mach = tw.tas_kt / 666.0  # Speed of sound at sea level ≈ 666 kts
        tw.airspeed_kts = tw.ias_kt  # Keep alias in sync

    def _update_engines(self, phase: str):
        n1_target = {"GROUND": 22.0, "TAXI": 28.0, "TAKEOFF": 100.0, "CLIMB": 94.0,
                     "CRUISE": 87.0, "DESCENT": 42.0, "APPROACH": 55.0, "LANDING": 68.0}.get(phase, 22.0)
        for eng_id, attr in ((1, "eng1"), (2, "eng2")):
            eng = getattr(self.twin, attr)
            if eng is None:
                eng = EngineState(engine_id=eng_id, n1_pct=22.0, n2_pct=68.0, egt_c=380.0,
                                  oil_temp_c=75.0, oil_press_psi=55.0, fuel_flow_kgh=450.0,
                                  thrust_kn=12.0, vibration_n1=0.1, fadec_active=True, fadec_channel=1)
            eng.n1_pct += (n1_target - eng.n1_pct) * 0.1 + math.sin(self._t / (2 + eng_id * 0.3)) * 0.2
            eng.n2_pct = eng.n1_pct * 1.05 + 10
            egt_target = 350 + eng.n1_pct * 2.8
            eng.egt_c += (egt_target - eng.egt_c) * 0.05 + math.sin(self._t / (3 + eng_id * 0.2)) * 2
            eng.fuel_flow_kgh = max(0, eng.n1_pct * 22.5)
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
                pump1_active=True, pump2_active=sys_name != "BLUE",
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

    def _update_fuel(self, phase: str, dt_sec: float = 0.1) -> None:
        """
        Fuel burn model based on engine N1 and phase-specific TSFC.
        A320neo CFM LEAP-1A: cruise TSFC ≈ 0.53 lb/lbf/hr
        """
        tw = self.twin
        if tw.fuel is None:
            tw.fuel = FuelState(
                total_kg=18000.0, left_wing_kg=7500.0,
                right_wing_kg=7500.0, center_tank_kg=3000.0,
            )

        # Fuel flow by phase (kg/hour per engine)
        ff_by_phase = {
            "GROUND": 150, "TAXI": 200, "TAKEOFF": 2800,
            "CLIMB": 1800, "CRUISE": 1200, "DESCENT": 400,
            "APPROACH": 600, "LANDING": 350,
        }
        flow_per_engine_kgh = ff_by_phase.get(phase, 150)
        total_flow = flow_per_engine_kgh * 2  # 2 engines
        burned_kg = total_flow * (dt_sec / 3600)

        tw.fuel.fuel_flow_total_kgh = total_flow
        tw.fuel.flow_eng1_kgh = flow_per_engine_kgh
        tw.fuel.flow_eng2_kgh = flow_per_engine_kgh
        tw.fuel.total_kg = max(0, tw.fuel.total_kg - burned_kg)

        # Distribute burn across tanks (center first, then wings)
        if tw.fuel.center_tank_kg > 0:
            center_burn = min(burned_kg * 0.6, tw.fuel.center_tank_kg)
            tw.fuel.center_tank_kg -= center_burn
            wing_burn = burned_kg - center_burn
        else:
            wing_burn = burned_kg
        tw.fuel.left_wing_kg = max(0, tw.fuel.left_wing_kg - wing_burn * 0.5)
        tw.fuel.right_wing_kg = max(0, tw.fuel.right_wing_kg - wing_burn * 0.5)

        # Imbalance (small random drift)
        tw.fuel.imbalance_kg = abs(tw.fuel.left_wing_kg - tw.fuel.right_wing_kg)

        # Fuel temperature varies with altitude (ISA lapse rate)
        tw.fuel.fuel_temperature_c = max(-40, 15 - (tw.altitude_ft / 1000) * 1.98)

    def _update_structural(self, phase: str, elapsed: float) -> None:
        """
        Compute structural loads based on phase and aircraft weight.
        Wing bending moment increases with lift (proportional to altitude/speed).
        """
        tw = self.twin
        speed = tw.ias_kt
        alt = tw.altitude_ft

        # G-load by phase
        g_by_phase = {
            "GROUND": 1.0, "TAXI": 1.05, "TAKEOFF": 1.2,
            "CLIMB": 1.15, "CRUISE": 1.0, "DESCENT": 1.05,
            "APPROACH": 1.1, "LANDING": 1.8,
        }
        g = g_by_phase.get(phase, 1.0)

        # Turbulence (random but phase-weighted)
        if phase == "CRUISE" and alt > 30000:
            intensity = random.choices(
                ["NIL", "LIGHT", "MODERATE"],
                weights=[0.75, 0.20, 0.05],
            )[0]
        elif phase in ("CLIMB", "DESCENT"):
            intensity = random.choices(
                ["NIL", "LIGHT", "MODERATE"],
                weights=[0.60, 0.30, 0.10],
            )[0]
        else:
            intensity = "NIL"

        # Wing bending: MTOW 73,500 kg A320neo, half-span ~17m
        mtow_kg = 73_500
        lift_n = mtow_kg * 9.81 * g
        bending = (lift_n * 8.5) / 1000  # kNm (approx half-span arm)

        tw.structural = StructuralState(
            wing_bending_moment_knm=round(bending, 1),
            wing_shear_force_kn=round(lift_n / 2 / 1000, 1),
            fuselage_hoop_stress_mpa=round(0.0875 * max(0, alt / 1000) * 6.895, 2),
            landing_gear_load_kn=round(
                mtow_kg * 9.81 / 1000 if phase in ("GROUND", "TAXI", "LANDING") else 0.0, 1
            ),
            g_load_factor=round(g + random.gauss(0, 0.02), 3),
            turbulence_intensity=intensity,
        )

    def _update_thermal(self, phase: str) -> None:
        """Thermal model for avionics, brakes, engines, cabin."""
        tw = self.twin
        if tw.thermal is None:
            tw.thermal = ThermalState()

        t = tw.thermal
        # Avionics bay: heat load proportional to sensor count and scan rate
        t.avionics_bay_c = 35 + random.gauss(0, 0.5)

        # Brakes: heat up on landing/taxi, cool in flight
        if phase in ("LANDING", "TAXI"):
            t.brake_temp_c = min(500, t.brake_temp_c + random.uniform(5, 25))
        elif phase in ("CLIMB", "CRUISE"):
            t.brake_temp_c = max(100, t.brake_temp_c - random.uniform(2, 8))

        # Cabin temperature
        t.cabin_temp_c = 22 + random.gauss(0, 0.3)

        # APU EGT (on during ground, off in flight)
        t.apu_egt_c = 420 + random.gauss(0, 5) if phase == "GROUND" else 0.0

        # Engine oil temperature
        if tw.eng1:
            t.eng1_oil_temp_c = min(120, 55 + tw.eng1.n1_pct * 0.65 + random.gauss(0, 1))
        if tw.eng2:
            t.eng2_oil_temp_c = min(120, 55 + tw.eng2.n1_pct * 0.65 + random.gauss(0, 1))

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
            self._update_fuel(phase, dt_sec=self.UPDATE_SEC)
            self._update_structural(phase, self._t)
            self._update_thermal(phase)
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
            "aircraft_type": tw.aircraft_type, "msn": tw.msn, "registration": tw.registration,
            "flight_phase": tw.flight_phase, "altitude_ft": round(tw.altitude_ft, 1),
            "ias_kt": round(tw.ias_kt, 1), "tas_kt": round(tw.tas_kt, 1),
            "airspeed_kts": round(tw.airspeed_kts, 1),
            "mach": round(tw.mach, 3), "vertical_speed_fpm": round(tw.vertical_speed_fpm, 0),
            "heading_deg": round(tw.heading_deg, 1), "pitch_deg": round(tw.pitch_deg, 2),
            "roll_deg": round(tw.roll_deg, 2),
            "latitude": round(tw.latitude, 6), "longitude": round(tw.longitude, 6),
            "isa_temp_c": round(tw.atmosphere.temperature_c, 2) if tw.atmosphere else 15.0,
            "isa_pressure_kpa": round(tw.atmosphere.pressure_kpa, 3) if tw.atmosphere else 101.325,
            "atmosphere": {
                "temperature_c": round(tw.atmosphere.temperature_c, 2) if tw.atmosphere else 15.0,
                "pressure_kpa": round(tw.atmosphere.pressure_kpa, 3) if tw.atmosphere else 101.325,
                "density_kgm3": round(tw.atmosphere.density_kgm3, 5) if tw.atmosphere else 1.225,
            },
            "engines": {
                "eng1": {"n1_pct": round(tw.eng1.n1_pct, 2), "n2_pct": round(tw.eng1.n2_pct, 2),
                         "egt_c": round(tw.eng1.egt_c, 1), "oil_temp_c": round(tw.eng1.oil_temp_c, 1),
                         "oil_press_psi": round(tw.eng1.oil_press_psi, 1),
                         "fuel_flow_kgh": round(tw.eng1.fuel_flow_kgh, 0),
                         "thrust_kn": round(tw.eng1.thrust_kn, 1),
                         "fadec_active": tw.eng1.fadec_active} if tw.eng1 else {},
                "eng2": {"n1_pct": round(tw.eng2.n1_pct, 2),
                         "egt_c": round(tw.eng2.egt_c, 1),
                         "thrust_kn": round(tw.eng2.thrust_kn, 1)} if tw.eng2 else {},
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
                "left_wing_kg": round(tw.fuel.left_wing_kg, 0) if tw.fuel else 7500,
                "right_wing_kg": round(tw.fuel.right_wing_kg, 0) if tw.fuel else 7500,
                "center_tank_kg": round(tw.fuel.center_tank_kg, 0) if tw.fuel else 3000,
                "imbalance_kg": round(tw.fuel.imbalance_kg, 1) if tw.fuel else 0,
                "fuel_flow_total_kgh": round(tw.fuel.fuel_flow_total_kgh, 0) if tw.fuel else 900,
                "fuel_temperature_c": round(tw.fuel.fuel_temperature_c, 1) if tw.fuel else 15,
                "flow_total_kgh": round((tw.fuel.flow_eng1_kgh + tw.fuel.flow_eng2_kgh), 0) if tw.fuel else 900,
            },
            "structural": {
                "wing_bending_moment_knm": round(tw.structural.wing_bending_moment_knm, 1) if tw.structural else 0,
                "wing_shear_force_kn": round(tw.structural.wing_shear_force_kn, 1) if tw.structural else 0,
                "fuselage_hoop_stress_mpa": round(tw.structural.fuselage_hoop_stress_mpa, 2) if tw.structural else 0,
                "landing_gear_load_kn": round(tw.structural.landing_gear_load_kn, 1) if tw.structural else 0,
                "g_load_factor": round(tw.structural.g_load_factor, 3) if tw.structural else 1.0,
                "turbulence_intensity": tw.structural.turbulence_intensity if tw.structural else "NIL",
            },
            "thermal": {
                "avionics_bay_c": round(tw.thermal.avionics_bay_c, 1) if tw.thermal else 35,
                "cabin_temp_c": round(tw.thermal.cabin_temp_c, 1) if tw.thermal else 22,
                "cargo_temp_c": round(tw.thermal.cargo_temp_c, 1) if tw.thermal else 10,
                "brake_temp_c": round(tw.thermal.brake_temp_c, 0) if tw.thermal else 100,
                "apu_egt_c": round(tw.thermal.apu_egt_c, 0) if tw.thermal else 0,
                "eng1_oil_temp_c": round(tw.thermal.eng1_oil_temp_c, 1) if tw.thermal else 75,
                "eng2_oil_temp_c": round(tw.thermal.eng2_oil_temp_c, 1) if tw.thermal else 75,
            },
            "session_elapsed_sec": round(tw.session_elapsed_sec, 1),
        }
