import { useState, useEffect } from 'react'

const PROJECTS = [
  { name: 'Dropship',        path: 'dropship',         desc: 'Auto parts dropshipping',         color: '#00ff41' },
  { name: 'Kalshi',          path: 'kalshi',           desc: 'Prediction market trading',        color: '#00ff41' },
  { name: 'Telegram Bridge', path: 'telegram-bridge',  desc: 'Claude Code integration',          color: '#00ff41' },
  { name: 'Dashboard',       path: 'dashboard',        desc: 'Command center',                   color: '#00ff41' },
]

function SysMetric({ label, value, color = '#00ff41' }) {
  return (
    <div className="flex justify-between text-xs border-b border-[#001a08] py-1">
      <span className="text-[#006622]">{label}</span>
      <span style={{ color }}>{value}</span>
    </div>
  )
}

export default function CompanyStatus() {
  const [now, setNow] = useState(new Date())

  useEffect(() => {
    const t = setInterval(() => setNow(new Date()), 1000)
    return () => clearInterval(t)
  }, [])

  const uptime = Math.floor(performance.now() / 1000)
  const uptimeStr = uptime < 60
    ? `${uptime}s`
    : uptime < 3600
    ? `${Math.floor(uptime/60)}m ${uptime%60}s`
    : `${Math.floor(uptime/3600)}h ${Math.floor((uptime%3600)/60)}m`

  return (
    <div className="neon-card rounded bg-[#080808] p-4 min-h-[220px]">
      <h2 className="text-xs font-bold tracking-widest mb-3 neon-text flex items-center gap-2">
        <span>▶</span>
        COMPANY STATUS
      </h2>

      {/* System metrics */}
      <div className="mb-4">
        <SysMetric label="SYS_TIME"   value={now.toLocaleString()} />
        <SysMetric label="DASHBOARD_UPTIME" value={uptimeStr} />
        <SysMetric label="OPERATOR"   value="ZachAI" />
        <SysMetric label="ENGINE"     value="Claude Code" color="#00cc33" />
      </div>

      {/* Projects */}
      <div className="space-y-2">
        {PROJECTS.map(p => (
          <div key={p.path} className="flex items-center gap-3">
            <span className="w-1.5 h-1.5 rounded-full flex-shrink-0 animate-pulse-neon"
                  style={{ backgroundColor: p.color, boxShadow: `0 0 6px ${p.color}` }} />
            <div className="flex-1 min-w-0">
              <span className="text-xs text-[#00ff41]">{p.name}</span>
              <span className="text-[10px] text-[#004d18] ml-2">{p.desc}</span>
            </div>
            <span className="text-[10px] text-[#006622] flex-shrink-0">ACTIVE</span>
          </div>
        ))}
      </div>

      <div className="mt-4 pt-2 border-t border-[#001a08]">
        <p className="text-[10px] text-[#002211] cursor-class">
          ZACHAI AUTONOMOUS OPERATIONS v1.0<span className="cursor" />
        </p>
      </div>
    </div>
  )
}
