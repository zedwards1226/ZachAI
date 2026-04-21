# wpflow — Pricing

**Unit of value:** one **site-month** — unlimited agent-driven WP operations against a single WordPress install for 30 days, with auth, token-efficient reads, and write guardrails.

One site-month replaces about one hour of $75-150/hr freelance WordPress-dev work per month.

## Tiers

| Tier | Price | Sites | Who it's for |
|---|---|---|---|
| **Free (OSS)** | **$0** | 1 | Self-host from GitHub. All 25 tools. Rate-limited to 100 WP calls/hr. No priority support. MIT license. |
| **Solo** | **$19 / mo** | 1 | Non-coder WordPress owners replacing $75/hr freelance dev work with Claude + wpflow. No rate limit, email support, roadmap voting. |
| **Pro** | **$49 / mo** | 5 | Prosumers running 3-5 WP sites, or consultants with 5 small clients. Everything in Solo + 5-site config + bulk update helpers + 24h priority email. |
| **Agency** | **$149 / mo** | 25 | Small WP agencies. Everything in Pro + team auth (multi-app-password rotation) + monthly audit export (CSV of every write the agent did) + Slack-channel support. |
| **Enterprise / white-label** | Quote (from $500 / mo) | Unlimited | Hosting companies, large agencies. Agency + SSO + custom SLAs + Hostinger/Kinsta/WP Engine white-label + on-call support. |

## Why these prices

- **$19 Solo** sits 5% below 21st.dev Magic's $20/mo anchor (the proven prosumer MCP price point), and exactly at the Zapier Starter "750 tasks" floor.
- **$49 Pro** is the top of the MCPize-guidance band for "API integrations + database connectors" — justified because wpflow ships 25 tools instead of 1-2.
- **$149 Agency** maps to an existing disclosed MCPize data point (AWS Security Auditor MCP, $149/mo × 82 subs = $8.5k/mo). That's the shape we're replicating: replace one billable hour per client-site per month.

## Free tier is load-bearing

It's not a giveaway. It's the OSS audit that makes a non-coder willing to paste an Application Password into their config. If you can't read the source, you shouldn't trust the tool. Free tier converts to Solo when the buyer hits the 100 call/hr limit or wants support.

## Refunds

30-day money back on Solo / Pro / Agency. Email the address in your receipt. No questions.

## Where to subscribe

- **MCPize marketplace:** (link will be here once listing is live)
- **Direct / self-host:** `pip install wpflow` — free tier. Upgrade link in the README.
