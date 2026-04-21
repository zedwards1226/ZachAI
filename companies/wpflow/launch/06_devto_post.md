# Dev.to post — technical walkthrough

**URL:** https://dev.to/new
**When:** Day 4.
**Tags:** `wordpress`, `python`, `mcp`, `claude` (Dev.to caps at 4).
**Cover image:** the 0:55 freeze-frame from the demo video — the wp-admin "0 untagged posts" moment.
**Canonical URL:** leave blank on Dev.to; point the Medium cross-post's canonical URL AT the Dev.to URL so Dev.to gets the SEO credit.

---

## Title

```
Building a WordPress agent with Claude and the REST API: the 3 design choices that actually matter
```

## Subtitle / TL;DR block (Dev.to renders the first paragraph as the listing preview)

I built a WordPress MCP server for Claude called **wpflow**. This post is the technical writeup — three design choices that made the difference between "toy" and "use this on a production site." If you want the marketing version, that's on the MCPize listing. This is what I'd want to read if I was evaluating a WP MCP in an afternoon.

---

## The problem I had

I own a WordPress site. It has ~100 posts, a messy plugin list, and a pending-comments queue nobody's touched in six months. I wanted to hand it to Claude. The existing WordPress MCPs on GitHub either (a) wrapped wp-cli in a way that needs SSH to my server (my managed host doesn't give me SSH), (b) dumped full `context=edit` HTML from the REST API into the agent's context window and exploded the token budget, or (c) had 3 tools that mapped to 3 REST endpoints and called it a day.

So I wrote one. Source is MIT-licensed at https://github.com/zedwards1226/wpflow. This post is about the 3 things inside it that made the biggest difference.

---

## Design choice #1 — Summary-first list responses

The WordPress REST API, on a `GET /wp-json/wp/v2/posts?per_page=100`, gives you every field of every post: `title.rendered`, `title.raw`, `content.rendered`, `content.raw`, `excerpt.rendered`, `excerpt.raw`, meta, links, the whole HAL envelope. For 100 posts, that's on the order of 150-250 KB depending on how chatty your content is.

Agents have to pay for every token they read. 200 KB of HTML is ~50 K tokens. That's nearly half a Claude 3.5 Sonnet context window gone on *a single list call* where the agent is probably going to filter down to 2-3 posts of interest.

wpflow's `list_posts` returns:

```json
{
  "id": 42,
  "title": "Q2 Product Update",
  "status": "publish",
  "date": "2026-04-15T10:30:00",
  "excerpt": "Shipping the agency tier and a new…",   // 200-char HTML-stripped
  "link": "https://example.com/q2-update/",
  "author_id": 1,
  "category_ids": [5, 12],
  "tag_ids": [8]
}
```

Same 100 posts in that shape: ~2 KB. Two orders of magnitude less context. Body HTML is a separate `get_post(id)` call the agent makes only when it needs it.

The rule in `tools/_common.py`:

```python
def post_summary(p: dict) -> dict:
    return {
        "id": p["id"],
        "title": _strip_html(p["title"]["rendered"]),
        "status": p["status"],
        "date": p["date"],
        "excerpt": _excerpt(p["excerpt"]["rendered"], 200),
        "link": p["link"],
        "author_id": p.get("author"),
        "category_ids": p.get("categories", []),
        "tag_ids": p.get("tags", []),
    }
```

Not clever. Just deliberate. Every list tool has one.

---

## Design choice #2 — Structured errors that tell the agent what to do next

The first version of wpflow returned raw WP REST error JSON. So the agent would get:

```json
{"code": "rest_user_invalid_id", "message": "Invalid user ID.", "data": {"status": 404}}
```

And loop, because "Invalid user ID" doesn't tell an agent which argument is wrong or how to fix it.

v0.1 has a 20-code taxonomy. Every tool maps any WP REST error (or any network / TLS / timeout failure) to one of these codes with a human-readable message aimed at the agent:

