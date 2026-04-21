# Phase 2 — Synthesis & Decision

**Date:** 2026-04-20
**Orchestrator:** Jarvis
**Inputs:** MARKET_MAP.md (supply) · DEMAND_SIGNALS.md (demand) · MONEY_PATTERNS.md (money)

---

## Cross-Reference Filter

Three lenses had to overlap to qualify:

1. **Demand:** ≥1 explicit, cited user request in last 90 days.
2. **Willingness-to-pay:** commercial context (marketer, business owner, enterprise, agency).
3. **Supply gap:** no dominant incumbent OR existing incumbents are broken/regressed/badly hosted.
4. **Ship-this-session:** no multi-week vendor review gate (OAuth app review, compliance cert, marketplace listing).

Seven ideas cleared 1-3. Four cleared 1-4.

---

## Ranked Shortlist — Top 5

### #1 — Hosted WordPress Operator MCP **← WINNER**
**Problem:** Non-coder WordPress site owners and agencies can't use Claude to do real production WP work — existing WP MCPs (wp-cli-mcp, REST wrappers) are thin, break on non-trivial tasks, and need dev setup.
**Buyer:** WordPress site owners (prosumer $19-39/mo) + small agencies managing 5-50 sites ($99-299/mo tier).
**Evidence:** DEMAND_SIGNALS Signal 3 ("Has anyone built an MCP to control WordPress on Hostinger? I always fail" — 2026-04-02) AND Signal 4 (full post 2026-04-19: "I own a WP site... past developer left codebase in rough shape... I am not a developer... Has anyone done non-trivial WordPress work via Claude Code + MCP end-to-end on a production site?" — explicitly trying to replace paid dev work). Two independent asks, 2.5 weeks apart, same root problem. MARKET_MAP rates the category LOW-MEDIUM with no clear leader.
**Build complexity:** WEEKEND. WP has Application Passwords (user-generated in wp-admin) — **no OAuth app-review gate**. REST API is mature, documented. Python FastMCP + requests. Ship v0.1 today.
**Monetization:** Subscription, two tiers. Direct analog: 21st.dev Magic ($20/mo → $10K MRR in 6 weeks, per MONEY_PATTERNS). 40% of the web runs WordPress → TAM is not the question.

### #2 — Meta Ads Write-Access MCP
**Problem:** Media buyers want Claude to create/edit FB/IG ad campaigns, not just read reports. Windsor.ai is read-only and paid.
**Buyer:** Media buyers, small ad agencies. $49-149/mo.
**Evidence:** Signal 1 (2026-04-11, user already rejected paid read-only option) + Signal 18 (non-dev marketer replacing "half my workflow").
**Build:** WEEK+. Meta Marketing API is rich but ads_management scope requires **Meta App Review (3-7+ days)**. Can run a dev-mode beta first.
**Why not #1:** App Review gate breaks ship-this-session constraint. Queue for v2.

### #3 — Hosted QuickBooks MCP (for C-suite)
**Problem:** Intuit's own QuickBooks MCP is node-stdio — can't deploy to C-suite FP&A users.
**Buyer:** SMB finance teams. $99-299/mo.
**Evidence:** Signal 2 (2026-04-15, explicit "am I missing something?" shopping signal).
**Build:** WEEK. Intuit OAuth app review (3-14 days) + intricate accounting API. Also risk: Intuit may ship their own hosted version.
**Why not #1:** OAuth gate + incumbent-strike-back risk.

### #4 — Unified Social Posting MCP (multi-network)
**Problem:** Creators want one MCP to post to X / IG / FB / LinkedIn / TikTok.
**Buyer:** Creators, solopreneurs. $19-49/mo.
**Evidence:** Signal 6 (2026-04-02). Weaker signal, single post.
**Build:** WEEK+. N-platform OAuth; each platform has its own review gate; TikTok and IG business accounts are messy.
**Why not #1:** Fragmented OAuth ordeal and review gates.

