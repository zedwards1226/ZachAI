// Fuzzy match a spoken/typed query to a machine doc.
// Returns { machine, doc, score } or null.

const STOP_WORDS = new Set([
  'a','an','the','of','on','in','for','to','me','show','open','pull','up','view','display',
  'please','jarvis','find','get','bring','give','can','you','hey','ok','okay','and','or',
  'drawing','drawings','manual','manuals','doc','docs','document','documents','pdf','print','prints',
  'file','files','the','that','this','it','go','look','at','i','want','need','like',
])

function tokens(s) {
  return (s || '')
    .toLowerCase()
    .replace(/[._\-()\[\]]/g, ' ')
    .replace(/[^a-z0-9\s]/g, ' ')
    .split(/\s+/)
    .filter(Boolean)
    .filter(t => !STOP_WORDS.has(t))
}

export function findDoc(question, machines) {
  const qTokens = tokens(question)
  if (qTokens.length === 0) return null

  let best = null
  for (const [machineName, info] of Object.entries(machines || {})) {
    const machineTokens = tokens(machineName)
    for (const bucket of ['electrical', 'manuals', 'other']) {
      for (const doc of (info.docs?.[bucket] || [])) {
        const docTokens = tokens(doc.name)
        const all = new Set([...machineTokens, ...docTokens])
        let hits = 0
        for (const t of qTokens) {
          if (all.has(t)) hits++
          else {
            // partial match (e.g. "fault" matches "faults")
            for (const a of all) {
              if (a.length >= 4 && (a.includes(t) || t.includes(a))) { hits += 0.6; break }
            }
          }
        }
        const score = hits / Math.max(qTokens.length, 1)
        if (!best || score > best.score) {
          best = { machine: machineName, doc, score }
        }
      }
    }
  }
  // Need >=50% of query tokens to match before auto-opening
  if (best && best.score >= 0.5) return best
  return null
}

const OPEN_VERBS = /\b(open|show|pull\s*up|view|display|bring\s*up|find|get|go\s*to)\b/i

export function looksLikeOpenCommand(question) {
  return OPEN_VERBS.test(question || '')
}
