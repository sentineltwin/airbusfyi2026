/**
 * SentinelTwin — Global State Store
 * Zustand-powered real-time operational state management
 * Manages: auth, sensors, AI, ECAM, twin, dispatch, hash chain
 */

import { create } from 'zustand'
import { devtools, subscribeWithSelector } from 'zustand/middleware'
import type { WSConnectionStatus } from '../hooks/useWebSocket'

// ─────────────────────────────────────────────────────────────
// TYPE DEFINITIONS
// ─────────────────────────────────────────────────────────────

export type SensorState =
  | 'HEALTHY' | 'DEGRADED' | 'FAILED' | 'DESYNCHRONIZED'
  | 'STALE' | 'SPOOFED' | 'OFFLINE' | 'MAINTENANCE' | 'UNVERIFIED'

export type FlightPhase =
  | 'GROUND' | 'TAXI' | 'TAKEOFF' | 'CLIMB'
  | 'CRUISE' | 'DESCENT' | 'APPROACH' | 'LANDING'

export type ECAMSeverity = 'STATUS' | 'CAUTION' | 'WARNING' | 'EMERGENCY'

export interface Sensor {
  sensor_id: string
  ata_chapter: number
  subsystem: string
  zone: string
  engineering_unit: string
  state: SensorState
  last_value: number
  physics_residual: number
  confidence_score: number
  ai_anomaly_score: number
  redundancy_group: string
  arinc_label: string
  validation_count: number
  sampling_rate: number
}

export interface ECAMMessage {
  message_id: string
  severity: ECAMSeverity
  system: string
  ata_chapter: number
  message: string
  procedure: string | null
  dispatch_impact: boolean
  mel_reference: string | null
  generated_at: string
  is_active: boolean
}

export interface HashBlock {
  sequence: number
  scan_id: string
  timestamp: string
  block_hash: string
  previous_hash: string
  healthy_count: number
  anomaly_count: number
  flight_phase: string
}

export interface AIStatus {
  model_version: string
  reconstruction_error: number
  severity: string
  confidence: number
  active_events: number
  anomaly_event_count: number
  inference_count: number
  false_positive_rate: number
  true_positive_rate: number
  anomaly_threshold: number
}

export interface TwinState {
  aircraft_type: string
  registration: string
  flight_phase: FlightPhase
  altitude_ft: number
  ias_kt: number
  tas_kt: number
  airspeed_kts: number
  mach: number
  vertical_speed_fpm: number
  heading_deg: number
  pitch_deg: number
  roll_deg: number
  latitude: number
  longitude: number
  isa_temp_c: number
  isa_pressure_kpa: number
  atmosphere: {
    temperature_c: number
    pressure_kpa: number
    density_kgm3: number
  }
  engines: {
    eng1: { n1_pct: number; egt_c: number; thrust_kn: number; oil_temp_c: number; fadec_active: boolean }
    eng2: { n1_pct: number; egt_c: number; thrust_kn: number }
  }
  hydraulics: { green_psi: number; blue_psi: number; yellow_psi: number }
  electrical: { gen1_online: boolean; gen2_online: boolean; ac_bus1_v: number; total_load_kva: number }
  fuel: {
    total_kg: number
    left_wing_kg: number
    right_wing_kg: number
    center_tank_kg: number
    imbalance_kg: number
    fuel_flow_total_kgh: number
    fuel_temperature_c: number
    flow_total_kgh: number
  }
  structural: {
    wing_bending_moment_knm: number
    wing_shear_force_kn: number
    fuselage_hoop_stress_mpa: number
    landing_gear_load_kn: number
    g_load_factor: number
    turbulence_intensity: string
  }
  thermal: {
    avionics_bay_c: number
    cabin_temp_c: number
    cargo_temp_c: number
    brake_temp_c: number
    apu_egt_c: number
    eng1_oil_temp_c: number
    eng2_oil_temp_c: number
  }
  session_elapsed_sec: number
}

export interface User {
  id: string
  username: string
  full_name: string
  role: string
  email: string
}

export interface SensorStats {
  total_sensors: number
  healthy_count: number
  anomaly_count: number
  health_pct: number
  state_counts: Record<SensorState, number>
  ata_breakdown: Record<number, { total: number; healthy: number; degraded: number; failed: number }>
  cycle_duration_ms: number
  scan_rate: number
}

