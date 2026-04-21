# wpflow — Architecture

**Version:** v0.1 (architecture frozen for BUILDER)
**Author:** ARCHITECT agent, 2026-04-20
**Source of scope:** `C:\ZachAI\companies\_research\DECISION.md`
**Target implementer:** BUILDER agent — this spec is authoritative; do not improvise.

---

## 1. Overview

**wpflow** is a local-first MCP server that lets an LLM agent (Claude Desktop, Claude Code, Cursor, etc.) operate a live WordPress site through the WordPress REST API, authenticated with an Application Password. The target buyer is a non-coder WP owner or a small agency; the v0.1 deliverable is a single-site, locally-runnable binary. Multi-site / hosted tiers are v0.2+.

**What it replaces:** the "I hire a dev to change a post / install a plugin / moderate comments" workflow.
**What it is NOT:** a code editor, a theme builder, a staging/deploy tool, a WooCommerce operator, or a WP-CLI passthrough.

**Key design bets:**
1. **Application Password over OAuth** — skips Meta/Intuit-style vendor review; the user pastes `site_url + username + app_password` and it works.
2. **Summaries by default, bodies on request** — a 100-post list returns ~2 KB, not 200 KB. Full body is a second tool call only when the agent actually needs it.
3. **Read-heavy surface first, write surface tight** — every write tool is explicit (`create_post`, `update_post`, `delete_post`); there is no generic `wp_request` escape hatch in v0.1 (Signal 28 security bet — no code-exec paths).
4. **Stdio transport, Python `mcp` SDK** — matches the Claude Desktop / Claude Code config the target buyer will actually paste.

---

## 2. Transport & SDK choice

- **SDK:** Official Anthropic Python `mcp` package (`pip install mcp`). **Not** FastMCP. **Not** Streamable HTTP.
  - Rationale: the target buyer runs Claude Desktop or Claude Code locally and pastes a JSON snippet. Stdio is the zero-config path; HTTP transports require the user to stand up a server, open a port, and hand out a URL — which is exactly the "I am not a developer" friction Signal 4 complained about.
  - DECISION.md §v0.1 originally said "Streamable HTTP + FastMCP" — that was before we pinned the buyer persona. Stdio + `mcp` is the revised pin. v0.2 (hosted SaaS tier) will add a Streamable HTTP transport behind the same tool definitions.
