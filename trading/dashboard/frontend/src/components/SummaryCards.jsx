import { useApi, api, fmt } from '../api.js'
import { motion } from 'framer-motion'

function Card({ label, value, sub, tone = 'neutral' }) {
  const toneClass =
    tone === 'profit' ? 'text-profit' :
    tone === 'loss'   ? 'text-loss' :
    tone === 'accent' ? 'text-accent' :
    'text-text-primary'
  return (
    <motion.div
      initial={{ opacity: 0, y: 6 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.25 }}
      className="gradient-card border border-border rounded-lg p-3 sm:p-4"
    >
      <div className="text-xs uppercase tracking-wider text-text-secondary">{label}</div>
      <div className={`mt-1 text-xl sm:text-2xl font-bold ${toneClass}`}>{value}</div>
      {sub && <div className="mt-0.5 text-xs text-text-muted">{sub}</div>}
    </motion.div>
  )
}

export default function SummaryCards() {
  const { data, error } = useApi(api.summary, [])
  if (error) {
    return (
      <div className="max-w-6xl mx-auto px-4 py-3 text-loss text-sm">
        Summary API error: {error}
      </div>
    )
  }
  if (!data) {
    return <div className="max-w-6xl mx-auto px-4 py-4 text-text-muted text-sm">Loading…</div>
  }

  const dayTone = data.today_pnl_usd > 0 ? 'profit' : data.today_pnl_usd < 0 ? 'loss' : 'neutral'
  const wtdTone = data.wtd_pnl_usd > 0 ? 'profit' : data.wtd_pnl_usd < 0 ? 'loss' : 'neutral'
  const armTone = data.armed ? 'profit' : 'loss'

  return (
    <div className="max-w-6xl mx-auto px-4 py-3 grid grid-cols-2 md:grid-cols-5 gap-3">
      <Card
        label="Today"
        value={fmt.usd(data.today_pnl_usd)}
        sub={`${data.today_trades} trade${data.today_trades !== 1 ? 's' : ''} · ${data.today_wins}W / ${data.today_losses}L`}
        tone={dayTone}
      />
      <Card
        label="WTD"
        value={fmt.usd(data.wtd_pnl_usd)}
        sub={`${data.wtd_trades} trade${data.wtd_trades !== 1 ? 's' : ''}`}
        tone={wtdTone}
      />
      <Card
        label="Lifetime"
        value={fmt.usd(data.lifetime_pnl_usd)}
        sub={`${data.lifetime_wins}W / ${data.lifetime_losses}L · ${fmt.pct(data.lifetime_wr)}`}
        tone={data.lifetime_pnl_usd >= 0 ? 'profit' : 'loss'}
      />
      <Card
        label="Open"
        value={fmt.int(data.open_positions)}
        sub={data.open_positions > 0 ? 'positions in market' : 'flat'}
        tone="accent"
      />
      <Card
        label={data.armed ? 'ARMED' : 'NOT ARMED'}
        value={data.paper_mode ? 'paper' : 'LIVE'}
        sub={data.armed ? 'gates passed' : 'arm check failed'}
        tone={armTone}
      />
    </div>
  )
}
