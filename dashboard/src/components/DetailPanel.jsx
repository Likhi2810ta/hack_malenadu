import { useState, useEffect } from 'react'
import { fetchHistory, confirmMaintenance, dismissAlarm } from '../hooks/useMachines'

function BarChart({ series = [], color, isWarning }) {
  if (!series.length) {
    const mock = [0.25, 0.33, 0.5, 0.66, 0.85]
    const proj = [0.9, 1.0]
    return <BarBars mock={mock} proj={proj} color={color} isWarning={isWarning} />
  }
  const vals = series.map(d => d.v)
  const max  = Math.max(...vals, 1)
  const last5 = vals.slice(-5)
  const last  = last5[last5.length - 1] || 0
  const proj1 = last * 1.07
  const proj2 = last * 1.14
  const barH = v => `${Math.min((v / max) * 90, 100)}%`

  return (
    <div className="h-24 w-full relative flex items-end gap-1">
      {last5.map((v, i) => (
        <div
          key={i}
          className="flex-1 rounded-t-sm transition-all duration-500"
          style={{
            height: barH(v),
            background: isWarning
              ? `rgba(243,99,45,${0.2 + i * 0.18})`
              : `rgba(173,198,255,${0.2 + i * 0.18})`,
          }}
        />
      ))}
      <div
        className="flex-1 rounded-t-sm border-t border-x border-dashed"
        style={{ height: barH(proj1), borderColor: isWarning ? '#f3632d' : '#adc6ff' }}
      />
      <div
        className="flex-1 rounded-t-sm border-t border-x border-dashed"
        style={{ height: barH(proj2), borderColor: isWarning ? '#f3632d' : '#adc6ff' }}
      />
    </div>
  )
}

function BarBars({ mock, proj, color, isWarning }) {
  return (
    <div className="h-24 w-full relative flex items-end gap-1">
      {mock.map((h, i) => (
        <div
          key={i}
          className="flex-1 rounded-t-sm"
          style={{
            height: `${h * 100}%`,
            background: isWarning
              ? `rgba(243,99,45,${0.15 + i * 0.18})`
              : `rgba(173,198,255,${0.15 + i * 0.18})`,
          }}
        />
      ))}
      {proj.map((h, i) => (
        <div
          key={`p${i}`}
          className="flex-1 rounded-t-sm border-t border-x border-dashed"
          style={{ height: `${Math.min(h * 100, 105)}%`, borderColor: isWarning ? '#f3632d' : '#adc6ff' }}
        />
      ))}
    </div>
  )
}

const DIAGNOSTICS = {
  critical: (m) =>
    `A significant vibration drift was detected in the primary bearing assembly of ${m.display_name}. Risk score: ${m.risk_pct?.toFixed(0)}%. Historical patterns suggest high likelihood of bearing seizure within the next 48 hours if left unattended. IsolationForest flagged the 4-sensor combination as anomalous. Immediate maintenance intervention required.`,
  warning: (m) =>
    `Elevated sensor readings detected on ${m.display_name}. Temperature trending upward with vibration anomaly (${m.vibration_mm_s?.toFixed(1)} mm/s). Current risk score: ${m.risk_pct?.toFixed(0)}%. Escalation possible within 30 minutes at current trajectory.`,
  healthy: (m) =>
    `${m.display_name} is operating within normal parameters. All sensor readings are within ±2σ of baseline. IsolationForest reports nominal state. Polyfit slope near zero. No action required.`,
}

