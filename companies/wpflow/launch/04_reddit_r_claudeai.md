# Reddit — r/ClaudeAI launch post

**Subreddit:** https://old.reddit.com/r/ClaudeAI/
**When:** Day 0, 4-5 hours after the r/mcp post. Never crosspost — this is a **first-principles rewrite** for a different audience (this sub is more "I used Claude and it worked" and less "here's the code").
**Flair:** whichever flair r/ClaudeAI uses for "project / community resource" at post time.

---

## Title

```
I built wpflow so Claude can finally run my WordPress site end-to-end (non-coders: this is the one that works)
```

## Body

Short version: wpflow is a WordPress MCP for Claude Desktop / Claude Code. You paste three env vars into your config, Claude gets 25 tools against your site, done. No OAuth, no plugin to install on the WordPress side, no developer required.

Repo: https://github.com/zedwards1226/wpflow

**Who this is for.** If you own a WordPress site and have been wishing Claude could "just do it" — draft posts, moderate the pending-comment pile, list inactive plugins so you can clean them up, run a site health check, update a bunch of post slugs — this is the tool. You do not need to code. You do need a WordPress Application Password (there's a 4-step guide in the repo).

**Why I wrote this sub specifically:** there are two posts on this sub from earlier this month that were basically "I'm not a developer, I have a WordPress site, every MCP I try falls down on real tasks, help." I was one of the people who would've replied "yeah same" and not had an answer. Now I do.

**What it does (plain English):**
- List or search your posts / pages — Claude reads titles, dates, excerpts (not the full body) by default so your context window doesn't explode.
- Create a new post as a draft, or update / publish / delete an existing one.
- Upload an image to your media library (from a URL or a local file — SSRF and MIME checks so Claude can't accidentally yank something private).
- List plugins (filter active vs inactive), activate or deactivate by slug.
- See pending comments, mark spam / approve / trash one by one or in a batch Claude handles.
- Add categories and tags (the docs say "taxonomy" because that's what WordPress calls it, but the tool is `create_term` = "add a category or a tag").
- Run a site health check — Claude reads WordPress's own Site Health module and tells you if anything is critical.

**Why I didn't just use wp-cli-mcp:** it needs SSH / WP-CLI access on your server. Most managed WP hosts don't give you that. Application Passwords work on every host I've tried (Hostinger, InstaWP, TasteWP, self-hosted).

**Why I didn't write a WordPress plugin:** that creates a code path running inside your WP server that anyone authenticated could trigger, which is scarier than a REST client running on my laptop that talks to WP with a password you can revoke in 1 click from wp-admin.

**Safety.** Every log line has your app password scrubbed out. No code-execution tool (no "run arbitrary WP code for me"). Writes don't auto-retry — if a `create_post` fails, it fails once and reports the error, so you won't end up with 3 duplicate drafts. MIT license, source is public — if you don't trust me, read the code or have your dev read it before you paste your app password.

**Pricing.** Free if you pip-install it from GitHub and self-host. $19/mo (Solo, 1 site) or $49/mo (Pro, 5 sites) on MCPize if you'd rather have it managed and supported. $149/mo Agency tier for shops with many client sites. Honesty: yes I'd like you to pay, but the code is MIT and the whole thing works free — the paid tiers are for the folks who want support and for the agency use case.

**Ask.** If you try it and something breaks, open a GitHub issue with the error code (it's a structured string like `rest_disabled_for_plugins`) and your host name. I'll fix it. If it works, tell me what you automated — that's the feedback that shapes v0.2.

Happy to answer setup questions in the comments. The 4-step app-password guide is at https://github.com/zedwards1226/wpflow/blob/main/docs/app_password_setup.md

## Do not

- Do not include screenshots of Claude replies that show actual WP content. This is a launch post, not a product demo — the video does that job. Pure text on this sub ranks higher.
- Do not reply to comments with marketing copy. Reply like a person. "Yes" / "no" / "you're right, that's a bug, opened #3" wins.
- Do not crosspost this to r/WordPress. Their moderators will eat it (self-promo rule). If someone there wants it, let them link to it organically.
