const TABS = ['Fleet Overview', 'Topology', 'Maintenance']

export default function Navbar({ activeTab, setActiveTab, connected }) {
  return (
    <header className="fixed top-0 right-0 left-0 h-16 flex items-center justify-between px-8 z-40 bg-slate-950/80 backdrop-blur-md border-b border-white/5">
      <div className="flex items-center gap-6">
        <div className="flex items-center gap-3">
          <span className="text-xl font-black text-blue-100 tracking-tight font-headline">MONITOR_UI</span>
          <span className={`w-2 h-2 rounded-full ${connected ? 'bg-green-400' : 'bg-red-500'}`} title={connected ? 'API connected' : 'API disconnected'} />
        </div>
        <nav className="hidden md:flex items-center gap-6">
          {TABS.map(tab => (
            <button
              key={tab}
              onClick={() => setActiveTab(tab)}
              className={`h-16 flex items-center px-1 font-label uppercase tracking-widest text-[10px] transition-colors border-b-2
                ${activeTab === tab
                  ? 'text-blue-400 border-blue-400'
                  : 'text-slate-400 hover:text-blue-200 border-transparent'
                }`}
            >
              {tab}
            </button>
          ))}
        </nav>
      </div>

      <div className="flex items-center gap-4">
        <div className="relative">
          <span className="absolute inset-y-0 left-3 flex items-center text-slate-500">
            <span className="material-symbols-outlined" style={{ fontSize: 18 }}>search</span>
          </span>
          <input
            className="bg-surface-container-highest/50 border-none rounded-lg pl-9 pr-4 py-1.5 text-xs focus:outline-none focus:ring-1 focus:ring-primary w-56 text-blue-100 placeholder-slate-500"
            placeholder="Search system entities..."
            type="text"
          />
        </div>
        <div className="flex items-center gap-1">
          <button className="p-2 text-slate-400 hover:text-blue-400 transition-colors">
            <span className="material-symbols-outlined">notifications</span>
          </button>
          <button className="p-2 text-slate-400 hover:text-blue-400 transition-colors">
            <span className="material-symbols-outlined">settings_input_component</span>
          </button>
          <button className="p-2 text-slate-400 hover:text-blue-400 transition-colors">
            <span className="material-symbols-outlined">logout</span>
          </button>
        </div>
      </div>
    </header>
  )
}
