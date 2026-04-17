import { useEffect, useRef, useState } from 'react'
import * as pdfjsLib from 'pdfjs-dist'
import pdfWorker from 'pdfjs-dist/build/pdf.worker.min.mjs?url'
import { ChevronLeft, ChevronRight, X } from 'lucide-react'

pdfjsLib.GlobalWorkerOptions.workerSrc = pdfWorker

export default function PDFViewer({ doc, onClose }) {
  const canvasRef = useRef(null)
  const [pdf, setPdf] = useState(null)
  const [page, setPage] = useState(1)
  const [total, setTotal] = useState(0)
  const [scale, setScale] = useState(1.2)

  // Load PDF
  useEffect(() => {
    if (!doc) return
    let cancel = false
    ;(async () => {
      const task = pdfjsLib.getDocument(`/api/drawing/${doc.id}`)
      const p = await task.promise
      if (cancel) return
      setPdf(p)
      setTotal(p.numPages)
      setPage(1)
    })()
    return () => { cancel = true }
  }, [doc])

  // Render page
  useEffect(() => {
    if (!pdf || !canvasRef.current) return
    let cancel = false
    ;(async () => {
      const p = await pdf.getPage(page)
      if (cancel) return
      const viewport = p.getViewport({ scale })
      const canvas = canvasRef.current
      const ctx = canvas.getContext('2d')
      canvas.width = viewport.width
      canvas.height = viewport.height
      await p.render({ canvasContext: ctx, viewport }).promise
    })()
    return () => { cancel = true }
  }, [pdf, page, scale])

  // Keep screen awake while viewing
  useEffect(() => {
    let wakeLock
    if ('wakeLock' in navigator) {
      navigator.wakeLock.request('screen').then((lock) => { wakeLock = lock }).catch(() => {})
    }
    return () => { wakeLock?.release?.() }
  }, [])

  return (
    <div className="absolute inset-0 bg-black/95 z-40 flex flex-col">
      <div className="flex items-center justify-between px-3 py-2 border-b border-cyan-900">
        <div className="text-cyan-300 text-sm truncate">{doc?.name}</div>
        <button onClick={onClose} className="text-cyan-400 p-2"><X size={20} /></button>
      </div>
      <div className="flex-1 overflow-auto flex items-start justify-center p-2">
        <canvas ref={canvasRef} className="max-w-full" />
      </div>
      <div className="flex items-center justify-between px-3 py-2 border-t border-cyan-900 gap-2">
        <button
          onClick={() => setPage((p) => Math.max(1, p - 1))}
          className="p-2 rounded bg-cyan-900/50 text-cyan-200 disabled:opacity-40"
          disabled={page <= 1}
        ><ChevronLeft size={20} /></button>
        <div className="text-cyan-300 text-sm">{page} / {total || '…'}</div>
        <div className="flex gap-1">
          <button onClick={() => setScale((s) => Math.max(0.6, s - 0.2))} className="px-3 py-2 rounded bg-cyan-900/50 text-cyan-200">−</button>
          <button onClick={() => setScale((s) => Math.min(3, s + 0.2))} className="px-3 py-2 rounded bg-cyan-900/50 text-cyan-200">+</button>
        </div>
        <button
          onClick={() => setPage((p) => Math.min(total, p + 1))}
          className="p-2 rounded bg-cyan-900/50 text-cyan-200 disabled:opacity-40"
          disabled={page >= total}
        ><ChevronRight size={20} /></button>
      </div>
    </div>
  )
}
