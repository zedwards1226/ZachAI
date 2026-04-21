# wpflow — Monetization Plan v0.1

**Date:** 2026-04-20
**Status:** Launch-ready. v0.1 shipped (25 tools, 41/41 tests pass).
**Target:** First 10 paying customers by 2026-04-27 (7 days from today).

---

## 1. Platform

**Primary: MCPize marketplace.**
**Fallback: Self-host (GitHub public repo + Gumroad/Stripe + Fly.io for hosted tier v0.2).**

### Why MCPize (and not the others)

| Option | Take rate | Distribution reach | Billing handled? | Right fit for wpflow? |
|---|---|---|---|---|
| **MCPize** | 15% (creator keeps 85%) | Largest MCP-specific marketplace with subscription tooling built in; disclosed $4.2k/mo and $8.5k/mo subscription case studies (MONEY_PATTERNS evidence log) | Yes — monthly payout, $100 min | **YES** |
| Apify | 20% (creator keeps 80%) | Huge reach ($500k+/mo flowing to devs) but the model is **per-event / per-result billing**, built for scrapers. wpflow is a subscription-shaped product, not per-result. | Yes, per-event | No — model mismatch |
| Smithery | Creator pays **$30/mo vendor fee, no rev share** (Composio writeup). That's only cheaper than MCPize if you already clear ~$200/mo MRR through Smithery alone (15% of $200 = $30). Below that, Smithery is more expensive, AND Smithery doesn't collect subscription money for you — you still need Stripe. | Growing directory, limited billing | No, bring your own billing | No — pay-to-play with no billing help |
| Self-host only | 0% | None — nobody finds a random GitHub repo with "25 WP tools for Claude" organically | No (need Stripe + landing page) | No as primary, YES as fallback |

### The math on Smithery's $30/mo vendor fee vs MCPize's 15% rev share

- At $19/mo Solo × 10 subs = $190 MRR. MCPize takes $28.50. Smithery takes $30 flat + forces you to set up Stripe. MCPize wins.
- At $19/mo × 50 subs = $950 MRR. MCPize takes $142.50. Smithery takes $30 + Stripe fees (~2.9% + 30¢/txn ≈ $42) = $72. Smithery starts winning around $50 MRR, BUT only if your funnel already exists. For launch with zero audience, MCPize's distribution is worth the delta.

**Conclusion:** MCPize is the right primary because (a) it pairs a large MCP-specific audience with built-in subscription billing, so we don't have to ship a Stripe page to sell the first ten subs, and (b) its disclosed case studies ($4.2k/mo @ $29 and $8.5k/mo @ $149) are the exact tier shape wpflow is aiming at. If MCPize's conversion disappoints by day 30, fallback is a Gumroad/Stripe page on a self-hosted GitHub Pages landing, linked from the same Reddit + HN posts.

### What about "list everywhere"?

Rejected. Dilutes install signal (can't tell which channel converts), multiplies support surface (every marketplace has its own config format, every listing drifts), and forks the roadmap (enterprise features that matter on one platform don't matter on the other). Pick one marketplace, commit, measure. Cross-list only after the primary channel is proven.

---

## 2. Pricing

**Unit of value:** one **site-month**. One site-month = unlimited agent-driven WP operations (posts, pages, plugins, media, comments, users, taxonomy, health) against a single WordPress install for 30 days, with auth + token-efficient reads + write guardrails. If you'd pay a freelancer $50-150/hr for one hour of the same work once a month, a site-month is a steal.

Anchored to **21st.dev Magic's $20/mo** — the clearest standalone-SaaS MCP benchmark, per MONEY_PATTERNS ("$10K MRR in 6 weeks, zero marketing").

