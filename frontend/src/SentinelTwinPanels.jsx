import React, { useState, useEffect, useRef, useMemo, useCallback } from "react";
import { useSentinelStore } from "./stores/sentinel.store";

// ── Typography injection ──────────────────────────────────────
const FONT_LINK = document.createElement("link");
FONT_LINK.rel = "stylesheet";
FONT_LINK.href = "https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@300;400;500;600;700&display=swap";
document.head.appendChild(FONT_LINK);

const C = {
  bg0:      "#030508",
  bg1:      "#060d1a",
  bg2:      "#0a1628",
  border:   "rgba(0,180,255,0.12)",
  borderHi: "rgba(0,180,255,0.35)",
  blue:     "#00b4ff",
  green:    "#00e676",
  amber:    "#ffab40",
  red:      "#ff1744",
  orange:   "#ff5722",
  purple:   "#e040fb",
  teal:     "#26c6da",
  dim:      "#546e7a",
  mid:      "#90a4ae",
  text:     "#c8d6e5",
  white:    "#ffffff",
};

// ═════════════════════════════════════════════════════════════
// FLEET DATA
// ═════════════════════════════════════════════════════════════
const FLEET_FALLBACK = [
  { msn:"8234", reg:"F-WXWB",  type:"A320neo", airline:"Air France",   cycles:4821,  hours:12450, status:"ACTIVE",      loc:"CDG", health:98.4 },
  { msn:"9012", reg:"D-AVVB",  type:"A321",    airline:"Lufthansa",    cycles:3201,  hours:8920,  status:"ACTIVE",      loc:"FRA", health:97.1 },
  { msn:"7891", reg:"G-EZWX",  type:"A320",    airline:"easyJet",      cycles:6432,  hours:15230, status:"MAINTENANCE", loc:"LTN", health:82.3 },
  { msn:"6543", reg:"EC-MXY",  type:"A350",    airline:"Iberia",       cycles:1823,  hours:5840,  status:"ACTIVE",      loc:"MAD", health:99.1 },
  { msn:"5210", reg:"OE-IVM",  type:"A320neo", airline:"Austrian",     cycles:2904,  hours:7612,  status:"ACTIVE",      loc:"VIE", health:96.8 },
  { msn:"4480", reg:"HB-JCA",  type:"A330",    airline:"Swiss",        cycles:5102,  hours:28430, status:"ACTIVE",      loc:"ZRH", health:94.2 },
  { msn:"3310", reg:"EI-DVM",  type:"A319",    airline:"Ryanair",      cycles:8120,  hours:18900, status:"ACTIVE",      loc:"DUB", health:95.7 },
  { msn:"2200", reg:"F-GZNN",  type:"A350",    airline:"Air France",   cycles:2341,  hours:9120,  status:"ACTIVE",      loc:"ORY", health:99.5 },
];

// ═════════════════════════════════════════════════════════════
// AFDX VIRTUAL LINKS
// ═════════════════════════════════════════════════════════════
const AFDX_VLS_FALLBACK = [
  { vl:"VL-0001", src:"ADIRU-1", dst:"FWC-1",   bw_kbps:1000,  frame_hz:100, jitter_us:8,   status:"NOMINAL" },
  { vl:"VL-0002", src:"ADIRU-2", dst:"FWC-2",   bw_kbps:1000,  frame_hz:100, jitter_us:9,   status:"NOMINAL" },
  { vl:"VL-0003", src:"FADEC-1", dst:"EEC-1",   bw_kbps:4000,  frame_hz:50,  jitter_us:12,  status:"NOMINAL" },
  { vl:"VL-0004", src:"FADEC-2", dst:"EEC-2",   bw_kbps:4000,  frame_hz:50,  jitter_us:11,  status:"NOMINAL" },
  { vl:"VL-0005", src:"LGCIU-1", dst:"BSCU",    bw_kbps:500,   frame_hz:25,  jitter_us:14,  status:"NOMINAL" },
  { vl:"VL-0006", src:"SFCC-1",  dst:"ELAC-1",  bw_kbps:2000,  frame_hz:100, jitter_us:7,   status:"NOMINAL" },
  { vl:"VL-0007", src:"SFCC-2",  dst:"ELAC-2",  bw_kbps:2000,  frame_hz:100, jitter_us:8,   status:"NOMINAL" },
  { vl:"VL-0008", src:"FCU",     dst:"AP-1",    bw_kbps:1500,  frame_hz:50,  jitter_us:10,  status:"NOMINAL" },
  { vl:"VL-0009", src:"GPS-1",   dst:"MCDU",    bw_kbps:250,   frame_hz:10,  jitter_us:22,  status:"NOMINAL" },
  { vl:"VL-0010", src:"ILS",     dst:"FWC-1",   bw_kbps:500,   frame_hz:25,  jitter_us:13,  status:"NOMINAL" },
  { vl:"VL-0011", src:"DME",     dst:"MCDU",    bw_kbps:125,   frame_hz:10,  jitter_us:18,  status:"NOMINAL" },
  { vl:"VL-0012", src:"WXR",     dst:"ND-CAPT", bw_kbps:8000,  frame_hz:25,  jitter_us:30,  status:"NOMINAL" },
  { vl:"VL-0013", src:"TCAS",    dst:"FWC-2",   bw_kbps:500,   frame_hz:10,  jitter_us:16,  status:"DEGRADED"},
  { vl:"VL-0014", src:"ROPS",    dst:"BSCU",    bw_kbps:250,   frame_hz:25,  jitter_us:11,  status:"NOMINAL" },
  { vl:"VL-0015", src:"TAWS",    dst:"FWC-1",   bw_kbps:500,   frame_hz:25,  jitter_us:9,   status:"NOMINAL" },
  { vl:"VL-0016", src:"CMC",     dst:"MCDU",    bw_kbps:250,   frame_hz:10,  jitter_us:20,  status:"NOMINAL" },
];

// ═════════════════════════════════════════════════════════════
// MAINTENANCE ACTIONS
// ═════════════════════════════════════════════════════════════
const MAINTENANCE_FALLBACK = [
  { id:"MA-001", ata:29, priority:"HIGH",   mel:"MEL 29-001", description:"HYD GREEN pump 1 pressure transducer calibration required", assigned:"J. Martin", due:"2026-05-14", status:"OPEN" },
  { id:"MA-002", ata:34, priority:"MEDIUM", mel:"MEL 34-002", description:"IRS-1 heading drift — gyro bias recalibration", assigned:"P. Dubois", due:"2026-05-15", status:"IN_PROGRESS" },
  { id:"MA-003", ata:71, priority:"HIGH",   mel:"MEL 79-001", description:"ENG1 oil pressure sensor replacement (PN: C29124-002)", assigned:"R. Schmidt", due:"2026-05-14", status:"OPEN" },
  { id:"MA-004", ata:32, priority:"LOW",    mel:"MEL 32-001", description:"LGCIU-2 bite test — schedule functional check", assigned:"A. Patel", due:"2026-05-18", status:"OPEN" },
  { id:"MA-005", ata:27, priority:"HIGH",   mel:"MEL 27-002", description:"ELAC-1 RAM Air temperature probe wiring inspection", assigned:"J. Martin", due:"2026-05-13", status:"OVERDUE" },
  { id:"MA-006", ata:24, priority:"LOW",    mel:"MEL 24-001", description:"GEN-2 load monitoring relay — schedule replacement next C-check", assigned:"P. Dubois", due:"2026-06-01", status:"DEFERRED" },
  { id:"MA-007", ata:49, priority:"MEDIUM", mel:"MEL 36-001", description:"APU bleed valve actuator — inspect for carbon build-up", assigned:"R. Schmidt", due:"2026-05-20", status:"OPEN" },
  { id:"MA-008", ata:21, priority:"LOW",    mel:"MEL 21-001", description:"PACK-1 flow control valve — schedule bench test", assigned:"A. Patel", due:"2026-05-25", status:"OPEN" },
];

// ═════════════════════════════════════════════════════════════
// SHARED PRIMITIVES
// ═════════════════════════════════════════════════════════════

const mono = { fontFamily:"'IBM Plex Mono',monospace" };
const box = (extra={}) => ({
  background:"rgba(6,13,26,0.9)",
  border:`1px solid ${C.border}`,
  padding:"10px 12px",
  ...extra,
});

const INPUT_STYLE = {
  background:"#0a1628", border:"1px solid #1e3a5f", color:"#c8d6e5",
  padding:"5px 8px", fontSize:10, letterSpacing:1, width:"100%",
  fontFamily:"IBM Plex Mono, monospace", boxSizing:"border-box",
};

function PanelBox({ title, children, style={} }) {
  return (
    <div style={{ ...box(), ...style }}>
      <div style={{ fontSize:8, color:C.blue, letterSpacing:3, marginBottom:8, paddingBottom:6, borderBottom:`1px solid ${C.border}` }}>{title}</div>
      {children}
    </div>
  );
}

function Metric({ label, value, color=C.text, size=18 }) {
  return (
    <div style={{ padding:"10px 14px", background:"rgba(6,13,26,0.9)", border:`1px solid ${C.border}`, borderTop:`2px solid ${color}` }}>
      <div style={{ fontSize:7, color:C.dim, letterSpacing:2, marginBottom:6 }}>{label}</div>
      <div style={{ fontSize:size, fontWeight:700, color, fontVariantNumeric:"tabular-nums" }}>{value}</div>
    </div>
  );
}

function Row({ label, value, color=C.text }) {
  return (
    <div style={{ display:"flex", justifyContent:"space-between", marginBottom:6, fontSize:9 }}>
      <span style={{ color:C.dim, letterSpacing:1 }}>{label}</span>
      <span style={{ color, fontVariantNumeric:"tabular-nums" }}>{value}</span>
    </div>
  );
}

function StatusPill({ value, ok }) {
  const c = ok ? C.green : C.red;
  return (
    <span style={{ padding:"1px 8px", background:`${c}14`, border:`1px solid ${c}44`, color:c, fontSize:8, letterSpacing:2 }}>{value}</span>
  );
}

function SectionHeader({ title }) {
  return (
    <div style={{ fontSize:9, color:C.blue, letterSpacing:3, marginBottom:10, paddingBottom:8, borderBottom:`1px solid ${C.border}` }}>{title}</div>
  );
}

function useUTC() {
  const [utc, setUTC] = useState("");
  useEffect(() => {
    const iv = setInterval(() => setUTC(new Date().toISOString().slice(0,19)+" UTC"), 1000);
    return () => clearInterval(iv);
  }, []);
  return utc;
}