### #5 — "Vibe" OpenAPI→MCP Quality Generator
**Problem:** Existing OpenAPI→MCP converters produce token-burning tool descriptions that fail agent calls (Signal 22, 23, 24).
**Buyer:** Semi-technical users wanting to point-and-click an MCP into existence. $29-99/mo.
**Evidence:** Three distinct signals in 2 weeks + 78k-tool analysis finding 98% unusable.
**Build:** WEEK. Harder than it looks — needs an LLM step to rewrite descriptions, filter endpoints, add examples. No review gates.
**Why not #1:** Dev-tools TAM with lower ARPU; harder to price above $29/mo without feeling like a Zapier clone.

---

## Decision: Build #1 — WordPress Operator MCP

**Codename:** `wpflow` (or `wpops` — name TBD, using wpflow for now).

**Five-sentence justification:**
1. It's the only top-5 idea that actually clears the ship-this-session gate — WP Application Passwords let us skip OAuth vendor review entirely, which kills #2, #3, and half of #4.
2. Demand is two independent cited asks in the last 3 weeks, both pointing at the SAME failure mode (existing WP MCPs break on non-trivial production work), not speculative.
3. Pricing fits the only proven standalone-SaaS MCP band — the $9-$30/mo prosumer lane where 21st.dev Magic hit $10K MRR in 6 weeks — and WordPress is 40% of the web, so the funnel is not the constraint.
4. Supply is genuinely weak (MARKET_MAP rates LOW-MEDIUM, no leader above a few hundred stars, existing wp-cli-mcp is a thin wrapper called out by name as insufficient), so even a mid-quality v0.1 beats what's on the shelf.
5. Clear upgrade path: solo-site prosumer tier → agency multi-site tier → white-label for Hostinger / Kinsta / WP Engine, which turns a $19/mo consumer SKU into a B2B2C revenue pipe.

---

## v0.1 Scope (this session)

- **Transport:** Streamable HTTP MCP server (Python + FastMCP).
- **Auth:** WordPress Application Password (site_url + username + app_password env vars / per-client config).
- **Core tools (token-efficient — summaries by default, full body only on request):**
  - `list_posts`, `get_post`, `create_post`, `update_post`, `delete_post`
  - `list_pages`, `get_page`, `update_page`
  - `list_plugins`, `activate_plugin`, `deactivate_plugin`
  - `list_themes`, `get_active_theme`
  - `list_media`, `upload_media` (URL or base64)
  - `list_users`, `get_user`
  - `list_comments`, `moderate_comment` (approve/spam/trash)
  - `site_health`, `search_content`
  - `list_categories`, `list_tags`, `create_term`
  - `verify_connection` (diagnostic)
- **Explicitly NOT in v0.1:** direct PHP/theme file editing, plugin install from zip, WP-CLI passthrough, multisite admin, WooCommerce. All v0.2+.
- **Deploy target:** Runnable locally via `uvx` AND hostable on Fly.io / Render for the paid tier. v0.1 ships local-first with a one-line Claude Desktop / Claude Code config.
- **Landing page:** Out of scope for v0.1 code — stub it with a README and a pricing-intent line. Full landing page is a Phase 4 task.
- **Pricing:** Solo $19/mo (1 site) · Pro $49/mo (5 sites, content calendar helpers) · Agency $149/mo (25 sites, team auth). Free tier: local-only, 1 site, rate-limited. Mirror 21st.dev Magic's $20 anchor.

---

## Non-Goals (protect scope)

- No full landing page / Stripe integration in v0.1 — proves the product first.
- No multi-tenant hosted SaaS in v0.1 — local-run only; SaaS is v0.2.
- No clever novel features — match or beat wp-cli-mcp's surface first; novelty comes after feedback.
- No agency-tier features in v0.1 — solo tier must be airtight before we multi-site.

---

## Next Phases

- **Phase 3 — BUILD:** Spawn BUILDER agent with narrow mission: FastMCP server + all v0.1 tools + working README + local Claude config + tests against a real WP test site.
- **Phase 4 — VERIFY:** Spawn a verifier to end-to-end test every tool against a real WP instance (paper test site). No "done" signal until verified.
- **Phase 5 — LAUNCH STUB:** Repo pushed public, README with install + pricing intent, post to r/mcp + r/ClaudeAI quoting the exact demand signals. Free tier open.
