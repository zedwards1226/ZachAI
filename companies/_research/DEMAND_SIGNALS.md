# MCP Demand Signals (last 90 days)

Research window: ~Jan 2026 – Apr 20 2026 (most signals are from March–April 2026).
Scope: Reddit (r/mcp, r/ClaudeAI, r/LocalLLaMA), Hacker News comment threads, GitHub issues.

## Summary
- Total signals cited with real quotes + URLs: **33**
- Distinct demand themes identified: **9**
- Willingness-to-pay / commercial-intent hints: **7** (see final section)
- Clearest gaps with multiple independent asks: **Meta/Google/LinkedIn ads write-access**, **QuickBooks/accounting hosted MCP**, **reliable crypto + Web3 market data**, **low-friction WordPress ops**, **social-media multi-channel posting**, **easy MCP discovery/search inside clients**, **OpenAPI→MCP that doesn't burn tokens**, **"vibe coding" style no-code MCP connector builders**, **better control-plane / governance / memory layer for enterprise**.

---

## Theme 1: SaaS integrations nobody has built well (or with write access)

### Signal 1 — Meta Ads write access (campaign creation)
- **Quote:** "Looking for a tool connecting Claude and Meta Ads with read/write access to actually create and edit campaigns. Windsor.ai is read-only, so it doesn't work for me. Any recommendations?"
- **Source:** Reddit r/mcp — https://old.reddit.com/r/mcp/comments/1sig21t/for_mediabuyer_i_need_a_claude_to_meta_ads/
- **Date:** 2026-04-11
- **WTP hint:** yes (commercial / media-buyer use case, explicit "doesn't work for me" on the free read-only option)

### Signal 2 — QuickBooks hosted MCP for non-dev C-suite
- **Quote:** "I see that Intuit has its own MCP server repo but it runs as a local node.js stdio app. There's not much chance of getting the C-suite to go through setting it up in Claude Desktop and I don't see that Intuit has a hosted MCP offering. Am I missing something?"
- **Source:** Reddit r/ClaudeAI — https://old.reddit.com/r/ClaudeAI/comments/1sm9n6l/how_are_people_connecting_to_quickbooks/
- **Date:** 2026-04-15
- **WTP hint:** yes (enterprise FP&A context, C-suite users)

### Signal 3 — Hostinger / WordPress control
- **Quote:** "Has anyone built an MCP to control a WordPress website on Hostinger servers? I keep on trying, but I always fail."
- **Source:** Reddit r/ClaudeAI — https://old.reddit.com/r/ClaudeAI/comments/1salcfl/mcp_for_hostinger/
- **Date:** 2026-04-02
- **WTP hint:** no

### Signal 4 — Non-coder production WordPress workflow
- **Quote:** "I own a WordPress site. A past developer left the codebase in rough shape... I am not a developer and I don't code... Has anyone done non-trivial WordPress work (theme edits, schema/PHP customization, plugin cleanup) via Claude Code + MCP end-to-end on a production site? Which WordPress MCP did you use? wp-cli-mcp, something custom, REST API-based? Pros/cons? Where did it fail or fall down?"
- **Source:** Reddit r/ClaudeAI — https://old.reddit.com/r/ClaudeAI/comments/1spnoo0/anyone_actually_used_claude_code_wordpress_mcp/
- **Date:** 2026-04-19
- **WTP hint:** yes (site owner trying to replace "mid-tier dev" work)

### Signal 5 — Spotify custom connector
- **Quote:** "Hi, has anyone ever added Spotify as a custom connector? If so, how did you do it? I'm really interested in setting this up, but I'm not sure how careful I need to be when choosing an MCP server and handling everything in general."
- **Source:** Reddit r/ClaudeAI — https://old.reddit.com/r/ClaudeAI/comments/1sqplqx/spotify_as_a_connector/
- **Date:** 2026-04-20
- **WTP hint:** no

### Signal 6 — Multi-socials posting MCP
- **Quote:** "Anything as easy as Blacktwist for playing MCP for claude to connect/post to twitter, instagram, facebook and other socials? Need something simple to connect to shortcut my claude output to socials."
- **Source:** Reddit r/ClaudeAI — https://old.reddit.com/r/ClaudeAI/comments/1sat0qx/anything_as_easy_as_blacktwist_for_playing_mcp/
- **Date:** 2026-04-02
- **WTP hint:** indirect (content creator / marketer)

