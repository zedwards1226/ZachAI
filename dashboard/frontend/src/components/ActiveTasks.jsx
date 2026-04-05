export default function ActiveTasks({ tasks }) {
  return (
    <div className="neon-card rounded bg-[#080808] p-4 min-h-[220px]">
      <h2 className="text-xs font-bold tracking-widest mb-3 neon-text flex items-center gap-2">
        <span className="text-yellow-400 animate-pulse">▶</span>
        ACTIVE TASKS
        <span className="ml-auto bg-[#001a08] border border-[#00ff41] rounded px-2 py-0.5 text-[10px]">
          {tasks.length}
        </span>
      </h2>

      {tasks.length === 0 ? (
        <p className="text-[#004d18] text-xs mt-6 text-center">
          — no running tasks —
        </p>
      ) : (
        <div className="space-y-2 max-h-64 overflow-y-auto pr-1">
          {tasks.map(task => (
            <div key={task.id}
                 className="border border-[#003311] bg-[#040d06] rounded p-2">
              <div className="flex items-center justify-between mb-1">
                <span className="text-[10px] text-[#006622]">#{task.id}</span>
                <span className="text-[10px] text-yellow-400 animate-pulse">RUNNING</span>
              </div>
              <p className="text-xs text-[#00cc33] truncate mb-1">{task.prompt}</p>
              {task.output && (
                <pre className="text-[10px] text-[#004d18] leading-tight max-h-14 overflow-hidden">
                  {task.output.split('\n').slice(-4).join('\n')}
                </pre>
              )}
              {task.start_time && (
                <p className="text-[10px] text-[#003311] mt-1">
                  Started {new Date(task.start_time).toLocaleTimeString()}
                </p>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
