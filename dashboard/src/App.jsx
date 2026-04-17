import { useState, useEffect, useRef } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import Sidebar from './components/Sidebar'
import Navbar from './components/Navbar'
import MachineCard from './components/MachineCard'
import DetailPanel from './components/DetailPanel'
import { initialMachines } from './data/machines'

/* ── Stat card (top row) ── */
function KpiCard({ label, value, sub, color, pulse }) {
  return (
    <motion.div
      initial={{ opacity: 0, y: -10 }}
      animate={{ opacity: 1, y: 0 }}
      className="flex-1 rounded-2xl px-4 py-3 relative overflow-hidden"
      style={{
        background: '#1C2541',
        border: `1px solid ${color}25`,
        boxShadow: `0 4px 20px rgba(0,0,0,0.3)`,
      }}
    >
      <div
        className="absolute inset-0 pointer-events-none"
        style={{ background: `radial-gradient(ellipse at top left, ${color}10, transparent 65%)` }}
      />
      <p className="text-[9px] text-gray-500 uppercase tracking-[0.2em] font-semibold">{label}</p>
      <div className="flex items-end gap-2 mt-1">
        <p className="text-xl font-black" style={{ color }}>{value}</p>
        {sub && <p className="text-[10px] text-gray-500 mb-0.5">{sub}</p>}
      </div>
      {pulse && (
        <div className="absolute top-3 right-3">
          <span className="relative flex h-2 w-2">
            <span className="animate-ping absolute inline-flex h-full w-full rounded-full opacity-75" style={{ background: color }} />
            <span className="relative inline-flex rounded-full h-2 w-2" style={{ background: color }} />
          </span>
        </div>
      )}
    </motion.div>
  )
}

export default function App() {
  const [machines, setMachines] = useState(initialMachines)
  const [selected, setSelected]   = useState(initialMachines[2]) // PUMP_03 default (critical)
  const [activeTab, setActiveTab]  = useState('Fleet Overview')
  const tickRef = useRef(0)

  /* ── Live data simulation ── */
  useEffect(() => {
    const id = setInterval(() => {
      tickRef.current += 1
      setMachines(prev => prev.map(m => {
        const drift = m.status === 'critical' ? 0.05 : 0
        return {
          ...m,
          temperature: clamp(m.temperature + jitter(1.2) + drift, 30, 115),
          vibration:   clamp(m.vibration   + jitter(0.25) + drift * 0.1, 0.1, 14),
          rpm:         clamp(m.rpm         + jitter(35)   - drift * 2, 500, 5900),
          current:     clamp(m.current     + jitter(0.35) + drift * 0.05, 1, 24),
        }
      }))
    }, 2500)
    return () => clearInterval(id)
  }, [])

  /* ── Keep selected in sync ── */
  useEffect(() => {
    if (selected) {
      const fresh = machines.find(m => m.id === selected.id)
      if (fresh) setSelected(fresh)
    }
  }, [machines])

  const critCount = machines.filter(m => m.status === 'critical').length
  const warnCount = machines.filter(m => m.status === 'warning').length
  const avgRisk   = Math.round(machines.reduce((a, m) => a + m.risk, 0) / machines.length)

  return (
    <div className="flex h-screen overflow-hidden bg-grid" style={{ background: '#0B132B', fontFamily: 'Inter, sans-serif' }}>

      {/* Scan line overlay */}
      <div className="scan-line" />

      {/* Corner decorations */}
      <div className="fixed top-0 left-0 w-32 h-32 pointer-events-none" style={{ background: 'radial-gradient(circle, rgba(58,134,255,0.06) 0%, transparent 70%)' }} />
      <div className="fixed bottom-0 right-0 w-48 h-48 pointer-events-none" style={{ background: 'radial-gradient(circle, rgba(255,107,53,0.04) 0%, transparent 70%)' }} />

      {/* Sidebar */}
      <Sidebar machines={machines} />

      {/* Main */}
      <div className="flex-1 flex flex-col overflow-hidden min-w-0">
        <Navbar activeTab={activeTab} setActiveTab={setActiveTab} alertCount={critCount + warnCount} />

        <div className="flex-1 flex overflow-hidden min-h-0">

          {/* Content */}
          <div className="flex-1 overflow-y-auto p-4 min-w-0">

            {/* KPI row */}
            <div className="flex gap-3 mb-4">
              <KpiCard label="Online Assets"  value="4 / 4"       color="#2EC4B6" />
              <KpiCard label="Active Alerts"  value={critCount + warnCount} sub="machines" color="#FF6B35" pulse={critCount > 0} />
              <KpiCard label="Avg Risk Score" value={`${avgRisk}%`}          color="#FFD166" />
              <KpiCard label="Fleet Uptime"   value="94.3%"        color="#3A86FF" />
            </div>

            {/* Section header */}
            <div className="flex items-center justify-between mb-3">
              <div className="flex items-center gap-3">
                <h2 className="text-white font-semibold text-sm tracking-wide">Machine Fleet</h2>
                <span
                  className="text-[9px] font-mono px-2 py-0.5 rounded-full"
                  style={{ background: 'rgba(58,134,255,0.12)', color: '#93C5FD', border: '1px solid rgba(58,134,255,0.2)' }}
                >
                  {machines.length} assets
                </span>
              </div>
              <div className="flex items-center gap-1.5 text-[10px] text-gray-500">
                <div className="w-1.5 h-1.5 rounded-full bg-teal-400 blink" />
                Live — updates every 2.5s
              </div>
            </div>

            {/* Machine grid */}
            <div className="grid grid-cols-2 gap-3">
              <AnimatePresence>
                {machines.map((m, i) => (
                  <motion.div
                    key={m.id}
                    initial={{ opacity: 0, y: 20 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ delay: i * 0.08 }}
                  >
                    <MachineCard
                      machine={m}
                      isSelected={selected?.id === m.id}
                      onClick={() => setSelected(m)}
                    />
                  </motion.div>
                ))}
              </AnimatePresence>
            </div>
          </div>

          {/* Detail panel */}
          <DetailPanel machine={selected} />
        </div>
      </div>
    </div>
  )
}

function jitter(amp) { return (Math.random() - 0.5) * amp * 2 }
function clamp(v, lo, hi) { return Math.max(lo, Math.min(hi, v)) }