// ═════════════════════════════════════════════════════════════
// AIRCRAFT SVG SILHOUETTES — TOP View
// ═════════════════════════════════════════════════════════════
function AircraftSVG({ type = "A320neo", width = 80, height = 120, healthColor = "#00e676", animate = true }) {
  const [tick, setTick] = React.useState(0);
  React.useEffect(() => {
    if (!animate) return;
    const iv = setInterval(() => setTick(t => t + 1), 60);
    return () => clearInterval(iv);
  }, [animate]);
  const pulse = 0.5 + Math.sin(tick * 0.12) * 0.5;

  const scales = {
    "A319":    { fuse:0.82, wing:0.82, stab:0.80, eng:0.82 },
    "A320":    { fuse:0.88, wing:0.90, stab:0.86, eng:0.88 },
    "A320neo": { fuse:0.90, wing:0.94, stab:0.88, eng:0.90 },
    "A321":    { fuse:1.00, wing:0.97, stab:0.94, eng:0.94 },
    "A330":    { fuse:1.00, wing:1.18, stab:1.02, eng:1.08 },
    "A350":    { fuse:1.00, wing:1.12, stab:0.98, eng:1.06 },
    "A220":    { fuse:0.76, wing:0.80, stab:0.76, eng:0.78 },
  };
  const s = scales[type] || scales["A320neo"];
  const isWidebody = type === "A330" || type === "A350";
  const cx = width / 2, cy = height / 2;
  const fuseH = 50 * s.fuse, fuseW = 4.5;
  const wingW = 40 * s.wing, wingSwpFwd = 10 * s.wing, wingSwpAft = 20 * s.wing;
  const stabW = 17 * s.stab;
  const engX = 25 * s.eng, engY = -5 * s.fuse, engR = 4.2;
  const uid = type.replace(/\s/g,"");

  return (
    <svg width={width} height={height} viewBox={`0 0 ${width} ${height}`} style={{ overflow:"visible" }}>
      <defs>
        <filter id={`g-${uid}`} x="-60%" y="-60%" width="220%" height="220%">
          <feGaussianBlur stdDeviation="2" result="b"/>
          <feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge>
        </filter>
        <radialGradient id={`eg-${uid}`} cx="50%" cy="50%" r="50%">
          <stop offset="0%" stopColor={`rgba(255,140,0,${0.5+pulse*0.45})`}/>
          <stop offset="100%" stopColor="rgba(255,50,0,0)"/>
        </radialGradient>
      </defs>

      {/* Engine exhaust glow rings */}
      {(isWidebody ? [-engX*1.5,-engX*0.5,engX*0.5,engX*1.5] : [-engX,engX]).map((ex,i) => (
        <circle key={i} cx={cx+ex} cy={cy+engY+7} r={engR*(2.2+pulse*0.8)}
          fill={`url(#eg-${uid})`} opacity={0.55+pulse*0.3} />
      ))}

      {/* Main wings */}
      <polygon
        points={`
          ${cx},${cy-wingSwpFwd}
          ${cx-wingW},${cy+wingSwpAft}
          ${cx-wingW+7},${cy+wingSwpAft+6}
          ${cx-3},${cy-wingSwpFwd+15}
          ${cx+3},${cy-wingSwpFwd+15}
          ${cx+wingW-7},${cy+wingSwpAft+6}
          ${cx+wingW},${cy+wingSwpAft}
        `}
        fill={`${healthColor}12`} stroke={healthColor} strokeWidth="0.85"
        filter={`url(#g-${uid})`}
      />

      {/* Fuselage */}
      <rect x={cx-fuseW} y={cy-fuseH} width={fuseW*2} height={fuseH*2}
        rx={fuseW} fill="#040b17" stroke={healthColor} strokeWidth="0.9" />

      {/* Nose */}
      <ellipse cx={cx} cy={cy-fuseH+2} rx={fuseW*0.65} ry={3.5}
        fill={healthColor} opacity={0.55} />

      {/* Horizontal stabiliser */}
      <polygon
        points={`
          ${cx},${cy+fuseH-9}
          ${cx-stabW},${cy+fuseH+4}
          ${cx-stabW+6},${cy+fuseH+9}
          ${cx},${cy+fuseH-2}
          ${cx+stabW-6},${cy+fuseH+9}
          ${cx+stabW},${cy+fuseH+4}
        `}
        fill={`${healthColor}15`} stroke={healthColor} strokeWidth="0.7"
      />

      {/* Dorsal fin */}
      <rect x={cx-1} y={cy+fuseH-22} width={2} height={14}
        fill={healthColor} opacity={0.65} rx={0.8} />

      {/* Engines */}
      {(isWidebody ? [-engX*1.5,-engX*0.5,engX*0.5,engX*1.5] : [-engX,engX]).map((ex,i) => (
        <g key={i}>
          <ellipse cx={cx+ex} cy={cy+engY} rx={engR} ry={engR*2.3}
            fill="#020810" stroke={healthColor} strokeWidth="0.7" />
          <ellipse cx={cx+ex} cy={cy+engY-engR*0.7} rx={engR*0.55} ry={engR*0.45}
            fill={`${healthColor}35`} />
        </g>
      ))}

      {/* Winglets (neo / A321) */}
      {(type==="A320neo"||type==="A321") && (<>
        <line x1={cx-wingW} y1={cy+wingSwpAft} x2={cx-wingW-3.5} y2={cy+wingSwpAft-7}
          stroke={healthColor} strokeWidth="1.3"/>
        <line x1={cx+wingW} y1={cy+wingSwpAft} x2={cx+wingW+3.5} y2={cy+wingSwpAft-7}
          stroke={healthColor} strokeWidth="1.3"/>
      </>)}

      {/* Sharklets A350 */}
      {type==="A350" && (<>
        <line x1={cx-wingW} y1={cy+wingSwpAft} x2={cx-wingW-5} y2={cy+wingSwpAft-10}
          stroke={healthColor} strokeWidth="1.5"/>
        <line x1={cx+wingW} y1={cy+wingSwpAft} x2={cx+wingW+5} y2={cy+wingSwpAft-10}
          stroke={healthColor} strokeWidth="1.5"/>
      </>)}

      {/* Status beacon — pulsing dot on nose */}
      <circle cx={cx} cy={cy-fuseH-4} r={2.5+pulse*1.2}
        fill="none" stroke={healthColor} strokeWidth="0.8" opacity={0.4+pulse*0.5} />
      <circle cx={cx} cy={cy-fuseH-4} r={1.8} fill={healthColor} opacity={0.9} />

      {/* Type label */}
      <text x={cx} y={cy+fuseH+20} textAnchor="middle" fontSize="5.5"
        fill={healthColor} opacity={0.8}
        fontFamily="IBM Plex Mono,monospace" letterSpacing="1.5">
        {type}
      </text>
    </svg>
  );
}

// ═════════════════════════════════════════════════════════════
// FLEET STATUS PANEL
// ═════════════════════════════════════════════════════════════
export function FleetPanel() {
  const [selected, setSelected] = useState(null);
  const [view, setView] = useState("CARDS");

  const [fleet, setFleet] = React.useState(null);
  React.useEffect(() => {
    fetch("/api/v1/fleet/status", {
      headers: { Authorization: `Bearer ${localStorage.getItem("st_token") || ""}` }
    })
      .then(r => r.ok ? r.json() : null)
      .then(d => { if (d?.aircraft) setFleet(d.aircraft); })
      .catch(() => {});
  }, []);

  const displayFleet = fleet || FLEET_FALLBACK;
  const active = displayFleet.filter(a => a.status === "ACTIVE").length;

  const healthColor = h => h > 95 ? C.green : h > 85 ? C.amber : C.red;
  const avgHealth = (displayFleet.reduce((a,b)=>a+b.health,0)/displayFleet.length).toFixed(1);

  return (
    <div style={{ flex:1, overflow:"auto", padding:12, ...mono }}>
      {/* Header KPIs */}
      <div style={{ display:"flex", alignItems:"center", gap:12, marginBottom:12 }}>
        <div style={{ fontSize:9, color:C.blue, letterSpacing:3, flex:1 }}>
          FLEET STATUS BOARD — AIRBUS AIRCRAFT REGISTRY
        </div>
        {/* View toggle */}
        {["CARDS","TABLE"].map(v => (
          <button key={v} onClick={() => setView(v)} style={{
            background: view===v ? `${C.blue}22` : "transparent",
            border: `1px solid ${view===v ? C.blue : C.border}`,
            color: view===v ? C.blue : C.dim,
            padding:"3px 10px", fontSize:8, letterSpacing:2, cursor:"pointer",
            fontFamily:"IBM Plex Mono,monospace",
          }}>{v}</button>
        ))}
      </div>

      <div style={{ display:"grid", gridTemplateColumns:"repeat(4,1fr)", gap:8, marginBottom:12 }}>
        <Metric label="TOTAL AIRCRAFT" value={displayFleet.length} color={C.blue} />
        <Metric label="ACTIVE" value={active} color={C.green} />
        <Metric label="MAINTENANCE" value={displayFleet.length-active} color={C.amber} />
        <Metric label="FLEET HEALTH" value={`${avgHealth}%`} color={parseFloat(avgHealth)>95?C.green:C.amber} />
      </div>

      <div style={{ display:"grid", gridTemplateColumns:"1fr 320px", gap:10 }}>

        {/* LEFT: Card grid or table */}
        <div>
          {view === "CARDS" ? (
            <div style={{ display:"grid", gridTemplateColumns:"repeat(auto-fill,minmax(180px,1fr))", gap:10 }}>
              {displayFleet.map(a => {
                const hc = healthColor(a.health);
                const isSelected = selected?.msn === a.msn;
                return (
                  <div key={a.msn}
                    onClick={() => setSelected(isSelected ? null : a)}
                    style={{
                      background: isSelected ? `rgba(0,180,255,0.07)` : "rgba(4,8,20,0.85)",
                      border: `1px solid ${isSelected ? C.blue : hc+"33"}`,
                      padding:"14px 12px 10px",
                      cursor:"pointer",
                      transition:"all 0.2s",
                      position:"relative",
                      display:"flex", flexDirection:"column", alignItems:"center",
                      boxShadow: isSelected ? `0 0 16px ${C.blue}22` : `0 0 8px ${hc}11`,
                    }}
                  >
                    {/* Status indicator top-right */}
                    <div style={{
                      position:"absolute", top:8, right:10,
                      fontSize:7, letterSpacing:2,
                      color: a.status==="ACTIVE"?C.green:C.amber,
                      background: `${a.status==="ACTIVE"?C.green:C.amber}15`,
                      padding:"2px 6px", border:`1px solid ${a.status==="ACTIVE"?C.green:C.amber}44`,
                    }}>{a.status==="ACTIVE"?"ACTIVE":"MX"}</div>

                    {/* Aircraft SVG Silhouette */}
                    <div style={{ marginBottom:8, position:"relative" }}>
                      <AircraftSVG type={a.type} width={72} height={108} healthColor={hc} animate={true} />
                    </div>

                    {/* Registration + airline */}
                    <div style={{ fontSize:11, color:C.white, letterSpacing:2, fontWeight:700, marginBottom:2 }}>
                      {a.reg}
                    </div>
                    <div style={{ fontSize:8, color:C.dim, letterSpacing:1, marginBottom:8 }}>
                      {a.airline}
                    </div>

                    {/* Health bar */}
                    <div style={{ width:"100%", marginBottom:4 }}>
                      <div style={{ display:"flex", justifyContent:"space-between", fontSize:7, color:C.dim, marginBottom:3 }}>
                        <span>HEALTH</span>
                        <span style={{ color:hc }}>{a.health}%</span>
                      </div>
                      <div style={{ height:3, background:"rgba(255,255,255,0.06)", borderRadius:2 }}>
                        <div style={{ height:"100%", width:`${a.health}%`, background:hc,
                          borderRadius:2, transition:"width 0.4s",
                          boxShadow:`0 0 6px ${hc}` }} />
                      </div>
                    </div>

                    {/* Footer stats */}
                    <div style={{ display:"grid", gridTemplateColumns:"1fr 1fr", gap:4, width:"100%", marginTop:4 }}>
                      {[["LOC",a.loc],["HRS",`${(a.hours/1000).toFixed(0)}K`],["CYCLES",a.cycles.toLocaleString()],["MSN",a.msn]].map(([l,v])=>(
                        <div key={l} style={{ fontSize:7, color:C.dim, letterSpacing:1 }}>
                          <span style={{ color:C.dim }}>{l} </span>
                          <span style={{ color:C.text }}>{v}</span>
                        </div>
                      ))}
                    </div>
                  </div>
                );
              })}
            </div>
          ) : (
            /* TABLE VIEW */
            <PanelBox title="AIRCRAFT REGISTRY">
              <div style={{ display:"grid", gridTemplateColumns:"60px 80px 70px 1fr 90px 60px 50px 70px 60px",
                fontSize:8, color:C.dim, letterSpacing:1, marginBottom:6, paddingBottom:4,
                borderBottom:`1px solid ${C.border}` }}>
                {["MSN","REG","TYPE","AIRLINE","STATUS","LOC","HRS","HEALTH","CYCLES"].map(h=>(
                  <div key={h}>{h}</div>
                ))}
              </div>
              {displayFleet.map(a => {
                const hc = healthColor(a.health);
                return (
                  <div key={a.msn} onClick={() => setSelected(selected?.msn===a.msn?null:a)}
                    style={{ display:"grid", gridTemplateColumns:"60px 80px 70px 1fr 90px 60px 50px 70px 60px",
                      fontSize:9, marginBottom:4, padding:"5px 4px",
                      borderBottom:`1px solid rgba(255,255,255,0.03)`,
                      background:selected?.msn===a.msn?"rgba(0,180,255,0.06)":"transparent",
                      cursor:"pointer", transition:"background 0.2s" }}>
                    <div style={{ color:C.amber }}>{a.msn}</div>
                    <div style={{ color:C.text }}>{a.reg}</div>
                    <div style={{ color:C.blue }}>{a.type}</div>
                    <div style={{ color:C.mid }}>{a.airline}</div>
                    <div><StatusPill value={a.status} ok={a.status==="ACTIVE"} /></div>
                    <div style={{ color:C.dim }}>{a.loc}</div>
                    <div style={{ color:C.text, fontVariantNumeric:"tabular-nums" }}>{(a.hours/1000).toFixed(0)}K</div>
                    <div style={{ color:hc }}>
                      <div style={{ display:"flex", alignItems:"center", gap:4 }}>
                        <div style={{ flex:1, height:3, background:"rgba(255,255,255,0.08)" }}>
                          <div style={{ height:"100%", width:`${a.health}%`, background:hc }} />
                        </div>
                        <span style={{ fontSize:8 }}>{a.health}%</span>
                      </div>
                    </div>
                    <div style={{ color:C.dim, fontVariantNumeric:"tabular-nums" }}>{a.cycles.toLocaleString()}</div>
                  </div>
                );
              })}
            </PanelBox>
          )}
        </div>

        {/* RIGHT: Aircraft detail panel */}
        <div>
          {selected ? (
            <PanelBox title={`AIRCRAFT — ${selected.reg}`} style={{ position:"sticky", top:0 }}>
              {/* Large aircraft SVG */}
              <div style={{ display:"flex", justifyContent:"center", padding:"16px 0 8px",
                background:"rgba(0,0,0,0.25)", margin:"0 -12px 12px", borderBottom:`1px solid ${C.border}` }}>
                <AircraftSVG type={selected.type} width={100} height={150}
                  healthColor={healthColor(selected.health)} animate={true} />
              </div>
              {[
                ["MSN",          selected.msn],
                ["REGISTRATION", selected.reg],
                ["TYPE",         selected.type],
                ["AIRLINE",      selected.airline],
                ["LOCATION",     selected.loc],
                ["STATUS",       selected.status],
                ["FLIGHT HOURS", selected.hours.toLocaleString()],
                ["CYCLES",       selected.cycles.toLocaleString()],
                ["HEALTH",       `${selected.health}%`],
              ].map(([k,v]) => <Row key={k} label={k} value={v} color={C.text} />)}

              <div style={{ marginTop:12, padding:"10px 12px",
                background:selected.status==="ACTIVE"?"rgba(0,230,118,0.06)":"rgba(255,171,64,0.06)",
                border:`1px solid ${selected.status==="ACTIVE"?C.green:C.amber}33` }}>
                <div style={{ fontSize:10, color:selected.status==="ACTIVE"?C.green:C.amber,
                  letterSpacing:2, fontWeight:700 }}>
                  {selected.status==="ACTIVE" ? "✓ AIRWORTHY" : "⚠ IN MAINTENANCE"}
                </div>
                <div style={{ fontSize:8, color:C.dim, marginTop:3 }}>
                  {selected.status==="ACTIVE" ? "All systems serviceable. Cleared for dispatch." : "Maintenance action in progress — Hold for release."}
                </div>
              </div>

              <button onClick={() => setSelected(null)} style={{
                width:"100%", marginTop:10, padding:"6px",
                background:"transparent", border:`1px solid ${C.border}`,
                color:C.dim, fontSize:8, letterSpacing:2, cursor:"pointer",
                fontFamily:"IBM Plex Mono,monospace",
              }}>CLEAR SELECTION</button>
            </PanelBox>
          ) : (
            <PanelBox title="FLEET COMPOSITION">
              {/* Fleet type breakdown with mini silhouettes */}
              {["A219","A220","A319","A320","A320neo","A321","A330","A350"].map(type => {
                const count = displayFleet.filter(a=>a.type===type).length;
                if (!count) return null;
                const avgH = displayFleet.filter(a=>a.type===type).reduce((s,a)=>s+a.health,0)/count;
                return (
                  <div key={type} style={{ display:"flex", alignItems:"center", gap:10,
                    marginBottom:14, padding:"8px 8px 4px",
                    background:"rgba(0,0,0,0.2)", border:`1px solid ${C.border}` }}>
                    <div style={{ flexShrink:0 }}>
                      <AircraftSVG type={type} width={38} height={56}
                        healthColor={healthColor(avgH)} animate={false} />
                    </div>
                    <div style={{ flex:1 }}>
                      <div style={{ fontSize:9, color:C.blue, letterSpacing:2, marginBottom:3 }}>{type}</div>
                      <div style={{ fontSize:8, color:C.dim }}>{count} aircraft</div>
                      <div style={{ height:2, background:"rgba(255,255,255,0.05)", marginTop:5 }}>
                        <div style={{ height:"100%", width:`${avgH}%`,
                          background:healthColor(avgH), transition:"width 0.4s" }} />
                      </div>
                      <div style={{ fontSize:7, color:C.dim, marginTop:2 }}>AVG HEALTH {(avgH||0).toFixed(1)}%</div>
                    </div>
                  </div>
                );
              })}
              <div style={{ fontSize:8, color:C.dim, textAlign:"center", marginTop:8, letterSpacing:1 }}>
                Click any aircraft card to inspect
              </div>
            </PanelBox>
          )}
        </div>
      </div>
    </div>
  );
}


