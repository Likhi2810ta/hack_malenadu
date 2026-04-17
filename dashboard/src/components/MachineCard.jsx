const STATUS = {
  healthy:  { badge: 'HEALTHY',  badgeCls: 'bg-[#2EC4B6]/10 text-[#2EC4B6] border border-[#2EC4B6]/20', glow: 'industrial-glow-healthy', card: 'bg-surface-container-low hover:bg-surface-container-high', metricCls: 'text-primary' },
  warning:  { badge: 'WARNING',  badgeCls: 'bg-tertiary-container/10 text-tertiary-container border border-tertiary-container/20', glow: 'industrial-glow-warning', card: 'bg-surface-container-high ring-1 ring-tertiary-container/40 border border-tertiary-container/20 scale-[1.02]', metricCls: 'text-tertiary-container font-bold' },
  critical: { badge: 'CRITICAL', badgeCls: 'bg-tertiary-container/10 text-tertiary-container border border-tertiary-container/20', glow: 'industrial-glow-warning', card: 'bg-surface-container-high ring-1 ring-tertiary-container/40 border border-tertiary-container/20 scale-[1.02]', metricCls: 'text-tertiary-container font-bold' },
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
    { label: 'FILTER LIFE', val: `${Math.max(60, 100 - machine.risk_pct * 0.5).toFixed(0)}%` },
  ]
}

export default function MachineCard({ machine, isSelected, onClick }) {
  const status = machine.status || 'healthy'
  const cfg    = STATUS[status] || STATUS.healthy
  const isBad  = status !== 'healthy'
  const metrics = metricLabel(machine)

  return (
    <div
      onClick={onClick}
      className={`relative rounded-lg p-6 overflow-hidden transition-all cursor-pointer ${cfg.card} ${cfg.glow} ${isSelected ? 'ring-2 ring-blue-400/60' : ''}`}
    >
      {/* Predictive drift badge (warning/critical only) */}
      {isBad && (
        <div className="absolute top-4 right-4 z-20">
          <div className="bg-tertiary-container/90 backdrop-blur-md px-3 py-2 rounded-lg flex items-center gap-2 shadow-xl shadow-black/40">
            <span className="material-symbols-outlined text-on-tertiary-container" style={{ fontSize: 18 }}>warning</span>
            <div className="text-[10px] font-headline font-bold text-on-tertiary-container leading-tight">
              <span className="block">PREDICTIVE DRIFT</span>
              <span>{machine.risk_pct?.toFixed(0) ?? '--'}% CRITICAL RISK</span>
            </div>
          </div>
        </div>
      )}

      {/* Header */}
      <div className="flex justify-between items-start mb-6">
        <div>
          <span className="font-label text-[10px] uppercase tracking-widest text-primary font-bold">
            ASSET: {machine.asset_id}
          </span>
          <h3 className="text-xl font-headline font-semibold text-on-surface">{machine.display_name}</h3>
          {machine.location && (
            <p className="text-[10px] text-slate-500 mt-0.5">{machine.location}</p>
          )}
        </div>
        <div className={`px-2 py-1 rounded font-label text-[10px] uppercase ${cfg.badgeCls}`}>
          {cfg.badge}
        </div>
      </div>

      {/* Machine image */}
      <div className="aspect-video bg-surface-container-lowest rounded overflow-hidden mb-6 relative group">
        <img
          className={`w-full h-full object-cover transition-opacity duration-300 ${isBad ? 'opacity-100' : 'opacity-60 group-hover:opacity-100'}`}
          src={machine.image}
          alt={machine.display_name}
        />
        <div className="absolute inset-0 bg-gradient-to-t from-surface-container-lowest to-transparent" />
      </div>

      {/* Metrics */}
      <div className="grid grid-cols-3 gap-4 font-label text-[10px] uppercase tracking-tighter text-slate-400">
        {metrics.map(({ label, val }) => (
          <div key={label} className="space-y-1">
            <span className="block">{label}</span>
            <span className={`text-lg font-headline ${cfg.metricCls}`}>{val}</span>
          </div>
        ))}
      </div>
    </div>
  )
}