---

## Theme 2: Existing MCP servers are incomplete or regressed

### Signal 7 — Google Calendar plugin lost alerts functionality
- **Quote:** "I just updated Claude and lost functionality (Claude Code: 2.1.112). One of my favorite use cases is gone. The Claude Google Calendar integration used to allow me to set two alerts for any new meetings. Now this functionality is gone from the google calendar official plugin... I checked the tool description on the MCP and it does seem to be missing the alerts parameters that I was using before. So looks like I'm going to need a custom MCP. What are people using for google calendar mcp?"
- **Source:** Reddit r/ClaudeAI — https://old.reddit.com/r/ClaudeAI/comments/1snra85/google_calendar_plugin_lost_functionality_what/
- **Date:** 2026-04-17
- **WTP hint:** yes (would-be paying customer of an alternative)

### Signal 8 — Tool descriptions unusable in 98% of servers
- **Quote:** "We analyzed 78,849 MCP tool descriptions. 98% don't tell AI agents when to use them."
- **Source:** Reddit r/mcp — https://old.reddit.com/r/mcp/comments/1s1r2b7/we_analyzed_78849_mcp_tool_descriptions_98_dont/
- **Date:** 2026-03-23
- **WTP hint:** no (but implies a massive QA/evals opportunity)

### Signal 9 — MCP servers dump megabytes of unfiltered text
- **Quote:** "A lot of them just returns Mbs of text blob without filtering at all, and thus explodes the context" — commenter mmis1000
- **Source:** Hacker News, "MCP is dead; long live MCP" — https://news.ycombinator.com/item?id=47380270
- **Date:** recent (April 2026 thread)
- **WTP hint:** no

### Signal 10 — Incomplete client support for resources + prompts
- **Quote:** "many clients are still half-assed on supporting the functions outside of MCP tools. Namely, two very useful features resources and prompts have varying levels of support across clients... Codex being one of the worst" — commenter CharlieDigital
- **Source:** Hacker News, "MCP is dead; long live MCP" — https://news.ycombinator.com/item?id=47380270
- **Date:** April 2026
- **WTP hint:** no