// ═════════════════════════════════════════════════════════════
// AFDX MONITOR PANEL
// ═════════════════════════════════════════════════════════════
export function AFDXPanel() {
  const storeAfdxVLs  = useSentinelStore(s => s.afdxVLs);
  const storeAfdxStats = useSentinelStore(s => s.afdxStats);
  const wsStatus  = useSentinelStore(s => s.wsStatus);

  // Fallback to hardcoded data when not connected
  const vls = (wsStatus === "CONNECTED" && storeAfdxVLs.length > 0) ? storeAfdxVLs : AFDX_VLS_FALLBACK;

  // Local jitter simulation only when offline
  const [localVLs, setLocalVLs] = useState(AFDX_VLS_FALLBACK);

  useEffect(() => {
    if (wsStatus === "CONNECTED") return;
    const iv = setInterval(() => {
      setLocalVLs(prev => prev.map(vl => ({
        ...vl,
        jitter_us: Math.max(1, vl.jitter_us + Math.round((Math.random()-0.5)*3)),
        status: Math.random() < 0.005 ? "DEGRADED" : Math.random() < 0.01 ? "TIMING_VIOLATION" : "NOMINAL",
        bw_util: Math.round(50 + Math.random()*40),
      })));
    }, 600);
    return () => clearInterval(iv);
  }, [wsStatus]);

  const displayVLs = wsStatus === "CONNECTED" && storeAfdxVLs.length > 0 ? storeAfdxVLs : localVLs;

  const nominal = displayVLs.filter(v => v.status==="NOMINAL").length;
  const totalBW = displayVLs.reduce((a,v) => a + (v.bw_kbps || 0), 0);

  return (
    <div style={{ flex:1, overflow:"auto", padding:12, ...mono }}>
      <SectionHeader title="AFDX NETWORK MONITOR — ARINC 664 VIRTUAL LINK ANALYSIS — 100 Mbps" />
      <div style={{ display:"grid", gridTemplateColumns:"repeat(5,1fr)", gap:8, marginBottom:12 }}>
        <Metric label="TOTAL VIRTUAL LINKS" value={displayVLs.length} color={C.blue} />
        <Metric label="NOMINAL" value={nominal} color={C.green} />
        <Metric label="DEGRADED" value={displayVLs.length-nominal} color={displayVLs.length-nominal>0?C.amber:C.green} />
        <Metric label="TOTAL BW ALLOC" value={`${totalBW/1000} Mbps`} color={C.blue} />
        <Metric label="NETWORK STATUS" value={nominal===displayVLs.length?"NORMAL":"DEGRADED"} color={nominal===displayVLs.length?C.green:C.amber} />
      </div>

      <PanelBox title="VIRTUAL LINK TABLE — END-TO-END TIMING VALIDATION">
        <div style={{ display:"grid", gridTemplateColumns:"80px 100px 100px 80px 70px 70px 80px 80px", fontSize:8, color:C.dim, letterSpacing:1, marginBottom:6, paddingBottom:4, borderBottom:`1px solid ${C.border}` }}>
          <div>VL-ID</div><div>SOURCE</div><div>DESTINATION</div><div>BW (kbps)</div><div>RATE (Hz)</div><div>JITTER (µs)</div><div>BAG</div><div>STATUS</div>
        </div>
        {displayVLs.map(vl => {
          const jitterOk = (vl.jitter_us || 0) <= 25;
          const statusColor = vl.status==="NOMINAL" ? C.green : vl.status==="DEGRADED" ? C.amber : C.red;
          return (
            <div key={vl.vl||vl.vl_id} style={{ display:"grid", gridTemplateColumns:"80px 100px 100px 80px 70px 70px 80px 80px", fontSize:9, marginBottom:3, padding:"3px 0", borderBottom:`1px solid rgba(255,255,255,0.03)` }}>
              <div style={{ color:C.amber }}>{vl.vl||vl.vl_id}</div>
              <div style={{ color:C.text }}>{vl.src||vl.publisher||""}</div>
              <div style={{ color:C.mid }}>{vl.dst||(vl.subscribers?.[0])||""}</div>
              <div style={{ color:C.blue, fontVariantNumeric:"tabular-nums" }}>{(vl.bw_kbps||0).toLocaleString()}</div>
              <div style={{ color:C.text, fontVariantNumeric:"tabular-nums" }}>{vl.frame_hz||"--"}</div>
              <div style={{ color:jitterOk?C.green:C.amber, fontVariantNumeric:"tabular-nums" }}>{vl.jitter_us||vl.avg_jitter_us||0}</div>
              <div style={{ color:C.dim, fontVariantNumeric:"tabular-nums" }}>{vl.frame_hz?Math.round(1000/vl.frame_hz)+"ms":vl.nominal_bag_ms?vl.nominal_bag_ms+"ms":"--"}</div>
              <div style={{ color:statusColor, fontSize:8, letterSpacing:1 }}>{(vl.status||"NOMINAL").slice(0,8)}</div>
            </div>
          );
        })}
      </PanelBox>

      <div style={{ display:"grid", gridTemplateColumns:"1fr 1fr", gap:8, marginTop:8 }}>
        <PanelBox title="AFDX SWITCH STATUS">
          {[
            ["SWITCH A (Port 1-24)","OPERATIONAL"],["SWITCH B (Port 1-24)","OPERATIONAL"],
            ["SWITCH C (Port 1-16)","OPERATIONAL"],["REDUNDANT PATH","ACTIVE"],
            ["BAG ENFORCEMENT","ENABLED"],["VL MONITORING","CONTINUOUS"],
            ["SKEW LIMIT","100µs"],["INTEGRITY CHECK","PASSED"],
          ].map(([k,v]) => <Row key={k} label={k} value={v} color={C.green} />)}
        </PanelBox>
        <PanelBox title="TIMING ANALYSIS">
          <div style={{ marginBottom:8 }}>
            <div style={{ fontSize:8, color:C.dim, marginBottom:4 }}>JITTER DISTRIBUTION (ALL VLs)</div>
            {[0,5,10,15,20,25,30].map(threshold => {
              const count = displayVLs.filter(v => (v.jitter_us||v.avg_jitter_us||0) <= threshold).length;
              const pct = count/displayVLs.length*100;
              return (
                <div key={threshold} style={{ display:"flex", alignItems:"center", gap:8, marginBottom:3 }}>
                  <div style={{ width:40, fontSize:8, color:C.dim, textAlign:"right" }}>≤{threshold}µs</div>
                  <div style={{ flex:1, height:4, background:"rgba(255,255,255,0.05)" }}>
                    <div style={{ height:"100%", width:`${pct}%`, background:threshold<=15?C.green:threshold<=25?C.amber:C.red, transition:"width 0.5s" }} />
                  </div>
                  <div style={{ width:30, fontSize:8, color:C.dim }}>{count}/{displayVLs.length}</div>
                </div>
              );
            })}
          </div>
          {[
            ["MAX JITTER",    `${displayVLs.length ? Math.max(...displayVLs.map(v=>v.jitter_us||v.avg_jitter_us||0)) : 0}µs`],
            ["AVG JITTER",    `${Math.round(displayVLs.reduce((a,v)=>a+(v.jitter_us||v.avg_jitter_us||0),0)/(displayVLs.length||1))}µs`],
            ["JITTER LIMIT",  "500µs (ARINC 664)"],
            ["LATENCY LIMIT", "200ms end-to-end"],
          ].map(([k,v]) => <Row key={k} label={k} value={v} />)}
        </PanelBox>
      </div>
    </div>
  );
}

