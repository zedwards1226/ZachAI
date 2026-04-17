import { FileText, Zap } from 'lucide-react'

export default function MachineList({ machines, onPickDoc }) {
  const names = Object.keys(machines || {}).sort()
  if (!names.length) {
    return (
      <div className="p-4 text-slate-400 text-sm">
        No machines cached yet. Configure <code>DRIVE_ROOT_FOLDER_ID</code> in
        <code> .env</code>, then run <code>python backend/drive_client.py --refresh</code>.
      </div>
    )
  }
  return (
    <div className="overflow-y-auto p-3 space-y-3">
      {names.map((name) => {
        const m = machines[name]
        const elec = m.docs.electrical || []
        const man = m.docs.manuals || []
        const other = m.docs.other || []
        return (
          <div key={name} className="border border-cyan-900 rounded-lg p-3 bg-black/30">
            <div className="text-cyan-300 font-semibold text-sm tracking-wide uppercase">{name}</div>
            {elec.length > 0 && <DocGroup icon={<Zap size={14} />} label="Electrical" docs={elec} machine={name} onPick={onPickDoc} />}
            {man.length > 0 && <DocGroup icon={<FileText size={14} />} label="Manuals" docs={man} machine={name} onPick={onPickDoc} />}
            {other.length > 0 && <DocGroup icon={<FileText size={14} />} label="Other" docs={other} machine={name} onPick={onPickDoc} />}
          </div>
        )
      })}
    </div>
  )
}

function DocGroup({ icon, label, docs, machine, onPick }) {
  return (
    <div className="mt-2">
      <div className="flex items-center gap-2 text-cyan-500 text-xs uppercase tracking-wider">
        {icon} {label}
      </div>
      <div className="mt-1 space-y-1">
        {docs.map((d) => (
          <button
            key={d.id}
            onClick={() => onPick({ ...d, machine })}
            className="w-full text-left text-sm text-slate-200 hover:text-cyan-300 px-2 py-1 rounded hover:bg-cyan-900/30"
          >
            {d.name}
          </button>
        ))}
      </div>
    </div>
  )
}
