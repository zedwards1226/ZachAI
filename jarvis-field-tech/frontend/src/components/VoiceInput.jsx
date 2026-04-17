import { Mic, MicOff, Send } from 'lucide-react'
import { useState } from 'react'

export default function VoiceInput({ listening, interim, supported, onStartMic, onStopMic, onSend }) {
  const [text, setText] = useState('')

  const send = () => {
    const q = text.trim()
    if (!q) return
    onSend(q)
    setText('')
  }

  return (
    <div className="flex items-center gap-2 p-3 bg-black/40 backdrop-blur border-t border-cyan-900">
      {supported && (
        <button
          onClick={listening ? onStopMic : onStartMic}
          className={`w-12 h-12 rounded-full flex items-center justify-center transition
            ${listening ? 'bg-amber-500 text-black shadow-lg shadow-amber-500/50' : 'bg-cyan-500 text-black shadow-lg shadow-cyan-500/50'}`}
          aria-label={listening ? 'Stop listening' : 'Start listening'}
        >
          {listening ? <MicOff size={22} /> : <Mic size={22} />}
        </button>
      )}
      <input
        type="text"
        value={listening ? interim : text}
        onChange={(e) => setText(e.target.value)}
        onKeyDown={(e) => e.key === 'Enter' && send()}
        placeholder={listening ? 'Listening…' : 'Ask Jarvis…'}
        className="flex-1 bg-black/60 border border-cyan-900 rounded px-3 py-3 text-cyan-100 placeholder-cyan-700 focus:outline-none focus:border-cyan-400"
        readOnly={listening}
      />
      <button
        onClick={send}
        className="w-12 h-12 rounded bg-cyan-900/60 border border-cyan-500 text-cyan-300 flex items-center justify-center"
        aria-label="Send"
      >
        <Send size={18} />
      </button>
    </div>
  )
}
