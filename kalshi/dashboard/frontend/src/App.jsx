import { useState, useEffect, useCallback } from 'react'
import TradesPanel    from './components/TradesPanel'
import PnlChart       from './components/PnlChart'
import ForecastsPanel from './components/ForecastsPanel'
import GuardrailPanel from './components/GuardrailPanel'

const API = '/api'

function useApi(path, interval = 10000) {
  const [data, setData] = useState(null)
  const [error, setError] = useState(null)

  const fetch_ = useCallback(async () => {
    try {
      const r = await fetch(`${API}${path}`)
      if (!r.ok) throw new Error(r.statusText)
      setData(await r.json())
      setError(null)
    } catch (e) {
      setError(e.message)
    }
  }, [path])

  useEffect(() => {
    fetch_()
    const t = setInterval(fetch_, interval)
    return () => clearInterval(t)
  }, [fetch_, interval])

  return { data, error, refresh: fetch_ }
}

export default function App() {
  const { data: status }     = useApi('/status',     8000)
  const { data: trades }     = useApi('/trades?limit=50', 8000)
  const { data: pnl }        = useApi('/pnl?limit=100',   15000)
  const { data: forecasts }  = useApi('/forecasts',  20000)
  const { data: guardrails } = useApi('/guardrails', 8000)

  const [scanning, setScanning] = useState(false)
  const [scanMsg,  setScanMsg]  = useState(null)

  async function triggerScan() {
    setScanning(true)
    setScanMsg(null)
    try {
      const r = await fetch(`${API}/scan`, { method: 'POST' })
      const d = await r.json()
      setScanMsg(d.ok
        ? `Scan complete — ${d.actions?.length ?? 0} action(s)`
        : `Error: ${d.error}`)
    } catch (e) {
      setScanMsg(`Error: ${e.message}`)
    } finally {
      setScanning(false)
      setTimeout(() => setScanMsg(null), 5000)
    }
  }

  const halted = guardrails?.halted
  const paper  = status?.paper_mode

  return (
    <div className="min-h-screen bg-[#050505] text-[#00ff41] font-mono">

      {/* Header */}
      <header className="border-b border-[#00ff41] px-4 py-3 flex flex-wrap items-center gap-3
                         sticky top-0 z-10 bg-[#050505]">
        <span className="text-lg font-bold tracking-widest neon-text">
          ◈ WEATHERALPHA
        </span>
        {paper && (
          <span className="text-xs border border-yellow-400 text-yellow-400 px-2 py-0.5 rounded">
            PAPER MODE
          </span>
        )}
        {halted && (
          <span className="text-xs border border-red-500 text-red-500 px-2 py-0.5 rounded animate-pulse">
            HALTED
          </span>
        )}

        <div className="ml-auto flex items-center gap-4 text-xs">
          {status && (
            <>
              <span className="text-[#006622]">
                Capital: <span className="text-[#00ff41]">${status.capital_usd?.toFixed(2)}</span>
              </span>
              <span className="text-[#006622]">
                P&L: <span className={status.summary?.total_pnl_usd >= 0 ? 'text-[#00ff41]' : 'text-red-400'}>
                  ${status.summary?.total_pnl_usd?.toFixed(2)}
                </span>
              </span>
            </>
          )}
          <button
            onClick={triggerScan}
            disabled={scanning}
            className="border border-[#00ff41] px-3 py-1 rounded text-xs hover:bg-[#001a08]
                       disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
          >
            {scanning ? '⟳ SCANNING…' : '▶ SCAN NOW'}
          </button>
        </div>
      </header>

      {scanMsg && (
        <div className="bg-[#001a08] border-b border-[#00ff41] px-4 py-2 text-xs text-[#00cc33]">
          {scanMsg}
        </div>
      )}

      {/* Dashboard grid */}
      <main className="p-3 md:p-4 grid grid-cols-1 md:grid-cols-2 gap-3 md:gap-4 max-w-7xl mx-auto">
        <ForecastsPanel forecasts={forecasts ?? []} />
        <GuardrailPanel guardrails={guardrails} />
        <PnlChart       pnl={pnl ?? []} summary={status?.summary} />
        <TradesPanel    trades={trades ?? []} />
      </main>

      <footer className="text-center text-[#003311] text-xs py-3 border-t border-[#001a08]">
        WEATHERALPHA v1.0 · Kalshi Weather Trading · Paper Mode
      </footer>
    </div>
  )
}
