const STATUS = {
  running:          { icon: '⟳', color: 'text-yellow-400' },
  completed:        { icon: '✓', color: 'text-[#00ff41]'  },
  failed:           { icon: '✗', color: 'text-red-500'    },
  pending_approval: { icon: '⏸', color: 'text-orange-400' },
}

function timeSince(iso) {
  if (!iso) return ''
  const diff = Date.now() - new Date(iso).getTime()
  const s = Math.floor(diff / 1000)
  if (s < 60)   return `${s}s ago`
  if (s < 3600) return `${Math.floor(s/60)}m ago`
  return `${Math.floor(s/3600)}h ago`
}

export default function BuildStatus({ tasks }) {
  const recent = [...tasks].reverse().slice(0, 15)

  return (
    <div className="neon-card rounded bg-[#080808] p-4 min-h-[220px]">
      <h2 className="text-xs font-bold tracking-widest mb-3 neon-text flex items-center gap-2">
        <span>▶</span>
        BUILD STATUS
        <span className="ml-auto bg-[#001a08] border border-[#00ff41] rounded px-2 py-0.5 text-[10px]">
          {tasks.filter(t => t.status === 'running').length} running
        </span>
      </h2>

      {recent.length === 0 ? (
        <p className="text-[#004d18] text-xs mt-6 text-center">
          — no builds yet — use /claude in Telegram —
        </p>
      ) : (
        <div className="space-y-1.5 max-h-64 overflow-y-auto pr-1">
          {recent.map(task => {
            const s = STATUS[task.status] ?? { icon: '?', color: 'text-[#004d18]' }
            return (
              <div key={task.id}
                   className="flex items-start gap-2 text-xs border-b border-[#001a08] pb-1.5">
                <span className={`flex-shrink-0 text-sm ${s.color} ${
                  task.status === 'running' ? 'animate-spin' : ''
                }`} style={task.status === 'running' ? {animationDuration:'1.5s'} : {}}>
                  {s.icon}
                </span>
                <div className="min-w-0 flex-1">
                  <p className="text-[#00cc33] truncate leading-tight">
                    {task.prompt?.slice(0, 70) ?? '—'}
                  </p>
                  <div className="flex gap-3 text-[10px] text-[#003311] mt-0.5">
                    <span className={s.color}>{task.status?.toUpperCase()}</span>
                    <span>#{task.id}</span>
                    <span className="ml-auto">{timeSince(task.start_time ?? task.updated_at)}</span>
                  </div>
                </div>
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}
