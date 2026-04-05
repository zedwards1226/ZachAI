import { useState, useEffect, useRef } from 'react'
import ActiveTasks    from './components/ActiveTasks'
import TelegramFeed   from './components/TelegramFeed'
import BuildStatus    from './components/BuildStatus'
import CompanyStatus  from './components/CompanyStatus'

export default function App() {
  const [state,     setState]     = useState({ tasks: [], messages: [], approvals: [] })
  const [connected, setConnected] = useState(false)
  const [lastPing,  setLastPing]  = useState(null)
  const wsRef = useRef(null)

  useEffect(() => {
    let retryTimer = null

    const connect = () => {
      const proto = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
      const ws    = new WebSocket(`${proto}//${window.location.host}/ws`)

      ws.onopen = () => {
        setConnected(true)
        setLastPing(new Date())
      }
      ws.onclose = () => {
        setConnected(false)
        retryTimer = setTimeout(connect, 3000)
      }
      ws.onerror = () => ws.close()
      ws.onmessage = (e) => {
        try {
          setState(JSON.parse(e.data))
          setLastPing(new Date())
        } catch (_) {}
      }
      wsRef.current = ws
    }

    connect()
    return () => {
      clearTimeout(retryTimer)
      wsRef.current?.close()
    }
  }, [])

  const runningTasks  = state.tasks?.filter(t => t.status === 'running')  ?? []
  const pendingAppr   = state.approvals?.filter(a => a.status === 'pending') ?? []

  return (
    <div className="min-h-screen bg-[#050505] text-[#00ff41] font-mono select-none">

      {/* ── Header ── */}
      <header className="border-b border-[#00ff41] px-4 py-3 flex items-center justify-between
                         sticky top-0 z-10 bg-[#050505]">
        <div className="flex items-center gap-3">
          <span className="text-lg md:text-xl font-bold tracking-widest neon-text">
            ◈ ZACHAI COMMAND CENTER
          </span>
        </div>
        <div className="flex items-center gap-4 text-xs">
          {pendingAppr.length > 0 && (
            <span className="text-orange-400 animate-pulse">
              ⚠ {pendingAppr.length} PENDING APPROVAL{pendingAppr.length > 1 ? 'S' : ''}
            </span>
          )}
          <div className="flex items-center gap-2">
            <span className={`w-2 h-2 rounded-full transition-all ${
              connected
                ? 'bg-[#00ff41] animate-pulse-neon'
                : 'bg-red-500'
            }`} />
            <span className={connected ? 'text-[#00ff41]' : 'text-red-500'}>
              {connected ? 'LIVE' : 'OFFLINE'}
            </span>
          </div>
        </div>
      </header>

      {/* ── Grid ── */}
      <main className="p-3 md:p-4 grid grid-cols-1 md:grid-cols-2 gap-3 md:gap-4 max-w-7xl mx-auto">
        <ActiveTasks  tasks    = {runningTasks} />
        <TelegramFeed messages = {state.messages ?? []} />
        <BuildStatus  tasks    = {state.tasks    ?? []} />
        <CompanyStatus />
      </main>

      {/* ── Footer ── */}
      <footer className="text-center text-[#003311] text-xs py-3 border-t border-[#001a08]">
        ZACHAI v1.0 · {lastPing ? `SYNC ${lastPing.toLocaleTimeString()}` : 'CONNECTING…'}
      </footer>
    </div>
  )
}