export interface DispatchStatus {
  dispatch_ready: boolean
  determination: 'GO' | 'NO-GO'
  sensor_health_pct: number
  ai_confidence: number
  active_ecam: number
  checklist: Record<string, boolean>
  checks_passed: number
  checks_total: number
}

export interface CyberEvent {
  id: string
  ts: string
  type: string
  src: string
  severity: 'LOW' | 'MEDIUM' | 'HIGH' | 'CRITICAL'
  status: 'BLOCKED' | 'DETECTED' | 'INVESTIGATING'
}

export interface EventLogEntry {
  id: string
  ts: string
  type: ECAMSeverity | 'INFO' | 'SYSTEM'
  msg: string
  ata: number
  source: string
}

export interface ArincLabel {
  label: string
  label_octal: number
  name: string
  value: number
  unit: string
  ssm: number
  ssm_str: string
  sdi: number
  parity_ok: boolean
  raw_word: string
  timestamp_utc: string
  integrity: string
  bus_rate_kbps: number
}

export interface AFDXVirtualLink {
  vl_id: string
  jitter_us: number
  actual_bag_ms: number
  nominal_bag_ms: number
  frame_bytes: number
  max_frame_bytes: number
  seq_num: number
  status: string
  bag_violation: boolean
  jitter_violation: boolean
  bw_kbps: number
  bw_utilization_pct: number
  publisher: string
  subscribers: string[]
  avg_jitter_us: number
  max_jitter_us: number
}

export interface AFDXNetworkStats {
  total_virtual_links: number
  nominal_count: number
  degraded_count: number
  failed_count: number
  total_utilization_pct: number
  total_bw_allocated_kbps: number
  network_speed_mbps: number
  total_frames: number
  total_violations: number
  violation_rate_pct: number
}

// ─────────────────────────────────────────────────────────────
// STORE INTERFACE
// ─────────────────────────────────────────────────────────────

interface SentinelStore {
  // ── Auth ────────────────────────────────────────────────────
  user: User | null
  accessToken: string | null
  isAuthenticated: boolean
  authError: string
  setUser: (user: User, token: string) => void
  clearAuth: () => void
  setAuthError: (err: string) => void

  // ── App State ───────────────────────────────────────────────
  appPhase: 'LOGIN' | 'BOOT' | 'MAIN'
  bootStep: number
  activePanel: string
  setAppPhase: (phase: 'LOGIN' | 'BOOT' | 'MAIN') => void
  setBootStep: (step: number) => void
  setActivePanel: (panel: string) => void

  // ── Sensor Data ─────────────────────────────────────────────
  sensors: Sensor[]
  sensorStats: SensorStats
  sensorFilter: SensorState | 'ALL'
  selectedATA: number | null
  setSensors: (sensors: Sensor[]) => void
  updateSensorStats: (stats: Partial<SensorStats>) => void
  setSensorFilter: (f: SensorState | 'ALL') => void
  setSelectedATA: (ata: number | null) => void

  // ── Digital Twin ────────────────────────────────────────────
  twinState: TwinState | null
  flightPhase: FlightPhase
  altitude: number
  speed: number
  elapsed: number
  updateTwin: (state: Partial<TwinState>) => void
  setFlightPhase: (phase: FlightPhase) => void
  setAltitude: (alt: number) => void
  setSpeed: (spd: number) => void
  tickElapsed: (dt: number) => void

  // ── AI Engine ───────────────────────────────────────────────
  aiStatus: AIStatus
  errorHistory: number[]
  updateAI: (status: Partial<AIStatus>) => void
  pushError: (err: number) => void

  // ── ECAM ────────────────────────────────────────────────────
  ecamMessages: ECAMMessage[]
  setECAM: (msgs: ECAMMessage[]) => void
  clearECAM: () => void

  // ── Hash Chain ──────────────────────────────────────────────
  hashChain: HashBlock[]
  chainValid: boolean
  pushHashBlock: (block: HashBlock) => void
  setChainValid: (valid: boolean) => void

