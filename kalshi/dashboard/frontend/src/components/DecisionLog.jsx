import { useEffect, useRef } from 'react'

const TYPE_CONFIG = {
  scan:    { color: '#006622', icon: '◈', prefix: 'SCAN' },
  trade:   { color: '#00ff41', icon: '▶', prefix: 'TRADE' },
  block:   { color: '#ff6600', icon: '⊘', prefix: 'BLOCK' },
  skip:    { color: '#003311', icon: '—', prefix: 'SKIP' },
  error:   { color: '#ff0040', icon: '✗', prefix: 'ERROR' },
  system:  { color: '#004d18', icon: '◆', prefix: 'SYS' },
  connect: { color: '#00cc33', icon: '◉', prefix: 'CONN' },
}

function LogEntry({ entry, isNew }) {
  const cfg = TYPE_CONFIG[entry.type] ?? TYPE_CONFIG.system

  return (
    <div className={`flex gap-2 py-1 border-b border-[#020d05] text-[11px] leading-tight
                     ${isNew ? 'log-entry' : ''}`}>
      {/* Timestamp */}
      <span className="shrink-0 text-[#002d11] w-14">
        {new Date(entry.ts).toLocaleTimeString('en-US', {
          hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false
        })}
      </span>

      {/* Icon */}
      <span className="shrink-0 w-3" style={{ color: cfg.color }}>
        {cfg.icon}
      </span>

      {/* Tag */}
      <span className="shrink-0 w-10 text-[9px]" style={{ color: cfg.color }}>
        {cfg.prefix}
      </span>

      {/* Message */}
      <span className="text-[#00aa33] break-all">{entry.msg}</span>
    </div>
  )
}

export default function DecisionLog({ entries }) {
  const scrollRef = useRef(null)

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = 0
    }
  }, [entries.length])

  return (
    <div className="flex flex-col h-full">
      <div ref={scrollRef}
           className="flex-1 overflow-y-auto pr-1 space-y-0"
           style={{ maxHeight: '100%' }}>
        {entries.length === 0 ? (
          <div className="text-[#002211] text-xs text-center mt-8">
            <div className="text-2xl mb-2 text-[#003311]">◈</div>
            awaiting first scan…
          </div>
        ) : (
          entries.map((entry, i) => (
            <LogEntry key={entry.id} entry={entry} isNew={i < 3} />
          ))
        )}
      </div>

      {/* Footer */}
      <div className="border-t border-[#001a08] pt-1 mt-1 text-[9px] text-[#002211] flex justify-between">
        <span>{entries.length} entries</span>
        <span className="blink">■</span>
      </div>
    </div>
  )
}
