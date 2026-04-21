# wpflow — ACTIVE FILES manifest

All tracked files. If a file isn't here, it shouldn't exist.

## Top level (project root)
- `ARCHITECTURE.md` — v0.1 spec (authoritative)
- `README.md` — install / configure / Claude Desktop snippet / quirks
- `CLAUDE.md` — project brain
- `ACTIVE_FILES.md` — this file
- `LICENSE` — MIT
- `PRIVACY.md` — privacy / data-flow statement (public-facing)
- `PRICING.md` — pricing tiers (public-facing)
- `MONETIZATION.md` — internal go-to-market plan (NOT shipped in public repo)
- `pyproject.toml` — PyPI package config (editable install + `wpflow` CLI entry point)
- `requirements.txt` — pinned runtime deps (kept alongside pyproject.toml for back-compat)
- `.env.example` — env var template
- `.gitignore` — blocks `.env`, `data/test_site.json`, `data/_seed.py`, `logs/`, `.venv/`, `dist/`, `build/`, `*.egg-info/`
- `server.py` — **compatibility shim** for Claude Desktop configs pointing at the old path; forwards to `wpflow.server:main`
- `test_server.py` — 13-phase live end-to-end harness (41 assertions)

## src/wpflow/ — installable Python package
- `src/wpflow/__init__.py` — `__version__ = "0.1.0"`
- `src/wpflow/server.py` — MCP entry (stdio, official `mcp` SDK). Exports `main()` for the `wpflow` CLI entry point.
- `src/wpflow/wp_client.py` — httpx REST client, auth, retries, secret scrubbing, 5 MB cap, browserish UA
- `src/wpflow/errors.py` — 20-code error taxonomy + `WPClientError`
- `src/wpflow/config.py` — env-var loader (dotenv)

## src/wpflow/tools/ — one module per tool group
- `tools/__init__.py` — aggregator
- `tools/_common.py` — summary/excerpt/pagination helpers
- `tools/posts.py` — list_posts, get_post, create_post, update_post, delete_post, search_content
- `tools/pages.py` — list_pages, get_page, update_page
- `tools/media.py` — list_media, upload_media
- `tools/plugins.py` — list_plugins, activate_plugin, deactivate_plugin
- `tools/themes.py` — list_themes, get_active_theme
- `tools/users.py` — list_users, get_user
- `tools/comments.py` — list_comments, moderate_comment
- `tools/taxonomy.py` — list_categories, list_tags, create_term
- `tools/health.py` — verify_connection, site_health

## docs/
- `docs/app_password_setup.md` — 4-step guide for creating a WP Application Password
- `docs/screenshots/*.png` — launch screenshots (captured Day 0 per runbook)

## data/ (mostly gitignored)
- `data/INGESTION.md` — test site provisioning record (tracked)
- `data/test_site.json` — live creds (GITIGNORED)
- `data/_seed.py` — one-shot seeder (GITIGNORED)

## logs/ (gitignored)
- Runtime logs now live at `~/.wpflow/logs/wpflow.log` (override with `WPFLOW_LOG_DIR`). The legacy `./logs/` dir is kept for historical local runs but no longer written to by default.

## dist/ (gitignored)
- `dist/wpflow-0.1.0-py3-none-any.whl` — PyPI wheel (built by `python -m build`)
- `dist/wpflow-0.1.0.tar.gz` — PyPI sdist

## launch/ (internal, NOT shipped in public repo)
- `launch/00_LAUNCH_RUNBOOK.md` — step-by-step launch ops (gh auth, pypi upload, MCPize submit, Reddit/HN/Dev.to posting order)
- `launch/01_demo_video_script.md` — 75-second demo beat sheet
- `launch/02_mcpize_listing.md` — MCPize listing copy
- `launch/03_reddit_r_mcp.md` — r/mcp launch post
- `launch/04_reddit_r_claudeai.md` — r/ClaudeAI launch post (first-principles rewrite)
- `launch/05_hn_show_hn.md` — Show HN post
- `launch/06_devto_post.md` — Dev.to technical walkthrough + Medium cross-post
- `launch/07_x_thread.md` — 8-tweet X/Twitter thread

## Tool count
**25 tools** registered with the MCP server. 41/41 end-to-end tests pass.

## Public repo mirror
- `C:\wpflow-public\` — standalone git repo, ready for `gh repo create zedwards1226/wpflow --public --source=. --push`.
  - Includes everything above EXCEPT: `.venv/`, `__pycache__/`, `logs/`, `data/test_site.json`, `data/_seed.py`, `dist/`, `MONETIZATION.md`, `CLAUDE.md`, `launch/` (all internal go-to-market docs).
  - Adds `.github/workflows/ci.yml`, `.github/ISSUE_TEMPLATE/*.md`, `CHANGELOG.md`.