// ═════════════════════════════════════════════════════════════
// MAINTENANCE CONSOLE PANEL
// ═════════════════════════════════════════════════════════════
export function MaintenancePanel() {
  // Attempt to fetch live maintenance data from API
  const [apiActions, setApiActions] = React.useState(null);
  React.useEffect(() => {
    fetch("/api/v1/maintenance/actions", {
      headers: { Authorization: `Bearer ${localStorage.getItem("st_token") || ""}` }
    })
      .then(r => r.ok ? r.json() : null)
      .then(d => { if (d?.actions) setApiActions(d.actions); })
      .catch(() => {});
  }, []);

  const [items, setItems] = useState(() => MAINTENANCE_FALLBACK);
  const displayItems = apiActions || items;
  const [filter, setFilter] = useState("ALL");

  const [showForm, setShowForm] = React.useState(false);
  const [creating, setCreating] = React.useState(false);
  const [newAction, setNewAction] = React.useState({
    title:"", ata_chapter: 27, system:"", priority:"ROUTINE", description:""
  });

  const filtered = filter==="ALL" ? displayItems : displayItems.filter(i=>i.status===filter||i.priority===filter);
  const open = displayItems.filter(i=>i.status==="OPEN").length;
  const overdue = displayItems.filter(i=>i.status==="OVERDUE").length;

  const priorityColor = { HIGH:C.red, MEDIUM:C.amber, LOW:C.blue, IMMEDIATE:C.red, URGENT:C.amber, ROUTINE:C.blue, DEFERRED:C.dim };
  const statusColor   = { OPEN:C.amber, IN_PROGRESS:C.blue, OVERDUE:C.red, DEFERRED:C.dim, COMPLETED:C.green };

  return (
    <div style={{ flex:1, overflow:"auto", padding:12, ...mono }}>
      <SectionHeader title="MAINTENANCE CONSOLE — MEL/CDL TRACKING — CAMO INTERFACE" />
      <div style={{ display:"grid", gridTemplateColumns:"repeat(5,1fr)", gap:8, marginBottom:12 }}>
        <Metric label="TOTAL ACTIONS" value={displayItems.length} color={C.blue} />
        <Metric label="OPEN" value={open} color={C.amber} />
        <Metric label="OVERDUE" value={overdue} color={overdue>0?C.red:C.green} />
        <Metric label="IN PROGRESS" value={displayItems.filter(i=>i.status==="IN_PROGRESS").length} color={C.blue} />
        <Metric label="DEFERRED" value={displayItems.filter(i=>i.status==="DEFERRED").length} color={C.dim} />
      </div>

      {/* New Action button + filter controls */}
      <div style={{ display:"flex", gap:6, marginBottom:10, flexWrap:"wrap", alignItems:"center" }}>
        <button onClick={() => setShowForm(f => !f)}
          style={{ fontSize:9, letterSpacing:2, padding:"4px 12px", background:"transparent",
                   border:`1px solid ${C.blue}`, color:C.blue, cursor:"pointer",
                   fontFamily:"IBM Plex Mono, monospace" }}>
          {showForm ? "× CANCEL" : "+ NEW ACTION"}
        </button>
        {["ALL","OPEN","IN_PROGRESS","OVERDUE","HIGH","MEDIUM","LOW"].map(f => (
          <button key={f} onClick={() => setFilter(f)}
            style={{ padding:"3px 10px", fontSize:8, letterSpacing:2, fontFamily:"inherit", cursor:"pointer", background:filter===f?"rgba(0,180,255,0.15)":"transparent", border:`1px solid ${filter===f?C.blue:"rgba(0,180,255,0.2)"}`, color:filter===f?C.blue:C.dim }}>
            {f}
          </button>
        ))}
      </div>

      {/* Inline creation form */}
      {showForm && (
        <div style={{ background:"#080f20", border:"1px solid #1e3a5f", padding:12, marginBottom:12 }}>
          <input placeholder="TITLE" value={newAction.title}
            onChange={e => setNewAction(n => ({...n, title: e.target.value}))}
            style={INPUT_STYLE} />
          <div style={{ display:"flex", gap:8, marginTop:6 }}>
            <select value={newAction.priority}
              onChange={e => setNewAction(n => ({...n, priority: e.target.value}))}
              style={INPUT_STYLE}>
              {["IMMEDIATE","URGENT","ROUTINE","DEFERRED"].map(p =>
                <option key={p} value={p} style={{background:"#060d1a"}}>{p}</option>
              )}
            </select>
            <input placeholder="SYSTEM" value={newAction.system}
              onChange={e => setNewAction(n => ({...n, system: e.target.value}))}
              style={{...INPUT_STYLE, flex:1}} />
          </div>
          <input placeholder="DESCRIPTION" value={newAction.description}
            onChange={e => setNewAction(n => ({...n, description: e.target.value}))}
            style={{...INPUT_STYLE, marginTop:6, width:"100%"}} />
          <button
            disabled={creating || !newAction.title}
            onClick={async () => {
              setCreating(true);
              try {
                const res = await fetch("/api/v1/maintenance/actions", {
                  method:"POST",
                  headers:{
                    "Content-Type":"application/json",
                    "Authorization": `Bearer ${localStorage.getItem("st_token")||""}`
                  },
                  body: JSON.stringify(newAction),
                });
                if (res.ok) {
                  const created = await res.json();
                  setApiActions(prev => [created, ...(prev || [])]);
                  setShowForm(false);
                  setNewAction({title:"",ata_chapter:27,system:"",priority:"ROUTINE",description:""});
                }
              } finally { setCreating(false); }
            }}
            style={{ marginTop:8, background:C.green, border:"none", color:"#000",
                     padding:"6px 16px", fontSize:10, letterSpacing:2, cursor:"pointer",
                     fontFamily:"IBM Plex Mono, monospace", fontWeight:700,
                     opacity: (creating || !newAction.title) ? 0.5 : 1 }}>
            {creating ? "CREATING..." : "CREATE ACTION"}
          </button>
        </div>
      )}

      <PanelBox title={`MAINTENANCE ACTIONS (${filtered.length})`}>
        {filtered.map(item => (
          <div key={item.id} style={{ marginBottom:8, padding:"8px 10px", background:"rgba(6,13,26,0.8)", border:`1px solid ${item.status==="OVERDUE"?"rgba(255,23,68,0.3)":item.priority==="HIGH"?"rgba(255,87,34,0.2)":"rgba(0,180,255,0.1)"}`, borderLeft:`3px solid ${priorityColor[item.priority]||C.dim}` }}>
            <div style={{ display:"flex", gap:12, marginBottom:5, alignItems:"center" }}>
              <div style={{ fontSize:9, color:C.amber, fontWeight:600 }}>{item.id}</div>
              <div style={{ fontSize:8, color:C.dim }}>ATA {item.ata}</div>
              <div style={{ padding:"1px 7px", background:`${priorityColor[item.priority]}14`, border:`1px solid ${priorityColor[item.priority]}44`, color:priorityColor[item.priority], fontSize:7, letterSpacing:1 }}>{item.priority}</div>
              <div style={{ padding:"1px 7px", background:`${statusColor[item.status]||C.dim}14`, border:`1px solid ${statusColor[item.status]||C.dim}44`, color:statusColor[item.status]||C.dim, fontSize:7, letterSpacing:1 }}>{item.status}</div>
              <div style={{ marginLeft:"auto", fontSize:8, color:C.dim }}>{item.mel}</div>
            </div>
            <div style={{ fontSize:10, color:C.text, marginBottom:5 }}>{item.description}</div>
            <div style={{ display:"flex", gap:16, fontSize:8, color:C.dim }}>
              <span>ASSIGNED: <span style={{ color:C.mid }}>{item.assigned}</span></span>
              <span>DUE: <span style={{ color:item.status==="OVERDUE"?C.red:C.mid }}>{item.due}</span></span>
            </div>
          </div>
        ))}
      </PanelBox>
    </div>
  );
}

