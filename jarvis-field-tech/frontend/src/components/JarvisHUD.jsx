export default function JarvisHUD({ state = 'idle' }) {
  const status = state === 'speaking' ? 'Speaking' : state === 'listening' ? 'Listening' : 'Online'
  return (
    <div className={`hud ${state}`}>
      <div className="hud-ring r1" />
      <div className="hud-ring r2" />
      <div className="hud-ring r3" />
      <div className="hud-core" />
      <div className="hud-status">{status}</div>
    </div>
  )
}