  // ── Dispatch ────────────────────────────────────────────────
  dispatchStatus: DispatchStatus | null
  dispatchReady: boolean
  updateDispatch: (status: Partial<DispatchStatus>) => void

  // ── Cyber ───────────────────────────────────────────────────
  cyberEvents: CyberEvent[]
  threatLevel: 'LOW' | 'MEDIUM' | 'HIGH' | 'CRITICAL'
  cyberStats: Record<string, number>
  pushCyberEvent: (evt: CyberEvent) => void
  setCyberStatus: (level: string, stats: Record<string, number>) => void

  // ── ARINC 429 ──────────────────────────────────────────────
  arincLabels: ArincLabel[]
  arincBusStats: Record<string, any>
  setArincFrame: (labels: ArincLabel[], stats: Record<string, any>) => void

  // ── AFDX ───────────────────────────────────────────────────
  afdxVirtualLinks: AFDXVirtualLink[]
  afdxNetworkStats: AFDXNetworkStats | null
  setAFDXStatus: (vls: AFDXVirtualLink[], stats: AFDXNetworkStats) => void

  // ── Event Log ───────────────────────────────────────────────
  eventLog: EventLogEntry[]
  pushEvent: (entry: EventLogEntry) => void
  clearEvents: () => void

  // ── WebSocket ───────────────────────────────────────────────
  wsConnected: boolean
  wsReconnecting: boolean
  wsMessageCount: number
  wsStatus: WSConnectionStatus
  setWSConnected: (v: boolean) => void
  setWSReconnecting: (v: boolean) => void
  incWSMessages: () => void
  setWSStatus: (status: WSConnectionStatus) => void
  handleWSFrame: (frame: any) => void

  // ── Live WS Data ────────────────────────────────────────────
  dispatchReason: string
  arincFrame: any[]
  arincStats: Record<string, any>
  afdxVLs: any[]
  afdxStats: Record<string, any>
  cyberStatus: Record<string, any>

  // ── Scan Metrics ────────────────────────────────────────────
  scanRate: number
  totalValidations: number
  cycleDurationMs: number
  setScanMetrics: (rate: number, total: number, cyclems: number) => void

  // ── Flight Info (from Mission Setup Modal) ──────────────────
  flightInfo: Record<string, string>
  setFlightInfo: (info: Record<string, string>) => void
}

// ─────────────────────────────────────────────────────────────
// DEFAULT VALUES
// ─────────────────────────────────────────────────────────────

const defaultSensorStats: SensorStats = {
  total_sensors: 8192,
  healthy_count: 0,
  anomaly_count: 0,
  health_pct: 0,
  state_counts: {
    HEALTHY: 0, DEGRADED: 0, FAILED: 0, DESYNCHRONIZED: 0,
    STALE: 0, SPOOFED: 0, OFFLINE: 0, MAINTENANCE: 0, UNVERIFIED: 0,
  },
  ata_breakdown: {},
  cycle_duration_ms: 0,
  scan_rate: 0,
}

const defaultAIStatus: AIStatus = {
  model_version: 'v2.4.1-prod',
  reconstruction_error: 0,
  severity: 'NOMINAL',
  confidence: 0.97,
  active_events: 0,
  anomaly_event_count: 0,
  inference_count: 0,
  false_positive_rate: 0.0042,
  true_positive_rate: 0.863,
  anomaly_threshold: 0.15,
}

// ─────────────────────────────────────────────────────────────
// STORE IMPLEMENTATION
// ─────────────────────────────────────────────────────────────

