# Sandbox

Experiments workspace. Nothing here auto-starts. Nothing here touches production state.

## Start a new experiment

```bash
# From C:\ZachAI\
cp -r sandbox/_template sandbox/my-idea
cd sandbox/my-idea
# Edit CLAUDE.md — scope, deps, port
# Edit run.py — your code
python run.py
```

## Rules (full details in `CLAUDE.md`)
- Ports 8000–8999 only
- No writes outside `sandbox/`
- No imports from `trading/`, `kalshi/`, `companies/`
- No VBS, no auto-start
- PAPER_MODE=True always
- Each experiment: its own subfolder + CLAUDE.md + ACTIVE_FILES.md

## Graduate an experiment
When it works + Zach approves, cherry-pick the files into `trading/` / `kalshi/` / etc., update their CLAUDE.md + ACTIVE_FILES.md, delete the sandbox subfolder.

## Why this exists
So you can try new Kalshi strategies, new ORB signal agents, new MCP integrations, etc., without accidentally killing a live bot during market hours.
