# ict-research — Active Files Manifest

Every file in this project must be listed here. If it's not listed, delete it.

## Root
- `CLAUDE.md` — mission + architecture
- `ACTIVE_FILES.md` — this file
- `README.md` — human overview (TBD)

## scout/ (Phase 1 — YouTube → rules)
- `harvester.py` — Agent 1: pulls ICT channel uploads + transcripts via YouTube Data API v3
- `librarian.py` — Agent 2: tags transcripts by ICT setup name (regex taxonomy), groups + dedupes by views
- `extractor.py` — Agent 3: Gemini Flash converts tagged transcripts → mechanizable rules JSON

## forge/ (Phase 2 — rules → backtest)
- `__init__.py` — package marker
- `primitives.py` — ICT building blocks (FVG, OB, MSS, swing points, sessions, PDH/PDL)

## scout/ (cont.)
- `coder.py` — Agent 4: Gemini translates rules JSON → strategy .py with smoke-test gate

## forge/strategies/ (one file per codified ICT setup, generated)
- `order_block__nQfHZ2DEJ8c.py` — OB-based MSS entry (from Mentorship Ep 3, conf 0.95)
- `premium_discount__0LhteuLVuDU.py` — equilibrium-based entry (from Month 1 Elements, conf 0.85)

## data/ (all gitignored except this note)
- `transcripts/` — raw YT transcript JSONs
- `rules/` — LLM-extracted strategy rules
- `backtests/` — backtest result JSONs
- `judge/` — leaderboard JSONs

## logs/
- *(gitignored)*
