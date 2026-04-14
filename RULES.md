# WeatherAlpha / ZachAI — Operating Rules

## AUTONOMY RULES
- Never ask for approval on bash commands, file edits, code changes, tool use, or any build decision
- Auto-accept everything: Bash(*), Write(*), Edit(*), Read(*), WebFetch(*), WebSearch(*) in settings.local.json
- Only 3 hard stops requiring Zach approval:
  1. Spending real money on any account
  2. Setting PAPER_MODE=false (going live with real trades)
  3. Adding real credentials or API keys to any file
- If something fails, fix it immediately without asking

## QUALITY RULES
- NEVER say done/complete/ready unless personally tested end to end with real data
- Test every button and interaction before reporting complete
- Test mobile viewport 390px on every UI build
- Check browser console for errors
- Verify API endpoints return real data, not empty responses
- Only report done via Telegram when truly working and tested

## BUILD RULES
- NEVER build from scratch when existing working code exists
- Always search GitHub and public repos first for working implementations
- Clone best 3-5 repos, analyze them, pick the best foundation
- Enhance and customize existing code instead of rebuilding
- Only build from scratch if nothing relevant exists after thorough search

## MEMORY RULES
- Read CLAUDE.md at start of every session
- Update CLAUDE.md after every major build or change
- Keep memory graph updated with all active companies and services

## SECURITY RULES
- Never push credentials, API keys, or .pem files to GitHub
- Always verify .gitignore protects keys/ and .env files before pushing
- Rotate any key that accidentally gets exposed immediately

## ANTI-HALLUCINATION RULES
- NEVER assume file contents — always read the file before editing or referencing it
- NEVER fabricate tool output, API responses, or command results
- If a tool or MCP is unavailable or errors, STOP and report the exact error — do not simulate or substitute results
- Never claim a task is complete without showing actual output or proof
- If a file does not exist, say so — do not invent its contents
- When current state is unknown, run ls or cat to verify — never assume
- If you don't know something, say so — never guess or fill in gaps with plausible-sounding info
- Broken MCPs (memory, sequentialthinking, playwright, filesystem, fetch) — if any of these are invoked and fail, flag it immediately and stop