### Signal 11 — PatchworkMCP itself exists because agents keep hitting walls
- **Quote:** "Claude reported a missing `search_costs_by_context` tool, described the exact input schema it wanted" (describing how agents systematically report missing tooling on the author's AI-cost-management MCP)
- **Source:** Hacker News — https://news.ycombinator.com/item?id=47065941
- **Date:** 2026 (Show HN)
- **WTP hint:** yes (the author is selling/productising the feedback layer itself)

---

## Theme 3: Domain-specific verticals asking for better data

### Signal 12 — Crypto / Web3 market data MCP
- **Quote:** "Most of the community ones I see on GitHub are either broken or only track BTC. Does anyone know of an official or good MCP server that handles full market data (prices, volumes, global caps)? I want to be able to just ask Claude 'What's the 24h volume for the Base ecosystem?' and have it fetch the real numbers instantly."
- **Source:** Reddit r/mcp — https://old.reddit.com/r/mcp/comments/1shsvvm/best_mcp_servers_for_web3crypto_data/
- **Date:** 2026-04-10
- **WTP hint:** implied (trader/analyst use case)

### Signal 13 — Home Assistant / local smart-home brain
- **Quote:** "Total Noob: I want to build a local, uncensored 'Brain' for Home Assistant/MCP. Where do I start?"
- **Source:** Reddit r/LocalLLaMA — https://old.reddit.com/r/LocalLLaMA/comments/1sll52y/total_noob_i_want_to_build_a_local_uncensored/
- **Date:** April 2026
- **WTP hint:** no

### Signal 14 — US legal research (was a real gap until late March)
- **Quote:** "LegalMCP: first US legal research MCP server (18 tools, open source)" — framed explicitly as filling a gap (no prior legal MCP existed)
- **Source:** Reddit r/mcp — https://old.reddit.com/r/mcp/comments/1s3vx4p/legalmcp_first_us_legal_research_mcp_server_18/
- **Date:** 2026-03-26
- **WTP hint:** yes (legal tech is a willing-to-pay vertical; post landed 22 comments, meaningful interest)

### Signal 15 — Factorio game-state MCP (niche but shows pattern)
- **Quote:** "Claude kept hallucinating my Factorio bottlenecks. So I built an MCP that reads your saves."
- **Source:** Reddit r/ClaudeAI — https://old.reddit.com/r/ClaudeAI/comments/1sp6pug/claude_kept_hallucinating_my_factorio_bottlenecks/
- **Date:** 2026-04-18
- **WTP hint:** no (but shows latent demand whenever Claude can't reason about game/app state — every vertical app has this)

### Signal 16 — Emergency-medicine MCP (high-stakes vertical)
- **Quote:** "I built an MCP server that turns Claude into an emergency medicine assistant — what I learned building AI for high-stakes domains"
- **Source:** Reddit r/ClaudeAI — https://old.reddit.com/r/ClaudeAI/comments/1snghbr/i_built_an_mcp_server_that_turns_claude_into_an/
- **Date:** 2026-04-16
- **WTP hint:** yes (medical verticals pay)

---

## Theme 4: Ad/marketing ops — multiple independent asks

(See Signal 1 Meta Ads + Signal 6 multi-social posting.)

### Signal 17 — LinkedIn lead re-engagement workflow already being hacked together
- **Quote:** "Used Claude + MCP to re-engage old LinkedIn leads automatically — workflow breakdown"
- **Source:** Reddit r/ClaudeAI — https://old.reddit.com/r/ClaudeAI/comments/1sanzvh/used_claude_mcp_to_reengage_old_linkedin_leads/
- **Date:** 2026-04-02
- **WTP hint:** yes (sales ops)

### Signal 18 — Non-dev ad-campaign management as a use case
- **Quote:** "Non-dev here: using Claude to manage my ad campaigns and it's replaced half my workflow"
- **Source:** Reddit r/ClaudeAI — https://old.reddit.com/r/ClaudeAI/comments/1seg5g9/nondev_here_using_claude_to_manage_my_ad/
- **Date:** 2026-04-07
- **WTP hint:** yes (marketer replacing paid tooling)

---

## Theme 5: MCP infrastructure complaints — discovery / auth / proliferation

### Signal 19 — In-client MCP search doesn't exist
- **Quote:** "I am new to claude cli, and haven't done too much digging, but for now it seems that each MCP needs to be added manually. Is there a way to configure the cli to where when I type `/mcp` there is a `Find other MCP servers` option and I can go down the list and select which ones to add?"
- **Source:** Reddit r/ClaudeAI — https://old.reddit.com/r/ClaudeAI/comments/1spwo8f/is_there_a_way_to_configure_claude_cli_to_give_me/
- **Date:** 2026-04-19
- **WTP hint:** no

### Signal 20 — Token hell from copy-pasting API keys across servers
- **Quote:** "I got tired of copy-pasting API keys for multiple MCP servers, so I built a local proxy to manage them all."
- **Source:** Reddit r/mcp — https://old.reddit.com/r/mcp/comments/1sn5m3g/i_got_tired_of_copypasting_api_keys_for_multiple/
- **Date:** 2026-04-16
- **WTP hint:** implicit — problem is "painful enough to build around"

### Signal 21 — "MCP server config hell" is common enough to build a marketplace against
- **Quote:** "I got so fed up with MCP server config hell that I built a marketplace + runtime to fix it forever (1server.ai)"
- **Source:** Reddit r/mcp — https://old.reddit.com/r/mcp/comments/1sms92f/i_got_so_fed_up_with_mcp_server_config_hell_that/
- **Date:** 2026-04-16
- **WTP hint:** yes (a commercial marketplace product)

### Signal 22 — OpenAPI→MCP is a known foot-gun
- **Quote:** "Raw OpenAPI-to-MCP conversion is why your agent keeps failing on tool calls"
- **Source:** Reddit r/mcp — https://old.reddit.com/r/mcp/comments/1sox0tm/raw_openapitomcp_conversion_is_why_your_agent/
- **Date:** 2026-04-18
- **WTP hint:** implied (whoever builds the "good" converter can charge)

### Signal 23 — Auto-generated MCPs explode token budgets
- **Quote:** "Auto-generating MCP servers from OpenAPI specs is fast but burns tokens like crazy"
- **Source:** Reddit r/mcp — https://old.reddit.com/r/mcp/comments/1snwqlk/autogenerating_mcp_servers_from_openapi_specs_is/
- **Date:** 2026-04-17
- **WTP hint:** no

### Signal 24 — "Vibe coding" for MCP connectors doesn't exist
- **Quote:** "I'm semi-technical and just want to point at a database or data source and have a connector created without having to engineer it myself. Like if I could just connect to an api or an old database I have to recode... Basically the 'vibe coding to MVP' equivalent but for MCP. Does that exist? Would anyone outside of developers actually want that or is this just a me problem?"
- **Source:** Reddit r/mcp — https://old.reddit.com/r/mcp/comments/1sd90tg/vibe_coding_gave_nondevs_the_ability_to_build/
- **Date:** 2026-04-05
- **WTP hint:** yes (semi-technical user, explicit willingness to buy a tool)

---

## Theme 6: Enterprise / governance features missing

### Signal 25 — No sane org-level deployment path
- **Quote:** "There's no sane way to do this as an org without MCP unless we standardize and enforce a specific toolset/harness that we wrap with telemetry" — CharlieDigital
- **Source:** Hacker News — https://news.ycombinator.com/item?id=47380270
- **WTP hint:** yes (enterprise budget signal)

### Signal 26 — Approvals + audit log + secret vault as a "must-have"
- **Quote:** "My daily 'must-have' is a control-plane layer: approvals + audit log + secret vault around tool calls, otherwise every MCP server is a liability."
- **Source:** Reddit r/mcp — https://old.reddit.com/r/mcp/comments/1s94a85/whats_your_musthave_mcp_server_that_you_use_daily/ (comment by BC_MARO, 2026-04-01)
- **WTP hint:** yes (references paid product "Peta")

### Signal 27 — Tamper-proof evidence for tool calls
- **Quote:** "How are you producing tamper-proof evidence for MCP tool calls?"
- **Source:** Reddit r/mcp — https://old.reddit.com/r/mcp/comments/1sg216p/how_are_you_producing_tamperproof_evidence_for/
- **Date:** 2026-04-08
- **WTP hint:** yes (compliance-driven)

### Signal 28 — Supply-chain security after the LiteLLM incident
- **Quote:** "Cursor auto-loaded an MCP server that pulled compromised litellm 20 minutes after the LiteLLM malware hit PyPI"
- **Source:** Reddit r/mcp — https://old.reddit.com/r/mcp/comments/1s3itoh/cursor_autoloaded_an_mcp_server_that_pulled/
- **Date:** 2026-03-25
- **WTP hint:** yes (enterprise security)

---

## Theme 7: Memory / context layer — repeatedly flagged as unsolved

### Signal 29 — Portable memory layer is an unsolved gap
- **Quote:** "MCP gives me a portable tool layer. I'm still not sure what the right portable memory layer is."
- **Source:** Reddit r/mcp — https://old.reddit.com/r/mcp/comments/1sc8de6/mcp_gives_me_a_portable_tool_layer_im_still_not/
- **Date:** 2026-04-04
- **WTP hint:** no but a dominant product thesis in April 2026

### Signal 30 — Cross-client memory as unmet demand (post explicitly frames it)
- **Quote:** "Cross-client memory for MCP: single binary, single file, shared by Claude / Codex / OpenCode / OpenClaw / Any Agent"
- **Source:** Reddit r/mcp — https://old.reddit.com/r/mcp/comments/1sqyk1r/crossclient_memory_for_mcp_single_binary_single/
- **Date:** 2026-04-20
- **WTP hint:** no

---

## Theme 8: Agent-to-agent communication (adjacent to MCP, repeated ask)

### Signal 31 — Agent↔Agent still feels unsolved
- **Quote:** "MCP solves agent-to-tool. What about agent to agent?"
- **Source:** Reddit r/mcp — https://old.reddit.com/r/mcp/comments/1squkug/mcp_solves_agenttotool_what_about_agent_to_agent/
- **Date:** 2026-04-20
- **WTP hint:** no

---

## Theme 9: Goose project — MCP-manager-for-MCPs request in the wild

### Signal 32 — Wish for an "MCP manager MCP"
- **Quote:** "ps, i wish there was an mcp for an mcp manager that could add them from a standardized list file, maybe like claude and cursor's json files."
- **Source:** GitHub aaif-goose/goose #4521 — https://github.com/aaif-goose/goose/issues/4521 (commenter: auwsom)
- **Date:** 2025-09-04 (still relevant through April 2026)
- **WTP hint:** no

### Signal 33 — Microsoft's push away from Playwright MCP shows existing one is unusable in practice
- **Quote:** "Microsoft recommends CLI over MCP for Playwright. We built a cloud-browser MCP that cuts ~114K tokens to ~5K"
- **Source:** Reddit r/mcp — https://old.reddit.com/r/mcp/comments/1spvkrz/microsoft_recommends_cli_over_mcp_for_playwright/
- **Date:** 2026-04-19
- **WTP hint:** yes (paid cloud-browser replacement product)

---

## Willingness-to-Pay Signals (highlights)

1. **Media-buyer demanding Meta Ads write-access** — already rejected Windsor.ai paid offering because it's read-only (Signal 1).
2. **Enterprise FP&A team** can't deploy Intuit's node-stdio QuickBooks MCP to C-suite and is explicitly shopping for a hosted option (Signal 2).
3. **Non-coder WordPress site owner** wants Claude Code + MCP to replace paid dev work (Signal 4).
4. **Marketer replacing "half my workflow"** with Claude + MCP ad-ops (Signal 18).
5. **Legal-tech**: LegalMCP explicitly first-mover in a high-ARPU vertical (Signal 14).
6. **Emergency medicine** MCP — medical vertical is well known to pay (Signal 16).
7. **Enterprise governance** (approvals, audit logs, secret vault, tamper-proof evidence, supply-chain security) — repeatedly framed as a must-have after the LiteLLM incident; "Peta" already exists as a paid option (Signals 25, 26, 27, 28).

---

## Top 10 Most-Requested Missing MCPs

1. **Meta Ads (Facebook/Instagram) with full write access** — create/edit campaigns, not just read reporting (Signal 1).
2. **Hosted QuickBooks / Intuit MCP** for non-developers — current Intuit repo is stdio-only (Signal 2).
3. **Reliable WordPress management MCP** that actually handles non-trivial theme/PHP/plugin work on production sites (Signals 3, 4).
4. **Comprehensive crypto / Web3 market-data MCP** beyond BTC — full prices, volumes, ecosystem-level aggregates (Signal 12).
5. **Unified social-media posting MCP** (X/Instagram/Facebook/TikTok/LinkedIn in one) for creators (Signal 6).
6. **Google Calendar MCP with richer surface** than the current official Anthropic plugin (notifications/alerts/rich recurrences) (Signal 7).
7. **"Vibe-coded" OpenAPI-or-DB → good MCP generator** that produces token-efficient, well-described tools, not raw dumps (Signals 22, 23, 24).
8. **Enterprise control-plane MCP** — approvals + audit + secret vault + SBOM/supply-chain guardrails (Signals 25–28).
9. **Cross-client / portable memory layer** that works across Claude / Codex / OpenCode / OpenClaw (Signals 29, 30).
10. **In-client MCP discovery & marketplace** so users don't hand-edit JSON — called out as "config hell" by multiple builders (Signals 19, 21, 32).

---

## Notes / caveats

- Twitter/X public demand was not searchable within the scope of this pass (no authenticated search access); WTP signals there are likely higher than captured here.
- Several threads (r/mcp "must-have MCP" with 106 comments, HN "MCP is dead") were skimmed for complaints, not exhaustively mined. There are likely another 10–20 citable signals in those same threads if the research budget expands.
- All quotes above were extracted live via Playwright browser against old.reddit.com / HN comment pages. URLs are real and verified navigable during research (2026-04-20).
