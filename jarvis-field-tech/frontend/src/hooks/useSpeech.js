import { useCallback, useEffect, useRef, useState } from 'react'

// Pick the most Jarvis-sounding British voice available on the device.
function pickJarvisVoice() {
  const voices = window.speechSynthesis?.getVoices() || []
  const preferences = [
    /Daniel/i,          // iOS British male
    /Google UK English Male/i,
    /Microsoft George/i,
    /Microsoft Ryan/i,
    /Oliver/i,
    /en-GB.*male/i,
    /en-GB/i,
  ]
  for (const re of preferences) {
    const v = voices.find((v) => re.test(`${v.name} ${v.lang}`))
    if (v) return v
  }
  return voices.find((v) => v.lang?.startsWith('en')) || null
}

export function useSpeech() {
  const [listening, setListening] = useState(false)
  const [speaking, setSpeaking] = useState(false)
  const [interim, setInterim] = useState('')
  const [supported, setSupported] = useState(true)
  const recogRef = useRef(null)
  const voiceRef = useRef(null)

  useEffect(() => {
    const SR = window.SpeechRecognition || window.webkitSpeechRecognition
    if (!SR) {
      setSupported(false)
      return
    }
    const r = new SR()
    r.continuous = false
    r.interimResults = true
    r.lang = 'en-US'
    recogRef.current = r

    const loadVoice = () => { voiceRef.current = pickJarvisVoice() }
    loadVoice()
    window.speechSynthesis?.addEventListener?.('voiceschanged', loadVoice)
    return () => window.speechSynthesis?.removeEventListener?.('voiceschanged', loadVoice)
  }, [])

  const start = useCallback((onFinal) => {
    const r = recogRef.current
    if (!r) return
    setInterim('')
    r.onresult = (e) => {
      let finalText = ''
      let interimText = ''
      for (let i = e.resultIndex; i < e.results.length; i++) {
        const chunk = e.results[i][0].transcript
        if (e.results[i].isFinal) finalText += chunk
        else interimText += chunk
      }
      setInterim(interimText)
      if (finalText) {
        setInterim('')
        onFinal?.(finalText.trim())
      }
    }
    r.onend = () => setListening(false)
    r.onerror = () => setListening(false)
    try {
      r.start()
      setListening(true)
    } catch {}
  }, [])

  const stop = useCallback(() => {
    try { recogRef.current?.stop() } catch {}
    setListening(false)
  }, [])

  const speak = useCallback((text) => {
    if (!text || !window.speechSynthesis) return
    window.speechSynthesis.cancel()
    const utter = new SpeechSynthesisUtterance(text)
    if (voiceRef.current) utter.voice = voiceRef.current
    utter.rate = 1.05
    utter.pitch = 0.95
    utter.onstart = () => setSpeaking(true)
    utter.onend = () => setSpeaking(false)
    utter.onerror = () => setSpeaking(false)
    window.speechSynthesis.speak(utter)
  }, [])

  const shutUp = useCallback(() => {
    window.speechSynthesis?.cancel()
    setSpeaking(false)
  }, [])

  return { listening, speaking, interim, supported, start, stop, speak, shutUp }
}
