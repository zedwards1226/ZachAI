import { useEffect, useRef } from 'react'

export default function ChatLog({ messages }) {
  const endRef = useRef(null)
  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages.length])

  return (
    <div className="flex-1 overflow-y-auto px-3 py-2 space-y-2">
      {messages.map((m, i) => (
        <div
          key={i}
          className={`max-w-[85%] rounded-lg px-3 py-2 text-sm leading-relaxed whitespace-pre-wrap
            ${m.role === 'user'
              ? 'ml-auto bg-cyan-900/40 border border-cyan-700 text-cyan-100'
              : 'mr-auto bg-slate-800/70 border border-slate-700 text-slate-100'}`}
        >
          {m.content}
        </div>
      ))}
      <div ref={endRef} />
    </div>
  )
}
