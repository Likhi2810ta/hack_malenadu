import { useState } from 'react'
import { useMachines } from './hooks/useMachines'
import Navbar from './components/Navbar'
import MachineCard from './components/MachineCard'
import DetailPanel from './components/DetailPanel'
import MaintenanceView from './components/MaintenanceView'

export default function App() {
  const { ordered, connected } = useMachines()
  const [selectedId, setSelectedId] = useState(null)
  const [activeTab, setActiveTab]   = useState('Fleet Overview')

  const selected = ordered.find(m => m.id === selectedId) ?? null

  function handleCardClick(machineId) {
    setSelectedId(prev => prev === machineId ? null : machineId)
  }

  const critCount = ordered.filter(m => m.status === 'critical').length
  const warnCount = ordered.filter(m => m.status === 'warning').length

  return (
    <div className="min-h-screen bg-surface text-on-surface">
      {/* Full-width main canvas */}
      <main className="fixed inset-0 overflow-y-auto no-scrollbar bg-surface">
        <Navbar activeTab={activeTab} setActiveTab={setActiveTab} connected={connected} />

        {/* Maintenance tab */}
        {activeTab === 'Maintenance' && (
          <MaintenanceView machines={ordered} />
        )}

        {/* Fleet Overview */}
        {activeTab !== 'Maintenance' && (
          <section className={`pt-20 px-8 pb-12 transition-all ${selected ? 'mr-[380px]' : ''}`}>

            {/* Page heading + fleet status */}
            <div className="flex items-start justify-between mb-6 mt-4">
              <div>
                <h2 className="text-3xl font-headline font-bold text-blue-100 tracking-tighter">
                  Self-Evolving Predictive Maintenance Agent
                </h2>
                <p className="text-slate-500 mt-1 text-xs font-label uppercase tracking-widest">
                  Monitoring: CNC_01 · CNC_02 · PUMP_03 · CONVEYOR_04 · API: localhost:8000
                </p>
              </div>
              <div className="flex items-center gap-2 mt-1">
                <div className={`w-2 h-2 rounded-full ${connected ? 'bg-green-400 animate-pulse' : 'bg-red-500'}`} />
                <span className="font-label text-[10px] uppercase tracking-widest text-slate-400">
                  {connected ? 'Live' : 'Connecting'}
                </span>
              </div>
            </div>

            {/* Alert banner */}
            {(critCount + warnCount) > 0 && (
              <div className="mb-6 flex items-center gap-3 px-4 py-3 rounded-lg bg-red-900/30 border border-red-500/20">
                <span className="material-symbols-outlined text-red-400" style={{ fontSize: 18 }}>warning</span>
                <span className="font-label text-sm text-red-300">
                  {critCount + warnCount} machine{critCount + warnCount > 1 ? 's' : ''} at risk
                  {critCount > 0 && ` — ${critCount} CRITICAL`}
                </span>
              </div>
            )}

            {/* Machine grid */}
            <div className="grid grid-cols-1 lg:grid-cols-2 xl:grid-cols-4 gap-6">
              {ordered.map(machine => (
                <MachineCard
                  key={machine.id}
                  machine={machine}
                  isSelected={machine.id === selectedId}
                  onClick={() => handleCardClick(machine.id)}
                />
              ))}
              {ordered.length === 0 && (
                <div className="col-span-4 flex flex-col items-center justify-center py-40 text-slate-600">
                  <span className="material-symbols-outlined block mb-4" style={{ fontSize: 48 }}>sensors_off</span>
                  <p className="font-label uppercase tracking-widest text-xs">Awaiting data stream…</p>
                </div>
              )}
            </div>
          </section>
        )}
      </main>

      {/* Right detail panel */}
      {activeTab !== 'Maintenance' && <DetailPanel machine={selected} />}
    </div>
  )
}
