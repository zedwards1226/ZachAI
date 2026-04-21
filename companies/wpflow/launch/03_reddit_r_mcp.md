# Reddit — r/mcp launch post

**Subreddit:** https://old.reddit.com/r/mcp/
**When:** Day 0 (launch day), 10-11 AM ET. Never crosspost — r/ClaudeAI gets a different post (file 04).
**Account:** Zach's normal Reddit account (do NOT use a throwaway — Reddit's spam filter eats new accounts posting GitHub links).
**Flair:** "Show-and-Tell" or "Project" (whichever r/mcp has active at post time).

---

## Title (match r/mcp's vibe — specific, no clickbait)

```
I built wpflow — a 25-tool WordPress MCP for Claude, because every existing WP MCP I tried broke on non-trivial tasks
```

## Body

Short version up top: wpflow is a local-first MCP server (stdio, official `mcp` SDK) that gives an LLM agent 25 task-scoped tools against a live WordPress site via the WP REST API. Auth is a WordPress Application Password — no OAuth, no plugin install on the WP side, no vendor review gate.

Repo: https://github.com/zedwards1226/wpflow
PyPI: `pip install wpflow`

**Why I built it.** Two specific posts in this sub got me: the Hostinger "I keep trying, but I always fail" MCP question, and the "my past developer left the codebase in rough shape, I am not a developer, which WP MCP actually works" thread on r/ClaudeAI. Both got answers like "use wp-cli-mcp" or "write your own." Neither worked for the non-coder use case, and I wanted to solve it.

**What's in the 25 tools.** Posts (list / get / create / update / delete / search), pages, media (with MIME whitelist + SSRF guard on URL sources), plugins (list / activate / deactivate), themes, users, comments (including moderate for the spam-pile use case), taxonomy (categories / tags / create_term), and a `site_health` that surfaces WP's own Site Health module.

**Context-efficiency design choice.** Every list tool returns compact summaries by default — id, title, status, date, excerpt-200, link. A 100-post list is ~2 KB, not 200 KB of body HTML. If the agent actually needs body HTML, it calls `get_post` on the one it cares about. This was the single biggest thing that made every WP MCP I tried fail: they dump the entire `context=edit` payload and drown the context window.

**Security.** No code execution path. No `eval`, no shell-out, no generic REST passthrough / `wp_request` escape hatch. TLS verify always on. 5 MB response cap. Every log line has the Authorization header and app password scrubbed (both with and without spaces). `upload_media` has a MIME whitelist + SSRF guard (rejects private / loopback / link-local IPs) + a path denylist (uploads can only come from directories you configure via `WPFLOW_UPLOAD_ROOT`, defaults to ~/Downloads and ~/Pictures).

**Current status.** 41/41 end-to-end tests passing against a live TasteWP site (Cloudflare-fronted — took a real browser-like User-Agent header to get through). Ready for "send me your site URL and let me break it" energy.

**What I'd love help with.**
- Edge cases from hosts that have unusual REST configs (Kinsta, WP Engine, GoDaddy's old managed plans). If your site is weird, ping me with the error code and I'll fix it.
- "Which tool is confusing for non-devs" feedback — I'm already planning to rename `create_term` wording to "add category or tag" in the docs because the word "taxonomy" trips non-coders.
- Use cases you want covered that aren't there: WooCommerce (v0.2 has read-only scoped), multi-site, scheduled-post helpers, a WP-plugin auto-installer for the app-password step.

**Pricing honesty.** OSS free tier is the entire code base, 1 site, rate-limited to 100 calls/hr. Solo $19/mo is the same code with no rate limit and email support. Pro $49 / 5 sites and Agency $149 / 25 sites exist because — per MCPize's disclosed numbers — that's where the WP-agency buyer actually pays. Subscribe via MCPize if you want that or just self-host from GitHub; both work.

Happy to answer "why didn't you just use wp-cli-mcp" and "why not a WordPress plugin instead of a REST client" in the comments. Short answers: because most non-coder buyers can't SSH, and a site-side plugin turns Zach's "no OAuth, no vendor review" pitch into "yes OAuth-ish, yes plugin review at the WP side" — defeats the install-in-60-seconds claim.
```

## Preview-before-posting checklist

- [ ] Replace the Hostinger / r/ClaudeAI paraphrases with actual quoted sentences if you can lift them verbatim without over-specifying which user (keeps the post feeling like "I read this sub" not "I'm name-dropping").
- [ ] Confirm the GitHub link resolves (no 404 — run `gh repo view zedwards1226/wpflow` before posting).
- [ ] Confirm `pip install wpflow` actually installs (PyPI is live).
- [ ] Confirm `wpflow` command resolves on a fresh machine — not a cached one. Spin up a `python -m venv /tmp/fresh && /tmp/fresh/bin/pip install wpflow && /tmp/fresh/bin/wpflow --help` sanity check before posting.
- [ ] Expect the top comment to be "is this yours? monetization disclosure?" — have "yes, mine; Free tier is the repo, paid tiers on MCPize, pricing in the README" ready as a one-liner reply within 5 minutes of the post going up.

## How to reply to the inevitable hard questions

| Likely comment | One-line reply |
|---|---|
| "Another WP MCP. How is this different from wp-cli-mcp?" | "wp-cli-mcp needs shell access to your WP server. wpflow only needs the REST API and a 24-char app password. Half the hosts I tested don't give you SSH." |
| "REST API is disabled on my host" | "wpflow surfaces that as a clean `rest_api_disabled` error. Usually re-saving permalinks re-enables it. If your host hard-disables it at the edge, nothing talking REST will work and you need shell access — wpflow isn't magic." |
| "What if my agent accidentally deletes all my posts?" | "`delete_post` takes a single ID — the agent has to enumerate and commit. If that's still too scary, use `delete_post(force=false)` which trashes instead of permanently deletes, same as the WP UI trash. Writes never auto-retry on failure." |
| "Is my app password safe?" | "It sits in your Claude Desktop config on your machine. wpflow sends it over HTTPS to your WP site. It's scrubbed from logs. The repo is MIT-licensed, source is public, audit it." |
| "Why not a plugin on the WP side?" | "A plugin means vendor-side review at wordpress.org and a code path running on your web server that the agent can trigger. REST-API-only is the smaller attack surface, and lets you revoke the app password instantly." |