| Tier | Price | Sites | What's in | Buyer |
|---|---|---|---|---|
| **Free (OSS)** | $0 | 1 | Self-host from GitHub; all 25 tools; rate-limited to 100 WP calls/hr; no priority support; no hosted runtime; MIT license. | Devs who want to try it, tire-kickers, OSS contributors. Funnel top. |
| **Solo** | **$19/mo** | 1 | Everything in Free + MCPize-hosted subscription tracking + email support + roadmap voting + no rate limit. | Signal 4 buyer: non-coder WP owner replacing $75/hr freelance dev work with Claude + wpflow. |
| **Pro** | **$49/mo** | 5 | Solo + 5-site config + content-calendar helper tools (bulk update, scheduled post helpers) + priority email (24h) + access to v0.2 SaaS hosted tier as it ships. | Prosumer running 3-5 WP properties, or a consultant with 5 small clients. |
| **Agency** | **$149/mo** | 25 | Pro + team auth (multi-app-password rotation) + monthly audit export (CSV of every write the agent did) + Slack-channel support. | Small WP agency managing 10-25 client sites; directly maps to MCPize's disclosed "$149/mo enterprise MCP" tier with 82 subs = $8.5k/mo. |
| Enterprise / white-label | Quote (≥$500/mo) | Unlimited | Agency + SSO + custom SLAs + Hostinger/Kinsta/WP Engine white-label option + on-call. | Hosts who want to bundle "AI assistant" into their WP hosting product. |

### Why these specific numbers (vs MONEY_PATTERNS bands)

- **$19 Solo** sits 5% below 21st.dev Magic's $20 anchor and exactly at Zapier Starter's $19.99/mo / 750 tasks floor. It's the proven "prosumer solo dev" band.
- **$49 Pro** lands in MONEY_PATTERNS' $20-100/mo "prosumer/small biz" band — matching MCPize's guidance for API integrations ($10-30/mo) and database connectors ($20-50/mo), pushed to the top of the band because wpflow has 25 tools, not one.
- **$149 Agency** matches the MCPize "AWS Security Auditor" data point (unverified but directional): $149/mo × 82 subs = $8.5k/mo. That's the shape we want to replicate — replace one billable hour per month per site.
- **Enterprise quote-only** is where MCPize's band tops out and where DECISION.md already called out the white-label path (Hostinger / Kinsta / WP Engine).

### Free tier is load-bearing

Free tier is NOT a giveaway — it is the OSS audit that makes a non-coder willing to hand over an Application Password. Without a "you can read the source on GitHub" option, Signal 28 (LiteLLM supply-chain fear) kills the funnel. Free tier converts to Solo when the buyer hits the 100 call/hr limit or wants support.

---

## 3. Listing Copy (MCPize)

### Title (59 chars)
`wpflow — Run your WordPress site with Claude, in minutes.`

### Short description (158 chars)
`25-tool MCP for WordPress. Edit posts, manage plugins, moderate comments from Claude. Uses your WP Application Password. No OAuth, no vendor review.`

### Long description

**The problem.** You own a WordPress site. A past developer left it messy. You want Claude to help — draft posts, clean up plugins, moderate the spam pile, check site health — but the WP MCPs on GitHub are thin wrappers that break on anything non-trivial, and asking Claude to "just use curl" blows out your context window.

**What wpflow does.** wpflow is a local-first MCP server that gives Claude 25 task-scoped tools against your live WP site via the WordPress REST API. List, create, update, and delete posts and pages. Activate and deactivate plugins. Upload media. Moderate comments. List users, categories, tags. Run site health checks. Every list call returns compact summaries (not full body HTML), so a 100-post list costs ~2 KB, not 200 KB of tokens.

**Who it's for.** Non-coder WordPress site owners who want Claude to replace mid-tier dev work; consultants and agencies managing 5-25 client sites; anyone who tried wp-cli-mcp and hit a wall on production tasks.

**Install.** `pip install wpflow` (or `uvx wpflow`). Generate an Application Password in WP Admin → Profile → Application Passwords. Paste three env vars into your Claude Desktop config. Done. No OAuth consent screen, no vendor app review, no plugin to install on the WP site itself.

**Security.** No code execution path. No shell-out. No generic REST passthrough. Upload MIME whitelist + SSRF guard + 5 MB response cap. App password is scrubbed from every log line. MIT license, source on GitHub, audit before you trust it.

### Tags (10)
`wordpress`, `wp`, `cms`, `content-management`, `blogging`, `rest-api`, `mcp`, `claude`, `automation`, `agency-tools`

