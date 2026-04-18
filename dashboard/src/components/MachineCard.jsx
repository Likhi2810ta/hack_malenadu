function riskLabel(pct) {
  if (pct >= 80) return { text: 'CRITICAL RISK', color: '#ff3355' }
  if (pct >= 60) return { text: 'HIGH RISK',     color: '#f3632d' }
  if (pct >= 40) return { text: 'MODERATE',      color: '#ffcc00' }
  if (pct >= 20) return { text: 'ELEVATED',       color: '#adc6ff' }
  return            { text: 'STABLE',             color: '#2EC4B6' }
}

const STATUS = {
  healthy:  { badge: 'HEALTHY',  badgeCls: 'bg-[#2EC4B6]/10 text-[#2EC4B6] border border-[#2EC4B6]/20', glow: 'industrial-glow-healthy', card: 'bg-surface-container-low hover:bg-surface-container-high', metricCls: 'text-primary' },
  warning:  { badge: 'WARNING',  badgeCls: 'bg-tertiary-container/10 text-tertiary-container border border-tertiary-container/20', glow: 'industrial-glow-warning', card: 'bg-surface-container-high ring-1 ring-tertiary-container/40 border border-tertiary-container/20 scale-[1.02]', metricCls: 'text-tertiary-container font-bold' },
  critical: { badge: 'CRITICAL', badgeCls: 'bg-red-500/10 text-red-400 border border-red-500/20', glow: 'industrial-glow-warning', card: 'bg-surface-container-high ring-2 ring-red-500/50 border border-red-500/30 scale-[1.02]', metricCls: 'text-red-400 font-bold' },
}

function metricLabel(machine) {
  const id = machine.id
  if (id === 'CNC_01') return [
    { label: 'TEMP',       val: `${machine.temperature_C?.toFixed(1) ?? '--'}°C` },
    { label: 'LOAD',       val: `${machine.risk_pct?.toFixed(1) ?? '--'}%` },
    { label: 'EFFICIENCY', val: machine.status === 'healthy' ? '99.8%' : `${Math.max(40, 100 - machine.risk_pct).toFixed(0)}%` },
  ]
  if (id === 'CNC_02') return [
    { label: 'AXIS 1',  val: `${(machine.vibration_mm_s / 1000).toFixed(3)}mm` },
    { label: 'TORQUE',  val: `${machine.current_A?.toFixed(1) ?? '--'} Nm` },
    { label: 'UPTIME',  val: machine.status === 'healthy' ? '1.2k HRS' : '0.9k HRS' },
  ]
  if (id === 'PUMP_03') return [
    { label: 'VIBRATION', val: `${machine.vibration_mm_s?.toFixed(1) ?? '--'} mm/s²` },
    { label: 'RPM',        val: machine.rpm ? Math.round(machine.rpm).toLocaleString() : '--' },
    { label: 'TEMP',       val: `${machine.temperature_C?.toFixed(1) ?? '--'}°C` },
  ]
  return [
    { label: 'PPM',         val: '0.04' },
    { label: 'AIRFLOW',     val: '450 m³/h' },
    { label: 'FILTER LIFE', val: `${Math.max(60, 100 - (machine.risk_pct ?? 0) * 0.5).toFixed(0)}%` },
  ]
}

export default function MachineCard({ machine, isSelected, onClick }) {
  const status  = machine.status || 'healthy'
  const cfg     = STATUS[status] || STATUS.healthy
  const isBad   = status !== 'healthy'
  const metrics = metricLabel(machine)
  const risk    = machine.risk_pct ?? 0
  const rl      = riskLabel(risk)

  return (
    <div
      onClick={onClick}
      className={`relative rounded-lg p-6 overflow-hidden transition-all cursor-pointer ${cfg.card} ${cfg.glow} ${isSelected ? 'ring-2 ring-blue-400/60' : ''}`}
    >
      {/* Predictive drift badge */}
      {isBad && (
        <div className="absolute top-4 right-4 z-20">
          <div className="bg-tertiary-container/90 backdrop-blur-md px-3 py-2 rounded-lg flex items-center gap-2 shadow-xl shadow-black/40">
            <span className="material-symbols-outlined text-on-tertiary-container" style={{ fontSize: 18 }}>warning</span>
            <div className="text-[10px] font-headline font-bold text-on-tertiary-container leading-tight">
              <span className="block">PREDICTIVE DRIFT</span>
              <span>{risk.toFixed(0)}% {rl.text}</span>
            </div>
          </div>
        </div>
      )}

      {/* Header */}
      <div className="flex justify-between items-start mb-6">
        <div>
          <h3 className="text-xl font-headline font-bold text-on-surface tracking-tight">{machine.id}</h3>
          <p className="text-[11px] text-slate-400 mt-0.5">{machine.subtitle || machine.display_name}</p>
          {machine.location && (
            <p className="text-[10px] text-slate-600 mt-0.5 font-label uppercase tracking-wider">{machine.location}</p>
          )}
        </div>
        <div className={`px-2 py-1 rounded font-label text-[10px] uppercase ${cfg.badgeCls}`}>
          {cfg.badge}
        </div>
      </div>

      {/* Machine image */}
      <div className="aspect-video bg-surface-container-lowest rounded overflow-hidden mb-4 relative group">
        <img
          className={`w-full h-full object-cover transition-opacity duration-300 ${isBad ? 'opacity-100' : 'opacity-60 group-hover:opacity-100'}`}
          src={machine.image}
          alt={machine.display_name}
        />
        <div className="absolute inset-0 bg-gradient-to-t from-surface-container-lowest to-transparent" />
      </div>

      {/* Risk score bar */}
      <div className="mb-5">
        <div className="flex justify-between items-center mb-1.5">
          <span className="font-label text-[9px] uppercase tracking-widest text-slate-500">Risk Score</span>
          <span className="font-headline font-bold text-xs" style={{ color: rl.color }}>
            {risk.toFixed(1)}% — {rl.text}
          </span>
        </div>
        <div className="w-full h-1 bg-surface-container-highest rounded-full overflow-hidden">
          <div
            className="h-full rounded-full transition-all duration-700"
            style={{ width: `${Math.min(risk, 100)}%`, background: rl.color }}
          />
        </div>
      </div>

      {/* Sensor metrics */}
      <div className="grid grid-cols-3 gap-4 font-label text-[10px] uppercase tracking-tighter text-slate-400">
        {metrics.map(({ label, val }) => (
          <div key={label} className="space-y-1">
            <span className="block">{label}</span>
            <span className={`text-lg font-headline ${cfg.metricCls}`}>{val}</span>
          </div>
        ))}
      </div>

      {/* IsolationForest / Polyfit badges */}
      {(machine.if_anomaly || (machine.polyfit_score ?? 0) > 20) && (
        <div className="mt-4 flex gap-2 flex-wrap">
          {machine.if_anomaly && (
            <span className="px-2 py-0.5 rounded bg-red-500/10 border border-red-500/20 font-label text-[9px] uppercase tracking-wider text-red-400">
              IF Anomaly
            </span>
          )}
          {(machine.polyfit_score ?? 0) > 20 && (
            <span className="px-2 py-0.5 rounded bg-yellow-500/10 border border-yellow-500/20 font-label text-[9px] uppercase tracking-wider text-yellow-400">
              Trend {machine.polyfit_score?.toFixed(0)}%
            </span>
          )}
        </div>
      )}
    </div>
  )
}
