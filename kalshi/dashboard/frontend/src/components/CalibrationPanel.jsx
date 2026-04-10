import { Target, TrendingUp, BarChart3 } from 'lucide-react'

function Metric({ label, value, color, sub }) {
  return (
    <div className="flex flex-col items-center gap-1 px-3 py-2">
      <span className="text-[9px] font-semibold text-text-muted" style={{ letterSpacing: '0.06em' }}>
        {label}
      </span>
      <span className="stat-value text-xl font-bold" style={{ color }}>
        {value}
      </span>
      {sub && <span className="text-[9px] text-text-muted">{sub}</span>}
    </div>
  )
}

export default function CalibrationPanel({ calibration }) {
  const c = calibration ?? {}
  const accuracy = c.accuracy ?? 0
  const brier = c.brier_score ?? 0
  const total = c.total_signals ?? 0
  const settled = c.settled ?? 0
  const correct = c.correct ?? 0

  const accColor = accuracy >= 0.55 ? '#26de81' : accuracy >= 0.45 ? '#fbbf24' : '#ff5e7d'
  const brierColor = brier <= 0.20 ? '#26de81' : brier <= 0.25 ? '#fbbf24' : '#ff5e7d'
  const brierLabel = brier <= 0.20 ? 'Good' : brier <= 0.25 ? 'Fair' : 'Poor'

  return (
    <div className="flex flex-col gap-3">
      <div className="flex items-center gap-2 mb-1">
        <Target size={13} style={{ color: '#818cf8' }} />
        <span className="text-[10px] font-semibold text-text-muted" style={{ letterSpacing: '0.08em' }}>
          MODEL CALIBRATION
        </span>
      </div>

      {total === 0 ? (
        <div className="text-sm text-text-muted text-center py-4">
          No signals tracked yet
        </div>
      ) : (
        <>
          {/* Large accuracy display */}
          <div className="flex items-center justify-center gap-6">
            <Metric
              label="ACCURACY"
              value={`${(accuracy * 100).toFixed(0)}%`}
              color={accColor}
              sub={`${correct} / ${settled} settled`}
            />
            <div className="w-px h-10" style={{ background: '#2a2a3a' }} />
            <Metric
              label="BRIER SCORE"
              value={brier.toFixed(3)}
              color={brierColor}
              sub={brierLabel}
            />
          </div>

          {/* Accuracy bar */}
          <div>
            <div className="flex items-center justify-between text-[10px] mb-1">
              <span className="text-text-muted">Prediction Accuracy</span>
              <span className="stat-value" style={{ color: accColor }}>
                {(accuracy * 100).toFixed(1)}%
              </span>
            </div>
            <div className="probability-bar">
              <div
                className="probability-bar-fill"
                style={{
                  width: `${accuracy * 100}%`,
                  background: accColor,
                }}
              />
            </div>
          </div>

          {/* Signal counts */}
          <div className="flex items-center justify-between text-[10px] pt-2 border-t" style={{ borderColor: '#2a2a3a' }}>
            <div>
              <span className="text-text-muted">Total Signals: </span>
              <span className="stat-value text-text-secondary">{total}</span>
            </div>
            <div>
              <span className="text-text-muted">Settled: </span>
              <span className="stat-value text-text-secondary">{settled}</span>
            </div>
            <div>
              <span className="text-text-muted">Pending: </span>
              <span className="stat-value" style={{ color: '#818cf8' }}>{total - settled}</span>
            </div>
          </div>
        </>
      )}
    </div>
  )
}