```python
class ErrorCode:
    AUTH_FAILED = "auth_failed"                    # Basic Auth rejected
    PERMISSION_DENIED = "permission_denied"        # wp thinks you exist but can't do this
    REST_API_DISABLED = "rest_api_disabled"        # /wp-json/ returns 404 or non-JSON
    REST_DISABLED_FOR_PLUGINS = "rest_disabled_for_plugins"  # /plugins endpoint specifically blocked
    NOT_FOUND = "not_found"                        # resource missing
    INVALID_ARGUMENT = "invalid_argument"          # 400 from WP
    RATE_LIMITED = "rate_limited"                  # includes retry_after if server sent it
    CLOUDFLARE_CHALLENGE = "cloudflare_challenge"  # CF bot management blocked us
    SSRF_REJECTED = "ssrf_rejected"                # upload URL points at a private IP
    MIME_REJECTED = "mime_rejected"                # upload type not in the whitelist
    PATH_REJECTED = "path_rejected"                # upload path not in WPFLOW_UPLOAD_ROOT
    RESPONSE_TOO_LARGE = "response_too_large"      # >5 MB
    TIMEOUT = "timeout"
    TLS_ERROR = "tls_error"
    NETWORK_ERROR = "network_error"
    SERVER_ERROR = "server_error"                  # 5xx after 2 retries
    # ...
```

Example: a `rest_api_disabled` error now comes back as:

```json
{
  "error": {
    "code": "rest_api_disabled",
    "message": "The WP REST API is not exposed at /wp-json/. Ask the user to open Settings → Permalinks in wp-admin and click Save — that re-registers the REST routes. If the problem persists, a security plugin is likely blocking it."
  }
}
```

That tells the agent what to try next. Across three agents I tested (Claude Desktop, Cursor, Claude Code), all three handed that message directly back to the user as a next-step suggestion instead of retrying the same failing call four more times.

---

## Design choice #3 — Browser-like User-Agent header (Cloudflare workaround)

Python `urllib` / `httpx` default User-Agent is like `python-httpx/0.27.0`. Cloudflare Bot Management — the default on TasteWP, InstaWP free tiers, and a pile of hosts running Cloudflare Pro or higher — flags that UA and returns HTTP 403 with `cf-mitigated: challenge`. The REST API never even hears the request.

The fix is one line and it drove me nuts to find:

```python
BROWSERISH_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)

self._client = httpx.Client(
    headers={"User-Agent": BROWSERISH_UA, "Accept": "application/json"},
    timeout=timeout_seconds,
)
```

Every time I see an MCP fail against a modern WP host, 8 times out of 10 this is why. If you're building any MCP that talks to an external HTTP service, add a real-looking UA to your defaults. The official Python HTTP UA is, in 2026, a deprecated signal. (Yes, Cloudflare's docs say you should register your bot. Realistically, consumer MCP installs aren't going to pre-register their laptop.)

---

## What I skipped on purpose

- **An auto-update watcher.** v0.1 has no "watch my site for changes" loop. Agents pull when asked.
- **A WordPress plugin that installs on the WP side to expose richer endpoints.** It would unlock some things (better plugin/theme file-level ops), but it also (a) means your wp-admin has a new attack surface, (b) requires wp.org review for distribution, and (c) undoes the 60-second install pitch. Net-negative.
- **A generic `wp_request` passthrough.** "Here's every REST endpoint, pick your own" sounds powerful and wastes context for every agent that isn't already a WP expert. The 25-tool surface is a deliberate filter.

---

## Install it

```
pip install wpflow
```

Then three env vars in your Claude Desktop config. Full setup + a screenshot guide for the Application Password step: https://github.com/zedwards1226/wpflow/blob/main/docs/app_password_setup.md

If it breaks on your host, open an issue with the error code — that's exactly what the 20-code taxonomy is designed to make easy to report.

---

*wpflow is MIT-licensed. Paid tiers (Solo $19/mo, Pro $49/mo, Agency $149/mo) on MCPize cover support and the hosted Streamable-HTTP transport when it ships in v0.2. If you self-host, the code is the same.*

---

## Medium cross-post (same post, softer intro for the non-dev audience)

**Title:** `What I automated away this weekend: running my WordPress site from Claude`

**First paragraph replacement (everything above "The problem I had" stays the same):**
> I spent a Saturday teaching my AI assistant to run my WordPress site. Not "write a blog post and I'll paste it in" — actually run the site. Draft posts. Mark spam. Clean up inactive plugins. Update a dozen slugs at once. I'll walk through the three technical decisions that made the difference, but if you're a non-dev site owner looking at this and wondering "can I use it?" — yes. Install is three steps. Code is MIT. Skip to the "Install it" section.

**Canonical URL:** the Dev.to URL.
