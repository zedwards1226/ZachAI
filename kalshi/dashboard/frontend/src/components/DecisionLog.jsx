import { useEffect, useRef } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import * as ScrollArea from '@radix-ui/react-scroll-area'

const TYPE_CONFIG = {
  scan:    { color: '#818cf8', label: 'SCAN'  },
  trade:   { color: '#26de81', label: 'TRADE' },
  block:   { color: '#ff5e7d', label: 'BLOCK' },
  skip:    { color: '#fbbf24', label: 'SKIP'  },
  error:   { color: '#ff5e7d', label: 'ERROR' },
  system:  { color: '#475569', label: 'SYS'   },
  connect: { color: '#38bdf8', label: 'CONN'  },
}

function TypeBadge({ type }) {
  const cfg = TYPE_CONFIG[type] ?? TYPE_CONFIG.system
  return (
    <span
      className="shrink-0 text-[9px] font-bold px-1.5 py-0.5 rounded"
      style={{
        color: cfg.color,
        background: `${cfg.color}18`,
        border: `1px solid ${cfg.color}30`,
        letterSpacing: '0.05em',
        lineHeight: 1,
      }}
    >
      {cfg.label}
    </span>
  )
}

function LogEntry({ entry }) {
  return (
    <motion.div
      initial={{ x: -8, opacity: 0 }}
      animate={{ x: 0,  opacity: 1 }}
      exit={{ opacity: 0 }}
      transition={{ duration: 0.2, ease: 'easeOut' }}
      className="flex items-start gap-2 py-2 border-b"
      style={{ borderColor: '#1a1a24' }}
    >
      <span
        className="stat-value shrink-0 text-[10px] text-text-muted pt-px"
        style={{ minWidth: '6ch' }}
      >
        {new Date(entry.ts).toLocaleTimeString('en-US', {
          hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false,
        })}
      </span>
      <TypeBadge type={entry.type} />
      <span
        className="text-[11px] leading-snug break-all"
        style={{ color: '#94a3b8' }}
      >
        {entry.msg}
      </span>
    </motion.div>
  )
}

export default function DecisionLog({ entries }) {
  const viewportRef = useRef(null)

  useEffect(() => {
    if (viewportRef.current) {
      viewportRef.current.scrollTop = 0
    }
  }, [entries.length])

  return (
    <div className="flex flex-col h-full">
      <ScrollArea.Root className="flex-1 min-h-0 overflow-hidden">
        <ScrollArea.Viewport
          ref={viewportRef}
          className="h-full w-full"
          style={{ maxHeight: '100%' }}
        >
          {entries.length === 0 ? (
            <div
              className="flex flex-col items-center justify-center py-12 text-sm"
              style={{ color: '#475569' }}
            >
              <div
                className="text-3xl mb-3 opacity-30"
                style={{ color: '#818cf8' }}
              >
                ◈
              </div>
              Awaiting first scan…
            </div>
          ) : (
            <AnimatePresence initial={false}>
              {entries.map(entry => (
                <LogEntry key={entry.id} entry={entry} />
              ))}
            </AnimatePresence>
          )}
        </ScrollArea.Viewport>
        <ScrollArea.Scrollbar
          orientation="vertical"
          className="flex select-none touch-none"
          style={{ width: 4, padding: '2px 0' }}
        >
          <ScrollArea.Thumb
            style={{
              background: '#2a2a3a',
              borderRadius: 2,
              flex: 1,
            }}
          />
        </ScrollArea.Scrollbar>
      </ScrollArea.Root>

      {/* Footer */}
      <div
        className="flex items-center justify-between pt-2 mt-1 border-t text-[10px]"
        style={{ borderColor: '#2a2a3a' }}
      >
        <span className="text-text-muted">{entries.length} entries</span>
        <div className="flex items-center gap-1.5">
          <div
            className="w-1.5 h-1.5 rounded-full animate-pulse-glow"
            style={{ background: '#26de81' }}
          />
          <span style={{ color: '#26de81' }}>LIVE</span>
        </div>
      </div>
    </div>
  )
}
