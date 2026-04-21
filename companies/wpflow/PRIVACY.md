# wpflow — Privacy

**Last updated:** 2026-04-20

## Short version

- wpflow runs **on your own machine**. It is a local process started by your LLM host (Claude Desktop, Claude Code, Cursor).
- Your WordPress **Application Password never leaves your machine** on the Free / Solo self-host tier. It sits in your Claude Desktop config (or a `.env` file you own) and is sent directly from your machine to your WordPress site over HTTPS.
- wpflow has **no analytics, no telemetry, no phone-home**. The binary does not open any outbound connection except to your configured `WPFLOW_SITE_URL`.
- wpflow writes one local log file at `~/.wpflow/logs/wpflow.log`. Rotating 5 MB × 3. **Authorization headers and the app password are scrubbed before any log line is written.**

## Data flow

```
Claude Desktop (your machine)
        │  stdio
        ▼
wpflow (your machine)
        │  HTTPS, Basic Auth = user:app_password
        ▼
your WordPress site
```

Nothing else is in the loop on the Free / Solo self-host tier.

## What wpflow reads from your WordPress site

Only what the agent asks it to. Each tool call maps 1:1 to a WordPress REST API endpoint. Examples:

| Tool | REST endpoint | Returns |
|---|---|---|
| `list_posts` | `GET /wp/v2/posts` | id, title, status, date, excerpt-200, link (no body HTML by default) |
| `get_post` | `GET /wp/v2/posts/{id}` | full post including body |
| `list_plugins` | `GET /wp/v2/plugins` | slug, name, status, version, author |
| `site_health` | `GET /wp-site-health/v1/tests/*` | WP's own health check results |

Full list: see [README.md](README.md) and `src/wpflow/tools/*.py`.

## What wpflow writes to your WordPress site

Only what the agent asks it to. Writes are **never retried** on failure — if a `create_post` or `update_post` call fails, it fails once and reports the error. Writes include:

- `create_post`, `update_post`, `delete_post`
- `update_page`
- `create_term` (categories / tags)
- `upload_media` (MIME whitelist enforced; 25 MB default cap; SSRF-guarded)
- `activate_plugin`, `deactivate_plugin`
- `moderate_comment`

Every write is logged locally (with the app password scrubbed).

## Logs

- **Location:** `~/.wpflow/logs/wpflow.log` (override with `WPFLOW_LOG_DIR` env var)
- **Rotation:** 5 MB × 3 files
- **Contents:** tool calls, request paths, response status codes, error codes, timing
- **Redacted:** `Authorization` header values, `app_password` (with and without spaces), URL userinfo (`https://user:pass@host`)

Logs stay on your machine. They are never transmitted anywhere by wpflow.

## Hosted tier (v0.2, not yet shipped)

The forthcoming hosted Streamable-HTTP tier will necessarily proxy your requests through a server. When it ships, this privacy doc will be updated to cover:

- where the proxy runs (region, provider)
- what it logs
- what retention policy applies
- how to rotate / revoke app passwords without restarting your agent

If you need a self-hosted deployment for compliance reasons, Free / Solo already gives you that — the hosted tier is purely a convenience for "I can't install Python."

## Third parties

None on Free / Solo self-host tier. wpflow depends on these open-source Python packages at runtime:

- `mcp` (Anthropic) — MCP protocol implementation
- `httpx` — HTTP client
- `pydantic` — schema validation
- `python-dotenv` — `.env` loader

All are installed from PyPI by `pip install wpflow`. wpflow does not bundle any analytics SDK, ad SDK, error-reporting SaaS, or similar.

## Contact

If you find a privacy issue — especially a log leak, a write amplification, or a credential exposure — please open an issue at https://github.com/zedwards1226/wpflow/issues (tag with `security`) or email the maintainer listed in `pyproject.toml`.