- **Server class:** `mcp.server.Server` with `@server.list_tools()` and `@server.call_tool()` decorators.
- **Entry point:** `server.py` calls `mcp.server.stdio.stdio_server()` and runs the event loop.
- **Python:** 3.11+ (matches `mcp` SDK floor and Claude Desktop's current recommendation).
- **Distribution:** published to PyPI as `wpflow`; user installs with `pip install wpflow` or `uvx wpflow`. Claude Desktop config example:
  ```json
  {
    "mcpServers": {
      "wpflow": {
        "command": "uvx",
        "args": ["wpflow"],
        "env": {
          "WPFLOW_SITE_URL": "https://example.com",
          "WPFLOW_USERNAME": "admin",
          "WPFLOW_APP_PASSWORD": "xxxx xxxx xxxx xxxx xxxx xxxx"
        }
      }
    }
  }
  ```

---

## 3. Configuration & Auth

### 3.1 Decision: **Single-site in v0.1**

Multi-site is v0.2+. Justification:
- DECISION.md §v0.1 Non-Goals explicitly says "No agency-tier features in v0.1 — solo tier must be airtight before we multi-site."
- Single-site lets every tool skip a `site_id` argument, which dramatically simplifies schemas and reduces agent-side token overhead.
- The $19/mo Solo tier is the first revenue target; multi-site is $49/$149 tiers.
- Migration path to multi-site is clean: v0.2 introduces a `site` optional arg on every tool, defaulting to the env-configured site.

### 3.2 Configuration surface

Configuration is **environment variables only** in v0.1. No config files, no per-tool auth args.

| Variable | Required | Example | Purpose |
|---|---|---|---|
| `WPFLOW_SITE_URL` | yes | `https://example.com` | Base URL, no trailing slash, must be HTTPS (HTTP allowed only if `WPFLOW_ALLOW_INSECURE=1`) |
| `WPFLOW_USERNAME` | yes | `admin` | WP username that owns the application password |
| `WPFLOW_APP_PASSWORD` | yes | `abcd efgh ijkl mnop qrst uvwx` | WP Application Password (spaces allowed, will be normalized) |
| `WPFLOW_ALLOW_INSECURE` | no | `1` | If set, allows `http://` URLs (dev only) |
| `WPFLOW_TIMEOUT_SECONDS` | no | `30` | HTTP timeout, default 30s |
| `WPFLOW_LOG_LEVEL` | no | `INFO` | `DEBUG`/`INFO`/`WARN`/`ERROR` (default INFO) |
| `WPFLOW_MAX_UPLOAD_MB` | no | `25` | Reject media uploads over this size; default 25 |

Missing required vars → the server still starts (so MCP handshake succeeds), but every tool call except `verify_connection` returns a structured `auth_not_configured` error. `verify_connection` returns the specific missing variable names. This behavior is intentional: agents need a call they can make to discover configuration problems without crashing the transport.

### 3.3 Secret handling

- App password is loaded into a module-local variable in `wp_client.py` at import time, never passed through tool arguments.
- Logs **must** scrub the `Authorization` header and the app password itself. Implementation: a `SECRET_SCRUBBER` regex in `wp_client.py` runs on every log line.
- No `print()` allowed anywhere — use the `logging` module so scrubbers are in the pipeline.
- Error messages returned to the agent never include the app password, the `Authorization` header, or the URL's userinfo portion.
- `.env.example` ships with dummy values; actual `.env` is gitignored.

---

## 4. Folder Structure

```
C:\ZachAI\companies\wpflow\
├── ARCHITECTURE.md          (this file)
├── ACTIVE_FILES.md          (manifest — required per project rules)
├── CLAUDE.md                (project brain — BUILDER writes this)
├── README.md                (install + config + pricing intent)
├── LICENSE                  (MIT)
├── pyproject.toml           (PyPI packaging; defines `wpflow` console_script)
├── requirements.txt         (runtime deps, pinned)
├── requirements-dev.txt     (test deps)
├── .env.example             (dummy WPFLOW_* vars)
├── .gitignore               (includes .env, logs/*.log, __pycache__, .venv)
├── server.py                (MCP entry — tool registry + stdio loop)
├── wp_client.py             (REST wrapper — auth, retries, scrubbing)
├── errors.py                (structured error codes + to-dict helpers)
├── schemas.py               (shared JSON Schema fragments: pagination, dates)
├── tools/
│   ├── __init__.py
│   ├── posts.py             (list_posts, get_post, create_post, update_post, delete_post, search_content)
│   ├── pages.py             (list_pages, get_page, update_page)
│   ├── media.py             (list_media, upload_media)
│   ├── plugins.py           (list_plugins, activate_plugin, deactivate_plugin)
│   ├── themes.py            (list_themes, get_active_theme)
│   ├── users.py             (list_users, get_user)
│   ├── comments.py          (list_comments, moderate_comment)
│   ├── taxonomy.py          (list_categories, list_tags, create_term)
│   └── health.py            (site_health, verify_connection)
├── test_server.py           (end-to-end test harness against a live WP)
├── tests/
│   ├── __init__.py
│   ├── test_wp_client.py    (unit: URL building, auth header, scrubber)
│   ├── test_schemas.py      (unit: schema round-trips)
│   └── fixtures/            (captured WP REST responses for offline unit tests)
├── logs/                    (runtime write-only; gitignored except .gitkeep)
│   └── .gitkeep
└── data/                    (reserved; empty in v0.1)
    └── .gitkeep
```

Notes:
- `tools/` modules each export a `TOOLS` list of `mcp.types.Tool` objects and a dispatch dict mapping name → async handler. `server.py` imports all, concatenates, and registers.
- No `__main__.py` — the PyPI entry point is defined in `pyproject.toml` as `wpflow = "server:main"`.
- No backup / `_old` / `v2` files (per CLAUDE.md file hygiene rules).

---

## 5. Tool Catalog

**Conventions used below:**
- All tools are async. All return a JSON-serializable dict.
- Every tool's description starts with a one-line WHEN clause (Signal 8 compliance — agents need "when to use").
- Schemas use JSON Schema Draft 2020-12, inline here.
- Pagination: list tools accept `page` (1-indexed, default 1) and `per_page` (default 10, max 100). Every list response includes `pagination: {page, per_page, total, total_pages, has_more}`.
- Date filters: ISO 8601 strings, e.g. `2026-04-01T00:00:00`.
- "Summary" post/page shape:
  ```
  {id, title, status, date, modified, slug, excerpt_200, link, author_id, categories?, tags?}
  ```
- "Full" post/page shape adds `content_html`, `content_rendered`, `featured_media`, `meta`, full `categories` (as objects), full `tags`.

### 5.1 `verify_connection`
**WHEN:** Use first when a user mentions a WordPress task to confirm credentials, site reachability, and required capabilities before attempting writes. Also use when other tools return `auth_failed` or `site_unreachable`.
**Input schema:**
```json
{
  "type": "object",
  "properties": {},
  "additionalProperties": false
}
```
**Output:**
```json
{
  "ok": true,
  "site_url": "https://example.com",
  "wp_version": "6.7.1",
  "user": {"id": 1, "username": "admin", "roles": ["administrator"]},
  "capabilities": {"edit_posts": true, "manage_options": true, "upload_files": true},
  "rest_prefix": "/wp-json",
  "latency_ms": 142
}
```
**WP endpoints:** `GET /wp-json/` (discovery) + `GET /wp-json/wp/v2/users/me?context=edit`
**Errors:** `auth_not_configured`, `auth_failed`, `site_unreachable`, `rest_api_disabled`.

### 5.2 `list_posts`
**WHEN:** Use to find posts by status, date, author, category, tag, or search term; returns summaries only (no full body) for token efficiency. Follow up with `get_post` for full content.
**Input schema:**
```json
{
  "type": "object",
  "properties": {
    "status": {"type": "string", "enum": ["publish","draft","pending","private","future","any"], "default": "publish"},
    "search": {"type": "string"},
    "author_id": {"type": "integer"},
    "category_ids": {"type": "array", "items": {"type": "integer"}},
    "tag_ids": {"type": "array", "items": {"type": "integer"}},
    "after": {"type": "string", "format": "date-time"},
    "before": {"type": "string", "format": "date-time"},
    "orderby": {"type": "string", "enum": ["date","modified","title","id"], "default": "date"},
    "order": {"type": "string", "enum": ["asc","desc"], "default": "desc"},
    "page": {"type": "integer", "minimum": 1, "default": 1},
    "per_page": {"type": "integer", "minimum": 1, "maximum": 100, "default": 10}
  },
  "additionalProperties": false
}
```
**Output:** `{posts: [<summary>, ...], pagination: {...}}`
**WP endpoint:** `GET /wp-json/wp/v2/posts?context=view&_fields=id,title,status,date,modified,slug,excerpt,link,author,categories,tags&per_page=10&page=1&status=publish`
**Errors:** `auth_failed`, `site_unreachable`, `invalid_params`, `rate_limited`.

### 5.3 `get_post`
**WHEN:** Use when you need the full content of a single post (body HTML, meta, featured image). Do NOT use for browsing — use `list_posts` first.
**Input schema:**
```json
{
  "type": "object",
  "properties": {
    "post_id": {"type": "integer", "minimum": 1},
    "include_raw": {"type": "boolean", "default": false, "description": "If true, returns raw block editor content in addition to rendered HTML."}
  },
  "required": ["post_id"],
  "additionalProperties": false
}
```
**Output:** `{post: <full>}` — `content_html` is rendered HTML; `content_raw` is block/Gutenberg source, only if `include_raw=true`.
**WP endpoint:** `GET /wp-json/wp/v2/posts/{id}?context=edit` (context=edit returns `raw` fields; if `include_raw=false` the handler strips them before returning)
**Errors:** `not_found` (post id doesn't exist), `permission_denied`, `auth_failed`.

### 5.4 `create_post`
**WHEN:** Use when the user asks to publish a new blog post or create a draft. For editing existing posts, use `update_post`.
**Input schema:**
```json
{
  "type": "object",
  "properties": {
    "title": {"type": "string", "minLength": 1, "maxLength": 500},
    "content_html": {"type": "string", "description": "Full HTML body. Accept HTML; do NOT accept executable code."},
    "status": {"type": "string", "enum": ["publish","draft","pending","private","future"], "default": "draft"},
    "excerpt": {"type": "string", "maxLength": 1000},
    "slug": {"type": "string"},
    "category_ids": {"type": "array", "items": {"type": "integer"}},
    "tag_ids": {"type": "array", "items": {"type": "integer"}},
    "featured_media_id": {"type": "integer"},
    "date": {"type": "string", "format": "date-time", "description": "Required if status=future"}
  },
  "required": ["title", "content_html"],
  "additionalProperties": false
}
```
**Output:** `{post: <full>, created: true}`
**WP endpoint:** `POST /wp-json/wp/v2/posts` with JSON body.
**Errors:** `permission_denied`, `invalid_params`, `conflict` (slug taken), `auth_failed`.

### 5.5 `update_post`
**WHEN:** Use to edit an existing post — title, body, status, categories/tags, slug, or featured image. Partial updates supported; only provided fields change.
**Input schema:**
```json
{
  "type": "object",
  "properties": {
    "post_id": {"type": "integer", "minimum": 1},
    "title": {"type": "string", "maxLength": 500},
    "content_html": {"type": "string"},
    "status": {"type": "string", "enum": ["publish","draft","pending","private","future"]},
    "excerpt": {"type": "string", "maxLength": 1000},
    "slug": {"type": "string"},
    "category_ids": {"type": "array", "items": {"type": "integer"}},
    "tag_ids": {"type": "array", "items": {"type": "integer"}},
    "featured_media_id": {"type": "integer"},
    "date": {"type": "string", "format": "date-time"}
  },
  "required": ["post_id"],
  "additionalProperties": false
}
```
**Output:** `{post: <full>, updated_fields: ["title","status"]}`
**WP endpoint:** `POST /wp-json/wp/v2/posts/{id}` (WP REST uses POST for updates; optionally also accepts PUT/PATCH). Request body contains only changed fields.
**Errors:** `not_found`, `permission_denied`, `invalid_params`, `auth_failed`.

### 5.6 `delete_post`
**WHEN:** Use only when the user explicitly asks to delete or trash a post. Defaults to trash (recoverable); pass `force=true` only if user says "permanently" or "purge".
**Input schema:**
```json
{
  "type": "object",
  "properties": {
    "post_id": {"type": "integer", "minimum": 1},
    "force": {"type": "boolean", "default": false, "description": "If false, moves to trash. If true, permanently deletes."}
  },
  "required": ["post_id"],
  "additionalProperties": false
}
```
**Output:** `{deleted: true, post_id: 42, force: false, previous_status: "publish"}`
**WP endpoint:** `DELETE /wp-json/wp/v2/posts/{id}?force=true|false`
**Errors:** `not_found`, `permission_denied`, `auth_failed`.

### 5.7 `list_pages`
**WHEN:** Use to find static pages (About, Contact, etc.). Separate from posts — WordPress treats pages and posts as distinct content types.
**Input schema:** same shape as `list_posts` minus `category_ids`/`tag_ids`, plus `parent_id` (integer).
**Output:** `{pages: [<summary>, ...], pagination: {...}}`
**WP endpoint:** `GET /wp-json/wp/v2/pages?context=view&_fields=...`
**Errors:** same as `list_posts`.

### 5.8 `get_page`
Mirrors `get_post`. Endpoint: `GET /wp-json/wp/v2/pages/{id}?context=edit`.

### 5.9 `update_page`
Mirrors `update_post`. Endpoint: `POST /wp-json/wp/v2/pages/{id}`. Adds optional `parent_id` field. No `create_page` in v0.1 (out of scope per DECISION.md list; pages are typically structural and created less often — add in v0.2 if signal appears).

### 5.10 `list_plugins`
**WHEN:** Use to see what plugins are installed and which are active. Do NOT use to install new plugins — that is not supported in v0.1.
**Input schema:**
```json
{
  "type": "object",
  "properties": {
    "status": {"type": "string", "enum": ["active","inactive","any"], "default": "any"},
    "search": {"type": "string"}
  },
  "additionalProperties": false
}
```
**Output:**
```json
{"plugins": [
  {"plugin": "akismet/akismet", "name": "Akismet Anti-spam", "status": "active", "version": "5.3", "author": "Automattic", "network_only": false, "requires_wp": "5.8", "requires_php": "5.6.20"}
]}
```
**WP endpoint:** `GET /wp-json/wp/v2/plugins` (requires `activate_plugins` capability).
**Errors:** `permission_denied` (user lacks activate_plugins), `auth_failed`, `rest_disabled_for_plugins` (some hosts disable this endpoint).

### 5.11 `activate_plugin` / 5.12 `deactivate_plugin`
**WHEN (`activate_plugin`):** Use when the user asks to turn on an already-installed plugin.
**WHEN (`deactivate_plugin`):** Use when the user asks to turn off a plugin (e.g., to troubleshoot a conflict).
**Input schema:**
```json
{
  "type": "object",
  "properties": {
    "plugin": {"type": "string", "description": "Plugin slug as returned by list_plugins, e.g. 'akismet/akismet'"}
  },
  "required": ["plugin"],
  "additionalProperties": false
}
```
**Output:** `{plugin: "akismet/akismet", previous_status: "inactive", new_status: "active"}`
**WP endpoint:** `POST /wp-json/wp/v2/plugins/{plugin}` with `{"status": "active"}` or `{"status": "inactive"}`.
**Errors:** `not_found`, `permission_denied`, `plugin_broken` (WP error on activation), `auth_failed`.

### 5.13 `list_themes`
**WHEN:** Use to see installed themes. v0.1 does not support activating or installing themes — read-only.
**Input:** `{}` (no params).
**Output:** `{themes: [{stylesheet, name, version, status, author, template, screenshot_url}]}`
**WP endpoint:** `GET /wp-json/wp/v2/themes`
**Errors:** `permission_denied`, `auth_failed`.

### 5.14 `get_active_theme`
**WHEN:** Use to identify which theme is currently running — useful before advising customizations.
**Input:** `{}`.
**Output:** `{theme: {stylesheet, name, version, template, author, screenshot_url, theme_supports}}`
**WP endpoint:** `GET /wp-json/wp/v2/themes?status=active` → pick first.
**Errors:** `permission_denied`, `auth_failed`.

### 5.15 `list_media`
**WHEN:** Use to find uploaded images, videos, or files in the media library. Returns summaries; does not download binary content.
**Input schema:**
```json
{
  "type": "object",
  "properties": {
    "mime_type": {"type": "string", "examples": ["image/jpeg","image/png","application/pdf"]},
    "search": {"type": "string"},
    "after": {"type": "string", "format": "date-time"},
    "before": {"type": "string", "format": "date-time"},
    "page": {"type": "integer", "minimum": 1, "default": 1},
    "per_page": {"type": "integer", "minimum": 1, "maximum": 100, "default": 10}
  },
  "additionalProperties": false
}
```
**Output:** `{media: [{id, title, mime_type, source_url, alt_text, caption, date, sizes: {thumbnail, medium, large}}], pagination: {...}}`
**WP endpoint:** `GET /wp-json/wp/v2/media?_fields=id,title,mime_type,source_url,alt_text,caption,date,media_details`
**Errors:** `auth_failed`, `site_unreachable`.

### 5.16 `upload_media`
**WHEN:** Use to add an image or file to the media library, e.g., when creating a post with a featured image. Accepts either a public URL or a local file path the server can read.
**Input schema:**
```json
{
  "type": "object",
  "properties": {
    "source": {"type": "string", "description": "Either a public https:// URL or an absolute local file path"},
    "filename": {"type": "string", "description": "Desired filename with extension; inferred from source if omitted"},
    "title": {"type": "string"},
    "alt_text": {"type": "string"},
    "caption": {"type": "string"}
  },
  "required": ["source"],
  "additionalProperties": false
}
```
**Security constraint (Signal 28 compliance):**
- If `source` is a URL: must be `https://`, max 25 MB (or `WPFLOW_MAX_UPLOAD_MB`), MIME must be in whitelist: `image/jpeg, image/png, image/gif, image/webp, image/svg+xml, video/mp4, application/pdf`.
- If `source` is a local path: must be an absolute path that resolves inside a directory listed in `WPFLOW_UPLOAD_ROOT` (defaults to user's home `Downloads/` and `Pictures/` folders). No symlinks followed across that boundary. Hard-coded denylist for system paths: `/etc`, `/var`, `C:\Windows`, `C:\ProgramData`, etc.
- No base64 inline uploads in v0.1 (too easy to accidentally ship a multi-MB token blob through the transport). If a user needs base64, they write the file to disk first.
**Output:** `{media: {id, title, source_url, mime_type, alt_text, caption}}`
**WP endpoint:** `POST /wp-json/wp/v2/media` with `multipart/form-data`, `Content-Disposition: attachment; filename="..."`.
**Errors:** `invalid_source`, `file_too_large`, `mime_not_allowed`, `path_not_allowed`, `permission_denied`, `auth_failed`, `upload_failed`.

### 5.17 `list_users`
**WHEN:** Use to find users/authors on the site. Sensitive fields (email) only visible if authenticated user has `list_users` capability.
**Input schema:**
```json
{
  "type": "object",
  "properties": {
    "role": {"type": "string", "examples": ["administrator","editor","author","contributor","subscriber"]},
    "search": {"type": "string"},
    "page": {"type": "integer", "minimum": 1, "default": 1},
    "per_page": {"type": "integer", "minimum": 1, "maximum": 100, "default": 10}
  },
  "additionalProperties": false
}
```
**Output:** `{users: [{id, username, name, slug, roles, post_count}], pagination: {...}}` (no email in summary; use `get_user`).
**WP endpoint:** `GET /wp-json/wp/v2/users?context=edit&_fields=id,username,name,slug,roles`
**Errors:** `permission_denied`, `auth_failed`.

### 5.18 `get_user`
**WHEN:** Use for full user details including email (requires `list_users` capability).
**Input:** `{"user_id": integer}` (required).
**Output:** `{user: {id, username, email, name, slug, roles, registered_date, post_count, url, description}}`
**WP endpoint:** `GET /wp-json/wp/v2/users/{id}?context=edit`
**Errors:** `not_found`, `permission_denied`, `auth_failed`.

### 5.19 `list_comments`
**WHEN:** Use to see comments, filter by status (approved / pending / spam / trash), or find comments on a specific post.
**Input schema:**
```json
{
  "type": "object",
  "properties": {
    "status": {"type": "string", "enum": ["approve","hold","spam","trash","any"], "default": "any"},
    "post_id": {"type": "integer"},
    "author_email": {"type": "string"},
    "search": {"type": "string"},
    "page": {"type": "integer", "minimum": 1, "default": 1},
    "per_page": {"type": "integer", "minimum": 1, "maximum": 100, "default": 10}
  },
  "additionalProperties": false
}
```
**Output:** `{comments: [{id, post_id, author_name, author_email?, status, date, content_excerpt_200, parent_id, link}], pagination: {...}}`
**WP endpoint:** `GET /wp-json/wp/v2/comments?context=edit&_fields=id,post,author_name,author_email,status,date,content,parent,link`
**Errors:** `permission_denied`, `auth_failed`.

### 5.20 `moderate_comment`
**WHEN:** Use to approve, spam, trash, or permanently delete a comment. This is the only comment-write tool in v0.1.
**Input schema:**
```json
{
  "type": "object",
  "properties": {
    "comment_id": {"type": "integer", "minimum": 1},
    "action": {"type": "string", "enum": ["approve","hold","spam","trash","delete_permanently"]}
  },
  "required": ["comment_id", "action"],
  "additionalProperties": false
}
```
**Output:** `{comment_id: 33, previous_status: "hold", action: "approve", new_status: "approved"}`
**WP endpoint:**
- `approve|hold|spam|trash` → `POST /wp-json/wp/v2/comments/{id}` with `{"status": "<action>"}` (`approve` maps to `"approved"`, `hold` to `"hold"`, etc.).
- `delete_permanently` → `DELETE /wp-json/wp/v2/comments/{id}?force=true`.
**Errors:** `not_found`, `permission_denied`, `invalid_action`, `auth_failed`.

### 5.21 `site_health`
**WHEN:** Use for a one-shot snapshot of site health: WP version, PHP version, plugin count, theme, last post date, and any critical issues reported by WP's own Site Health module.
**Input:** `{}`.
**Output:**
```json
{
  "wp_version": "6.7.1",
  "php_version": "8.2.10",
  "mysql_version": "8.0.36",
  "multisite": false,
  "plugins_active": 12,
  "plugins_inactive": 3,
  "active_theme": "twentytwentyfour",
  "last_post_date": "2026-04-18T14:22:00",
  "total_posts": 487,
  "total_pages": 14,
  "total_users": 3,
  "site_health_checks": [
    {"test": "rest_availability", "status": "good", "label": "REST API is available"},
    {"test": "https_status", "status": "good"},
    {"test": "background_updates", "status": "recommended", "description": "Background updates are not working properly."}
  ]
}
```
**WP endpoints (composed):**
- `GET /wp-json/` (server metadata)
- `GET /wp-json/wp/v2/plugins` (count)
- `GET /wp-json/wp/v2/themes?status=active` (name)
- `GET /wp-json/wp/v2/posts?per_page=1&orderby=date&order=desc&_fields=id,date` + `X-WP-Total` header
- `GET /wp-json/wp-site-health/v1/tests/` (direct tests, if available; fall back to `[]`)
**Errors:** `auth_failed`, `partial` (some sub-queries failed — result includes `partial_errors: [...]` and returns what it could).

### 5.22 `search_content`
**WHEN:** Use for a cross-content-type search: one call hits posts, pages, and media at once and returns a unified summary list.
**Input schema:**
```json
{
  "type": "object",
  "properties": {
    "query": {"type": "string", "minLength": 1},
    "types": {"type": "array", "items": {"type": "string", "enum": ["post","page","attachment"]}, "default": ["post","page"]},
    "per_type": {"type": "integer", "minimum": 1, "maximum": 20, "default": 5}
  },
  "required": ["query"],
  "additionalProperties": false
}
```
**Output:** `{results: [{type, id, title, link, excerpt_200}], query: "pricing"}`
**WP endpoint:** `GET /wp-json/wp/v2/search?search={query}&subtype={comma-separated}&per_page={per_type * len(types)}`
**Errors:** `invalid_params`, `auth_failed`.

### 5.23 `list_categories` / 5.24 `list_tags`
**WHEN (categories):** Use to see taxonomy structure for a post — categories are hierarchical. Use when helping the user organize content.
**WHEN (tags):** Use to see all tags — tags are flat. Pair with `create_term` when the user wants to add a new one.
**Input schema (both):**
```json
{
  "type": "object",
  "properties": {
    "search": {"type": "string"},
    "parent_id": {"type": "integer", "description": "Categories only; ignored for tags"},
    "page": {"type": "integer", "minimum": 1, "default": 1},
    "per_page": {"type": "integer", "minimum": 1, "maximum": 100, "default": 50}
  },
  "additionalProperties": false
}
```
**Output:** `{terms: [{id, name, slug, count, parent_id}], pagination: {...}}`
**WP endpoints:**
- Categories: `GET /wp-json/wp/v2/categories?_fields=id,name,slug,count,parent`
- Tags: `GET /wp-json/wp/v2/tags?_fields=id,name,slug,count`
**Errors:** `auth_failed`.

### 5.25 `create_term`
**WHEN:** Use when the user wants to add a new category or tag before assigning it to a post.
**Input schema:**
```json
{
  "type": "object",
  "properties": {
    "taxonomy": {"type": "string", "enum": ["category","tag"]},
    "name": {"type": "string", "minLength": 1, "maxLength": 200},
    "slug": {"type": "string"},
    "description": {"type": "string"},
    "parent_id": {"type": "integer", "description": "Categories only; creates a subcategory"}
  },
  "required": ["taxonomy", "name"],
  "additionalProperties": false
}
```
**Output:** `{term: {id, taxonomy, name, slug, parent_id}, created: true}`
**WP endpoint:** `POST /wp-json/wp/v2/categories` or `POST /wp-json/wp/v2/tags`.
**Errors:** `permission_denied`, `conflict` (name/slug already exists — returns existing id), `invalid_params`, `auth_failed`.

---

## 6. Token-Efficiency Contract

**Rules every tool MUST follow:**

1. **Summaries by default.** List tools never return body HTML. `excerpt_200` is the WP-provided excerpt truncated to 200 characters (trailing ellipsis if cut).
2. **Explicit `_fields` params on every GET.** Every list call passes `_fields=` to WP to suppress unrequested columns server-side.
3. **`per_page` default 10, max 100.** Server rejects `per_page > 100` with `invalid_params`. If a user asks for "all posts", the agent should paginate — the tool must never iterate internally and return a giant payload.
4. **HTML stripping helpers available but opt-in.** `get_post` returns `content_html`; if the caller passes `include_raw=true` it gets the Gutenberg block source additionally. `content_rendered` is NEVER returned alongside `content_html` (they are the same thing; WP's duplication is wasteful).
5. **Error payloads are short.** A scrubbed error message, never a full WP error trace.
6. **No echoing inputs.** Write tools return the updated resource but do not re-include every input field verbatim.
7. **`search_content` caps results.** Default 5 per type, max 20, to keep token footprint predictable.
8. **Pagination metadata is always present on list returns** — the agent must never guess whether more results exist.

---

## 7. Error Handling Contract

**Rule:** every tool handler catches its own exceptions and returns a structured error dict. The MCP transport never sees a Python exception.

**Error dict shape:**
```json
{
  "error": {
    "code": "auth_failed",
    "message": "WordPress rejected the application password. Check WPFLOW_USERNAME and WPFLOW_APP_PASSWORD.",
    "http_status": 401,
    "hint": "Run verify_connection to confirm credentials."
  }
}
```

**Canonical error codes (in `errors.py`):**

| Code | HTTP | Meaning | Agent hint |
|---|---|---|---|
| `auth_not_configured` | — | Env vars missing | "Ask user to set WPFLOW_SITE_URL / WPFLOW_USERNAME / WPFLOW_APP_PASSWORD" |
| `auth_failed` | 401 | WP rejected credentials | "Run verify_connection; likely bad app password" |
| `permission_denied` | 403 | User lacks capability | "The configured user lacks the capability for this action" |
| `not_found` | 404 | Resource missing | Try listing first to confirm id |
| `invalid_params` | 400 | Schema validation or WP rejected | Fix the offending field |
| `conflict` | 409 | Slug/name collision | Try a different slug or re-use returned existing_id |
| `rate_limited` | 429 | Too many requests | Retry after `retry_after_s` |
| `site_unreachable` | — | DNS / TCP / TLS fail | Check WPFLOW_SITE_URL is correct and site is online |
| `rest_api_disabled` | 404 on /wp-json/ | WP REST turned off | Ask user to re-enable WP REST API |
| `rest_disabled_for_plugins` | 404 on /plugins | Some hosts block it | Suggest enabling the plugins REST endpoint |
| `file_too_large` | — | > WPFLOW_MAX_UPLOAD_MB | Ask user to reduce file size |
| `mime_not_allowed` | — | MIME not in whitelist | Reject |
| `path_not_allowed` | — | Path outside WPFLOW_UPLOAD_ROOT | Reject |
| `upload_failed` | 5xx | WP couldn't store file | Check WP uploads dir writable |
| `plugin_broken` | 500 | Activation failed | Check WP error log |
| `partial` | — | Composite tool got some results | Included `partial_errors` list |
| `internal` | — | Unexpected error | Report; include request_id for logs |

**Example: auth fail**
```json
{"error": {"code": "auth_failed", "message": "WordPress rejected the application password.", "http_status": 401, "hint": "Run verify_connection."}}
```

**Example: not found**
```json
{"error": {"code": "not_found", "message": "No post with id 9999.", "http_status": 404, "hint": "Call list_posts to confirm ids."}}
```

**Example: rate limit**
```json
{"error": {"code": "rate_limited", "message": "Host throttled the request.", "http_status": 429, "retry_after_s": 30}}
```

**Retry policy (inside `wp_client.py`):**
- Idempotent GETs: retry up to 2 times on 5xx or connection error, exponential backoff 1s / 3s.
- Writes (POST/DELETE): never auto-retry. Return the error.
- Rate limit (429): no auto-retry; surface `rate_limited` with `retry_after_s` from the `Retry-After` header.

---

## 8. Security Constraints

Per DEMAND_SIGNALS Signal 28 (LiteLLM supply-chain incident), wpflow is explicitly NOT a code-execution surface. The following are hard rules for BUILDER:

1. **No `eval`, `exec`, `pickle.loads`, `yaml.load` (use `yaml.safe_load` if YAML needed — it isn't in v0.1).** There is no code path anywhere that turns a WP response into executable Python.
2. **No generic `wp_request` / `raw_rest_call` tool.** v0.1's surface is fixed. Agents cannot funnel arbitrary REST calls through wpflow. v0.2 may add one with an allowlist.
3. **No shell-out.** No `subprocess`, no `os.system`, no WP-CLI passthrough in v0.1.
4. **Upload whitelist enforced at the tool layer, not trusted to WP.** See §5.16.
5. **SSRF guard on `upload_media` URL sources.** Before fetching, resolve the hostname and reject if it's in RFC1918, loopback, link-local, or `.internal`. Reject `file://`, `gopher://`, etc.
6. **TLS verification always on.** `requests.get(..., verify=True)`. No way to disable it from the tool surface. `WPFLOW_ALLOW_INSECURE=1` only relaxes the HTTP-vs-HTTPS check on the base URL; it does NOT disable certificate verification.
7. **Secret scrubbing in logs.** Regex strips `Authorization: Basic <b64>`, the app password with and without spaces, and the userinfo portion of any URL.
8. **Input validation happens before network calls.** Schema rejects weird types at the tool boundary; no unchecked passthrough.
9. **Response size cap.** Any single WP response over 5 MB is rejected with `response_too_large` — protects against a hacked WP instance blasting the agent with junk.
10. **No HTML interpretation.** `content_html` returned to the agent is a string; wpflow never parses it, renders it, or inspects it for "magic" fields. The agent decides what to do with it.

---

## 9. Dependencies (requirements.txt preview)

```
mcp>=1.2.0,<2.0.0
httpx>=0.27.0,<1.0.0
pydantic>=2.6.0,<3.0.0
python-dotenv>=1.0.0,<2.0.0
```

**Dev (`requirements-dev.txt`):**
```
pytest>=8.0.0
pytest-asyncio>=0.23.0
pytest-httpx>=0.30.0
ruff>=0.3.0
```

**Notes:**
- `httpx` over `requests`: async support, native HTTP/2, first-class TLS controls.
- `pydantic` for internal input validation of each tool's `arguments` dict (MCP SDK validates against JSON Schema for advertising, but we revalidate server-side).
- No `Pillow` — we don't process images.
- No `beautifulsoup4` — we don't parse HTML.
- No WP-specific library (`python-wordpress-xmlrpc` etc.) — we talk REST directly.

---

## 10. Test Plan (what `test_server.py` must cover)

`test_server.py` is an end-to-end test harness that runs against a **live WordPress test site**. It is NOT a unit test suite (those live under `tests/`). Test site requirement: a disposable WP instance (LocalWP, a dev subdomain, or a free `InstaWP` sandbox) with an Administrator user and an Application Password.

**Config:** reads `.env.test` (gitignored) with `WPFLOW_TEST_SITE_URL`, `WPFLOW_TEST_USERNAME`, `WPFLOW_TEST_APP_PASSWORD`.

**Test phases (sequential, each builds on the previous):**

1. **Connectivity (`verify_connection`)**
   - Confirms HTTP 200 from `/wp-json/`
   - Confirms `/users/me` returns the test user
   - Asserts latency < 5s
   - Negative: bad password → `auth_failed`
   - Negative: wrong URL → `site_unreachable`

2. **Taxonomy seed (`list_categories`, `list_tags`, `create_term`)**
   - Create category "wpflow-test-cat" — asserts `created: true`
   - Create tag "wpflow-test-tag"
   - Re-create same — asserts `conflict` with existing id returned
   - `list_categories` returns the new category

3. **Media (`upload_media`, `list_media`)**
   - Upload a fixture PNG from `tests/fixtures/test_image.png` — asserts `source_url` returned
   - `list_media` finds it
   - Negative: upload a 30 MB file → `file_too_large`
   - Negative: upload from `http://` → `invalid_source`

4. **Posts CRUD full cycle (`create_post`, `get_post`, `list_posts`, `update_post`, `delete_post`)**
   - `create_post` draft with the test category, test tag, and uploaded featured image
   - `get_post` returns full body
   - `list_posts` with status=draft includes the new post
   - `update_post` changes status to publish
   - `list_posts` with status=publish, search=<test title> finds it
   - `delete_post` force=false trashes it
   - `delete_post` force=true purges it
   - Negative: `get_post` on nonexistent id → `not_found`
   - Negative: `update_post` without fields → `invalid_params`

5. **Pages (`list_pages`, `get_page`, `update_page`)**
   - List pages, pick the first, get it, update its title (then revert)

6. **Plugins (`list_plugins`, `activate_plugin`, `deactivate_plugin`)**
   - List, pick an inactive non-critical plugin (or install Hello Dolly as prep)
   - Activate it → asserts `new_status: active`
   - Deactivate → asserts `new_status: inactive`
   - Negative: `activate_plugin` with bogus slug → `not_found`

7. **Themes (`list_themes`, `get_active_theme`)**
   - List returns ≥1 theme
   - Active theme matches one of them

8. **Users (`list_users`, `get_user`)**
   - List returns the test admin
   - Get by id returns email

9. **Comments (`list_comments`, `moderate_comment`)**
   - Pre-seed a comment via REST (direct) to have something to moderate
   - List pending → finds it
   - Moderate approve → status changes to approved
   - Moderate trash → goes to trash
   - Moderate delete_permanently → gone; `list_comments` doesn't return it

10. **Search (`search_content`)**
    - Search for known post title substring — returns the post

11. **Site health (`site_health`)**
    - Returns wp_version, php_version, post/page counts > 0
    - `site_health_checks` is a list

12. **Token-efficiency smoke checks**
    - `list_posts` default response JSON size < 5 KB for 10 posts
    - `get_post` single post returns full content
    - `list_media` does not return binary data

13. **Security smoke checks**
    - `upload_media` with `source=file:///etc/passwd` → `invalid_source`
    - `upload_media` with `source=http://127.0.0.1:8080/foo.png` → `invalid_source` (SSRF guard)
    - Log file after a full run contains zero occurrences of the app password

**Runner:** `python test_server.py` — prints one line per tool `[OK]`/`[FAIL]` plus a final summary. Exits non-zero on any fail.

**Cleanup:** test suite trashes/purges everything it created (test post, test category, test tag, test media, test comment). On SIGINT, partial cleanup attempted.

---

## Appendix A — HTTP / Auth details

**Base URL:** `{WPFLOW_SITE_URL}/wp-json`
**Auth header:** `Authorization: Basic {base64(WPFLOW_USERNAME + ":" + WPFLOW_APP_PASSWORD_normalized)}`
**App password normalization:** strip leading/trailing whitespace, preserve interior spaces exactly as WP generates them (the spaces are part of the credential — do NOT strip them).
**Headers on every request:**
- `User-Agent: wpflow/0.1 (+https://github.com/zedwards1226/wpflow)`
- `Accept: application/json`
- `Content-Type: application/json` (writes) or `multipart/form-data` (uploads)
**Follow redirects:** yes, up to 3, same-origin only.

---

## Appendix B — Field mapping reference

| Our field | WP REST field |
|---|---|
| `content_html` | `content.rendered` |
| `content_raw` | `content.raw` (only with `context=edit`) |
| `excerpt_200` | `excerpt.rendered` → HTML-stripped → truncated |
| `author_id` | `author` |
| `category_ids` | `categories` |
| `tag_ids` | `tags` |
| `featured_media_id` | `featured_media` |
| `post_id` (inputs) | path segment `/posts/{id}` |

---

**END OF SPEC.** BUILDER should be able to implement from this alone. Open questions go back to ARCHITECT.
