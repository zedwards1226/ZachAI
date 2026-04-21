# wpflow — Project Brain

## Overview
**wpflow** is a local-first MCP server that lets an LLM agent operate a live WordPress site through the WP REST API, authenticated by an Application Password. Built per `ARCHITECTURE.md` v0.1.

- **Mode:** LOCAL / PAPER (no real-money path, no production site wired in yet).
- **Transport:** stdio (official `mcp` Python SDK) — **not** FastMCP, **not** HTTP.
- **Python:** 3.11+ (tested on 3.14 via `.venv`).
- **Tools:** 25 total — see ACTIVE_FILES.md.

## Services + ports
None. This is a stdio server; invoked by the LLM host (Claude Desktop / Claude Code) and communicates over stdin/stdout. No listening ports.

## Key files
- `server.py` — MCP entry, `main()` runs the stdio loop.
- `wp_client.py` — httpx sync client, 5 MB cap, secret scrubber, retry policy (GET ×2 on 5xx, writes never retry), browserish User-Agent (Cloudflare workaround).
- `tools/*.py` — one module per tool group.
- `errors.py` — 20-code error taxonomy.
- `config.py` — env loader (dotenv).
- `test_server.py` — live end-to-end harness (read creds from `data/test_site.json`).
- `logs/wpflow.log` — rotating, scrubbed.

## Live test site
- Provider: TasteWP free (48 h TTL from 2026-04-20).
- Cloudflare in front — browserish User-Agent is mandatory.
- Creds in `data/test_site.json` (gitignored).

## Run
```bash
# Install
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt

# Test end-to-end (live site)
.venv\Scripts\python test_server.py

# Claude Desktop: see README.md for JSON snippet
```

## Auto-merge exception
**None** — wpflow is a greenfield MCP server, not live-trading or credentialed infra. Standard merge policy applies.

## Security constraints (hard rules)
1. No code-exec paths (no `eval`, `exec`, `pickle.loads`, shell-out).
2. No generic `wp_request` / REST-passthrough tool.
3. MIME whitelist on `upload_media` + SSRF guard on URL sources + path denylist on local sources.
4. TLS verify always on; `WPFLOW_ALLOW_INSECURE=1` only relaxes `https://` URL check.
5. Logs scrub Authorization headers, app password (with and without spaces), URL userinfo.
6. 5 MB response cap.
7. Writes (POST/DELETE) never auto-retry.

## Status (2026-04-20)
- All 25 tools implemented and live-tested against TasteWP site → **41/41 PASS**.
- Log file populated, no app password leakage.
- `data/test_site.json` + `data/_seed.py` confirmed gitignored.
- Ready to publish to GitHub / PyPI when an owner Application Password for the real site is supplied.

## Next
- Phase 4 VERIFY — run harness again after any test site refresh.
- Phase 5 LAUNCH STUB — push public, README + r/mcp + r/ClaudeAI post quoting Signals 3 and 4.
- v0.2 scope: multi-site, Streamable HTTP transport for hosted SaaS tier, `create_page`, WooCommerce read-only.