export const useSentinelStore = create<SentinelStore>()(
  devtools(
    subscribeWithSelector((set, get) => ({
      // ── Auth ──────────────────────────────────────────────────
      user: null,
      accessToken: null,
      isAuthenticated: false,
      authError: '',
      setUser: (user, token) => set({ user, accessToken: token, isAuthenticated: true, authError: '' }),
      clearAuth: () => set({ user: null, accessToken: null, isAuthenticated: false }),
      setAuthError: (authError) => set({ authError }),

      // ── App State ─────────────────────────────────────────────
      appPhase: 'LOGIN',
      bootStep: 0,
      activePanel: 'OVERVIEW',
      setAppPhase: (appPhase) => set({ appPhase }),
      setBootStep: (bootStep) => set({ bootStep }),
      setActivePanel: (activePanel) => set({ activePanel }),

      // ── Sensors ───────────────────────────────────────────────
      sensors: [],
      sensorStats: defaultSensorStats,
      sensorFilter: 'ALL',
      selectedATA: null,
      setSensors: (sensors) => {
        // Compute stats inline
        const counts = {} as Record<SensorState, number>
        const ataBreakdown = {} as Record<number, { total: number; healthy: number; degraded: number; failed: number }>
        for (const s of sensors) {
          counts[s.state] = (counts[s.state] || 0) + 1
          if (!ataBreakdown[s.ata_chapter]) {
            ataBreakdown[s.ata_chapter] = { total: 0, healthy: 0, degraded: 0, failed: 0 }
          }
          ataBreakdown[s.ata_chapter].total++
          if (s.state === 'HEALTHY') ataBreakdown[s.ata_chapter].healthy++
          else if (s.state === 'DEGRADED') ataBreakdown[s.ata_chapter].degraded++
          else if (s.state === 'FAILED') ataBreakdown[s.ata_chapter].failed++
        }
        const healthy = counts.HEALTHY || 0
        set({
          sensors,
          sensorStats: {
            ...get().sensorStats,
            total_sensors: sensors.length,
            healthy_count: healthy,
            anomaly_count: sensors.length - healthy,
            health_pct: sensors.length > 0 ? (healthy / sensors.length) * 100 : 0,
            state_counts: counts,
            ata_breakdown: ataBreakdown,
          },
        })
      },
      updateSensorStats: (stats) => set((s) => ({ sensorStats: { ...s.sensorStats, ...stats } })),
      setSensorFilter: (sensorFilter) => set({ sensorFilter }),
      setSelectedATA: (selectedATA) => set({ selectedATA }),

      // ── Digital Twin ──────────────────────────────────────────
      twinState: null,
      flightPhase: 'GROUND',
      altitude: 0,
      speed: 0,
      elapsed: 0,
      updateTwin: (state) => set((s) => ({
        twinState: s.twinState ? { ...s.twinState, ...state } : state as TwinState,
        altitude: state.altitude_ft ?? s.altitude,
        speed: state.ias_kt ?? s.speed,
        flightPhase: (state.flight_phase as FlightPhase) ?? s.flightPhase,
      })),
      setFlightPhase: (flightPhase) => set({ flightPhase }),
      setAltitude: (altitude) => set({ altitude }),
      setSpeed: (speed) => set({ speed }),
      tickElapsed: (dt) => set((s) => ({ elapsed: s.elapsed + dt })),

      // ── AI ────────────────────────────────────────────────────
      aiStatus: defaultAIStatus,
      errorHistory: Array.from({ length: 60 }, () => 0.06 + Math.random() * 0.04),
      updateAI: (status) => set((s) => ({ aiStatus: { ...s.aiStatus, ...status } })),
      pushError: (err) => set((s) => ({
        errorHistory: [...s.errorHistory.slice(-299), err],
      })),

      // ── ECAM ──────────────────────────────────────────────────
      ecamMessages: [],
      setECAM: (ecamMessages) => set({ ecamMessages }),
      clearECAM: () => set({ ecamMessages: [] }),

      // ── Hash Chain ────────────────────────────────────────────
      hashChain: [],
      chainValid: true,
      pushHashBlock: (block) => set((s) => ({
        hashChain: [block, ...s.hashChain].slice(0, 100),
      })),
      setChainValid: (chainValid) => set({ chainValid }),

      // ── Dispatch ──────────────────────────────────────────────
      dispatchStatus: null,
      dispatchReady: false,
      updateDispatch: (status) => set((s) => ({
        dispatchStatus: s.dispatchStatus ? { ...s.dispatchStatus, ...status } : status as DispatchStatus,
        dispatchReady: status.dispatch_ready ?? s.dispatchReady,
      })),

      // ── Cyber ─────────────────────────────────────────────────
      cyberEvents: [],
      threatLevel: 'LOW',
      cyberStats: {},
      pushCyberEvent: (evt) => set((s) => ({
        cyberEvents: [evt, ...s.cyberEvents].slice(0, 200),
        threatLevel: evt.severity === 'CRITICAL' ? 'CRITICAL'
          : evt.severity === 'HIGH' ? 'HIGH'
          : s.threatLevel,
      })),
      setCyberStatus: (level, stats) => set({ threatLevel: level as any, cyberStats: stats }),

      // ── ARINC 429 ──────────────────────────────────────────────
      arincLabels: [],
      arincBusStats: {},
      setArincFrame: (labels, stats) => set({ arincLabels: labels, arincBusStats: stats }),

      // ── AFDX ───────────────────────────────────────────────────
      afdxVirtualLinks: [],
      afdxNetworkStats: null,
      setAFDXStatus: (vls, stats) => set({ afdxVirtualLinks: vls, afdxNetworkStats: stats }),

      // ── Event Log ─────────────────────────────────────────────
      eventLog: [],
      pushEvent: (entry) => set((s) => ({
        eventLog: [entry, ...s.eventLog].slice(0, 500),
      })),
      clearEvents: () => set({ eventLog: [] }),

      // ── WebSocket ─────────────────────────────────────────────
      wsConnected: false,
      wsReconnecting: false,
      wsMessageCount: 0,
      wsStatus: 'DISCONNECTED' as WSConnectionStatus,
      setWSConnected: (wsConnected) => set({ wsConnected, wsReconnecting: false }),
      setWSReconnecting: (wsReconnecting) => set({ wsReconnecting }),
      incWSMessages: () => set((s) => ({ wsMessageCount: s.wsMessageCount + 1 })),
      setWSStatus: (status) => set({
        wsStatus: status,
        wsConnected: status === 'CONNECTED',
        wsReconnecting: status === 'RECONNECTING',
      }),
      handleWSFrame: (frame) => {
        if (!frame?.channel || !frame?.data) return;
        const { channel, data } = frame;
        const s = get();
        get().incWSMessages();

        switch (channel) {
          case 'telemetry':
            if (data.type === 'sensor_stats') {
              set({
                sensorStats: {
                  ...s.sensorStats,
                  total_sensors: data.total_sensors ?? s.sensorStats.total_sensors,
                  healthy_count: data.healthy_count ?? s.sensorStats.healthy_count,
                  anomaly_count: data.anomaly_count ?? s.sensorStats.anomaly_count,
                  health_pct: data.total_sensors > 0
                    ? (data.healthy_count / data.total_sensors) * 100
                    : s.sensorStats.health_pct,
                  scan_rate: data.scan_rate ?? s.sensorStats.scan_rate,
                  cycle_duration_ms: data.cycle_duration_ms ?? s.sensorStats.cycle_duration_ms,
                },
                scanRate: data.scan_rate ?? s.scanRate,
              });
              get().setScanMetrics(
                data.scan_rate || 0,
                data.total_validations || 0,
                data.cycle_duration_ms || 0,
              );
            }
            break;

          case 'ai':
            if (data.type === 'ai_status') {
              get().updateAI({
                reconstruction_error: data.reconstruction_error,
                severity: data.severity,
                confidence: data.confidence,
                active_events: data.active_events,
                inference_count: data.inference_count,
              });
              if (typeof data.reconstruction_error === 'number') {
                get().pushError(data.reconstruction_error);
              }
            }
            break;

          case 'twin':
            if (data.type === 'twin_state') {
              get().updateTwin(data);
            }
            break;

          case 'ecam':
            if (data.type === 'ecam_update') {
              get().setECAM(data.active || []);
            }
            break;

          case 'hashchain':
            if (data.type === 'hash_block') {
              get().pushHashBlock(data.block);
              get().setChainValid(data.chain_valid);
            }
            break;

          case 'dispatch':
            if (data.type === 'dispatch_status') {
              get().updateDispatch({
                dispatch_ready: data.dispatch_ready,
                determination: data.dispatch_ready ? 'GO' : 'NO-GO',
              });
              set({ dispatchReason: data.reason ?? '' });
            }
            break;

          case 'arinc':
            if (data.type === 'arinc_frame') {
              get().setArincFrame(data.frame || [], data.bus_stats || {});
              set({ arincFrame: data.frame || [], arincStats: data.bus_stats || {} });
            }
            break;

          case 'afdx':
            if (data.type === 'afdx_status') {
              get().setAFDXStatus(data.virtual_links || [], data.network_stats || {});
              set({ afdxVLs: data.virtual_links || [], afdxStats: data.network_stats || {} });
            }
            break;

          case 'cyber':
            if (data.type === 'cyber_status') {
              get().setCyberStatus(
                data.threat_level || 'LOW',
                data.statistics || {},
              );
              set({
                cyberStatus: {
                  threat_level: data.threat_level ?? s.cyberStatus?.threat_level,
                  active_threats: data.active_threats ?? s.cyberStatus?.active_threats,
                  statistics: data.statistics ?? s.cyberStatus?.statistics,
                },
              });
            }
            break;

          default:
            break;
        }
      },

      // ── Live WS Data ───────────────────────────────────────────
      dispatchReason: '',
      arincFrame: [],
      arincStats: {},
      afdxVLs: [],
      afdxStats: {},
      cyberStatus: {},

      // ── Scan Metrics ──────────────────────────────────────────
      scanRate: 0,
      totalValidations: 0,
      cycleDurationMs: 0,
      setScanMetrics: (scanRate, totalValidations, cycleDurationMs) =>
        set({ scanRate, totalValidations, cycleDurationMs }),

      // ── Flight Info (from Mission Setup Modal) ────────────────
      flightInfo: {},
      setFlightInfo: (info) => set({ flightInfo: info }),
    })),
    { name: 'SentinelTwin' }
  )
)