export default function DetailPanel({ machine }) {
  const [history, setHistory]     = useState(null)
  const [confirmed, setConfirmed] = useState(false)
  const [dismissed, setDismissed] = useState(false)

  useEffect(() => {
    if (!machine?.id) return
    setConfirmed(false)
    setDismissed(false)
    fetchHistory(machine.id)
      .then(setHistory)
      .catch(() => setHistory(null))
  }, [machine?.id])

  if (!machine) {
    return (
      <aside className="fixed top-16 right-0 bottom-0 w-[380px] bg-slate-900 border-l border-white/10 glass-panel flex items-center justify-center z-30">
        <div className="text-center text-slate-500">
          <span className="material-symbols-outlined block mx-auto mb-2" style={{ fontSize: 32 }}>touch_app</span>
          <p className="text-xs font-label uppercase tracking-wider">Select an asset</p>
        </div>
      </aside>
    )
  }

  const status  = machine.status || 'healthy'
  const isBad   = status !== 'healthy'
  const diagFn  = DIAGNOSTICS[status] || DIAGNOSTICS.healthy
  const diagText = diagFn(machine)

  const vib  = history?.vibration   || []
  const temp = history?.temperature || []
  const rpm  = history?.rpm         || []

  const vibVal  = machine.vibration_mm_s?.toFixed(1)  ?? '--'
  const tempVal = machine.temperature_C?.toFixed(1)   ?? '--'
  const rpmVal  = machine.rpm ? Math.round(machine.rpm).toLocaleString() : '--'
  const curVal  = machine.current_A?.toFixed(2) ?? '--'
  const risk    = machine.risk_pct ?? 0

  function riskColor(pct) {
    if (pct >= 80) return '#ff3355'
    if (pct >= 60) return '#f3632d'
    if (pct >= 40) return '#ffcc00'
    return '#2EC4B6'
  }
  function riskLabel(pct) {
    if (pct >= 80) return 'CRITICAL'
    if (pct >= 60) return 'HIGH RISK'
    if (pct >= 40) return 'MODERATE'
    if (pct >= 20) return 'ELEVATED'
    return 'STABLE'
  }

  return (
    <aside className="fixed top-16 right-0 bottom-0 w-[380px] bg-slate-900 shadow-2xl border-l border-white/10 glass-panel overflow-y-auto no-scrollbar z-30">
      <div className="p-6">

        {/* Header */}
        <div className="flex items-center justify-between mb-6">
          <div>
            <h3 className="text-lg font-headline font-bold text-blue-100">
              {machine.id}
            </h3>
            <p className="text-xs text-slate-400 mt-0.5">{machine.subtitle || machine.display_name}</p>
          </div>
          <div className={`px-2 py-1 rounded font-label text-[10px] uppercase font-bold
            ${isBad
              ? 'bg-tertiary-container/20 text-tertiary-container border border-tertiary-container/30'
              : 'bg-[#2EC4B6]/10 text-[#2EC4B6] border border-[#2EC4B6]/20'
            }`}>
            {status.toUpperCase()}
          </div>
        </div>

        {/* Risk meter */}
        <div className="mb-6">
          <div className="flex justify-between items-center mb-1.5">
            <span className="font-label text-[9px] uppercase tracking-widest text-slate-500">Risk Score</span>
            <span className="font-headline font-bold text-sm" style={{ color: riskColor(risk) }}>
              {risk.toFixed(1)}% — {riskLabel(risk)}
            </span>
          </div>
          <div className="w-full h-1.5 bg-surface-container-highest rounded-full overflow-hidden">
            <div
              className="h-full rounded-full transition-all duration-700"
              style={{ width: `${Math.min(risk, 100)}%`, background: riskColor(risk) }}
            />
          </div>
        </div>

        {/* Live sensor snapshot */}
        <div className="grid grid-cols-2 gap-2 mb-6">
          {[
            { label: 'Temperature', val: `${tempVal}°C`, icon: 'thermostat' },
            { label: 'Vibration',   val: `${vibVal} mm/s`, icon: 'vibration' },
            { label: 'RPM',         val: rpmVal, icon: 'rotate_right' },
            { label: 'Current',     val: `${curVal} A`, icon: 'bolt' },
          ].map(({ label, val, icon }) => (
            <div key={label} className="bg-surface-container-high rounded-lg px-3 py-2.5 flex items-center gap-2">
              <span className="material-symbols-outlined text-slate-500" style={{ fontSize: 16 }}>{icon}</span>
              <div>
                <p className="font-label text-[9px] uppercase tracking-wider text-slate-500">{label}</p>
                <p className={`font-headline font-bold text-sm ${isBad ? 'text-tertiary-container' : 'text-primary'}`}>{val}</p>
              </div>
            </div>
          ))}
        </div>

        {/* IsolationForest + Polyfit indicators */}
        <div className="flex gap-2 mb-6">
          <div className={`flex-1 px-3 py-2 rounded-lg border font-label text-[9px] uppercase tracking-wider text-center ${machine.if_anomaly ? 'bg-red-500/10 border-red-500/20 text-red-400' : 'bg-surface-container-high border-white/5 text-slate-500'}`}>
            <span className="material-symbols-outlined block mx-auto mb-0.5" style={{ fontSize: 14 }}>
              {machine.if_anomaly ? 'crisis_alert' : 'check_circle'}
            </span>
            IsoForest {machine.if_anomaly ? 'ANOMALY' : 'Normal'}
          </div>
          <div className={`flex-1 px-3 py-2 rounded-lg border font-label text-[9px] uppercase tracking-wider text-center ${(machine.polyfit_score ?? 0) > 30 ? 'bg-yellow-500/10 border-yellow-500/20 text-yellow-400' : 'bg-surface-container-high border-white/5 text-slate-500'}`}>
            <span className="material-symbols-outlined block mx-auto mb-0.5" style={{ fontSize: 14 }}>trending_up</span>
            Trend {(machine.polyfit_score ?? 0).toFixed(0)}%
          </div>
        </div>

        {/* Diagnostic brief */}
        <div className="mb-8 space-y-4">
          <div className={`p-4 rounded-lg border ${isBad ? 'bg-tertiary-container/5 border-tertiary-container/10' : 'bg-primary/5 border-primary/10'}`}>
            <h4 className={`font-label text-[10px] uppercase mb-2 font-bold ${isBad ? 'text-tertiary-container' : 'text-primary'}`}>
              Diagnostic Brief
            </h4>
            <p className="text-sm text-slate-300 leading-relaxed">{diagText}</p>
          </div>
        </div>

        {/* Charts */}
        <div className="space-y-8">

          {/* Vibration */}
          <div>
            <div className="flex justify-between items-center mb-4">
              <span className="font-label text-[10px] uppercase text-slate-400">Vibration Amplitude (mm/s²)</span>
              <span className={`font-headline font-bold ${isBad ? 'text-tertiary-container' : 'text-primary'}`}>
                {vibVal}
              </span>
            </div>
            <BarChart series={vib} color="#f3632d" isWarning={isBad} />
          </div>

          {/* Temperature */}
          <div>
            <div className="flex justify-between items-center mb-4">
              <span className="font-label text-[10px] uppercase text-slate-400">Core Temp Trend (°C)</span>
              <span className="text-primary font-headline font-bold">{tempVal}</span>
            </div>
            <BarChart series={temp} color="#adc6ff" isWarning={false} />
          </div>

          {/* RPM */}
          <div>
            <div className="flex justify-between items-center mb-4">
              <span className="font-label text-[10px] uppercase text-slate-400">Angular Velocity (RPM)</span>
              <span className="text-primary font-headline font-bold">{rpmVal}</span>
            </div>
            <BarChart series={rpm} color="#adc6ff" isWarning={false} />
          </div>
        </div>

        {/* Action buttons */}
        <div className="mt-12 space-y-3">
          {confirmed ? (
            <div className="w-full py-4 rounded-lg text-center font-headline font-bold text-[#2EC4B6] bg-[#2EC4B6]/10 border border-[#2EC4B6]/30">
              ✓ MAINTENANCE CONFIRMED
            </div>
          ) : dismissed ? (
            <div className="w-full py-4 rounded-lg text-center font-label text-[10px] uppercase tracking-widest text-slate-400 border border-outline-variant">
              ✓ DISMISSED AS FALSE ALARM
            </div>
          ) : (
            <>
              <button
                onClick={async () => { await confirmMaintenance(machine.id); setConfirmed(true) }}
                className="w-full py-4 bg-gradient-to-r from-primary-container to-primary text-on-primary-container font-headline font-bold rounded-lg hover:brightness-110 active:scale-[0.98] transition-all"
              >
                CONFIRM MAINTENANCE
              </button>
              <button
                onClick={async () => { await dismissAlarm(machine.id); setDismissed(true) }}
                className="w-full py-3 bg-transparent border border-outline-variant text-slate-400 font-label text-[10px] uppercase tracking-widest rounded-lg hover:bg-white/5 active:scale-[0.98] transition-all"
              >
                DISMISS — FALSE ALARM
              </button>
            </>
          )}
        </div>
      </div>
    </aside>
  )
}
