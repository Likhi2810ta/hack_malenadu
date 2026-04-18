import { useState, useEffect } from 'react'

const API_BASE =
  import.meta.env.VITE_API_URL || "http://localhost:8000";
function riskColor(pct) {
  if (pct >= 80) return { bg: 'bg-red-500/10', border: 'border-red-500/20', text: 'text-red-400', dot: '#ff3355' }
  if (pct >= 60) return { bg: 'bg-tertiary-container/10', border: 'border-tertiary-container/20', text: 'text-tertiary-container', dot: '#f3632d' }
  if (pct >= 40) return { bg: 'bg-yellow-500/10', border: 'border-yellow-500/20', text: 'text-yellow-400', dot: '#ffcc00' }
  return { bg: 'bg-[#2EC4B6]/10', border: 'border-[#2EC4B6]/20', text: 'text-[#2EC4B6]', dot: '#2EC4B6' }
}

function riskLabel(pct) {
  if (pct >= 80) return 'CRITICAL'
  if (pct >= 60) return 'HIGH RISK'
  if (pct >= 40) return 'MODERATE'
  return 'STABLE'
}

function prioritySort(queue) {
  return [...queue].sort((a, b) => b.risk_pct - a.risk_pct)
}

export default function MaintenanceView({ machines }) {
  const [algo, setAlgo]       = useState('priority')
  const [actions, setActions] = useState({})
  const [alerts, setAlerts]   = useState([])

  useEffect(() => {
    fetch(`${API_BASE}/api/alerts`).then(r => r.json()).then(setAlerts).catch(() => {})
  }, [])

  const queue = machines.filter(m => m.status !== 'healthy')
  const sorted = algo === 'priority' ? prioritySort(queue)
    : algo === 'fcfs'     ? [...queue]
    : [...queue].sort((a, b) => a.risk_pct - b.risk_pct) // SJF = lowest risk first

  async function handleConfirm(id) {
    await fetch(`${API_BASE}/api/machines/${id}/confirm`, { method: 'POST' })
    setActions(p => ({ ...p, [id]: 'confirmed' }))
    const r = await fetch(`${API_BASE}/api/alerts`)
    setAlerts(await r.json())
  }
  async function handleDismiss(id) {
    await fetch(`${API_BASE}/api/machines/${id}/dismiss`, { method: 'POST' })
    setActions(p => ({ ...p, [id]: 'dismissed' }))
  }

  return (
    <div className="pt-20 px-8 pb-12 mt-4">
      <div className="mb-8">
        <h2 className="text-4xl font-headline font-bold text-blue-100 tracking-tighter">Maintenance Scheduler</h2>
        <p className="text-slate-400 mt-2 text-sm">Predictive queue — sorted by algorithm. Acknowledge to dispatch.</p>
      </div>

      {/* Algorithm selector */}
      <div className="flex items-center gap-3 mb-8">
        <span className="font-label text-[10px] uppercase tracking-widest text-slate-500">Algorithm:</span>
        {[
          { key: 'priority', label: 'Priority Queue' },
          { key: 'fcfs',     label: 'FCFS' },
          { key: 'sjf',      label: 'SJF' },
        ].map(({ key, label }) => (
          <button
            key={key}
            onClick={() => setAlgo(key)}
            className={`px-4 py-1.5 rounded-lg font-label text-[10px] uppercase tracking-widest transition-all
              ${algo === key
                ? 'bg-primary/20 border border-primary/40 text-primary'
                : 'bg-surface-container-high border border-white/5 text-slate-500 hover:text-slate-300 hover:bg-surface-container-highest'
              }`}
          >
            {label}
          </button>
        ))}
        {queue.length === 0 && (
          <span className="ml-auto flex items-center gap-2 text-[#2EC4B6] font-label text-[10px] uppercase tracking-widest">
            <span className="material-symbols-outlined" style={{ fontSize: 16 }}>check_circle</span>
            All machines nominal
          </span>
        )}
      </div>

      {/* Maintenance queue */}
      {queue.length === 0 ? (
        <div className="flex flex-col items-center justify-center py-32 text-slate-600">
          <span className="material-symbols-outlined block mb-4" style={{ fontSize: 48 }}>verified</span>
          <p className="font-label uppercase tracking-widest text-xs">No machines in maintenance queue</p>
        </div>
      ) : (
        <div className="space-y-4">
          {sorted.map((m, i) => {
            const rc      = riskColor(m.risk_pct)
            const action  = actions[m.id]
            return (
              <div key={m.id} className={`rounded-lg border p-6 ${rc.bg} ${rc.border} relative overflow-hidden`}>
                {/* Priority badge */}
                <div className="absolute top-4 right-4 flex items-center gap-1.5">
                  <span className="font-label text-[9px] uppercase tracking-widest text-slate-500">#{i + 1}</span>
                  <div className={`w-2 h-2 rounded-full`} style={{ background: rc.dot }} />
                </div>

                <div className="flex gap-6">
                  {/* Machine image */}
                  <div className="w-24 h-20 rounded-lg overflow-hidden flex-shrink-0">
                    <img src={m.image} alt={m.display_name} className="w-full h-full object-cover" />
                  </div>

                  {/* Info */}
                  <div className="flex-1 min-w-0">
                    <div className="flex items-start justify-between mb-2">
                      <div>
                        <span className="font-label text-[9px] uppercase tracking-widest text-slate-500">ASSET: {m.asset_id}</span>
                        <h4 className="font-headline font-bold text-on-surface">{m.display_name}</h4>
                      </div>
                      <span className={`font-label text-[10px] uppercase font-bold ${rc.text}`}>
                        {riskLabel(m.risk_pct)}
                      </span>
                    </div>

                    {/* Risk bar */}
                    <div className="flex items-center gap-3 mb-3">
                      <div className="flex-1 h-1 bg-surface-container-highest rounded-full overflow-hidden">
                        <div className="h-full rounded-full transition-all duration-700"
                          style={{ width: `${m.risk_pct}%`, background: rc.dot }} />
                      </div>
                      <span className="font-headline font-bold text-sm" style={{ color: rc.dot }}>
                        {m.risk_pct.toFixed(1)}%
                      </span>
                    </div>

                    {/* Sensor snapshot */}
                    <div className="grid grid-cols-4 gap-3 mb-4 text-[9px] font-label uppercase tracking-tighter text-slate-500">
                      <div><span className="block">Temp</span><span className={`font-headline text-sm font-bold ${rc.text}`}>{m.temperature_C?.toFixed(1)}°C</span></div>
                      <div><span className="block">Vib</span><span className={`font-headline text-sm font-bold ${rc.text}`}>{m.vibration_mm_s?.toFixed(1)}</span></div>
                      <div><span className="block">RPM</span><span className={`font-headline text-sm font-bold ${rc.text}`}>{m.rpm ? Math.round(m.rpm).toLocaleString() : '--'}</span></div>
                      <div><span className="block">Current</span><span className={`font-headline text-sm font-bold ${rc.text}`}>{m.current_A?.toFixed(1)}A</span></div>
                    </div>

                    {/* Diagnostic tags */}
                    <div className="flex gap-2 flex-wrap mb-4">
                      {m.if_anomaly && (
                        <span className="px-2 py-0.5 rounded bg-red-500/15 border border-red-500/25 font-label text-[9px] uppercase tracking-wider text-red-400">
                          IsoForest Anomaly
                        </span>
                      )}
                      {(m.polyfit_score ?? 0) > 20 && (
                        <span className="px-2 py-0.5 rounded bg-yellow-500/15 border border-yellow-500/25 font-label text-[9px] uppercase tracking-wider text-yellow-400">
                          Trend {m.polyfit_score?.toFixed(0)}% severity
                        </span>
                      )}
                      <span className={`px-2 py-0.5 rounded border font-label text-[9px] uppercase tracking-wider ${rc.bg} ${rc.border} ${rc.text}`}>
                        {m.status === 'critical' ? 'Bearing risk' : 'Elevated sensors'}
                      </span>
                    </div>

                    {/* Action buttons */}
                    {action === 'confirmed' ? (
                      <div className="text-[#2EC4B6] font-label text-[10px] uppercase tracking-widest flex items-center gap-1.5">
                        <span className="material-symbols-outlined" style={{ fontSize: 14 }}>check_circle</span>
                        Maintenance dispatched
                      </div>
                    ) : action === 'dismissed' ? (
                      <div className="text-slate-500 font-label text-[10px] uppercase tracking-widest flex items-center gap-1.5">
                        <span className="material-symbols-outlined" style={{ fontSize: 14 }}>remove_circle</span>
                        Dismissed as false alarm
                      </div>
                    ) : (
                      <div className="flex gap-2">
                        <button
                          onClick={() => handleConfirm(m.id)}
                          className="px-4 py-2 bg-gradient-to-r from-primary-container to-primary text-on-primary-container font-headline font-bold text-xs rounded-lg hover:brightness-110 active:scale-[0.98] transition-all"
                        >
                          ✔ Confirm Maintenance
                        </button>
                        <button
                          onClick={() => handleDismiss(m.id)}
                          className="px-4 py-2 bg-transparent border border-outline-variant text-slate-400 font-label text-[9px] uppercase tracking-widest rounded-lg hover:bg-white/5 active:scale-[0.98] transition-all"
                        >
                          Dismiss
                        </button>
                      </div>
                    )}
                  </div>
                </div>
              </div>
            )
          })}
        </div>
      )}

      {/* Action log */}
      {alerts.length > 0 && (
        <div className="mt-10">
          <h3 className="font-label text-[10px] uppercase tracking-widest text-blue-400 font-bold mb-4">Action Log</h3>
          <div className="space-y-2">
            {[...alerts].reverse().slice(0, 10).map((a, i) => (
              <div key={i} className="flex items-center gap-3 text-[11px] text-slate-400 font-label">
                <span className={`material-symbols-outlined ${a.action === 'confirmed' ? 'text-[#2EC4B6]' : 'text-slate-500'}`} style={{ fontSize: 14 }}>
                  {a.action === 'confirmed' ? 'check_circle' : 'remove_circle'}
                </span>
                <span className="text-slate-500">{new Date(a.ts).toLocaleTimeString()}</span>
                <span>{a.machine_id}</span>
                <span className={a.action === 'confirmed' ? 'text-[#2EC4B6]' : 'text-slate-500'}>
                  {a.action === 'confirmed' ? '— maintenance confirmed' : '— dismissed as false alarm'}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
