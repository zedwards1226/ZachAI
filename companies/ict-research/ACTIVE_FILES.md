# ict-research — Active Files Manifest

Every file in this project must be listed here. If it's not listed, delete it.

## Root
- `CLAUDE.md` — mission + architecture
- `ACTIVE_FILES.md` — this file
- `README.md` — human overview (TBD)

## scout/ (Phase 1 — YouTube → rules)
- `harvester.py` — Agent 1: pulls ICT channel uploads + transcripts via YouTube Data API v3

## forge/ (Phase 2 — rules → backtest)
- *(empty — pending Phase 2 build)*

## forge/strategies/ (one file per codified ICT setup)
- *(empty — Coder agent generates these)*

## data/ (all gitignored except this note)
- `transcripts/` — raw YT transcript JSONs
- `rules/` — LLM-extracted strategy rules
- `backtests/` — backtest result JSONs
- `judge/` — leaderboard JSONs

## logs/
- *(gitignored)*
