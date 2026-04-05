import { useEffect, useRef } from 'react'

export default function TelegramFeed({ messages }) {
  const bottomRef = useRef(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages.length])

  const recent = messages.slice(-30)

  return (
    <div className="neon-card rounded bg-[#080808] p-4 min-h-[220px]">
      <h2 className="text-xs font-bold tracking-widest mb-3 neon-text flex items-center gap-2">
        <span>▶</span>
        TELEGRAM FEED
        <span className="ml-auto bg-[#001a08] border border-[#00ff41] rounded px-2 py-0.5 text-[10px]">
          {messages.length}
        </span>
      </h2>

      <div className="space-y-1.5 max-h-64 overflow-y-auto pr-1">
        {recent.length === 0 ? (
          <p className="text-[#004d18] text-xs mt-6 text-center">
            — no messages yet —
          </p>
        ) : (
          recent.map(msg => (
            <div
              key={msg.id}
              className={`text-xs rounded p-2 ${
                msg.direction === 'in'
                  ? 'bg-[#001a08] border-l-2 border-[#00ff41]'
                  : 'bg-[#000d05] border-l-2 border-[#005522] ml-3'
              }`}
            >
              <div className="flex justify-between items-center mb-0.5">
                <span className={`text-[10px] font-bold ${
                  msg.direction === 'in' ? 'text-[#00ff41]' : 'text-[#006622]'
                }`}>
                  {msg.direction === 'in' ? '← YOU' : '→ BOT'}
                </span>
                <span className="text-[10px] text-[#002211]">
                  {new Date(msg.timestamp).toLocaleTimeString()}
                </span>
              </div>
              <p className="text-[#00aa33] break-words">{msg.text}</p>
            </div>
          ))
        )}
        <div ref={bottomRef} />
      </div>
    </div>
  )
}
