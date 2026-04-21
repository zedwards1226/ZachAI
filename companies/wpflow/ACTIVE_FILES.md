# wpflow — ACTIVE FILES manifest

All tracked files. If a file isn't here, it shouldn't exist.

## Top level
- `ARCHITECTURE.md` — v0.1 spec (authoritative)
- `README.md` — install / configure / Claude Desktop snippet / quirks
- `CLAUDE.md` — project brain
- `ACTIVE_FILES.md` — this file
- `requirements.txt` — pinned runtime deps
- `.env.example` — env var template
- `.gitignore` — blocks `.env`, `data/test_site.json`, `data/_seed.py`, `logs/`, `.venv/`
- `server.py` — MCP entry (stdio, official `mcp` SDK)
- `wp_client.py` — httpx REST client, auth, retries, secret scrubbing, 5MB cap
- `errors.py` — 20-code error taxonomy + `WPClientError`
- `config.py` — env-var loader (dotenv)
- `test_server.py` — 13-phase live end-to-end harness

## tools/ — one module per tool group
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

## data/ (mostly gitignored)
- `data/INGESTION.md` — test site provisioning record (tracked)
- `data/test_site.json` — live creds (GITIGNORED)
- `data/_seed.py` — one-shot seeder (GITIGNORED)

## logs/ (gitignored)
- `logs/wpflow.log` — rotating file handler, 5 MB × 3, secrets scrubbed

## Tool count
**25 tools** registered with the MCP server.
