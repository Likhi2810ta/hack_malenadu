import { useState } from 'react'

const NAV = [
  { icon: 'dashboard',               label: 'Dashboard'   },
  { icon: 'analytics',               label: 'Telemetry'   },
  { icon: 'precision_manufacturing', label: 'Diagnostics' },
  { icon: 'settings',                label: 'Config'      },
  { icon: 'terminal',                label: 'System Logs' },
]

function RangeSlider({ label, min, max, step = 1, defaultValue, display }) {
  const [val, setVal] = useState(defaultValue)
  const shown = display ? display(val) : val
  return (
    <div className="space-y-3">
      <div className="flex justify-between items-center">
        <label className="text-[10px] font-label uppercase tracking-tighter text-slate-400">{label}</label>
        <span className="text-[10px] text-blue-200">{shown}</span>
      </div>
      <input
        className="w-full h-1 rounded-lg appearance-none cursor-pointer accent-primary"
        type="range" min={min} max={max} step={step} value={val}
        onChange={e => setVal(+e.target.value)}
      />
    </div>
  )
}

export default function Sidebar({ machines = [] }) {
  const [active, setActive] = useState('Dashboard')
  const critCount = machines.filter(m => m?.status === 'critical').length
  const warnCount = machines.filter(m => m?.status === 'warning').length

  return (
    <aside className="fixed inset-y-0 left-0 z-50 flex flex-col h-full w-64 border-r border-blue-500/10 bg-slate-900/80 backdrop-blur-xl shadow-2xl shadow-black/40">
      <div className="p-6 flex flex-col h-full">

        {/* Brand */}
        <div className="mb-8">
          <h1 className="text-lg font-bold tracking-tighter text-blue-200 font-headline">ORBITAL FOUNDRY</h1>
          <p className="font-label uppercase tracking-widest text-[10px] text-slate-500">V.2.04-HYDRA</p>
          {(critCount > 0 || warnCount > 0) && (
            <div className="mt-2 flex gap-2">
              {critCount > 0 && (
                <span className="text-[9px] font-label uppercase tracking-wider px-2 py-0.5 rounded bg-tertiary-container/20 text-tertiary-container border border-tertiary-container/30">
                  {critCount} CRITICAL
                </span>
              )}
              {warnCount > 0 && (
                <span className="text-[9px] font-label uppercase tracking-wider px-2 py-0.5 rounded bg-yellow-500/10 text-yellow-400 border border-yellow-500/20">
                  {warnCount} WARN
                </span>
              )}
            </div>
          )}
        </div>

        {/* Nav */}
        <nav className="space-y-1 mb-8">
          {NAV.map(({ icon, label }) => {
            const isActive = active === label
            return (
              <button
                key={label}
                onClick={() => setActive(label)}
                className={`w-full flex items-center gap-3 px-3 py-2 font-label uppercase tracking-widest text-[10px] transition-colors text-left
                  ${isActive
                    ? 'text-blue-300 font-bold border-r-2 border-blue-400 bg-blue-400/5'
                    : 'text-slate-500 hover:text-slate-300 hover:bg-white/5'
                  }`}
              >
                <span className="material-symbols-outlined" style={{ fontSize: 18 }}>{icon}</span>
                {label}
              </button>
            )
          })}
        </nav>

        {/* Runtime Parameters */}
        <div className="space-y-6 mt-4 pt-6 border-t border-white/5">
          <h3 className="font-label uppercase tracking-widest text-[10px] text-blue-400 font-bold">Runtime Parameters</h3>
          <RangeSlider
            label="Detection Sensitivity"
            min={0} max={1} step={0.01} defaultValue={0.84}
            display={v => v.toFixed(2)}
          />
          <RangeSlider
            label="Update Frequency"
            min={1} max={500} defaultValue={120}
            display={v => `${v}Hz`}
          />
          <div className="space-y-3">
            <div className="flex justify-between items-center">
              <label className="text-[10px] font-label uppercase tracking-tighter text-slate-400">Health Thresholds</label>
              <span className="text-[10px] text-blue-200">Low Latency</span>
            </div>
            <div className="flex gap-1 h-1">
              <div className="flex-1 bg-primary rounded-full" />
              <div className="flex-1 bg-surface-container-highest rounded-full" />
              <div className="flex-1 bg-surface-container-highest rounded-full" />
            </div>
          </div>
        </div>

        {/* Footer */}
        <div className="mt-auto pt-6">
          <button className="w-full py-2 bg-blue-400/10 border border-blue-400/30 text-blue-200 font-label uppercase tracking-widest text-[10px] hover:bg-blue-400/20 transition-all active:scale-95 duration-150">
            Deploy Patch
          </button>
          <div className="mt-4 flex items-center gap-2 text-slate-500">
            <span className="material-symbols-outlined text-green-400" style={{ fontSize: 14 }}>check_circle</span>
            <span className="font-label uppercase tracking-widest text-[10px]">Status: Optimal</span>
          </div>
        </div>

      </div>
    </aside>
  )
}