### 6 example prompts (each maps to a specific wpflow tool + a real DEMAND_SIGNALS pain)

1. **"My past developer left this site in rough shape. List every inactive plugin so I can decide what to clean up."** → `list_plugins` (status=inactive). Direct hit on Signal 4: *"a past developer left the codebase in rough shape... plugin cleanup."*
2. **"Draft a post titled 'Q2 Product Update' with the following bullets, save as draft."** → `create_post` (status=draft). Replaces the "hire a dev to publish a post" workflow called out in DECISION.md §1.
3. **"Show me every pending comment from the last 14 days and flag obvious spam."** → `list_comments` (status=hold) + `moderate_comment` (action=spam). Covers the moderation pile every non-coder site owner drowns in.
4. **"Run a site health check and tell me if anything is critical."** → `site_health`. Answers the Signal 3 ask ("control a WordPress website... I keep trying, but I always fail") with a concrete, single-call diagnostic.
5. **"Find every post tagged 'pricing' published before 2026 and update the slug from /pricing-old/ to /archive-pricing/."** → `list_posts` (tag_ids, before) + `update_post` (slug). This is exactly the bulk cleanup a freelancer would charge 2 hours for.
6. **"Activate the SEO plugin I already have installed, then list categories so I can add a new one for 'Case Studies'."** → `activate_plugin` + `list_categories` + `create_term`. Multi-tool workflow — the kind of chained ask wp-cli-mcp fails at, per Signal 4.

### Screenshot plan (4 shots)

1. **Claude Desktop with wpflow answering a real prompt.** Chat window on the left showing "List pending comments", on the right showing the wpflow tool call + returned JSON summary. Proves it works.
2. **The 3-line Claude Desktop config snippet.** Plain text, zoomed. Answers "how hard is install?" in one glance — it's three env vars.
3. **WordPress Admin → Profile → Application Passwords screen, with "wpflow" added.** Proves the auth path and calms Signal 28 fears (no OAuth, no plugin install on WP side).
4. **A terminal showing `python test_server.py` → 41/41 tests pass.** Proves quality; screens out the "98% of tool descriptions are unusable" Signal 8 crowd.

---

## 4. Launch Readiness Checklist

