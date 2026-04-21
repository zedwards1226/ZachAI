# wpflow — MCPize Listing Copy

**Purpose:** copy-paste into the MCPize creator dashboard when submitting wpflow for listing.
**Anchor case studies to cite in any MCPize creator conversations:** MCPize's own disclosed numbers — AWS Security Auditor at $149/mo × 82 subs = $8.5k/mo; API integration tier at $29 × ~145 subs ≈ $4.2k/mo.

---

## Server name (what appears in the marketplace grid)

```
wpflow
```

## Tagline (59 chars max)

```
Run your WordPress site with Claude, in minutes.
```

## Short description (158 chars max — shows on the marketplace card)

```
25-tool MCP for WordPress. Edit posts, manage plugins, moderate comments from Claude. Uses your WP Application Password. No OAuth, no vendor review.
```

## Category

- Primary: **Content Management / CMS**
- Secondary: **Automation**

## Tags (10)

```
wordpress, wp, cms, content-management, blogging, rest-api, mcp, claude, automation, agency-tools
```

## Long description

**The problem.** You own a WordPress site. A past developer left it messy. You want Claude to help — draft posts, clean up plugins, moderate the spam pile, check site health — but the WordPress MCPs on GitHub are thin wrappers that break on anything non-trivial, and asking Claude to "just use curl" blows out your context window.

**What wpflow does.** wpflow is a local-first MCP server that gives Claude 25 task-scoped tools against your live WordPress site via the WordPress REST API. List, create, update, and delete posts and pages. Activate and deactivate plugins. Upload media. Moderate comments. List users, categories, tags. Run site health checks. Every list call returns compact summaries (not full body HTML), so a 100-post list costs ~2 KB, not 200 KB of tokens.

**Who it's for.** Non-coder WordPress site owners who want Claude to replace mid-tier dev work; consultants and agencies managing 5-25 client sites; anyone who tried wp-cli-mcp and hit a wall on production tasks.

**Install.** `pip install wpflow` (or `uvx wpflow`). Generate an Application Password in WP Admin → Profile → Application Passwords. Paste three env vars into your Claude Desktop config. Done. No OAuth consent screen, no vendor app review, no plugin to install on the WP site itself.

**Security.** No code execution path. No shell-out. No generic REST passthrough. Upload MIME whitelist + SSRF guard + 5 MB response cap. App password is scrubbed from every log line. MIT license, source on GitHub, audit before you trust it.

## Setup instructions (MCPize "how to install" field)

```json
{
  "mcpServers": {
    "wpflow": {
      "command": "wpflow",
      "env": {
        "WPFLOW_SITE_URL": "https://your-site.com",
        "WPFLOW_USERNAME": "your-wp-username",
        "WPFLOW_APP_PASSWORD": "abcd efgh ijkl mnop qrst uvwx"
      }
    }
  }
}
```

Three steps:
1. `pip install wpflow`
2. In WP Admin → Profile → Application Passwords, create one named "wpflow" and copy the 24-character password (spaces included).
3. Paste the JSON above into your Claude Desktop config with your real site URL, username, and the password. Restart Claude Desktop.

Full guide (with screenshots): https://github.com/zedwards1226/wpflow/blob/main/docs/app_password_setup.md

## 6 example prompts (MCPize "Try it" field — each maps 1:1 to a real DEMAND_SIGNALS quote)

1. **"My past developer left this site in rough shape. List every inactive plugin so I can decide what to clean up."**
2. **"Draft a post titled 'Q2 Product Update' with the following bullets, save as draft."**
3. **"Show me every pending comment from the last 14 days and flag obvious spam."**
4. **"Run a site health check and tell me if anything is critical."**
5. **"Find every post tagged 'pricing' published before 2026 and update the slug from /pricing-old/ to /archive-pricing/."**
6. **"Activate the SEO plugin I already have installed, then list categories so I can add a new one for 'Case Studies'."**

## Pricing tiers (MCPize billing config)

| Tier | Monthly price | What buyer gets | Stripe-product ID (MCPize fills this) |
|---|---|---|---|
| Free | $0 | 1 site, rate-limited 100 WP calls / hour, self-install from GitHub | n/a (OSS) |
| Solo | $19 | 1 site, no rate limit, email support | |
| Pro | $49 | 5 sites, bulk update helpers, 24h priority email | |
| Agency | $149 | 25 sites, team auth with app-password rotation, monthly audit CSV export, Slack-channel support | |
| Enterprise | Quote (≥$500) | Unlimited sites, SSO, white-label, SLAs, on-call | Contact sales |

**Free trial:** 14 days on Solo / Pro / Agency.

## Screenshots (upload 4)

1. `01-claude-desktop-with-wpflow-answering-real-prompt.png` — split screen: Claude chat on left asking "list pending comments", wpflow tool call + JSON summary on right.
2. `02-claude-desktop-config-snippet.png` — zoomed plain-text 3-line config. Answers "how hard is install" in one glance.
3. `03-wp-admin-application-passwords.png` — WP Admin → Profile → Application Passwords panel with "wpflow" added. Proves the auth path.
4. `04-tests-pass.png` — terminal showing `python test_server.py` → 41/41 PASS. Proves quality.

*(Screenshots live in `C:\ZachAI\companies\wpflow\docs\screenshots\` — capture before launch. See `launch/06_launch_runbook.md` for the exact shot list.)*

## Demo video

Paste the Loom embed URL. Fallback: YouTube Unlisted `youtu.be/...`. Do NOT put the MP4 inline — MCPize's player handles it better via Loom/YouTube.

## Repo link

```
https://github.com/zedwards1226/wpflow
```

## Support

```
GitHub Issues: https://github.com/zedwards1226/wpflow/issues
Email: wpflow@<your-domain>.dev (set this up on a forwarder before listing goes live)
```

## License

```
MIT
```

## Version at launch

```
0.1.0
```
