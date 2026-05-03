import { useState, useEffect, useCallback } from 'react'
import Header from './components/Header'
import HeroTiles from './components/HeroTiles'
import OpenPositions from './components/OpenPositions'
import ActivityRail from './components/ActivityRail'
import EquityChart from './components/EquityChart'
import StrategyCards from './components/StrategyCards'

/** Custom hook: poll a JSON endpoint at a fixed interval. */
function usePoll(path, intervalMs = 5000) {
  const [data, setData] = useState(null)
  const [error, setError] = useState(null)

  const fetchOnce = useCallback(async () => {
    try {
      const r = await fetch(path)
      if (!r.ok) throw new Error(`${r.status}`)
      const json = await r.json()
      setData(json)
      setError(null)
    } catch (e) {
      setError(e.message || 'fetch failed')
    }
  }, [path])

  useEffect(() => {
    fetchOnce()
    const id = setInterval(fetchOnce, intervalMs)
    return () => clearInterval(id)
  }, [fetchOnce, intervalMs])

  return { data, error }
}

export default function App() {
  const { data: summary } = usePoll('/api/summary', 5000)
  const { data: positions } = usePoll('/api/positions', 5000)
  const { data: activity } = usePoll('/api/activity', 5000)
  const { data: equity } = usePoll('/api/equity', 30000)
  const { data: strategies } = usePoll('/api/strategies', 15000)

  return (
    <div className="min-h-screen bg-bg flex flex-col">
      <Header
        paperMode={summary?.paper_mode ?? true}
        kalshiOk={summary?.kalshi_ok ?? null}
      />

      <main className="flex-1 px-4 md:px-8 py-6 max-w-[1600px] w-full mx-auto">
        <HeroTiles summary={summary} />

        <div className="mt-6 grid grid-cols-1 lg:grid-cols-3 gap-4">
          <div className="lg:col-span-2 flex flex-col gap-4">
            <OpenPositions
              positions={positions?.positions ?? []}
              recentEntries={activity?.entries ?? []}
            />
            <EquityChart
              points={equity?.points ?? []}
              startingCapital={summary?.starting_capital_usd ?? 100}
            />
            <StrategyCards strategies={strategies?.strategies ?? []} />
          </div>
          <div>
            <ActivityRail entries={activity?.entries ?? []} />
          </div>
        </div>
      </main>
    </div>
  )
}
