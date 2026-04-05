# ZACH'S AI COMPANY FACTORY — MASTER BRAIN

## OWNER
Name: Zach Edwards
GitHub: zedwards1226
Telegram: command center
Location: Memphis TN
Work schedule: 7AM-7PM, Fridays off

## VM SETUP
VM Name: ClaudeVM
Host User: zedwa
Shared Folder: C:\ZachAI (also Z: inside VM)
OS: Windows 10
RAM: 6GB
Storage: 200GB

## BACKUP SYSTEM (AUTO)
- Git push every 2 hours via Task Scheduler
- Git push on shutdown via Task Scheduler
- Daily VM snapshot at 2AM via host Task Scheduler
- GitHub repo: https://github.com/zedwards1226/ZachAI

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

## ACTIVE COMPANIES
1. PrecisionFittedParts — eBay F150 dropship (building)
2. WeatherAlpha — Kalshi weather trading bot (live, paper mode)

## WEATHERALPHA STATUS
- Bot API: http://localhost:5000 (Flask, PID auto-started via KalshiBot.vbs)
- Dashboard: http://localhost:3001 (serve.py, auto-started via WeatherAlphaDashboard.vbs)
- Tunnel: localhost.run SSH → https://*.lhr.live (auto-started via WeatherAlphaTunnel.vbs)
- SSH key: C:\Users\zedwa\.ssh\localhost_run_key
- Kalshi keys: C:\ZachAI\kalshi\keys\ (gitignored)
- Paper mode: ON (NEVER change without explicit approval)
- Cities: NYC, CHI, MIA, LAX, MEM, DEN

## AGENT STACK
- SCOUT — scans internet 24/7, daily pitch report to Telegram
- ARCHITECT — designs approved business ideas
- BUILDER — Claude Code builds everything
- OPERATOR — runs companies after launch
- ANALYST — monitors performance

## FREE APIs AVAILABLE
- Open-Meteo (weather)
- FRED (economic data)
- Yahoo Finance (yfinance)
- NewsAPI (free tier)
- GDELT (global news)
- Reddit API
- Google Trends (pytrends)
- GitHub API
- CoinGecko (crypto)
- eBay API (developer account)

## FOLDER STRUCTURE
C:\ZachAI\
├── CLAUDE.md (this file — master brain)
├── RULES.md (operating rules — read every session)
├── backup.bat (auto GitHub push)
├── companies\
│   ├── precisionfittedparts\
│   └── weatheralpha\
├── dropship\
├── kalshi\
│   ├── bots\ (Flask API, trader, edge, scheduler)
│   ├── dashboard\ (React frontend + Flask proxy on :3001)
│   └── keys\ (gitignored — private keys here)
├── agents\
└── logs\

## VM AGENT INSTRUCTIONS
If VM crashes or restarts:
1. Open VirtualBox on host
2. Start ClaudeVM
3. cd C:\ZachAI
4. git pull origin master
5. Resume work from last commit
6. Startup folder scripts auto-launch bot + dashboard + tunnel

## MISSION
Build autonomous digital companies with zero/minimal overhead.
One prompt = one new company.
Every company runs itself after launch.
