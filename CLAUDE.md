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

## RULES
- Always work inside C:\ZachAI
- Never store code outside shared folder
- Run backup.bat manually after major builds
- Always shut down VM properly from Start Menu
- Push to GitHub after every completed feature

## ACTIVE COMPANIES
1. PrecisionFittedParts — eBay F150 dropship (building)
2. WeatherAlpha — Kalshi weather trading bot (building)

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
├── backup.bat (auto GitHub push)
├── companies\
│   ├── precisionfittedparts\
│   └── weatheralpha\
├── dropship\
├── kalshi\
├── agents\
└── logs\

## VM AGENT INSTRUCTIONS
If VM crashes or restarts:
1. Open VirtualBox on host
2. Start ClaudeVM
3. cd C:\ZachAI
4. git pull origin master
5. Resume work from last commit

## MISSION
Build autonomous digital companies with zero/minimal overhead.
One prompt = one new company.
Every company runs itself after launch.