// ═════════════════════════════════════════════════════════════
// REPLAY CONSOLE — WIRED TO BACKEND SIMULATOR API
// ═════════════════════════════════════════════════════════════
export function ReplayConsole() {
  const [status, setStatus]         = useState(null);
  const [sessions, setSessions]     = useState(REPLAY_SESSIONS_FALLBACK);
  const [selected, setSelected]     = useState(null);
  const [speed, setSpeed]           = useState(1.0);
  const [replayState, setReplayState] = useState("STOPPED");
  const [progress, setProgress]     = useState(0);
  const [csvPath, setCsvPath]       = useState("");
  const [loading, setLoading]       = useState(false);
  const [statusMsg, setStatusMsg]   = useState("");
  const progressRef = useRef(null);

  // Keep hardcoded sessions for demo when no backend sessions exist
  const SPEEDS = [0.5, 1.0, 2.0, 4.0];

  // Poll simulator status every 2s
  useEffect(() => {
    const poll = () => {
      const tok = typeof localStorage !== "undefined" ? localStorage.getItem("st_token") || "" : "";
      if (!tok) return; // No token yet — skip silently
      fetch("/api/v1/simulator/status", {
        headers:{ Authorization:`Bearer ${tok}` }
      })
        .then(r => r.ok ? r.json() : null)
        .then(d => {
          if (!d) return;
          setStatus(d);
          // Update progress from backend replay index
          if (d.replay_total > 0) {
            setProgress((d.replay_index / d.replay_total) * 100);
          }
          if (d.source === "CSV_REPLAY") {
            setReplayState(d.replay_index < d.replay_total ? "PLAYING" : "COMPLETE");
          } else if (d.source !== "CSV_REPLAY" && replayState === "PLAYING") {
            // Replay ended
            setReplayState("STOPPED");
          }
        })
        .catch(() => {});
    };
    poll();
    const iv = setInterval(poll, 2000);
    return () => clearInterval(iv);
  }, [replayState]);

  const loadReplay = async () => {
    if (!csvPath.trim()) {
      setStatusMsg("ERROR: Enter a CSV file path");
      return;
    }
    setLoading(true);
    setStatusMsg("Loading CSV replay...");
    try {
      const tok = localStorage.getItem("st_token") || "";
      const r = await fetch(
        `/api/v1/simulator/replay/load?csv_path=${encodeURIComponent(csvPath)}`,
        { method:"POST", headers:{ Authorization:`Bearer ${tok}` } }
      );
      if (r.status === 401) { setStatusMsg("✗ Session expired — please log in again"); return; }
      const d = await r.json();
      if (d.loaded) {
        setStatusMsg(`✓ Loaded ${d.frame_count?.toLocaleString()} frames`);
        setProgress(0);
        setReplayState("STOPPED");
      } else {
        setStatusMsg("✗ Failed to load — check file path");
      }
    } catch (e) {
      setStatusMsg(`✗ Error: ${e.message}`);
    } finally {
      setLoading(false);
    }
  };

  const startReplay = async () => {
    setLoading(true);
    setStatusMsg("Starting replay...");
    try {
      const tok = localStorage.getItem("st_token") || "";
      const r = await fetch(
        `/api/v1/simulator/replay/start?speed=${speed}`,
        { method:"POST", headers:{ Authorization:`Bearer ${tok}` } }
      );
      if (r.status === 401) { setStatusMsg("✗ Session expired — please log in again"); return; }
      const d = await r.json();
      if (d.status === "PLAYING") {
        setReplayState("PLAYING");
        setProgress(0);
        setStatusMsg(`▶ Playing at ${speed}x — ${d.frames?.toLocaleString()} frames`);
      }
    } catch (e) {
      setStatusMsg(`✗ ${e.message}`);
    } finally {
      setLoading(false);
    }
  };

  const connectXPlane = async () => {
    setLoading(true);
    setStatusMsg("Connecting to X-Plane on port 49001...");
    try {
      const tok = typeof localStorage !== "undefined" ? localStorage.getItem("st_token") || "" : token;
      const r = await fetch("/api/v1/simulator/xplane/connect?port=49001",
        { method:"POST", headers:{ Authorization:`Bearer ${tok}` } }
      );
      if (r.status === 401) {
        setStatusMsg("✗ Authentication required — please log in again");
        return;
      }
      const d = await r.json();
      if (d.connected) {
        setStatusMsg("✓ X-Plane CONNECTED — live data streaming");
        setReplayState("XPLANE");
      } else {
        setStatusMsg("✗ X-Plane not reachable — ensure X-Plane 11/12 is running with UDP Data Output enabled on port 49001");
      }
    } catch (e) {
      setStatusMsg(`✗ Connection error: ${e.message}`);
    } finally {
      setLoading(false);
    }
  };

  const exportSession = () => {
    if (!selected) return;
    const blob = new Blob(
      [JSON.stringify(selected, null, 2)],
      { type:"application/json" }
    );
    const url = URL.createObjectURL(blob);
    const a   = document.createElement("a");
    a.href    = url;
    a.download= `sentineltwin-session-${selected.id}.json`;
    a.click();
    URL.revokeObjectURL(url);
  };

  // Source badge color
  const sourceBadge = {
    XPLANE:      { color:"#00e676", label:"X-PLANE LIVE" },
    CSV_REPLAY:  { color:"#00b4ff", label:"CSV REPLAY" },
    SYNTHETIC:   { color:"#546e7a", label:"SYNTHETIC" },
    NO_SIMULATOR:{ color:"#E24B4A", label:"NO SOURCE" },
  };
  const badge = sourceBadge[status?.source || "SYNTHETIC"] || sourceBadge.SYNTHETIC;

  return (
    <div style={{ flex:1, overflow:"auto", padding:12, ...mono }}>
      <SectionHeader title="TELEMETRY REPLAY CONSOLE — INCIDENT INVESTIGATION & SIMULATOR" />

      <div style={{ display:"grid", gridTemplateColumns:"1fr 340px", gap:8 }}>

        {/* LEFT: Session library */}
        <div>
          <PanelBox title="REPLAY SESSION LIBRARY">
            {sessions.map(s => (
              <div key={s.id} onClick={() => setSelected(s)}
                style={{ marginBottom:6, padding:"8px 10px",
                         background: selected?.id===s.id
                           ? "rgba(0,180,255,0.08)" : "rgba(6,13,26,0.6)",
                         border:`1px solid ${selected?.id===s.id ? C.blue : C.border}`,
                         cursor:"pointer" }}>
                <div style={{ display:"flex", justifyContent:"space-between",
                               marginBottom:4 }}>
                  <span style={{ fontSize:9, color:C.amber }}>{s.id}</span>
                  <span style={{ fontSize:8, color:C.dim }}>{s.date}</span>
                </div>
                <div style={{ fontSize:10, color:C.text, marginBottom:4 }}>{s.name}</div>
                <div style={{ display:"flex", gap:12, fontSize:9, color:C.dim }}>
                  <span>⏱ {s.duration}</span>
                  <span style={{ color: s.anomalies > 5 ? C.red : C.amber }}>
                    ⚠ {s.anomalies} anomalies
                  </span>
                  <span>{s.size}</span>
                </div>
              </div>
            ))}
          </PanelBox>
        </div>

        {/* RIGHT: Controls */}
        <div style={{ display:"flex", flexDirection:"column", gap:8 }}>

          {/* Data source status */}
          <PanelBox title="DATA SOURCE">
            <div style={{ display:"flex", alignItems:"center", gap:8, marginBottom:8 }}>
              <div style={{ width:8, height:8, borderRadius:"50%",
                            background:badge.color,
                            boxShadow:`0 0 6px ${badge.color}` }} />
              <span style={{ fontSize:10, letterSpacing:2, color:badge.color }}>
                {badge.label}
              </span>
            </div>
            {status && (
              <div style={{ fontSize:9, color:C.dim }}>
                {status.source === "CSV_REPLAY" && (
                  <div>Frame {status.replay_index?.toLocaleString()} / {status.replay_total?.toLocaleString()}</div>
                )}
              </div>
            )}
            <button onClick={connectXPlane} disabled={loading}
              style={{ width:"100%", marginTop:8, background:"transparent",
                       border:"1px solid #1D9E75", color:"#1D9E75",
                       padding:"6px 0", fontSize:9, letterSpacing:2,
                       cursor:"pointer", fontFamily:"IBM Plex Mono, monospace" }}>
              CONNECT X-PLANE UDP
            </button>
          </PanelBox>

          {/* CSV replay loader */}
          <PanelBox title="CSV REPLAY">
            <div style={{ fontSize:9, color:C.dim, marginBottom:6, letterSpacing:1 }}>
              CSV format: timestamp_utc,altitude_ft,airspeed_kts,...
            </div>
            <input value={csvPath} onChange={e => setCsvPath(e.target.value)}
              placeholder="/path/to/recording.csv"
              style={{ background:"#0a1628", border:"1px solid #1e3a5f",
                       color:C.text, padding:"5px 8px", fontSize:10,
                       width:"100%", fontFamily:"IBM Plex Mono, monospace",
                       marginBottom:6, boxSizing:"border-box" }} />
            <button onClick={loadReplay} disabled={loading || !csvPath}
              style={{ width:"100%", background:"transparent",
                       border:"1px solid #1e3a5f", color:C.dim,
                       padding:"5px 0", fontSize:9, letterSpacing:2,
                       cursor:"pointer", fontFamily:"IBM Plex Mono, monospace" }}>
              LOAD CSV FILE
            </button>
          </PanelBox>

          {/* Playback controls */}
          <PanelBox title="PLAYBACK CONTROLS">
            <div style={{ display:"flex", gap:6, marginBottom:8 }}>
              {SPEEDS.map(s => (
                <button key={s} onClick={() => setSpeed(s)}
                  style={{ flex:1, background: speed===s ? "#00b4ff" : "transparent",
                           border:"1px solid #1e3a5f",
                           color: speed===s ? "#000" : C.dim,
                           padding:"4px 0", fontSize:9, letterSpacing:1,
                           cursor:"pointer", fontFamily:"IBM Plex Mono, monospace",
                           fontWeight: speed===s ? 700 : 400 }}>
                  {s}×
                </button>
              ))}
            </div>
            <div style={{ display:"flex", gap:6 }}>
              <button onClick={startReplay}
                disabled={loading || status?.source === "XPLANE"}
                style={{ flex:2, background:"#00b4ff", border:"none",
                         color:"#000", padding:"7px 0", fontSize:9,
                         letterSpacing:2, cursor:"pointer",
                         fontFamily:"IBM Plex Mono, monospace", fontWeight:700 }}>
                ▶ PLAY
              </button>
              <button onClick={exportSession} disabled={!selected}
                style={{ flex:1, background:"transparent", border:"1px solid #1e3a5f",
                         color:C.dim, padding:"7px 0", fontSize:9,
                         letterSpacing:1, cursor:"pointer",
                         fontFamily:"IBM Plex Mono, monospace" }}>
                EXPORT
              </button>
            </div>
          </PanelBox>

          {/* Progress bar */}
          <PanelBox title="REPLAY PROGRESS">
            <div style={{ height:6, background:"#1e3a5f", borderRadius:3,
                           overflow:"hidden", marginBottom:6 }}>
              <div style={{ height:"100%", background:"#00b4ff", borderRadius:3,
                             width:`${progress.toFixed(1)}%`, transition:"width 0.5s" }} />
            </div>
            <div style={{ fontSize:9, color:C.dim, textAlign:"right" }}>
              {progress.toFixed(1)}%
            </div>
          </PanelBox>

          {/* Status message */}
          {statusMsg && (
            <div style={{ padding:"8px 10px", background:"rgba(0,180,255,0.05)",
                           border:"1px solid #1e3a5f", fontSize:10,
                           color: statusMsg.startsWith("✓") ? "#1D9E75"
                                : statusMsg.startsWith("✗") ? "#E24B4A"
                                : C.text, letterSpacing:1 }}>
              {statusMsg}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

// Hardcoded fallback sessions (shown when no backend sessions exist)
const REPLAY_SESSIONS_FALLBACK = [
  { id:"REC-001", name:"CDG→LHR AF1234", date:"2026-05-10", duration:"2h 14m", anomalies:3, size:"1.2 GB" },
  { id:"REC-002", name:"FRA→JFK LH401",  date:"2026-05-09", duration:"8h 45m", anomalies:7, size:"4.8 GB" },
  { id:"REC-003", name:"LTN→BCN EZY422", date:"2026-05-08", duration:"1h 52m", anomalies:1, size:"0.9 GB" },
  { id:"REC-004", name:"ZRH→ORD LX23",   date:"2026-05-07", duration:"9h 12m", anomalies:12,size:"5.1 GB" },
  { id:"REC-005", name:"CDG→NRT AF271",  date:"2026-05-06", duration:"11h 8m", anomalies:4, size:"6.2 GB" },
];


// ═════════════════════════════════════════════════════════════
// PHASE TIMELINE PANEL
// ═════════════════════════════════════════════════════════════
export function PhaseTimeline({ flightPhase, elapsed, altitude, speed }) {
  const twin = useSentinelStore(s => s.twinState);
  const phases = ["GROUND","TAXI","TAKEOFF","CLIMB","CRUISE","DESCENT","APPROACH","LANDING"];

  const alt      = twin?.altitude_ft  ?? altitude  ?? 0;
  const phase    = twin?.flight_phase ?? flightPhase ?? "GROUND";
  const spd      = twin?.airspeed_kts ?? speed      ?? 0;
  const elapsedS = twin?.elapsed_sec  ?? elapsed    ?? 0;

  const currentIdx = phases.indexOf(phase);
  const canvasRef = useRef(null);

  // Altitude profile history
  const histRef = useRef([]);
  useEffect(() => {
    histRef.current = [...histRef.current, { alt, t: elapsedS, spd }].slice(-200);
  }, [alt, elapsedS, spd]);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    const W = canvas.width, H = canvas.height;
    ctx.clearRect(0,0,W,H);
    ctx.fillStyle = "#040b17";
    ctx.fillRect(0,0,W,H);

    // Grid
    ctx.strokeStyle = "rgba(0,180,255,0.04)"; ctx.lineWidth = 1;
    for (let y = 0; y < H; y += 20) { ctx.beginPath(); ctx.moveTo(0,y); ctx.lineTo(W,y); ctx.stroke(); }

    const hist = histRef.current;
    if (hist.length < 2) return;

    const maxAlt = Math.max(40000, ...hist.map(h=>h.alt));
    const maxSpd = Math.max(300, ...hist.map(h=>h.spd));

    // Altitude profile
    ctx.beginPath();
    ctx.strokeStyle = C.blue; ctx.lineWidth = 1.5;
    hist.forEach((h, i) => {
      const x = (i / (hist.length-1)) * W;
      const y = H - (h.alt / maxAlt) * (H * 0.85) - 10;
      i === 0 ? ctx.moveTo(x, y) : ctx.lineTo(x, y);
    });
    ctx.stroke();

    // Fill under altitude
    ctx.beginPath();
    hist.forEach((h, i) => {
      const x = (i / (hist.length-1)) * W;
      const y = H - (h.alt / maxAlt) * (H * 0.85) - 10;
      i === 0 ? ctx.moveTo(x, y) : ctx.lineTo(x, y);
    });
    ctx.lineTo(W, H); ctx.lineTo(0, H); ctx.closePath();
    const grad = ctx.createLinearGradient(0,0,0,H);
    grad.addColorStop(0, "rgba(0,180,255,0.2)");
    grad.addColorStop(1, "rgba(0,180,255,0.01)");
    ctx.fillStyle = grad; ctx.fill();

    // Speed profile
    ctx.beginPath();
    ctx.strokeStyle = C.amber; ctx.lineWidth = 1;
    hist.forEach((h, i) => {
      const x = (i / (hist.length-1)) * W;
      const y = H - (h.spd / maxSpd) * (H * 0.6) - 10;
      i === 0 ? ctx.moveTo(x, y) : ctx.lineTo(x, y);
    });
    ctx.stroke();

    // Labels
    ctx.font = "8px 'IBM Plex Mono'";
    ctx.fillStyle = C.blue; ctx.fillText("ALTITUDE", 6, 14);
    ctx.fillStyle = C.amber; ctx.fillText("IAS", 6, 26);
    ctx.fillStyle = C.dim;
    ctx.fillText(`${Math.round(maxAlt).toLocaleString()} FT`, W-80, 14);
  }, [alt, elapsedS]);

  return (
    <div style={{ flex:1, overflow:"auto", padding:12, ...mono }}>
      <SectionHeader title="FLIGHT PHASE TIMELINE — ALTITUDE & SPEED PROFILE" />

      {/* Phase progress bar */}
      <PanelBox title="FLIGHT PHASE PROGRESSION">
        <div style={{ display:"flex", gap:2, marginTop:8 }}>
          {phases.map((ph, i) => {
            const isPast = i < currentIdx;
            const isCurrent = i === currentIdx;
            const isFuture = i > currentIdx;
            return (
              <div key={ph} style={{ flex:1, textAlign:"center" }}>
                <div style={{ height:4, background:isPast?C.green:isCurrent?C.blue:"rgba(255,255,255,0.06)", marginBottom:6, boxShadow:isCurrent?`0 0 8px ${C.blue}`:undefined }} />
                <div style={{ fontSize:7, color:isPast?C.green:isCurrent?C.blue:C.dim, letterSpacing:1 }}>{ph}</div>
                {isCurrent && <div style={{ fontSize:10, color:C.blue, marginTop:3 }}>◉</div>}
              </div>
            );
          })}
        </div>
      </PanelBox>

      {/* Altitude/speed canvas */}
      <div style={{ marginTop:8 }}>
        <PanelBox title="ALTITUDE & SPEED PROFILE — REAL-TIME TRACE">
          <canvas ref={canvasRef} width={700} height={180} style={{ width:"100%", objectFit:"fill", background:"#040b17", border:`1px solid ${C.border}` }} />
        </PanelBox>
      </div>

      {/* Phase metrics */}
      <div style={{ display:"grid", gridTemplateColumns:"repeat(4,1fr)", gap:8, marginTop:8 }}>
        <Metric label="CURRENT PHASE" value={phase} color={C.blue} size={14} />
        <Metric label="ALTITUDE" value={`${Math.round(alt).toLocaleString()} FT`} color={C.text} size={14} />
        <Metric label="IAS" value={`${Math.round(spd)} KT`} color={C.amber} size={14} />
        <Metric label="SESSION TIME" value={`${Math.floor(elapsedS/60).toString().padStart(2,"0")}:${Math.floor(elapsedS%60).toString().padStart(2,"0")}`} color={C.dim} size={14} />
      </div>
    </div>
  );
}

// ═════════════════════════════════════════════════════════════
// NEURAL NETWORK VISUALISER
// ═════════════════════════════════════════════════════════════
export function NeuralNetworkPanel({ aiConfidence }) {
  const aiStatus = useSentinelStore(s => s.aiStatus);
  const modelVersion   = aiStatus?.model_version         || "v2.4.1";
  const reconError     = aiStatus?.reconstruction_error  || 0;
  const inferenceCount = aiStatus?.inference_count        || 0;
  const fpr            = aiStatus?.false_positive_rate    || 0.004;
  const tpr            = aiStatus?.true_positive_rate     || 0.94;

  const canvasRef = useRef(null);
  const animRef = useRef(null);
  const [errHistory, setErrHistory] = useState(() => Array.from({length:80},(_,i)=>0.06+Math.random()*0.04));

  const reconErr = aiStatus?.reconstruction_error ?? null;

  // Push real reconstruction error from store when available
  useEffect(() => {
    if (reconErr === null) return;
    setErrHistory(h => [...h.slice(1), reconErr]);
  }, [reconErr]);

  // Fallback: simulate error only when no WS data exists yet
  useEffect(() => {
    if (reconErr !== null) return;  // real data exists, don't simulate
    const iv = setInterval(() => {
      const err = 0.04 + Math.random()*0.12 + (1-aiConfidence)*0.2;
      setErrHistory(h => [...h.slice(1), err]);
    }, 800);
    return () => clearInterval(iv);
  }, [reconErr, aiConfidence]);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    const W = canvas.width, H = canvas.height;
    let frame = 0;

    const LAYERS = [
      { nodes:8,  label:"INPUT\n256→8",  x:0.08 },
      { nodes:6,  label:"ENC1\n128",      x:0.25 },
      { nodes:5,  label:"ENC2\n64",       x:0.38 },
      { nodes:4,  label:"LATENT\n32",     x:0.50 },
      { nodes:5,  label:"DEC1\n64",       x:0.62 },
      { nodes:6,  label:"DEC2\n128",      x:0.75 },
      { nodes:8,  label:"OUTPUT\n8→256",  x:0.92 },
    ];

    const nodeY = (layerIdx, nodeIdx, count) => {
      const spacing = H / (count + 1);
      return spacing * (nodeIdx + 1);
    };

    function draw() {
      ctx.clearRect(0,0,W,H);
      ctx.fillStyle = "#040b17";
      ctx.fillRect(0,0,W,H);

      // Grid
      ctx.strokeStyle = "rgba(0,180,255,0.03)"; ctx.lineWidth = 1;
      for (let x=0; x<W; x+=30) { ctx.beginPath(); ctx.moveTo(x,0); ctx.lineTo(x,H); ctx.stroke(); }
      for (let y=0; y<H; y+=30) { ctx.beginPath(); ctx.moveTo(0,y); ctx.lineTo(W,y); ctx.stroke(); }

      const currentErr = errHistory[errHistory.length-1] || 0.08;
      const anomaly = currentErr > 0.15;

      // Draw connections between layers
      for (let li=0; li<LAYERS.length-1; li++) {
        const la = LAYERS[li], lb = LAYERS[li+1];
        const ax = la.x * W, bx = lb.x * W;
        for (let ni=0; ni<la.nodes; ni++) {
          const ay = nodeY(li, ni, la.nodes);
          for (let nj=0; nj<lb.nodes; nj++) {
            const by = nodeY(li+1, nj, lb.nodes);
            // Pulse animation
            const pulse = Math.sin(frame*0.05 + li*0.5 + ni*0.2 + nj*0.3);
            const alpha = 0.04 + pulse * 0.03;
            const isLatent = li === 3;
            ctx.beginPath();
            ctx.moveTo(ax, ay); ctx.lineTo(bx, by);
            ctx.strokeStyle = anomaly ? `rgba(255,87,34,${alpha})` : isLatent ? `rgba(0,230,118,${alpha})` : `rgba(0,180,255,${alpha})`;
            ctx.lineWidth = 0.5;
            ctx.stroke();
          }
        }
      }

      // Draw nodes
      LAYERS.forEach((layer, li) => {
        const lx = layer.x * W;
        layer.label.split("\n").forEach((line, i) => {
          ctx.font = "7px 'IBM Plex Mono'";
          ctx.fillStyle = C.dim;
          ctx.textAlign = "center";
          ctx.fillText(line, lx, H - 28 + i*10);
        });

        for (let ni=0; ni<layer.nodes; ni++) {
          const ly = nodeY(li, ni, layer.nodes);
          const activation = 0.4 + Math.sin(frame*0.03 + li*1.2 + ni*0.7)*0.6;
          const r = 7;
          const isLatent = li === 3;
          const nodeColor = isLatent
            ? `rgba(0,230,118,${activation*0.8})`
            : anomaly
            ? `rgba(255,87,34,${activation*0.9})`
            : `rgba(0,180,255,${activation*0.8})`;

          // Glow
          ctx.beginPath();
          ctx.arc(lx, ly, r+4, 0, Math.PI*2);
          ctx.fillStyle = isLatent ? "rgba(0,230,118,0.05)" : anomaly ? "rgba(255,87,34,0.05)" : "rgba(0,180,255,0.05)";
          ctx.fill();

          // Node
          ctx.beginPath();
          ctx.arc(lx, ly, r, 0, Math.PI*2);
          ctx.fillStyle = nodeColor;
          ctx.fill();
          ctx.strokeStyle = isLatent ? C.green : anomaly ? C.orange : C.blue;
          ctx.lineWidth = 1;
          ctx.stroke();
        }
      });

      // Stats overlay
      ctx.font = "8px 'IBM Plex Mono'";
      ctx.textAlign = "left";
      ctx.fillStyle = C.blue;
      ctx.fillText("SPARSE AUTOENCODER — PHYSICS-NORMALISED RESIDUALS", 12, 18);
      ctx.fillStyle = C.dim;
      ctx.fillText(`RECONSTRUCTION ERROR: ${currentErr.toFixed(4)}   THRESHOLD: 0.1500   STATUS: ${anomaly?"ANOMALY":"NOMINAL"}`, 12, 30);
      ctx.fillStyle = anomaly ? C.red : C.green;
      ctx.fillText(anomaly ? "⚠ ANOMALY DETECTED" : "✓ NOMINAL", 12, 42);

      frame++;
      animRef.current = requestAnimationFrame(draw);
    }

    draw();
    return () => cancelAnimationFrame(animRef.current);
  }, [errHistory, aiConfidence]);

  return (
    <div style={{ flex:1, overflow:"auto", padding:12, ...mono }}>
      <SectionHeader title="NEURAL NETWORK VISUALISER — SPARSE AUTOENCODER — LATENT SPACE MONITOR" />
      <canvas ref={canvasRef} width={800} height={360} style={{ width:"100%", background:"#040b17", border:`1px solid ${C.border}`, marginBottom:8 }} />
      <div style={{ display:"grid", gridTemplateColumns:"repeat(5,1fr)", gap:8 }}>
        <Metric label="MODEL VERSION" value={modelVersion} color={C.blue} size={12} />
        <Metric label="CONFIDENCE" value={`${(aiConfidence*100).toFixed(2)}%`} color={aiConfidence>0.9?C.green:C.amber} size={12} />
        <Metric label="INFERENCES" value={inferenceCount.toLocaleString()} color={C.text} size={12} />
        <Metric label="FPR / TPR" value={`${(fpr*100).toFixed(2)}% / ${(tpr*100).toFixed(1)}%`} color={C.green} size={11} />
        <Metric label="RECON ERROR" value={reconError.toFixed(6)} color={reconError>0.15?C.red:C.green} size={12} />
      </div>
    </div>
  );
}

