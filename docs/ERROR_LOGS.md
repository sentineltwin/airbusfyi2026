# SentinelTwin — Error Logs & Fix History

**Last scanned:** `2026-05-24T08:53:00Z`  
**Status:** ✅ NO ACTIVE ERRORS

---

## Current System Status

| Service | Status | URL |
|---------|--------|-----|
| Backend API | ✅ OPERATIONAL | http://localhost:8000 |
| Frontend UI | ✅ OPERATIONAL | http://localhost:5173 |
| WebSocket | ✅ RUNNING | ws://localhost:8000/ws/telemetry |
| Digital Twin Engine | ✅ RUNNING at 10 Hz | — |
| ECAM Engine | ✅ RUNNING | — |
| AI Autoencoder | ✅ Warm-up complete | — |

---

## Bug Fix History (2026-05-21 → 2026-05-24)

### Frontend — Field Name Bugs (Fixed 2026-05-21)

| File | Line | Bug | Fix |
|------|------|-----|-----|
| `SentinelTwin.jsx` | 984 | `s.sensor_state` — field doesn't exist (should be `s.state`) | `(s.state \|\| s.sensor_state)` |
| `SentinelTwin.jsx` | 1061-1062 | `VIRT_STATE_COLORS[s.sensor_state]` — always `undefined`, STATE column blank | `(s.state \|\| s.sensor_state)` |
| `SentinelTwin.jsx` | 368-374 | ECAM messages not normalized — WS store uses `severity/message/system/ata_chapter` but all render code uses `sev/msg/sys/ata` | Added `ecamNormalize` useMemo normalizer |
| `SentinelTwin.jsx` | 1104 | `let angle = 0` — declared but never used | Removed dead variable |

### Frontend — Crash-Risk Patterns (Fixed 2026-05-24)

| File | Line | Bug | Fix |
|------|------|-----|-----|
| `SentinelTwinPanels.jsx` | 610 | `Math.max(...[])` on empty `displayVLs` → returns `-Infinity` | Guard: `displayVLs.length ? Math.max(...) : 0` |
| `SentinelTwinPanels.jsx` | 611 | `reduce / displayVLs.length` → `NaN` when array empty | Guard: `/ (displayVLs.length \|\| 1)` |
| `SentinelTwinPanels.jsx` | 501 | `avgH.toFixed(1)` — `avgH` could be `NaN` if `health` field missing | Guard: `(avgH\|\|0).toFixed(1)` |

### Build Verification

```
vite v5.4.21 building for development...
✓ 48 modules transformed.
✓ built in 1.55s
0 errors  |  0 warnings
```

---

## Error Categories (Reference)

| Code | Category | Resolution |
|------|----------|------------|
| `SENSOR_ENGINE_NOT_READY` | Engine not initialized | Wait for startup; check logs |
| `TOKEN_EXPIRED` | JWT expired | Re-login or use refresh endpoint |
| `BRUTE_FORCE_LOCKOUT` | Too many auth failures | Wait 5 minutes |
| `ACCOUNT_LOCKED` | Account locked after 5 failures | Admin must unlock |
| `DISPATCH_NOT_AUTHORIZED` | GO checks failed | Review checklist items |

---

## Auto-Bug Fix (LAUNCH.bat / LAUNCH.ps1)

| Issue | Auto-Fix |
|-------|---------|
| Port conflict (8000/5173) | Kill stale process via PowerShell `Get-NetTCPConnection` |
| Missing `node_modules` | Run `npm install --no-audit --no-fund` |
| Services slow to start | Wait loop polls every 2s, up to 90s |
| Browser launch | `start "" http://localhost:5173` after services ready |

---

*Updated 2026-05-24T08:53:00Z — SentinelTwin v4.4.0*
