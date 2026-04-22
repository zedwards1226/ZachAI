# Hacker News — Show HN post

**Url to post at:** https://news.ycombinator.com/submit
**When:** Day 2 (2026-04-22, NOT Day 1 — Reddit first, gather one round of feedback and fix anything obvious, then HN).
**Best time:** Tuesday-Thursday, 8-9 AM ET. Avoid Monday (dominated by "weekend projects") and Friday (traffic drop).
**Account:** Use your existing HN account with karma >50 if possible. New accounts with 0 karma posting Show HN + a GitHub link get auto-deprioritized.

---

## Title (HN title rules: factual, no SEO, no hype, ≤80 chars)

```
Show HN: Wpflow – 25-tool WordPress MCP for Claude (Python, MIT)
```

**Why not "built in a weekend" or "the first / the best":** HN guidelines explicitly discourage superlatives. "25-tool" is a factual handle and it defends the scope claim.

## URL field

```
https://github.com/zedwards1226/wpflow
```

## Text (HN lets you post text on a Show HN even when there's a URL — use it to frame)

Hi HN. I built wpflow because every WordPress MCP I tried fell down on anything beyond "list my posts."

It's a stdio MCP server (official `mcp` Python SDK) with 25 task-scoped tools for the WP REST API: posts, pages, media, plugins, themes, users, comments, taxonomy, site health. Auth is a WordPress Application Password — native to WP 5.6+, revocable from wp-admin, no OAuth / no vendor app review / no plugin installed on the WP side.

Three design choices that made it usable for me:

1. **Summary-first list responses.** `list_posts(per_page=100)` returns id/title/status/date/excerpt-200/link — about 2 KB for 100 rows. `get_post` is a separate call when the agent actually needs the body. The prior MCPs I tried returned `context=edit` HTML for every row and ate ~200 KB of context for the same request.

2. **Structured error taxonomy (20 codes).** `auth_failed`, `rest_api_disabled`, `rest_disabled_for_plugins`, `permission_denied`, `cloudflare_challenge`, `ssrf_rejected`, `mime_rejected`, and so on. Actionable: the error message tells the agent what to try next ("re-save Permalinks," "check that the upload is a jpeg/png/gif/webp/svg/mp4/pdf"). Critical for agents that otherwise loop.

3. **Browser-like User-Agent.** If you try to hit a Cloudflare-fronted WP site with Python's default `urllib` UA, Cloudflare Bot Management returns 1010 and blocks the request. wpflow sends a realistic `Mozilla/5.0 … Chrome/…` header on every request. Found this the hard way against a TasteWP site. If someone at Cloudflare wants to point to an official "programmatic access" header pattern, I'd happily switch.

Security: no code-execution path, no generic `wp_request` passthrough, TLS verify always on, 5 MB response cap, `upload_media` has MIME whitelist + SSRF guard + path denylist, logs scrub the Authorization header and the app password.

Tested against a live TasteWP site: 41/41 end-to-end tests pass.

Planned v0.2: multi-site config, Streamable-HTTP transport for a hosted tier, `create_page` symmetry, WooCommerce read-only.

Happy to take it apart in the comments — especially interested in (a) what WP hosts have REST configurations I haven't seen, and (b) where the 25-tool surface is missing a tool that would unlock a real workflow.

---

## After posting — the first 60 minutes matter

HN ranking in the first hour decides the day. Here's the playbook:

- Stay at your keyboard for 60 minutes after posting. Reply to every comment within 10 minutes.
- Do NOT ask anyone to upvote. HN detects vote rings and buries the post.
- Post on a day where you've got no conflicts. If you can't sit with it for an hour, wait a day.
- Expected first-hour traffic if it catches: 300-1,500 uniques to the repo. Make sure the GitHub README loads fast and the install instructions are the first thing after the title.

## Comments you should pre-draft replies to

| Likely question | Pre-drafted reply |
|---|---|
| "How is this different from wp-cli-mcp?" | "wp-cli-mcp shells out to WP-CLI, which needs SSH or at least a shell context on the WP server. Most managed WP hosts don't give you that. wpflow is REST + Application Password, which works on every host I've tested." |
| "REST API auth via HTTP Basic over TLS — isn't that shakier than OAuth?" | "The app password IS the OAuth replacement WordPress core ships since 5.6 — separate credential per client, revocable from wp-admin, user-scoped. TLS carries it. The attack surface is identical to any `Authorization: Basic` over HTTPS. The upside is no vendor review: you don't wait weeks for 'WordPress org' to approve your app." |
| "Why not WooCommerce from day one?" | "Because WC read+write is a 30+ tool surface on its own, and I wanted v0.1 to be small enough to actually ship. Read-only WC is in the v0.2 scope." |
| "How do you keep the agent from writing to the wrong site?" | "The active site is whichever the single `WPFLOW_SITE_URL` env var points at. Multi-site is v0.2, and the design there is one app password per site with a site-select argument, so the agent has to name the site every write." |
| "What about rate limits?" | "Free OSS tier has a soft rate-limit of 100 WP calls/hr enforced client-side (catches runaway agents). Paid tiers lift it. The WP REST API itself has no built-in rate limit — your host's WAF or security plugin might impose one, and wpflow surfaces that as a `rate_limited` error with the `Retry-After` value if the server returned one." |
| "Why Python and not TypeScript?" | "Because I had a working httpx + pydantic foundation in 2 hours vs a longer ramp on the TS SDK. No principled reason — a TS port would be welcome and nothing in the protocol stops it." |