// ─────────────────────────────────────────────────────────────
// WEBSOCKET SERVICE (connects to backend)
// ─────────────────────────────────────────────────────────────

export class SentinelWebSocket {
  private ws: WebSocket | null = null
  private url: string
  private reconnectDelay = 2000
  private maxDelay = 30000
  private _destroyed = false
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null

  constructor(url = 'ws://localhost:8000/ws/telemetry') {
    this.url = url
  }

  connect() {
    if (this._destroyed) return
    const store = useSentinelStore.getState()
    store.setWSReconnecting(true)

    try {
      this.ws = new WebSocket(this.url)

      this.ws.onopen = () => {
        console.log('[SentinelTwin WS] Connected')
        useSentinelStore.getState().setWSConnected(true)
        this.reconnectDelay = 2000
      }

      this.ws.onmessage = (event) => {
        try {
          const payload = JSON.parse(event.data)
          useSentinelStore.getState().incWSMessages()
          this._dispatch(payload)
        } catch (e) {
          console.warn('[SentinelTwin WS] Parse error', e)
        }
      }

      this.ws.onclose = () => {
        useSentinelStore.getState().setWSConnected(false)
        if (!this._destroyed) this._scheduleReconnect()
      }

      this.ws.onerror = (err) => {
        console.warn('[SentinelTwin WS] Error', err)
        this.ws?.close()
      }
    } catch (e) {
      console.error('[SentinelTwin WS] Failed to connect:', e)
      if (!this._destroyed) this._scheduleReconnect()
    }
  }