// ═════════════════════════════════════════════════════════════
// ENVIRONMENTAL SYSTEMS PANEL
// ═════════════════════════════════════════════════════════════
export function EnvironmentalPanel({ altitude, flightPhase }) {
  const twin = useSentinelStore(s => s.twinState);

  // Use live twin data if available, fallback to props/derived
  const alt   = twin?.altitude_ft    ?? altitude    ?? 0;
  const phase = twin?.flight_phase   ?? flightPhase ?? "GROUND";
  const fuel  = twin?.fuel           ?? {};
  const therm = twin?.thermal        ?? {};
  const struct= twin?.structural     ?? {};

  // ISA atmosphere (derived from altitude)
  const isaTempC     = twin?.isa_temp_c        ?? (15 - alt / 1000 * 1.98);
  const isaPresKpa   = twin?.isa_pressure_kpa  ?? (101.325 * Math.pow(1 - 0.0000225577 * alt * 0.3048, 5.25588));
  const apuOn        = phase === "GROUND";

  return (
    <div style={{ flex:1, overflow:"auto", padding:12, ...mono }}>
      <SectionHeader title="ENVIRONMENTAL SYSTEMS — ATA 21/28/30 — LIVE TWIN DATA" />
      <div style={{ display:"grid", gridTemplateColumns:"1fr 1fr 1fr", gap:8 }}>

        {/* CABIN PRESSURISATION */}
        <PanelBox title="CABIN PRESSURISATION (ATA 21)">
          {[
            ["CABIN ALTITUDE",    `${Math.round(Math.max(0, alt * 0.25)).toLocaleString()} FT`],
            ["DIFFERENTIAL ΔP",  `${(Math.max(0, alt) / 40000 * 8.6).toFixed(2)} PSI`],
            ["CABIN TEMP",        `${(therm.cabin_temp_c ?? 22).toFixed(1)} °C`],
            ["OUTFLOW VALVE",     "AUTO / 28%"],
            ["PACK 1 FLOW",       "98%"],
            ["PACK 2 FLOW",       "97%"],
            ["PACK TEMP",         `${(18 + (alt > 20000 ? -2 : 0)).toFixed(1)} °C`],
            ["BLEED SOURCE",      "ENG 1+2"],
            ["SAFETY VALVE",      "CLOSED"],
            ["SMOKE DETECT",      "CLEAR"],
          ].map(([k,v]) => <Row key={k} label={k} value={v} />)}
        </PanelBox>

        {/* ICE & RAIN PROTECTION */}
        <PanelBox title="ICE & RAIN PROTECTION (ATA 30)">
          {[
            ["WING ANTI-ICE",     phase==="CLIMB"||alt>20000?"ACTIVE":"OFF"],
            ["ENG 1 ANTI-ICE",    alt>20000&&isaTempC<-10?"ACTIVE":"OFF"],
            ["ENG 2 ANTI-ICE",    alt>20000&&isaTempC<-10?"ACTIVE":"OFF"],
            ["WINDSHIELD HEAT L", "ACTIVE"],
            ["WINDSHIELD HEAT R", "ACTIVE"],
            ["PROBE HEAT CAPT",   "ACTIVE"],
            ["PROBE HEAT F/O",    "ACTIVE"],
            ["ICE DETECT 1",      "ARMED"],
            ["ICE DETECT 2",      "ARMED"],
            ["RAIN REPELLENT",    "STBY"],
          ].map(([k,v]) => <Row key={k} label={k}
            value={v} color={v==="ACTIVE"?C.green:v==="OFF"?C.dim:C.text} />)}
        </PanelBox>

        {/* ISA ATMOSPHERE */}
        <PanelBox title="ISA ATMOSPHERE — REAL-TIME">
          {[
            ["ALTITUDE",          `${Math.round(alt).toLocaleString()} FT`],
            ["ISA TEMP",          `${isaTempC.toFixed(1)} °C`],
            ["ISA PRESSURE",      `${isaPresKpa.toFixed(2)} kPa`],
            ["MACH",              `${(twin?.mach ?? 0).toFixed(3)}`],
            ["TAS",               `${Math.round(twin?.tas_kt ?? twin?.airspeed_kts ?? 0)} KTS`],
            ["TURBULENCE",        struct.turbulence_intensity ?? "NIL"],
            ["G-LOAD",            `${(struct.g_load_factor ?? 1.0).toFixed(3)} G`],
          ].map(([k,v]) => <Row key={k} label={k}
            value={v} color={k==="TURBULENCE"&&v==="MODERATE"?C.amber:k==="TURBULENCE"&&v==="SEVERE"?C.red:C.text} />)}
        </PanelBox>

        {/* FUEL SYSTEM */}
        <PanelBox title="FUEL SYSTEM (ATA 28) — LIVE BURN">
          {[
            ["TOTAL FUEL",        `${Math.round(fuel.total_kg ?? 18000).toLocaleString()} KG`],
            ["LEFT WING",         `${Math.round(fuel.left_wing_kg ?? 7500).toLocaleString()} KG`],
            ["RIGHT WING",        `${Math.round(fuel.right_wing_kg ?? 7500).toLocaleString()} KG`],
            ["CENTER TANK",       `${Math.round(fuel.center_tank_kg ?? 3000).toLocaleString()} KG`],
            ["IMBALANCE",         `${(fuel.imbalance_kg ?? 0).toFixed(1)} KG`],
            ["TOTAL FLOW",        `${Math.round(fuel.fuel_flow_total_kgh ?? 900)} KG/H`],
            ["FUEL TEMP",         `${(fuel.fuel_temperature_c ?? 15).toFixed(1)} °C`],
            ["CROSSFEED",         "CLOSED"],
          ].map(([k,v]) => <Row key={k} label={k}
            value={v} color={k==="IMBALANCE"&&(fuel.imbalance_kg??0)>300?C.amber:C.text} />)}
        </PanelBox>

        {/* THERMAL MONITORING */}
        <PanelBox title="THERMAL MONITORING">
          {[
            ["AVIONICS BAY",      `${(therm.avionics_bay_c ?? 35).toFixed(1)} °C`],
            ["CABIN",             `${(therm.cabin_temp_c ?? 22).toFixed(1)} °C`],
            ["CARGO FWD",         `${(therm.cargo_temp_c ?? 10).toFixed(1)} °C`],
            ["BRAKE TEMP",        `${Math.round(therm.brake_temp_c ?? 100)} °C`],
            ["APU EGT",           apuOn ? `${Math.round(therm.apu_egt_c ?? 420)} °C` : "OFF"],
            ["ENG 1 OIL TEMP",    `${(therm.eng1_oil_temp_c ?? 75).toFixed(1)} °C`],
            ["ENG 2 OIL TEMP",    `${(therm.eng2_oil_temp_c ?? 75).toFixed(1)} °C`],
          ].map(([k,v]) => <Row key={k} label={k}
            value={v}
            color={k==="BRAKE TEMP"&&(therm.brake_temp_c??0)>300?C.red
                  :k==="AVIONICS BAY"&&(therm.avionics_bay_c??0)>55?C.amber:C.text} />)}
        </PanelBox>

        {/* STRUCTURAL LOADS */}
        <PanelBox title="STRUCTURAL LOADS (ATA 57)">
          {[
            ["WING BENDING",      `${(struct.wing_bending_moment_knm ?? 0).toFixed(1)} kNm`],
            ["WING SHEAR",        `${(struct.wing_shear_force_kn ?? 0).toFixed(1)} kN`],
            ["FUSELAGE HOOP",     `${(struct.fuselage_hoop_stress_mpa ?? 0).toFixed(2)} MPa`],
            ["GEAR LOAD",         `${(struct.landing_gear_load_kn ?? 0).toFixed(1)} kN`],
            ["G-LOAD FACTOR",     `${(struct.g_load_factor ?? 1.0).toFixed(3)} G`],
            ["TURBULENCE",        struct.turbulence_intensity ?? "NIL"],
          ].map(([k,v]) => <Row key={k} label={k}
            value={v}
            color={k==="TURBULENCE"&&v!=="NIL"?C.amber:C.text} />)}
        </PanelBox>

      </div>
    </div>
  );
}