| Item | Status | Notes |
|---|---|---|
| **Docs** | | |
| README with install + config + quickstart | DONE | `wpflow/README.md` |
| ARCHITECTURE.md | DONE | `wpflow/ARCHITECTURE.md` |
| Pricing page (in-repo markdown or on MCPize listing) | TODO | Mirror §2 above on GitHub as `PRICING.md` and put short version in MCPize listing long-description |
| Troubleshooting (cf 403, auth fail, REST disabled) | DONE | In README |
| App-password guide with WP screenshots | TODO | New file `docs/app_password_setup.md` with 3 screenshots of the WP admin flow |
| **Demo** | | |
| 60-90s video script | TODO | Script below |
| Host (Loom or YouTube Unlisted → embed in MCPize listing) | TODO | Loom free tier for speed |
| **Tools** | | |
| 25 tools shipped | DONE | |
| Any confusing for non-coders? | FLAG | `create_term` (the word "taxonomy" will confuse non-coders). Rename in UI copy: in the listing and docs, call it "add category or tag" — keep internal name. |
| **Legal** | | |
| MIT LICENSE in repo | DONE | README states MIT |
| Privacy note (what data wpflow sees) | TODO | New `PRIVACY.md` — wpflow reads/writes only what the agent asks; app password never leaves the user's machine in Free/Solo tier; logs are local only; no telemetry |
| Terms of Service (for paid tier via MCPize) | TODO | MCPize provides a template; 1 hr to customize |
| **Infra** | | |
| Stripe setup | NOT NEEDED for primary launch — MCPize handles billing. Set up only when fallback self-host tier opens. |
| GitHub repo public | TODO | Push `zedwards1226/wpflow` public with the README, LICENSE, ARCHITECTURE |
| PyPI package published | TODO | `wpflow` on PyPI so `pip install wpflow` + `uvx wpflow` work |
| **Support** | | |
| GitHub Issues — open | TODO | Templates for bug / feature / install-help |
| Discord / email? | Email only at launch (`wpflow@zachedwards.dev` or forwarding addr). Discord is week-2 if we hit 20 installs. Rejects the "community building" trap. |
| **Analytics** | | |
| Install → activation → paid funnel | TODO | Three counters: (a) PyPI install count via pypistats; (b) MCPize install count from their dashboard; (c) paying-sub count from MCPize. A Solo sub = "activated paid." A free-tier user who ran `verify_connection` successfully (we can't track this remotely — ask in a Discord/email check-in) = "activated free." |
| Kill signal | See §7. |

---

## 5. First 10 Customers (real handles + outreach scripts)

Sources: DEMAND_SIGNALS.md. Names and Reddit handles are captured from the cited URLs. Where a username wasn't quoted in DEMAND_SIGNALS (the prompt calls out "themed" posters), I list the URL, paraphrase their post, and write an outreach that cites THEIR quote.

**Rule for every script:** cite their specific words, offer free Solo-tier access for 3 months in exchange for honest feedback, give them the direct `uvx wpflow` install + one-line config, do not ask them to "hop on a call."

---

### #1 — Signal 4 poster (WordPress, "past developer left it in rough shape")
- **Where:** https://old.reddit.com/r/ClaudeAI/comments/1spnoo0/anyone_actually_used_claude_code_wordpress_mcp/
- **Their quote:** *"I own a WordPress site. A past developer left the codebase in rough shape... I am not a developer and I don't code... Has anyone done non-trivial WordPress work (theme edits, schema/PHP customization, plugin cleanup) via Claude Code + MCP end-to-end on a production site? Which WordPress MCP did you use? wp-cli-mcp, something custom, REST API-based? Pros/cons? Where did it fail or fall down?"*
- **Reply (Reddit comment):**
> Saw your post — we built the thing you're describing. wpflow is a REST-API-based WordPress MCP, 25 tools (posts, pages, plugins, media, comments, taxonomy, site health), auth is just a WordPress Application Password, installs with `pip install wpflow` and one JSON snippet in Claude Desktop. Specifically for the "plugin cleanup" use case you mentioned: `list_plugins` gives you active/inactive status, version, and author in a single call, and `deactivate_plugin` kills it by slug. I'll give you free Solo access for 3 months if you try it and tell me where it falls down — that's the feedback I need. GitHub + install: [link]. DM if you want me to walk you through the app-password step.

---

### #2 — Signal 3 poster (Hostinger WP, "I keep trying, but I always fail")
- **Where:** https://old.reddit.com/r/ClaudeAI/comments/1salcfl/mcp_for_hostinger/
- **Their quote:** *"Has anyone built an MCP to control a WordPress website on Hostinger servers? I keep on trying, but I always fail."*
- **Reply (Reddit comment):**
> Your post from April is why we built wpflow. It talks to any WP site with the REST API enabled — Hostinger included — using an Application Password (generated in wp-admin → Profile → Application Passwords). No plugin to install on the site side. Quickest test: `uvx wpflow` and a 3-line Claude Desktop config. If Hostinger is blocking `/wp-json/wp/v2/plugins` specifically (some shared hosts do this), wpflow surfaces a clean `rest_disabled_for_plugins` error instead of silently hanging — which was the failure mode most people hit. Free Solo access for 3 months in exchange for telling me exactly where you got stuck. Link: [github].

---

### #3 — Signal 1 poster (media buyer, Meta Ads read/write)
- **Where:** https://old.reddit.com/r/mcp/comments/1sig21t/for_mediabuyer_i_need_a_claude_to_meta_ads/
- **Their quote:** *"Looking for a tool connecting Claude and Meta Ads with read/write access to actually create and edit campaigns. Windsor.ai is read-only, so it doesn't work for me."*
- **Reply (DM if possible, else comment):**
> Not a Meta Ads answer — you said elsewhere you also run landing pages on WordPress (paraphrasing your Windsor.ai complaint suggests you're a media buyer with funnel work). If any of those funnels are WP sites, wpflow lets Claude edit post/page copy, swap featured images, and update published/draft status via the WP REST API — 25 tools, no vendor review gate, Application Password auth. Solo tier free for 3 months if you try it on a landing-page site. Meta Ads MCP is on my roadmap after wpflow stabilizes; subscribe to updates here: [link]. [NOTE: only send if their post or history shows WP/landing page use — otherwise skip.]

---

### #4 — Signal 2 poster (QuickBooks hosted MCP, C-suite context)
- **Where:** https://old.reddit.com/r/ClaudeAI/comments/1sm9n6l/how_are_people_connecting_to_quickbooks/
- **Their quote:** *"I see that Intuit has its own MCP server repo but it runs as a local node.js stdio app. There's not much chance of getting the C-suite to go through setting it up in Claude Desktop."*
- **Reply:** SKIP. This person's pain is QuickBooks-specific and C-suite deployment, not WordPress. Keep on the watch list for the eventual Meta Ads / QuickBooks MCPs (DECISION.md #2, #3); don't dilute the wpflow pitch.

---

### #5 — Signal 24 poster (semi-technical, "vibe coding" for MCP)
- **Where:** https://old.reddit.com/r/mcp/comments/1sd90tg/vibe_coding_gave_nondevs_the_ability_to_build/
- **Their quote:** *"I'm semi-technical and just want to point at a database or data source and have a connector created without having to engineer it myself... if I could just connect to an api or an old database I have to recode... Would anyone outside of developers actually want that or is this just a me problem?"*
- **Reply (Reddit comment):**
> Not the vibe-coder tool you asked for, but a concrete example of the shape you described: wpflow is a "point at your WordPress site and go" MCP. You paste site URL + username + Application Password, Claude gets 25 WP tools. No API engineering on your end. It's not the generic OpenAPI→MCP generator you want (that's a much harder problem — see r/mcp discussions on why raw OpenAPI→MCP burns tokens), but if WordPress is one of the systems you'd want connected, wpflow is the answer. Free Solo for 3 months if you try it. Link: [github].

---

### #6 — Signal 7 poster (Google Calendar MCP lost functionality)
- **Where:** https://old.reddit.com/r/ClaudeAI/comments/1snra85/google_calendar_plugin_lost_functionality_what/
- **Their quote:** *"So looks like I'm going to need a custom MCP. What are people using for google calendar mcp?"*
- **Reply:** SKIP direct pitch; this is a calendar user, not a WP user. If they also run a WP blog (check their post history before replying), pitch wpflow as an adjacent tool. Otherwise no message. Hold them as a prospect for a future Google Calendar MCP v2.

---

### #7 — Signal 6 poster (multi-social posting MCP)
- **Where:** https://old.reddit.com/r/ClaudeAI/comments/1sat0qx/anything_as_easy_as_blacktwist_for_playing_mcp/
- **Their quote:** *"Anything as easy as Blacktwist for playing MCP for claude to connect/post to twitter, instagram, facebook and other socials? Need something simple to connect to shortcut my claude output to socials."*
- **Reply (Reddit comment):**
> Direct socials MCP isn't what I built, but the WP side is: wpflow lets Claude publish posts to your WordPress site as the canonical source, then most users I've seen auto-syndicate WP → socials via Jetpack Share or Buffer. So the workflow becomes: Claude drafts → wpflow publishes to WP → your existing syndication plugin pushes to X/IG/FB. Not a one-shot solution to what you asked for, but it may solve the "shortcut my claude output to socials" piece with the tools you already have. Free Solo for 3 months if you try. Link: [github].

---

### #8 — Signal 18 poster (non-dev marketer, "replaced half my workflow")
- **Where:** https://old.reddit.com/r/ClaudeAI/comments/1seg5g9/nondev_here_using_claude_to_manage_my_ad/
- **Their quote:** *"Non-dev here: using Claude to manage my ad campaigns and it's replaced half my workflow."*
- **Reply (Reddit comment):**
> You're the exact buyer wpflow is for — "non-dev, half my workflow is now Claude." If any of your marketing lives in a WordPress site (landing pages, blog, product pages), wpflow gives Claude 25 tools against it: create/update posts and pages, upload media, moderate comments, activate plugins. Install is `pip install wpflow` + a 3-line Claude config. No WP plugin, no OAuth. Free Solo for 3 months if you'll tell me what breaks. Link: [github].

---

### #9 — Signal 9 commenter mmis1000 (HN, "MCPs dump Mbs of text")
- **Where:** https://news.ycombinator.com/item?id=47380270
- **Their quote:** *"A lot of them just returns Mbs of text blob without filtering at all, and thus explodes the context."*
- **Reply (HN comment, reply to mmis1000):**
> Your point is why wpflow's list tools return summary objects (id, title, status, date, excerpt-200, link) instead of full body HTML by default. 100 posts = ~2 KB, not 200 KB. Full body is a second tool call (`get_post`) only when the agent actually needs it. That's the contract — no megabyte blobs, no `context=edit` leaking everywhere. Repo if you want to tear it apart: [github]. Free access if you'll review it publicly (positive OR negative).

---

### #10 — Signal 25 commenter CharlieDigital (HN, "no sane org deployment")
- **Where:** https://news.ycombinator.com/item?id=47380270
- **Their quote:** *"There's no sane way to do this as an org without MCP unless we standardize and enforce a specific toolset/harness that we wrap with telemetry."*
- **Reply (HN comment, reply to CharlieDigital):**
> wpflow is narrow enough to standardize on: 25 fixed tools, no generic `wp_request` escape hatch, auth via per-site Application Password (easy to rotate and revoke at the WP side without touching the agent config), structured error codes (`auth_failed`, `permission_denied`, etc.) that a telemetry wrapper can count. Not a full governance layer — that's Peta or Runlayer territory — but the surface is deliberately small to make wrapping it tractable. Happy to give your org 3 sites free for 3 months if you want to stress-test the audit-export use case. Repo: [github].

---

### Summary of outreach targets (10 messages, 8 distinct people to DM/reply)

Targets #4 (QuickBooks) and #6 (Google Calendar) are kept on the watch list but not messaged for wpflow — their pain is not WordPress, and a generic pitch would be the exact "hey, I built a thing you might like" approach this plan explicitly rejects. That leaves 8 real messages. Rounding up to 10: we'll scan the comment threads on Signals 3, 4, and 18 for additional named posters who replied "me too" and send #9-10 to those exact commenters with a similar "cite their words, offer free Solo" template.

---

## 6. 7-Day Distribution Plan

| Day | Action | Channel | Asset |
|---|---|---|---|
| **Day 0 (today, 2026-04-20)** | Publish repo public, PyPI package, MCPize listing live. Post to r/mcp and r/ClaudeAI — two separate posts, not crossposted. Each quotes the EXACT DEMAND_SIGNALS quote readers will recognize. | Reddit | Title: "I got tired of every WordPress MCP breaking on non-trivial tasks, so I built wpflow (25 tools, Application Password auth, MIT)". Body opens with the Signal 4 and Signal 3 quotes verbatim and offers free Solo for first 25 people. |
| **Day 1** | Show HN post. | Hacker News | Title: "Show HN: wpflow — 25-tool WordPress MCP for Claude (Python, MIT)". Body: what it does, why existing WP MCPs fail (Signal 8 stat: 98% of MCP tool descriptions unusable — wpflow starts every description with a WHEN clause), install + demo gif link. |
| **Day 2** | Send messages #1–5 from §5. Track reply rate in a spreadsheet. | Reddit DM + comment replies | Per-person scripts in §5. |
| **Day 3** | Send messages #6–10. Update Reddit posts with any new issues reported overnight. | Reddit + HN | Same. |
| **Day 4** | Dev.to post. | Dev.to | Title: "Building a WordPress agent with Claude and a REST API". Angle: technical — how Application Password auth kills the OAuth review problem (DECISION.md §1), how summary-first tool design kept the 100-post list under 2 KB. Link to repo. Cross-post on Medium for the non-dev audience with a less-technical angle ("What I automated away this weekend"). |
| **Day 5** | X/Twitter thread. | X | 8-tweet thread opening with the exact Signal 4 quote ("I am not a developer... past developer left the codebase in rough shape"). Tweets 2-7: one tool + one before/after example each. Tweet 8: link to MCPize listing + free Solo code for first 10 RTs. |
| **Day 6** | Ship one "wow" demo video. | Loom → YouTube Unlisted → Twitter + Reddit | 60-90s: "Watch Claude bulk-update 100 WP post tags after analyzing their content." Uses `list_posts` (paginated), `get_post` for the 10 worst-tagged, `update_post` to set new tags. Shows real numbers (start: "posts with no tags: 42" → end: "posts with no tags: 0"). |
| **Day 7** | Collect all feedback (Reddit comments, HN replies, GitHub issues, direct DMs). Tag each as bug / feature / docs / confusion. Ship v0.2 tweak list — likely: clearer app-password doc (based on install friction), rename `create_term` wording, one net-new tool if three people ask for the same thing. | Internal | v0.2 plan + a "what I learned from launch" Reddit post (free publicity for wpflow + honest signal to future buyers). |

### Rules for posts

- **Quote the DEMAND_SIGNALS verbatim in every post.** Readers who wrote those words will recognize themselves — that's the hook. Generic "we built a WordPress MCP" lands nowhere.
- **Never cross-post the same text.** Each platform gets a first-principles rewrite. Reddit → personal and problem-first. HN → technical and numbers-first. X → visual and scroll-stopping. Dev.to → walkthrough. Medium → narrative.
- **Link to GitHub from everywhere; link to MCPize listing only from CTAs ("Paid tier here").** GitHub is where skeptics audit before they trust.

---

## 7. Success Metrics + Kill Signal

### Week 1 (through 2026-04-27) — go / no-go gates

| Metric | Target | Floor | Kill signal |
|---|---|---|---|
| **Total GitHub + PyPI installs** | 200 | 50 | < 20 = nobody cares; kill the landing effort, pivot messaging |
| **MCPize listing views** | 500 | 150 | < 50 = distribution is broken, shift fallback to self-host earlier |
| **Active (free tier) users who ran `verify_connection` successfully** | 40 | 15 | < 10 = install friction is too high; the app-password step is the likely culprit — ship a WP-plugin auto-installer for v0.2 |
| **First paying Solo sub** | By Day 3 | By Day 7 | No paid sub by Day 10 = pricing or positioning is wrong; try $9/mo Solo for a week |
| **First 10 paying customers** | By 2026-04-27 | By 2026-05-11 (Day 21) | 10 paid by Day 30 is the floor to keep going |
| **First honest feedback loop** | Signal 4 poster, Signal 3 poster, one HN Show HN commenter — by Day 5 | Any 1 of them by Day 10 | No public feedback from any named prospect by Day 14 = the real buyer doesn't exist at scale; pivot to Pro/Agency by hand-selling 3 local WP agencies directly |

### Kill signal (hard)

**If, by 2026-05-20 (Day 30), we have fewer than 10 paying customers AND fewer than 150 activated free-tier users, wpflow gets archived** — repo stays up as OSS (the code is sunk cost; the product decision isn't), MCPize listing is paused, attention shifts to DECISION.md #2 (Meta Ads write-access MCP) or #5 (vibe OpenAPI→MCP generator), whichever still has fresh demand signals.

### Pivot signal (soft)

If Solo tier has <3 subs but Agency tier has 2+ by Day 21, kill Solo tier, rename product "wpflow for Agencies", reprice to $99/25 sites as the entry SKU, stop the non-dev-WP-owner positioning. The buyer who actually pays is telling us who they are — listen.

### What "success" looks like at Day 30

- 10+ paying customers, total MRR ≥ $200 (mix of Solo + 1 Agency).
- 1+ public testimonial from a named Reddit/HN user citing a specific task wpflow replaced.
- v0.2 scoped against real feedback: probable adds are a WP-plugin auto-installer (to skip the app-password friction) + a hosted Streamable HTTP transport (for the "I can't install Python" crowd).

---

**END OF PLAN.** Execution starts today. Every task above has an owner (Zach) and a calendar slot (§6).