  private _dispatch(payload: any) {
    const store = useSentinelStore.getState()
    const { channel, data } = payload

    switch (channel) {
      case 'telemetry':
        if (data.type === 'sensor_stats') {
          store.setScanMetrics(
            data.scan_rate || 0,
            data.total_validations || 0,
            data.cycle_duration_ms || 0
          )
          store.updateSensorStats({
            healthy_count: data.healthy_count,
            anomaly_count: data.anomaly_count,
          })
        }
        break

      case 'ai':
        if (data.type === 'ai_status') {
          store.updateAI({
            reconstruction_error: data.reconstruction_error,
            severity: data.severity,
            confidence: data.confidence,
            active_events: data.active_events,
            anomaly_event_count: data.anomaly_event_count,
            inference_count: data.inference_count,
          })
          store.pushError(data.reconstruction_error)
        }
        break

      case 'twin':
        if (data.type === 'twin_state') {
          store.updateTwin(data)
        }
        break

      case 'ecam':
        if (data.type === 'ecam_update') {
          store.setECAM(data.active || [])
        }
        break

      case 'hashchain':
        if (data.type === 'hash_block') {
          store.pushHashBlock(data.block)
          store.setChainValid(data.chain_valid)
        }
        break

      case 'dispatch':
        if (data.type === 'dispatch_status') {
          store.updateDispatch({
            dispatch_ready: data.dispatch_ready,
            determination: data.dispatch_ready ? 'GO' : 'NO-GO',
          })
        }
        break

      case 'arinc':
        if (data.type === 'arinc_frame') {
          store.setArincFrame(data.frame || [], data.bus_stats || {})
        }
        break

      case 'afdx':
        if (data.type === 'afdx_status') {
          store.setAFDXStatus(data.virtual_links || [], data.network_stats || {})
        }
        break

      case 'cyber':
        if (data.type === 'cyber_status') {
          store.setCyberStatus(
            data.threat_level || 'LOW',
            data.statistics || {},
          )
        }
        break
    }
  }