// ═════════════════════════════════════════════════════════════
// FAULT TIMELINE PANEL — ECAM EVENTS BY ATA CHAPTER × TIME
// ═════════════════════════════════════════════════════════════
export function FaultTimelinePanel() {
  const ecamMessages = useSentinelStore(s => s.ecamMessages);
  const eventLog     = useSentinelStore(s => s.eventLog);
  const canvasRef    = useRef(null);
  const [selected, setSelected] = useState(null);

  const ATA_CHAPTERS = [21,22,24,27,28,29,30,31,32,34,36,49,52,71];
  const SEVERITY_COLOR = {
    STATUS:"#378ADD", CAUTION:"#EF9F27", WARNING:"#F97316", EMERGENCY:"#E24B4A"
  };

  // Build event list from ecamMessages + eventLog
  const events = useMemo(() => {
    const now = Date.now();
    const fromEcam = (ecamMessages || []).map((m, i) => ({
      id: m.message_id || `ecam-${i}`,
      ata_chapter: m.ata_chapter || m.ata,
      severity: m.severity || m.sev || "STATUS",
      message: m.message || m.msg || "",
      procedure: m.procedure || "",
      mel: m.mel_reference || m.mel || "—",
      timestamp_ms: m.timestamp_ms || now - (i * 45000),
    }));
    const fromLog = (eventLog || [])
      .filter(e => (e.ata_chapter || e.ata) && (e.severity || e.type))
      .map((e, i) => ({
        id: `log-${i}`,
        ata_chapter: e.ata_chapter || e.ata,
        severity: e.severity || e.type || "STATUS",
        message: e.message || e.msg || "",
        procedure: "",
        mel: "—",
        timestamp_ms: e.timestamp_ms || (now - i * 30000),
      }));
    return [...fromEcam, ...fromLog]
      .filter(e => ATA_CHAPTERS.includes(e.ata_chapter))
      .slice(0, 200);
  }, [ecamMessages, eventLog]);

  // Canvas rendering
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    const W = canvas.width, H = canvas.height;
    ctx.clearRect(0, 0, W, H);
    ctx.fillStyle = "#040b17";
    ctx.fillRect(0, 0, W, H);

    const MARGIN_LEFT = 52;
    const MARGIN_TOP  = 16;
    const MARGIN_BOT  = 28;
    const plotW = W - MARGIN_LEFT - 16;
    const plotH = H - MARGIN_TOP - MARGIN_BOT;

    const now   = Date.now();
    const start = now - 60 * 60 * 1000;
    const rowH  = plotH / ATA_CHAPTERS.length;

    // Horizontal grid lines
    ctx.strokeStyle = "rgba(0,180,255,0.05)";
    ctx.lineWidth = 1;
    ATA_CHAPTERS.forEach((_, i) => {
      const y = MARGIN_TOP + i * rowH;
      ctx.beginPath(); ctx.moveTo(MARGIN_LEFT, y); ctx.lineTo(W - 16, y); ctx.stroke();
    });

    // Vertical time grid (every 10 minutes)
    ctx.strokeStyle = "rgba(0,180,255,0.04)";
    for (let m = 0; m <= 60; m += 10) {
      const x = MARGIN_LEFT + (m / 60) * plotW;
      ctx.beginPath(); ctx.moveTo(x, MARGIN_TOP); ctx.lineTo(x, H - MARGIN_BOT); ctx.stroke();
    }

    // ATA labels
    ctx.fillStyle = "#546e7a";
    ctx.font = "9px 'IBM Plex Mono', monospace";
    ctx.textAlign = "right";
    ATA_CHAPTERS.forEach((ata, i) => {
      const y = MARGIN_TOP + i * rowH + rowH / 2 + 3;
      ctx.fillText(`ATA ${ata}`, MARGIN_LEFT - 6, y);
    });

    // X-axis time labels
    ctx.fillStyle = "#37474f";
    ctx.textAlign = "center";
    for (let m = 0; m <= 60; m += 10) {
      const x = MARGIN_LEFT + (m / 60) * plotW;
      const label = `-${60 - m}m`;
      ctx.fillText(label, x, H - MARGIN_BOT + 14);
    }

    // Event dots
    events.forEach(evt => {
      const ataIdx = ATA_CHAPTERS.indexOf(evt.ata_chapter);
      if (ataIdx < 0) return;
      const progress = Math.max(0, Math.min(1, (evt.timestamp_ms - start) / (now - start)));
      const x = MARGIN_LEFT + progress * plotW;
      const y = MARGIN_TOP + ataIdx * rowH + rowH / 2;
      const r = evt.severity === "EMERGENCY" ? 5 : evt.severity === "WARNING" ? 4 : 3;
      const color = SEVERITY_COLOR[evt.severity] || "#378ADD";

      ctx.beginPath();
      ctx.arc(x, y, r, 0, Math.PI * 2);
      ctx.fillStyle = color;
      ctx.fill();

      // Glow for high severity
      if (evt.severity === "EMERGENCY" || evt.severity === "WARNING") {
        ctx.beginPath();
        ctx.arc(x, y, r + 2, 0, Math.PI * 2);
        ctx.strokeStyle = color + "55";
        ctx.lineWidth = 1.5;
        ctx.stroke();
      }
    });
  }, [events]);

  // Click detection on canvas
  const handleCanvasClick = (e) => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const rect = canvas.getBoundingClientRect();
    const cx = (e.clientX - rect.left) * (canvas.width / rect.width);
    const cy = (e.clientY - rect.top) * (canvas.height / rect.height);
    const W = canvas.width, H = canvas.height;
    const MARGIN_LEFT = 52, MARGIN_TOP = 16, MARGIN_BOT = 28;
    const plotW = W - MARGIN_LEFT - 16;
    const plotH = H - MARGIN_TOP - MARGIN_BOT;
    const rowH  = plotH / ATA_CHAPTERS.length;
    const now   = Date.now();
    const start = now - 60 * 60 * 1000;

    let hit = null;
    events.forEach(evt => {
      const ataIdx = ATA_CHAPTERS.indexOf(evt.ata_chapter);
      if (ataIdx < 0) return;
      const progress = Math.max(0, Math.min(1, (evt.timestamp_ms - start) / (now - start)));
      const x = MARGIN_LEFT + progress * plotW;
      const y = MARGIN_TOP + ataIdx * rowH + rowH / 2;
      if (Math.hypot(cx - x, cy - y) < 8) hit = evt;
    });
    setSelected(hit);
  };

  return (
    <div style={{ flex:1, overflow:"hidden", padding:12, ...mono,
                  display:"flex", flexDirection:"column" }}>
      <SectionHeader title="FAULT TIMELINE — LAST 60 MINUTES — ECAM EVENTS BY ATA CHAPTER" />

      {/* Legend */}
      <div style={{ display:"flex", gap:16, marginBottom:8 }}>
        {Object.entries(SEVERITY_COLOR).map(([sev, col]) => (
          <span key={sev} style={{ fontSize:9, letterSpacing:2, color:col, display:"flex", alignItems:"center", gap:4 }}>
            <span style={{ width:6, height:6, borderRadius:"50%", background:col, display:"inline-block" }}/>
            {sev}
          </span>
        ))}
        <span style={{ fontSize:9, color:C.dim, marginLeft:"auto" }}>
          {events.length} events plotted
        </span>
      </div>

      {/* Canvas */}
      <canvas
        ref={canvasRef}
        width={900} height={360}
        onClick={handleCanvasClick}
        style={{ width:"100%", height:360, cursor:"crosshair",
                 border:"1px solid #1e3a5f", display:"block" }}
      />

      {/* Detail card on click */}
      {selected && (
        <div style={{ marginTop:8, padding:"10px 14px", background:"#080f20",
                      border:`1px solid ${SEVERITY_COLOR[selected.severity]}`,
                      display:"grid", gridTemplateColumns:"1fr 1fr 1fr", gap:8 }}>
          <div>
            <div style={{ fontSize:8, color:C.dim, letterSpacing:2 }}>SEVERITY</div>
            <div style={{ fontSize:11, color:SEVERITY_COLOR[selected.severity],
                          fontWeight:700, letterSpacing:2 }}>{selected.severity}</div>
          </div>
          <div>
            <div style={{ fontSize:8, color:C.dim, letterSpacing:2 }}>ATA CHAPTER</div>
            <div style={{ fontSize:11, color:C.text }}>{selected.ata_chapter}</div>
          </div>
          <div>
            <div style={{ fontSize:8, color:C.dim, letterSpacing:2 }}>MEL REF</div>
            <div style={{ fontSize:11, color:C.text }}>{selected.mel}</div>
          </div>
          <div style={{ gridColumn:"1/-1" }}>
            <div style={{ fontSize:8, color:C.dim, letterSpacing:2 }}>MESSAGE</div>
            <div style={{ fontSize:11, color:C.blue }}>{selected.message}</div>
          </div>
          {selected.procedure && (
            <div style={{ gridColumn:"1/-1" }}>
              <div style={{ fontSize:8, color:C.dim, letterSpacing:2 }}>PROCEDURE</div>
              <div style={{ fontSize:10, color:C.text }}>{selected.procedure}</div>
            </div>
          )}
          <div style={{ gridColumn:"1/-1", textAlign:"right" }}>
            <span onClick={() => setSelected(null)}
              style={{ fontSize:9, color:C.dim, cursor:"pointer", letterSpacing:2 }}>
              [DISMISS]
            </span>
          </div>
        </div>
      )}
    </div>
  );
}

