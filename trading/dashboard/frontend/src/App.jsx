import { useState } from 'react'
import { Activity, ListChecks, TrendingUp, Brain } from 'lucide-react'
import SummaryCards from './components/SummaryCards.jsx'
import Live from './pages/Live.jsx'
import Trades from './pages/Trades.jsx'
import Equity from './pages/Equity.jsx'
import Learning from './pages/Learning.jsx'

const TABS = [
  { id: 'live',     label: 'Live',     icon: Activity,    Comp: Live },
  { id: 'trades',   label: 'Trades',   icon: ListChecks,  Comp: Trades },
  { id: 'equity',   label: 'Equity',   icon: TrendingUp,  Comp: Equity },
  { id: 'learning', label: 'Learning', icon: Brain,       Comp: Learning },
]

export default function App() {
  const [tab, setTab] = useState('live')
  const Active = TABS.find((t) => t.id === tab)?.Comp ?? Live

  return (
    <div className="min-h-screen flex flex-col">
      {/* Top bar */}
      <header className="border-b border-border bg-bg-panel sticky top-0 z-10">
        <div className="max-w-6xl mx-auto px-4 py-3 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <span className="text-2xl font-bold text-accent">ORB</span>
            <span className="text-sm text-text-secondary hidden sm:inline">— War Room</span>
          </div>
          <nav className="flex gap-1">
            {TABS.map((t) => {
              const Icon = t.icon
              const active = tab === t.id
              return (
                <button
                  key={t.id}
                  onClick={() => setTab(t.id)}
                  className={
                    'px-3 sm:px-4 py-2 rounded-md text-sm font-medium transition flex items-center gap-1.5 ' +
                    (active
                      ? 'bg-accent/15 text-accent'
                      : 'text-text-secondary hover:text-text-primary hover:bg-bg-card')
                  }
                >
                  <Icon size={16} />
                  <span className="hidden sm:inline">{t.label}</span>
                </button>
              )
            })}
          </nav>
        </div>
      </header>

      {/* Summary cards always visible */}
      <SummaryCards />

      {/* Main page */}
      <main className="flex-1 max-w-6xl w-full mx-auto px-4 pb-8">
        <Active />
      </main>

      {/* Footer */}
      <footer className="border-t border-border py-3 text-center text-xs text-text-muted">
        ORB Dashboard · port 8502 · read-only against journal.db · refreshes every 30s
      </footer>
    </div>
  )
}
