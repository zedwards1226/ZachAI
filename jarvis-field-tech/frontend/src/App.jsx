import { useEffect, useState } from 'react'
import { List, MessageSquare } from 'lucide-react'
import JarvisHUD from './components/JarvisHUD.jsx'
import VoiceInput from './components/VoiceInput.jsx'
import ChatLog from './components/ChatLog.jsx'
import MachineList from './components/MachineList.jsx'
import PDFViewer from './components/PDFViewer.jsx'
import { useSpeech } from './hooks/useSpeech.js'
import { api, apiPost } from './hooks/useApi.js'
import { findDoc, looksLikeOpenCommand } from './lib/docMatch.js'

export default function App() {
  const speech = useSpeech()
  const [messages, setMessages] = useState([])
  const [machines, setMachines] = useState({})
  const [machineName, setMachineName] = useState('')
  const [activeDoc, setActiveDoc] = useState(null)
  const [view, setView] = useState('chat') // 'chat' | 'list'
  const [booted, setBooted] = useState(false)

  // Boot sequence: greet + load machines
  useEffect(() => {
    if (booted) return
    setBooted(true)
    api('/machines')
      .then((r) => setMachines(r.machines || {}))
      .catch(() => {})
    api('/greet')
      .then((r) => {
        if (r.text) {
          setMessages([{ role: 'assistant', content: r.text }])
          // Small delay so Web Speech voices register on first load
          setTimeout(() => speech.speak(r.text), 400)
        }
      })
      .catch(() => {})
  }, [booted, speech])

  const send = async (question) => {
    const history = messages.slice(-6)
    setMessages((m) => [...m, { role: 'user', content: question }])

    // Intent: "open/show/pull up <drawing name>" → match a doc and display it
    if (looksLikeOpenCommand(question)) {
      const match = findDoc(question, machines)
      if (match) {
        const doc = { ...match.doc, machine: match.machine, _open: true }
        setMachineName(match.machine)
        setActiveDoc(doc)
        const reply = `Pulling up ${match.doc.name} for ${match.machine}.`
        setMessages((m) => [...m, { role: 'assistant', content: reply }])
        speech.speak(reply)
        return
      }
    }

    try {
      const r = await apiPost('/ask', {
        question,
        machine: machineName,
        doc_id: activeDoc?.id || '',
        history,
      })
      const text = r.text || r.error || '(no response)'
      setMessages((m) => [...m, { role: 'assistant', content: text }])
      speech.speak(text)
    } catch (e) {
      setMessages((m) => [...m, { role: 'assistant', content: `Error: ${e.message}` }])
    }
  }

  const hudState = speech.listening ? 'listening' : speech.speaking ? 'speaking' : 'idle'

  return (
    <div className="h-full flex flex-col">
      <header className="flex items-center justify-between px-4 py-2 border-b border-cyan-900 bg-black/40">
        <div className="text-cyan-300 tracking-widest text-sm">JARVIS · FIELD TECH</div>
        <div className="flex gap-2">
          <button
            onClick={() => setView(view === 'chat' ? 'list' : 'chat')}
            className="p-2 rounded bg-cyan-900/40 text-cyan-200 border border-cyan-800"
            aria-label="Toggle view"
          >
            {view === 'chat' ? <List size={18} /> : <MessageSquare size={18} />}
          </button>
        </div>
      </header>

      <div className="py-6 flex-shrink-0">
        <JarvisHUD state={hudState} />
      </div>

      {machineName && (
        <div className="text-center text-xs text-cyan-400 mb-1">
          Focus: <span className="text-cyan-200">{machineName}</span>
          {activeDoc && <> · <span className="text-cyan-200">{activeDoc.name}</span></>}
        </div>
      )}

      <div className="flex-1 flex flex-col min-h-0">
        {view === 'chat'
          ? <ChatLog messages={messages} />
          : <MachineList machines={machines} onPickDoc={(d) => {
              setMachineName(d.machine)
              setActiveDoc(d)
              setView('chat')
            }} />
        }
      </div>

      <VoiceInput
        listening={speech.listening}
        interim={speech.interim}
        supported={speech.supported}
        onStartMic={() => speech.start(send)}
        onStopMic={speech.stop}
        onSend={send}
      />

      {activeDoc && view === 'chat' && (
        <button
          onClick={() => setActiveDoc({ ...activeDoc, _open: true })}
          className="absolute right-3 bottom-24 rounded-full bg-cyan-500 text-black px-4 py-2 shadow-lg shadow-cyan-500/40"
        >
          View drawing
        </button>
      )}

      {activeDoc?._open && (
        <PDFViewer
          doc={activeDoc}
          onClose={() => setActiveDoc((d) => ({ ...d, _open: false }))}
        />
      )}
    </div>
  )
}