// ═════════════════════════════════════════════════════════════
// OPERATIONAL LOGS PANEL — LIVE SYSTEM EVENT STREAM
// ═════════════════════════════════════════════════════════════
export function OperationalLogsPanel() {
  const eventLog = useSentinelStore(s => s.eventLog);
  const [logs, setLogs]             = useState([]);
  const [levelFilter, setLevelFilter] = useState("ALL");
  const [search, setSearch]         = useState("");
  const [autoScroll, setAutoScroll] = useState(true);
  const bottomRef = useRef(null);
  const token = typeof localStorage !== "undefined"
    ? localStorage.getItem("st_token") || "" : "";

  const LEVELS = ["ALL", "DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"];
  const LEVEL_COLOR = {
    DEBUG:"#546e7a", INFO:"#90a4ae", WARNING:"#EF9F27",
    ERROR:"#E24B4A", CRITICAL:"#FF0000",
  };

  // Poll operational logs from backend every 3 seconds
  useEffect(() => {
    const fetchLogs = () => {
      fetch("/api/v1/logs/operational?limit=500", {
        headers: { Authorization: `Bearer ${token}` }
      })
        .then(r => r.ok ? r.json() : null)
        .then(d => { if (d?.logs) setLogs(d.logs); })
        .catch(() => {});
    };
    fetchLogs();
    const iv = setInterval(fetchLogs, 3000);
    return () => clearInterval(iv);
  }, [token]);

  // Merge in eventLog entries from store (real-time additions)
  useEffect(() => {
    if (!eventLog?.length) return;
    setLogs(prev => {
      const existing = new Set(prev.map(l => l.id || l.message));
      const newEntries = eventLog
        .filter(e => !existing.has(e.id || e.message))
        .map(e => ({
          id:         e.id || Math.random().toString(36).slice(2),
          timestamp:  e.timestamp || e.ts || new Date().toISOString(),
          level:      e.level || e.type || "INFO",
          source:     e.source || "sentineltwin",
          message:    e.message || e.msg || "",
        }));
      if (!newEntries.length) return prev;
      return [...prev, ...newEntries].slice(-1000);
    });
  }, [eventLog]);

  // Auto-scroll to bottom
  useEffect(() => {
    if (autoScroll && bottomRef.current) {
      bottomRef.current.scrollIntoView({ behavior:"smooth" });
    }
  }, [logs, autoScroll]);

  const filtered = useMemo(() => {
    return logs.filter(l => {
      const levelOk  = levelFilter === "ALL" || l.level === levelFilter;
      const searchOk = !search || l.message?.toLowerCase().includes(search.toLowerCase())
                               || l.source?.toLowerCase().includes(search.toLowerCase());
      return levelOk && searchOk;
    });
  }, [logs, levelFilter, search]);

  const handleExport = () => {
    const text = filtered
      .map(l => `${l.timestamp} [${l.level}] ${l.source}: ${l.message}`)
      .join("\n");
    const blob = new Blob([text], { type:"text/plain" });
    const url  = URL.createObjectURL(blob);
    const a    = document.createElement("a");
    a.href     = url;
    a.download = `sentineltwin-logs-${new Date().toISOString().slice(0,10)}.txt`;
    a.click();
    URL.revokeObjectURL(url);
  };

  return (
    <div style={{ flex:1, overflow:"hidden", display:"flex",
                  flexDirection:"column", padding:12, ...mono }}>
      <SectionHeader title="OPERATIONAL LOGS — LIVE SYSTEM EVENT STREAM" />

      {/* Controls */}
      <div style={{ display:"flex", gap:8, marginBottom:8, flexWrap:"wrap", alignItems:"center" }}>
        <select value={levelFilter} onChange={e => setLevelFilter(e.target.value)}
          style={{ background:"#0a1628", border:"1px solid #1e3a5f", color:"#c8d6e5",
                   fontSize:10, padding:"4px 8px", fontFamily:"IBM Plex Mono, monospace" }}>
          {LEVELS.map(l => <option key={l} value={l}>{l}</option>)}
        </select>
        <input value={search} onChange={e => setSearch(e.target.value)}
          placeholder="FILTER LOGS..."
          style={{ background:"#0a1628", border:"1px solid #1e3a5f", color:"#c8d6e5",
                   fontSize:10, padding:"4px 8px", width:200,
                   fontFamily:"IBM Plex Mono, monospace" }} />
        <label style={{ fontSize:9, color:C.dim, letterSpacing:2, display:"flex",
                        alignItems:"center", gap:4, cursor:"pointer" }}>
          <input type="checkbox" checked={autoScroll}
            onChange={e => setAutoScroll(e.target.checked)} />
          AUTO-SCROLL
        </label>
        <button onClick={handleExport}
          style={{ marginLeft:"auto", fontSize:9, letterSpacing:2, padding:"4px 12px",
                   background:"transparent", border:"1px solid #1e3a5f",
                   color:C.dim, cursor:"pointer", fontFamily:"IBM Plex Mono, monospace" }}>
          EXPORT .TXT
        </button>
        <span style={{ fontSize:9, color:C.dim, letterSpacing:1 }}>
          {filtered.length} / {logs.length} lines
        </span>
      </div>

      {/* Log table */}
      <div style={{ flex:1, overflow:"auto", fontSize:10, lineHeight:1.6 }}>
        {/* Header */}
        <div style={{ display:"grid", gridTemplateColumns:"160px 80px 140px 1fr",
                      fontSize:8, letterSpacing:2, color:C.dim, padding:"3px 0",
                      borderBottom:"1px solid #1e3a5f", position:"sticky", top:0,
                      background:"#060d1a" }}>
          {["UTC","LEVEL","SOURCE","MESSAGE"].map(h =>
            <span key={h}>{h}</span>
          )}
        </div>

        {filtered.length === 0 ? (
          <div style={{ color:C.dim, fontSize:10, padding:"24px 0", textAlign:"center",
                        letterSpacing:2 }}>
            NO LOGS — SYSTEM INITIALIZING...
          </div>
        ) : filtered.map((log, i) => (
          <div key={log.id || i}
            style={{
              display:"grid", gridTemplateColumns:"160px 80px 140px 1fr",
              padding:"2px 0", borderBottom:"1px solid rgba(30,58,95,0.2)",
              background: log.level === "ERROR"    ? "rgba(226,75,74,0.05)"
                        : log.level === "CRITICAL" ? "rgba(255,0,0,0.08)"
                        : log.level === "WARNING"  ? "rgba(239,159,39,0.04)"
                        : "transparent",
            }}>
            <span style={{ color:"#37474f", fontSize:9 }}>
              {log.timestamp?.slice(0,19).replace("T"," ")}Z
            </span>
            <span style={{ color: LEVEL_COLOR[log.level] || C.text,
                           fontWeight: log.level === "ERROR" || log.level === "CRITICAL"
                                       ? 700 : 400 }}>
              {log.level}
            </span>
            <span style={{ color:"#546e7a", overflow:"hidden",
                           textOverflow:"ellipsis", whiteSpace:"nowrap" }}>
              {log.source}
            </span>
            <span style={{ color: log.level === "ERROR"    ? "#E24B4A"
                                 : log.level === "WARNING" ? "#EF9F27"
                                 : C.text,
                           overflow:"hidden", textOverflow:"ellipsis", whiteSpace:"nowrap" }}>
              {log.message}
            </span>
          </div>
        ))}
        <div ref={bottomRef} />
      </div>
    </div>
  );
}

// ═════════════════════════════════════════════════════════════
// REDUNDANCY MATRIX PANEL — 2oo3 VOTING — LIVE API DATA
// ═════════════════════════════════════════════════════════════
export function RedundancyMatrixPanel() {
  const [groups, setGroups]       = useState([]);
  const [ataFilter, setAtaFilter] = useState("");
  const [loading, setLoading]     = useState(true);
  const token = typeof localStorage !== "undefined"
    ? localStorage.getItem("st_token") || "" : "";

  const ATA_OPTIONS = [21,22,24,27,28,29,30,31,32,34,36,49,52,71];
  const STATE_COLOR = {
    HEALTHY:"#1D9E75", DEGRADED:"#EF9F27", FAILED:"#E24B4A",
    DESYNCHRONIZED:"#e040fb", STALE:"#90a4ae", SPOOFED:"#ff6d00",
  };
  const METHOD_COLOR = {
    TRIPLEX_AGREE:"#1D9E75", "2oo3_MAJORITY":"#EF9F27",
    BYZANTINE:"#E24B4A", DUPLEX:"#378ADD", UNKNOWN:"#546e7a",
  };

  const fetchGroups = useCallback(() => {
    const url = ataFilter
      ? `/api/v1/sensors/redundancy?ata_chapter=${ataFilter}`
      : "/api/v1/sensors/redundancy";
    fetch(url, { headers:{ Authorization:`Bearer ${token}` } })
      .then(r => r.ok ? r.json() : null)
      .then(d => { if (d?.groups) { setGroups(d.groups); setLoading(false); } })
      .catch(() => setLoading(false));
  }, [ataFilter, token]);

  useEffect(() => {
    fetchGroups();
    const iv = setInterval(fetchGroups, 2000);
    return () => clearInterval(iv);
  }, [fetchGroups]);

  return (
    <div style={{ flex:1, overflow:"hidden", display:"flex", flexDirection:"column",
                  padding:12, ...mono }}>
      <SectionHeader title="REDUNDANCY MATRIX — 2oo3 VOTING — BYZANTINE FAULT DETECTION" />

      {/* Filter + stats */}
      <div style={{ display:"flex", gap:8, marginBottom:8, alignItems:"center" }}>
        <select value={ataFilter} onChange={e => setAtaFilter(e.target.value)}
          style={{ background:"#0a1628", border:"1px solid #1e3a5f", color:"#c8d6e5",
                   fontSize:10, padding:"4px 8px", fontFamily:"IBM Plex Mono, monospace" }}>
          <option value="">ALL ATA</option>
          {ATA_OPTIONS.map(a => <option key={a} value={a}>ATA {a}</option>)}
        </select>
        <span style={{ fontSize:9, color:C.dim, letterSpacing:2 }}>
          {groups.length} REDUNDANCY GROUPS
        </span>
        {groups.some(g => g.vote?.byzantine_fault) && (
          <span style={{ fontSize:9, letterSpacing:2, color:"#E24B4A", fontWeight:700,
                         padding:"2px 8px", border:"1px solid #E24B4A" }}>
            ⚠ BYZANTINE FAULT DETECTED
          </span>
        )}
        <button onClick={fetchGroups}
          style={{ marginLeft:"auto", fontSize:9, letterSpacing:2, padding:"3px 10px",
                   background:"transparent", border:"1px solid #1e3a5f",
                   color:C.dim, cursor:"pointer", fontFamily:"IBM Plex Mono, monospace" }}>
          REFRESH
        </button>
      </div>

      {/* Groups grid */}
      <div style={{ flex:1, overflow:"auto" }}>
        {loading ? (
          <div style={{ color:C.dim, textAlign:"center", padding:24, letterSpacing:2 }}>
            LOADING REDUNDANCY DATA...
          </div>
        ) : groups.length === 0 ? (
          <div style={{ color:C.dim, textAlign:"center", padding:24, letterSpacing:2 }}>
            NO REDUNDANCY GROUPS — SELECT ATA CHAPTER ABOVE
          </div>
        ) : (
          <div style={{ display:"grid", gridTemplateColumns:"repeat(auto-fill, minmax(300px, 1fr))",
                        gap:8 }}>
            {groups.map(g => (
              <div key={g.group_id}
                style={{ background:"#080f20", border:`1px solid ${
                  g.vote?.byzantine_fault ? "#E24B4A" : "#1e3a5f"
                }`, padding:"10px 12px" }}>

                {/* Group header */}
                <div style={{ display:"flex", justifyContent:"space-between",
                               marginBottom:8, fontSize:9, letterSpacing:2 }}>
                  <span style={{ color:C.blue }}>{g.group_id}</span>
                  <span style={{ color:C.dim }}>ATA {g.ata_chapter}</span>
                  <span style={{ color: METHOD_COLOR[g.vote?.method] || C.dim }}>
                    {g.vote?.method || "—"}
                  </span>
                </div>

                {/* Channel columns */}
                <div style={{ display:"grid",
                               gridTemplateColumns: `repeat(${g.channel_count}, 1fr)`,
                               gap:4, marginBottom:8 }}>
                  {g.channels.map(ch => (
                    <div key={ch.index}
                      style={{ background:"rgba(0,180,255,0.04)",
                               border:`1px solid ${
                                 g.vote?.failed_channels?.includes(ch.index)
                                   ? "#E24B4A" : "#1e3a5f"
                               }`,
                               padding:"6px 8px", textAlign:"center" }}>
                      <div style={{ fontSize:8, color:C.dim, letterSpacing:2,
                                    marginBottom:3 }}>CH{ch.index + 1}</div>
                      <div style={{ fontSize:11, color: STATE_COLOR[ch.state] || C.text,
                                    fontWeight:700 }}>
                        {typeof ch.value === "number" ? ch.value.toFixed(2) : "—"}
                      </div>
                      <div style={{ fontSize:8, color:C.dim }}>{ch.unit}</div>
                      <div style={{ fontSize:8, color: STATE_COLOR[ch.state] || C.dim,
                                    marginTop:2 }}>{ch.state}</div>
                    </div>
                  ))}
                </div>

                {/* Voted value */}
                {g.vote && (
                  <div style={{ borderTop:"1px solid #1e3a5f", paddingTop:6 }}>
                    <div style={{ display:"flex", justifyContent:"space-between",
                                   fontSize:9 }}>
                      <span style={{ color:C.dim, letterSpacing:2 }}>VOTED VALUE</span>
                      <span style={{ color: g.vote.byzantine_fault ? "#E24B4A" : C.green }}>
                        {g.vote.voted_value ?? "—"}
                      </span>
                    </div>
                    <div style={{ display:"flex", justifyContent:"space-between",
                                   fontSize:9, marginTop:3 }}>
                      <span style={{ color:C.dim, letterSpacing:2 }}>CONFIDENCE</span>
                      <span style={{ color: g.vote.confidence >= 0.9 ? C.green
                                          : g.vote.confidence >= 0.6 ? C.amber : C.red }}>
                        {g.vote.confidence != null ? `${(g.vote.confidence*100).toFixed(1)}%` : "—"}
                      </span>
                    </div>
                    {/* Confidence bar */}
                    <div style={{ height:3, background:"#1e3a5f", borderRadius:2,
                                   marginTop:4, overflow:"hidden" }}>
                      <div style={{ height:"100%", borderRadius:2,
                                     width:`${(g.vote.confidence || 0) * 100}%`,
                                     background: g.vote.byzantine_fault ? "#E24B4A"
                                               : g.vote.confidence >= 0.9 ? "#1D9E75" : "#EF9F27",
                                     transition:"width 0.4s" }} />
                    </div>
                  </div>
                )}
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
