# wpflow — WordPress Operator MCP Server

**v0.1** · Single-site WordPress operator for LLM agents (Claude Desktop, Claude Code, Cursor).
Authenticates with a WordPress **Application Password** — no OAuth, no vendor review.
Local-first, stdio transport, official Anthropic `mcp` SDK.

**Pricing intent (launch):** Solo $19/mo · Pro $49/mo · Agency $149/mo. Free tier = local install, 1 site.

---

## What it does

Gives an agent 25 task-scoped tools against a live WP site via the REST API:

- Posts — `list_posts`, `get_post`, `create_post`, `update_post`, `delete_post`, `search_content`
- Pages — `list_pages`, `get_page`, `update_page`
- Media — `list_media`, `upload_media`
- Plugins — `list_plugins`, `activate_plugin`, `deactivate_plugin`
- Themes — `list_themes`, `get_active_theme`
- Users — `list_users`, `get_user`
- Comments — `list_comments`, `moderate_comment`
- Taxonomy — `list_categories`, `list_tags`, `create_term`
- Health — `site_health`, `verify_connection`

List tools default to 10 results / max 100, return summaries (not full bodies) — token-efficient by design.

---

## Install

```
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
```

## Configure

Create an Application Password in WordPress:
`{site_url}/wp-admin/profile.php` → Application Passwords → Add New → copy the 24-char space-separated value.

Copy `.env.example` to `.env` and fill in:

```
WPFLOW_SITE_URL=https://your-site.com
WPFLOW_USERNAME=admin
WPFLOW_APP_PASSWORD=xxxx xxxx xxxx xxxx xxxx xxxx
```

## Claude Desktop config

Add to `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "wpflow": {
      "command": "python",
      "args": ["C:/path/to/wpflow/server.py"],
      "env": {
        "WPFLOW_SITE_URL": "https://your-site.com",
        "WPFLOW_USERNAME": "admin",
        "WPFLOW_APP_PASSWORD": "xxxx xxxx xxxx xxxx xxxx xxxx"
      }
    }
  }
}
```

## Run tests

```
.venv\Scripts\python test_server.py
```

Reads `data/test_site.json` (gitignored) for live credentials, then exercises every tool.

---

## Troubleshooting

### Cloudflare 403 / error 1010 (browser_signature_banned)
Hosts behind Cloudflare Bot Management (TasteWP, InstaWP free tiers, some shared hosts) block requests with Python's default `urllib` User-Agent. **wpflow already sends a real browser-like UA on every request** — you shouldn't see this unless you've forked the client and removed the header. If you DO see 403 with `cf-mitigated: challenge`, check that your edit preserved the `BROWSERISH_UA` in `wp_client.py`.

### `auth_failed` on verify_connection
The Application Password is 24 characters with spaces. Copy it exactly as WP displays it — the interior spaces are part of the credential. Don't strip them.

### `rest_api_disabled`
Some managed hosts (or a misbehaving security plugin) turn off the WP REST API entirely. Re-enable at `{site}/wp-admin` under Settings → Permalinks (just re-save) or disable the plugin causing it.

### `rest_disabled_for_plugins`
A few hosts allow the public REST API but block `/wp-json/wp/v2/plugins` specifically. Use `wp-admin` to manage plugins, or migrate to a host that exposes the full REST surface.

### Log location
`logs/wpflow.log` (rotating, 5 MB × 3). Auth tokens and app passwords are scrubbed.

---

## Known quirks

- WP 6.9 doesn't expose `wp_version` via `/wp-json/` (site info only). `verify_connection` returns `"unknown"` for `wp_version`; `site_health` likewise. If you need it, read `X-Generator` on a rendered-page GET or query `wp-admin`.
- `delete_post(force=false)` returns `previous_status: "trash"` immediately (WP moves it to trash and reports the new status, not the pre-trash status). This matches WP REST behavior.
- `list_comments` default shows all statuses (`status=any`); WP REST requires `context=edit` for that, which requires auth. Unauthenticated calls will 401.

---

## Security

- No code execution path — no `eval`, no shell, no WP-CLI passthrough.
- `upload_media` MIME whitelist: jpeg, png, gif, webp, svg, mp4, pdf.
- `upload_media` URL source: SSRF-guarded (private/loopback/link-local IPs rejected; https only).
- `upload_media` local path: must resolve inside `WPFLOW_UPLOAD_ROOT` (defaults to `~/Downloads` and `~/Pictures`).
- 5 MB response cap per WP call.
- TLS verification always on; `WPFLOW_ALLOW_INSECURE=1` only relaxes the https-required check for dev sites, not certificate verification.

---

## License

MIT.