  send(data: object) {
    if (this.ws?.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify(data))
    }
  }

  private _scheduleReconnect() {
    useSentinelStore.getState().setWSReconnecting(true)
    this.reconnectTimer = setTimeout(() => {
      this.reconnectDelay = Math.min(this.reconnectDelay * 1.5, this.maxDelay)
      this.connect()
    }, this.reconnectDelay)
  }

  destroy() {
    this._destroyed = true
    if (this.reconnectTimer) clearTimeout(this.reconnectTimer)
    this.ws?.close()
  }
}

// ─────────────────────────────────────────────────────────────
// API CLIENT
// ─────────────────────────────────────────────────────────────

const BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000/api/v1'

export async function apiRequest<T>(
  path: string,
  options: RequestInit = {}
): Promise<T> {
  const token = useSentinelStore.getState().accessToken
  const res = await fetch(`${BASE_URL}${path}`, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...options.headers,
    },
  })
  if (!res.ok) {
    const error = await res.json().catch(() => ({ detail: res.statusText }))
    throw new Error(error.detail || `HTTP ${res.status}`)
  }
  return res.json()
}

export const api = {
  auth: {
    login: (username: string, password: string, role: string) =>
      apiRequest<{ access_token: string; refresh_token: string; user: User }>('/auth/login', {
        method: 'POST',
        body: JSON.stringify({ username, password, role }),
      }),
    me: () => apiRequest<User>('/auth/me'),
    logout: (refresh_token: string) =>
      apiRequest('/auth/logout', { method: 'POST', body: JSON.stringify({ refresh_token }) }),
  },
  sensors: {
    summary: () => apiRequest('/sensors/summary'),
    byATA: (ata: number, limit = 100, offset = 0) =>
      apiRequest(`/sensors/ata/${ata}?limit=${limit}&offset=${offset}`),
    anomalous: (threshold = 0.5) => apiRequest(`/sensors/anomalous?threshold=${threshold}`),
  },
  ecam: {
    active: () => apiRequest('/ecam/active'),
    history: (limit = 100) => apiRequest(`/ecam/history?limit=${limit}`),
  },
  dispatch: {
    status: () => apiRequest<DispatchStatus>('/dispatch/status'),
    authorize: (body: object) =>
      apiRequest('/dispatch/authorize', { method: 'POST', body: JSON.stringify(body) }),
  },
  twin: {
    state: () => apiRequest('/twin/state'),
    setPhase: (phase: string) =>
      apiRequest('/twin/phase', { method: 'POST', body: JSON.stringify({ phase }) }),
  },
  ai: {
    status: () => apiRequest('/ai/status'),
    events: (limit = 50) => apiRequest(`/ai/events?limit=${limit}`),
    setThreshold: (threshold: number) =>
      apiRequest(`/ai/threshold?threshold=${threshold}`, { method: 'POST' }),
  },
  hashchain: {
    latest: (n = 50) => apiRequest(`/hashchain/latest?n=${n}`),
    verify: () => apiRequest('/hashchain/verify'),
  },
  fleet: {
    all: () => apiRequest('/fleet/'),
    aircraft: (msn: string) => apiRequest(`/fleet/${msn}`),
  },
  system: {
    health: () => apiRequest('/system/health'),
    metrics: () => apiRequest('/system/metrics'),
  },
}
